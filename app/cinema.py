"""Animação v3, "desenho animado" programado (47e §3).

Divisão de papéis (diretriz do Lucas, 18/11): o DIRETOR (Claude/GPT pelo combo rt-planejar do llm-access) escreve a história e o
plano de cada cena com o vocabulário do kit; o QWEN escreve o código dos planos (shots.js) usando o kit `motion/cinema`; um
validador em Node roda o código num canvas falso e devolve o erro ao Qwen (até 2 correções); se ainda falhar, um gerador
determinístico monta os planos direto do plano do diretor (nunca sai vídeo vazio). O Remotion (composição "Cinema") desenha
cada quadro num canvas, com a voz (edge-tts, tempo por palavra) e os efeitos sonoros.
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from pathlib import Path

import httpx

from app.motor.juiz import _json

log = logging.getLogger("viralizai.cinema")
MOTION = Path(__file__).resolve().parent.parent / "motion"
KIT = MOTION / "cinema"
ORDEM = ["lib.js", "chars.js", "env.js", "cenarios.js", "props.js", "alto.js"]

CENARIOS = ["quarto_noite", "corredor_escuro", "rua_noite", "floresta_noite", "cemiterio", "estrada_noite", "sala_aula", "escritorio",
            "cozinha", "campo_dia", "cidade_dia", "praia", "espaco", "palco"]
QUEM = ["heroi", "heroina", "amigo", "amiga", "idoso", "crianca", "policial", "medico", "chefe", "pirata", "marinheiro"]
ACOES = ["parado", "andar", "correr", "assustado", "tremer", "apontar", "acenar", "pensar", "comemorar", "cair", "sentado", "deitado",
         "celular", "falar", "esconder", "empurrar", "segurar"]
HUMORES = ["normal", "feliz", "triste", "medo", "raiva", "surpreso", "desconfiado", "serio", "tonto", "morto"]
CAMERAS = ["empurra", "afasta", "pan", "sobe", "desce", "treme", "zoom_rapido"]
EFEITOS = ["vinheta", "chuva", "raio", "flash_vermelho", "poeira", "neblina", "escurecer", "tinta_vermelha", "tinta_azul", "tinta_sepia"]
OBJETOS = ["porta", "cama", "mesa", "cadeira", "vela", "celular", "tv", "foto", "carro", "arvore", "relogio", "dinheiro", "caixa", "livro",
           "lapide", "vulto", "fantasma"]
SONS = ["whoosh", "impacto", "pop", "riser", "tic", "ding", "notif", "erro"]

PROMPT_DIRETOR = """Você é o diretor de um canal de DESENHO ANIMADO faceless que viraliza no TikTok (estilo bonequinho de cabeça branca,
traço de tinta, cenários com uma luz marcante). Ideia do cliente: {ideia}
Duração: {segundos} s (~{palavras} palavras de narração no TOTAL). Português do Brasil, frases faladas e curtas (5 a 16 palavras).

Escreva UMA história com gancho forte na 1ª frase (concreto: objeto, lugar, hora), tensão crescente, reviravolta e final que pede
comentário. {n_cenas} cenas. Cada cena = 1 frase narrada + o que a ANIMAÇÃO mostra. A animação tem que CASAR com a frase: se a fala diz
"abriu a porta", a cena mostra a porta abrindo; se diz "três da manhã", aparece um relógio nas 3. Nada de texto na tela.

Vocabulário do desenho (use SÓ estes nomes):
- cenario: {cenarios}
- quem (personagens): {quem}  (dê a cada personagem da história um destes, e mantenha o mesmo em todas as cenas)
- acao: {acoes}
- humor: {humores}
- camera: {cameras} (varie; treme/zoom_rapido só no susto)
- efeitos: {efeitos}
- objetos: {objetos}
- som (efeito sonoro no início da cena, opcional): {sons}
- opcoes do cenário: quarto_noite {{"armario":0..1,"olhosArmario":bool,"abajur":0..1,"chuva":bool,"sombraJanela":0..1}},
  corredor_escuro {{"pisca":bool,"portaFundoAberta":bool}}, rua_noite {{"posteLuz":0..1,"chuva":bool}}, estrada_noite {{"farois":0..1}},
  sala_aula {{"lousa":"até 3 palavras"}}, escritorio {{"quadro":"1 palavra"}}
- imagem (opcional, só quando uma FOTO REAL ajuda: lugar famoso, pessoa, objeto real): {{"busca":"2-4 palavras em inglês","onde":"tv|quadro|celular"}}
- desenho_extra (opcional): algo que precisa ser desenhado à mão porque não existe no kit (ex.: "um gato cinza sai do armário andando").

Responda SÓ JSON:
{{"titulo":"","gancho":"até 6 palavras","legenda":"legenda do post","hashtags":["..."],
 "elenco":{{"nome na história":"quem"}},
 "cenas":[{{"fala":"","cenario":"","opcoes":{{}},"camera":"","atores":[{{"quem":"","acao":"","humor":"","segura":"","de_onde":"esquerda|centro|direita","para_onde":"esquerda|centro|direita"}}],
   "objetos":[""],"efeitos":[""],"som":"","imagem":null,"desenho_extra":"","transicao":"whip|cut|fade"}}]}}"""

PROMPT_CODIGO = """Você escreve o código (JavaScript, canvas 2D) de um desenho animado usando o KIT abaixo. Saída: SÓ o conteúdo do arquivo
shots.js (sem markdown, sem explicação), começando com `const SHOTS = [];` e um `SHOTS.push({{...}})` por cena, com EXATAMENTE os start/end
dados. Use só funções do kit e canvas 2D. Determinístico (sem Math.random). Cada draw começa com `const cam = camera(...)` e `cenario(...)`.

=== KIT (referência) ===
{api}

=== EXEMPLO de shots.js bem feito (outra história) ===
{exemplo}

=== PLANO DO DIRETOR (escreva estas cenas) ===
{plano}

Seja ENXUTO: cada cena com 6 a 18 linhas (o arquivo inteiro precisa caber na resposta).
Regras: a ação de cada cena acontece no começo dela (lt pequeno) e casa com a fala; atores grandes e visíveis; nada de texto solto;
desenhe o "desenho_extra" de cada cena com formas simples (elipses, círculos, path) e contorno INK; imagens reais estão em IMG.img1, IMG.img2...
Responda só o código."""


# ---------------------------------------------------------------- LLM
def _chat(modelo: str, prompt: str, cfg, json_obj: bool, max_tokens: int = 6000, temperatura: float = .7) -> str:
    corpo = {"model": modelo, "temperature": temperatura, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]}
    if json_obj:
        corpo["response_format"] = {"type": "json_object"}
    if "qwen" in modelo:
        corpo["chat_template_kwargs"] = {"enable_thinking": False}
    r = httpx.post(cfg.llm_base + "/chat/completions", headers={"Authorization": f"Bearer {cfg.llm_key}"}, json=corpo, timeout=420)
    r.raise_for_status()
    return re.sub(r"<think>.*?</think>", "", r.json()["choices"][0]["message"]["content"] or "", flags=re.S)


def diretor_modelo(cfg) -> str:
    return getattr(cfg, "llm_diretor", "") or "rt-planejar"


# ---------------------------------------------------------------- 1. plano do diretor
def plano(ideia: str, segundos: int, cfg) -> dict:
    segundos = max(15, min(90, int(segundos or 45)))
    n = max(5, min(12, round(segundos / 4.5)))
    prompt = PROMPT_DIRETOR.format(ideia=ideia, segundos=segundos, palavras=int(segundos * 2.5), n_cenas=f"{n - 1} a {n + 1}",
                                   cenarios=", ".join(CENARIOS), quem=", ".join(QUEM), acoes=", ".join(ACOES), humores=", ".join(HUMORES),
                                   cameras=", ".join(CAMERAS), efeitos=", ".join(EFEITOS), objetos=", ".join(OBJETOS), sons=", ".join(SONS))
    ultimo = None
    for modelo in (diretor_modelo(cfg), cfg.llm_modelo):
        try:
            j = _json(_chat(modelo, prompt, cfg, True, 5000, .8))
            p = validar_plano(j)
            p["formato"], p["segundos"], p["diretor"] = "desenho", segundos, modelo
            return p
        except Exception as e:  # noqa: BLE001
            ultimo = e
            log.warning("diretor %s falhou: %s", modelo, str(e)[:200])
    raise RuntimeError(f"diretor sem resposta: {ultimo}")


def _um(v, lista, padrao):
    v = str(v or "").strip().lower()
    return v if v in lista else padrao


def validar_plano(j: dict) -> dict:
    """Normaliza o plano para o vocabulário do kit (o diretor às vezes inventa nomes). Idempotente."""
    cenas = []
    for c in (j.get("cenas") or [])[:14]:
        fala = re.sub(r"\s+", " ", str(c.get("fala") or "")).strip()[:220]
        if not fala:
            continue
        atores = []
        for a in (c.get("atores") or [])[:3]:
            if not isinstance(a, dict):
                continue
            atores.append({"quem": _um(a.get("quem"), QUEM, "heroi"), "acao": _um(a.get("acao"), ACOES, "parado"), "humor": _um(a.get("humor"), HUMORES, "normal"),
                           "segura": str(a.get("segura") or "")[:12], "de_onde": _um(a.get("de_onde"), ["esquerda", "centro", "direita"], "centro"),
                           "para_onde": _um(a.get("para_onde"), ["esquerda", "centro", "direita"], "centro")})
        img = c.get("imagem") if isinstance(c.get("imagem"), dict) and c["imagem"].get("busca") else None
        cenas.append({"fala": fala, "cenario": _um(c.get("cenario"), CENARIOS, "palco"), "opcoes": c.get("opcoes") if isinstance(c.get("opcoes"), dict) else {},
                      "camera": _um(c.get("camera"), CAMERAS, "empurra"), "atores": atores,
                      "objetos": [o for o in (c.get("objetos") or []) if o in OBJETOS][:4], "efeitos": [e for e in (c.get("efeitos") or []) if e in EFEITOS][:3],
                      "som": _um(c.get("som"), SONS, ""), "imagem": {"busca": str(img["busca"])[:60], "onde": _um(img.get("onde"), ["tv", "quadro", "celular"], "quadro")} if img else None,
                      "desenho_extra": str(c.get("desenho_extra") or "")[:200], "transicao": _um(c.get("transicao"), ["whip", "cut", "fade"], "cut")})
    if len(cenas) < 2:
        raise ValueError("plano sem cenas")
    tags = [("#" + str(h).lstrip("#").replace(" ", "")) for h in (j.get("hashtags") or [])][:8]
    return {"titulo": str(j.get("titulo") or "")[:90], "gancho": str(j.get("gancho") or "")[:60], "legenda": str(j.get("legenda") or "")[:600],
            "hashtags": tags, "elenco": j.get("elenco") if isinstance(j.get("elenco"), dict) else {}, "cenas": cenas,
            "formato": "desenho", "segundos": int(j.get("segundos") or 45)}


# ---------------------------------------------------------------- 2. código dos planos
def codigo_filme(shots_js: str) -> str:
    partes = [(KIT / f).read_text(encoding="utf-8") for f in ORDEM]
    return "\n;\n".join(partes + [shots_js, (KIT / "main.js").read_text(encoding="utf-8")])


def validar_codigo(shots_js: str, pasta: Path) -> dict:
    arq = pasta / "filme_teste.js"
    arq.write_text(codigo_filme(shots_js), encoding="utf-8")
    r = subprocess.run(["node", str(KIT / "valida.js"), str(arq)], capture_output=True, text=True, timeout=120)
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:  # noqa: BLE001
        return {"ok": False, "erros": [(r.stderr or r.stdout or "validador sem saída")[-400:]]}


def _limpa_codigo(txt: str) -> str:
    m = re.search(r"```(?:js|javascript)?\s*(.*?)```", txt, re.S)
    txt = m.group(1) if m else txt
    i = txt.find("const SHOTS")
    return txt[i:].strip() if i >= 0 else txt.strip()


def _limpa_continuacao(txt: str) -> str:
    m = re.search(r"```(?:js|javascript)?\s*(.*?)```", txt, re.S)
    txt = m.group(1) if m else txt
    i = txt.find("SHOTS.push(")
    return txt[i:].strip() if i >= 0 else ""


def _plano_para_llm(p: dict, tempos: list[tuple[float, float]]) -> str:
    linhas = []
    for i, (c, (a, b)) in enumerate(zip(p["cenas"], tempos)):
        linhas.append(json.dumps({"cena": i + 1, "start": round(a, 2), "end": round(b, 2), **{k: v for k, v in c.items() if v not in (None, "", [], {})}},
                                 ensure_ascii=False))
    return "\n".join(linhas)


def gerar_shots(p: dict, tempos: list[tuple[float, float]], pasta: Path, cfg, avisar=None) -> tuple[str, str]:
    """Qwen escreve; validador confere; até 2 correções; senão gerador determinístico. -> (shots_js, origem)."""
    prompt = PROMPT_CODIGO.format(api=(KIT / "API.md").read_text(encoding="utf-8"), exemplo=(KIT / "exemplo_shots.js").read_text(encoding="utf-8"),
                                  plano=_plano_para_llm(p, tempos))
    conversa = prompt
    for tentativa in range(3):
        try:
            cod = _limpa_codigo(_chat(cfg.llm_modelo, conversa, cfg, False, 16000, .4))
            if cod.count("SHOTS.push(") < len(tempos) or not cod.rstrip().endswith(("});", "}")):
                # veio cortado (limite de tokens): pede só a continuação, a partir da última cena completa
                ult = cod.rfind("SHOTS.push(")
                base = cod[:ult] if ult > 0 else cod
                feitas = base.count("SHOTS.push(")
                pedido = (prompt + "\n\n=== VOCÊ JÁ ESCREVEU (não repita) ===\n" + base[-6000:] +
                          f"\n\nContinue a partir da cena {feitas + 1} até a última. Responda só os SHOTS.push que faltam.")
                cod = base + "\n" + _limpa_continuacao(_chat(cfg.llm_modelo, pedido, cfg, False, 12000, .4))
            cod = _ajusta_tempos(cod, tempos)
            v = validar_codigo(cod, pasta)
            if v.get("ok"):
                return cod, f"qwen{tentativa + 1}"
            log.info("código da IA com erro (tentativa %s): %s", tentativa + 1, v.get("erros"))
            conversa = prompt + "\n\n=== SUA VERSÃO ANTERIOR ===\n" + cod[:12000] + "\n\n=== ERRO AO RODAR ===\n" + "\n".join(v.get("erros") or [])[:800] + \
                "\nCorrija e devolva o shots.js inteiro."
        except Exception as e:  # noqa: BLE001
            log.warning("Qwen falhou ao gerar código: %s", str(e)[:200])
    cod = shots_deterministico(p, tempos)
    v = validar_codigo(cod, pasta)
    if not v.get("ok"):
        raise RuntimeError(f"gerador determinístico com erro: {v.get('erros')}")
    return cod, "deterministico"


def _ajusta_tempos(cod: str, tempos: list[tuple[float, float]]) -> str:
    """Garante os start/end exatos (a IA às vezes arredonda): reescreve na ordem em que aparecem."""
    it = iter(tempos)

    def troca(m):
        try:
            a, b = next(it)
        except StopIteration:
            return m.group(0)
        return f"start: {a:.2f}, end: {b:.2f}"
    return re.sub(r"start\s*:\s*[\d.]+\s*,\s*end\s*:\s*[\d.]+", troca, cod)


POS = {"esquerda": 260, "centro": 540, "direita": 820}


def shots_deterministico(p: dict, tempos: list[tuple[float, float]]) -> str:
    """Monta os planos direto do plano do diretor (sem IA): cenário + atores + objetos + efeitos + câmera."""
    out = ["const SHOTS = [];"]
    for i, (c, (a, b)) in enumerate(zip(p["cenas"], tempos)):
        foco = "[540, 980]"
        linhas = [f"const cam = camera(lt, dur, {{ tipo: {json.dumps(c['camera'])}, foco: {foco}, forca: 30 }});",
                  f"cenario({json.dumps(c['cenario'])}, ctx, t, cam, {json.dumps(c.get('opcoes') or {}, ensure_ascii=False)});"]
        for k, o in enumerate(c.get("objetos") or []):
            x = [300, 800, 540, 150][k % 4]
            linhas.append({
                "porta": f"porta(ctx, {x}, CHAO, 1, kf(lt, [[0.2, 0], [1.4, 0.8]]));", "cama": f"cama(ctx, {x}, CHAO, .9);",
                "mesa": f"mesa(ctx, {x}, CHAO);", "cadeira": f"cadeira(ctx, {x}, CHAO);", "vela": f"vela(ctx, {x}, CHAO - 200, 1.2, t);",
                "celular": f"celular(ctx, {x}, 760, 1.1, '#3ea6ee', {{ texto: '...' }});", "tv": f"tv(ctx, {x}, CHAO - 80, 1, IMG.img1 || null, 1, t);",
                "foto": f"fotoQuadro(ctx, {x}, 600, 300, 220, IMG.img1, 'quadro', -0.04);", "carro": f"carro(ctx, kf(lt, [[0, -300], [dur, 1300]]), CHAO + 80, .9, '#e0392f', t, 1);",
                "arvore": f"arvore(ctx, {x}, CHAO, .9);", "relogio": f"relogio(ctx, {x}, 420, 90, 3, 0);", "dinheiro": f"dinheiro(ctx, {x}, CHAO, 6, 1.1);",
                "caixa": f"caixa(ctx, {x}, CHAO, 220, 180);", "livro": f"livro(ctx, {x}, CHAO - 220, 1.2, '#7a4bc4', 1);",
                "lapide": f"lapide(ctx, {x}, CHAO, 1.2);", "vulto": f"vulto(ctx, {x}, CHAO, 620, kf(lt, [[0, 0], [1, .9]]), t);",
                "fantasma": f"fantasma(ctx, {x}, CHAO - 300, 1.1, t, kf(lt, [[0, 0], [.8, .85]]));",
            }.get(o, ""))
        n = len(c.get("atores") or [])
        for k, at in enumerate(c.get("atores") or []):
            x0, x1 = POS[at["de_onde"]], POS[at["para_onde"]]
            if n > 1 and x0 == x1:
                x0 = x1 = [330, 760, 540][k % 3]
            props = {"quem": at["quem"], "acao": at["acao"], "humor": at["humor"], "x": x1, "x0": x0, "x1": x1, "de": .1, "ate": max(.6, (b - a) * .8),
                     "dir": 1 if x1 >= x0 and k == 0 else -1, "s": 560, "semente": k + 1}
            if at.get("segura") in ("lanterna", "vela", "celular", "papel", "dinheiro", "faca"):
                props["segura"] = at["segura"]
            linhas.append(f"ator(ctx, t, lt, {json.dumps(props, ensure_ascii=False)});")
        ef = {"vinheta": "vinheta(ctx, .55);", "chuva": "chuva(ctx, t, 1);", "raio": "raio(ctx, lt, .3);", "flash_vermelho": "flash(ctx, lt, 0, '200,20,20', .35);",
              "poeira": "poeira(ctx, t, 40);", "neblina": "neblina(ctx, t, CHAO, .5);", "escurecer": "escurecer(ctx, .4);",
              "tinta_vermelha": "tinta(ctx, 'vermelho', .3);", "tinta_azul": "tinta(ctx, 'azul', .3);", "tinta_sepia": "tinta(ctx, 'sepia', .35);"}
        linhas += [ef[e] for e in c.get("efeitos") or [] if e in ef]
        if "vinheta" not in (c.get("efeitos") or []):
            linhas.append("vinheta(ctx, .4);")
        corpo = "\n  ".join(x for x in linhas if x)
        out.append(f"SHOTS.push({{ start: {a:.2f}, end: {b:.2f}, tr: {json.dumps(c['transicao'])}, draw(ctx, lt, t, dur) {{\n  {corpo}\n}} }});")
    return "\n".join(out)


# ---------------------------------------------------------------- 3. imagens reais (Pixabay, quando a cena pede)
def buscar_imagens(p: dict, pub: Path, cfg) -> dict[str, str]:
    chave = getattr(cfg, "pixabay_key", "") or ""
    imgs: dict[str, str] = {}
    if not chave:
        return imgs
    (pub / "img").mkdir(parents=True, exist_ok=True)
    k = 0
    for c in p["cenas"]:
        if not c.get("imagem"):
            continue
        k += 1
        try:
            r = httpx.get("https://pixabay.com/api/", params={"key": chave, "q": c["imagem"]["busca"], "image_type": "photo", "safesearch": "true", "per_page": 5},
                          timeout=30).json()
            hit = (r.get("hits") or [None])[0]
            if not hit:
                continue
            dados = httpx.get(hit.get("webformatURL") or hit["previewURL"], timeout=60).content
            (pub / "img" / f"img{k}.jpg").write_bytes(dados)
            imgs[f"img{k}"] = f"img/img{k}.jpg"
        except Exception as e:  # noqa: BLE001
            log.warning("imagem '%s' falhou: %s", c["imagem"]["busca"], str(e)[:120])
    return imgs


# ---------------------------------------------------------------- 4. render
def renderizar(pub: Path, props: dict, destino: Path) -> None:
    pub, destino = pub.resolve(), destino.resolve()
    (pub / "props.json").write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
    import os
    npx = "npx.cmd" if os.name == "nt" else "npx"
    cmd = [npx, "remotion", "render", "src/index.ts", "Cinema", str(destino), f"--props={pub / 'props.json'}", f"--public-dir={pub}",
           "--log=error", f"--concurrency={os.environ.get('VIRALIZAI_RENDER_CONC', '4')}"]
    r = subprocess.run(cmd, cwd=MOTION, capture_output=True, text=True, timeout=1800)
    if r.returncode != 0 or not destino.exists():
        raise RuntimeError("render: " + (r.stderr or r.stdout)[-600:])


def fazer(entrada: dict, pasta: Path, cfg, avisar) -> dict:
    from app import animacao_v2
    from app.pipeline import duracao
    pasta = pasta.resolve()
    pasta.mkdir(parents=True, exist_ok=True)
    p = validar_plano(entrada["roteiro"])
    pub = pasta / "pub"
    shutil.rmtree(pub, ignore_errors=True)
    shutil.copytree(MOTION / "public" / "sfx", pub / "sfx")
    avisar("Gravando a narração", 0.12)
    voz = animacao_v2.VOZES.get(entrada.get("voz") or "masculina") or animacao_v2.VOZES["masculina"]
    partes = [(c["fala"], .3) for c in p["cenas"]]
    palavras, faixas = animacao_v2.narrar(partes, voz, pub / "voz.mp3")
    # tempos dos planos: cada cena começa quando a fala dela começa; a última segura 1,2 s depois da voz
    inicios = [0.0] + [max(0.0, fa[0] - .05) for fa in faixas[1:]]
    fim_total = (faixas[-1][1] if faixas else 10) + 1.2
    tempos = [(inicios[i], inicios[i + 1] if i + 1 < len(inicios) else fim_total) for i in range(len(inicios))]
    avisar("Buscando imagens", 0.2)
    imgs = buscar_imagens(p, pub, cfg)
    avisar("Desenhando as cenas", 0.3)
    shots, origem = gerar_shots(p, tempos, pasta, cfg, avisar)
    (pasta / "shots.js").write_text(shots, encoding="utf-8")
    (pub / "filme.js").write_text(codigo_filme(shots), encoding="utf-8")
    sfx = [[round(a + .02, 2), c["som"], .5] for c, (a, _) in zip(p["cenas"], tempos) if c.get("som")]
    props = {"duracao": round(fim_total, 2), "voz": "voz.mp3", "palavras": [{"w": w["w"], "s": w["t0"], "e": w["t1"]} for w in palavras],
             "sfx": sfx, "imagens": imgs, "legenda": True}
    avisar("Animando", 0.45)
    out = pasta / "animacao.mp4"
    renderizar(pub, props, out)
    capa = pasta / "animacao.jpg"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "2", "-i", str(out), "-frames:v", "1", "-vf", "scale=360:-2", "-q:v", "4", str(capa)], check=False)
    shutil.rmtree(pub, ignore_errors=True)
    (pasta / "filme_teste.js").unlink(missing_ok=True)
    log.info("desenho pronto (%s, %s cenas, %.1fs)", origem, len(p["cenas"]), fim_total)
    return {"titulo": p["titulo"] or p["gancho"], "formato": "desenho", "origem_codigo": origem,
            "cortes": [{"k": 1, "estado": "pronto", "arquivo": out.name, "arquivos": {"tiktok": out.name}, "capa": capa.name if capa.exists() else None,
                        "titulo": p["titulo"], "gancho": p["gancho"], "legenda": p["legenda"], "hashtags": p["hashtags"], "duracao": round(duracao(out), 1)}]}
