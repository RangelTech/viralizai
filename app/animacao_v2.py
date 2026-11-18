"""Criar animação (spec 47d): o DIRETOR (IA) preenche um JSON validado; os MOLDES feitos à mão (motion/, Remotion) desenham.
A IA nunca escreve HTML. Voz neural com o tempo de cada palavra (legenda acompanha), efeitos sonoros automáticos nos cortes,
ênfases e revelações, B-roll do Pexels quando houver chave. Sem IA de imagem/vídeo (decisão do Lucas)."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import shutil
import subprocess
from pathlib import Path

import httpx

from app.motor.juiz import _json

log = logging.getLogger("viralizai.animacao")
MOTION = Path(__file__).resolve().parent.parent / "motion"
# Todas as vozes grátis (edge-tts) que falam português; as "multilíngues" falam pt com um leve sotaque.
# (código, voz, nome na tela, descrição). Amostras em static/vozes/<voz>.mp3.
VOZES_LISTA = [
    ("masculina", "pt-BR-AntonioNeural", "Antônio", "masculina, grave"),
    ("feminina", "pt-BR-FranciscaNeural", "Francisca", "feminina, clara"),
    ("jovem", "pt-BR-ThalitaMultilingualNeural", "Thalita", "feminina, jovem"),
    ("andre", "en-US-AndrewMultilingualNeural", "André", "masculina, narrador"),
    ("bruno", "en-US-BrianMultilingualNeural", "Bruno", "masculina, animada"),
    ("ava", "en-US-AvaMultilingualNeural", "Ava", "feminina, animada"),
    ("ema", "en-US-EmmaMultilingualNeural", "Ema", "feminina, calma"),
    ("william", "en-AU-WilliamMultilingualNeural", "William", "masculina, sotaque leve"),
    ("remy", "fr-FR-RemyMultilingualNeural", "Rémy", "masculina, sotaque leve"),
    ("vivi", "fr-FR-VivienneMultilingualNeural", "Vivi", "feminina, sotaque leve"),
    ("giuseppe", "it-IT-GiuseppeMultilingualNeural", "Giuseppe", "masculina, sotaque italiano"),
    ("hyunsu", "ko-KR-HyunsuMultilingualNeural", "Hyunsu", "masculina, jovem"),
    ("duarte", "pt-PT-DuarteNeural", "Duarte", "masculina, de Portugal"),
    ("raquel", "pt-PT-RaquelNeural", "Raquel", "feminina, de Portugal"),
]
VOZES = {c: v for c, v, _, _ in VOZES_LISTA}
VOZES_PUBLICAS = [{"codigo": c, "nome": n, "descricao": d, "amostra": f"/s/vozes/{v}.mp3"} for c, v, n, d in VOZES_LISTA] + \
    [{"codigo": "sem", "nome": "Sem voz", "descricao": "só texto na tela", "amostra": None}]
FORMATOS = {
    "historia": ("História narrada", "voz conta uma história com legenda gigante e fundo hipnótico"),
    "conversa": ("Conversa de WhatsApp", "conversa aparecendo bolha a bolha, com reviravolta"),
    "top5": ("Top 5", "contagem regressiva até o nº 1"),
    "curiosidade": ("Você sabia?", "fatos com ícones e zoom, legenda cinética"),
    "quiz": ("Quiz", "pergunta, 3 opções, contador e revelação"),
    "impacto": ("Frase de impacto", "palavras explodindo no ritmo"),
    "noticia": ("Notícia urgente", "plantão com manchete e números"),
    "versus": ("X contra Y", "tela dividida comparando e vencedor"),
}
FORMATOS_PUBLICOS = [{"codigo": k, "nome": v[0], "frase": v[1]} for k, v in FORMATOS.items()]

BASE = """Você é o diretor de um canal faceless que viraliza no TikTok, em português do Brasil.
Ideia do cliente: {ideia}
Duração alvo: {segundos} segundos (~{palavras} palavras de narração no total).
Formato: {formato} ({desc}).

Regras: gancho de ATÉ 6 PALAVRAS nos 2 primeiros segundos que faz parar de rolar; frases curtas e faladas (como gente fala); 1 ideia por cena;
nada de número inventado com cara de dado oficial (se não tiver certeza, não use número); a última cena chama para seguir/comentar.
"destaque": 2 a 5 palavras que aparecem GRANDES na tela. "emoji": 1 emoji que combina. "enfase": 1 a 2 palavras da fala que levam zoom.
"broll": 2 a 4 palavras em INGLÊS para buscar vídeo de apoio (ex.: "police car chase").
{extra}
Responda SÓ com JSON: {esquema}"""

ESQUEMA_CENAS = '"cenas": [{"fala": "...", "destaque": "...", "emoji": "🔥", "enfase": ["..."], "broll": "..."}]'
EXTRA = {
    "historia": ("Conte UMA história com começo, tensão e reviravolta no fim, em 1ª pessoa ou narrador. 6 a 10 cenas.",
                 '{"titulo": "", "gancho": "até 6 palavras MAIÚSCULAS", ' + ESQUEMA_CENAS + ', "legenda": "", "hashtags": []}'),
    "curiosidade": ("5 a 8 cenas, cada uma um fato curioso ligado ao tema.",
                    '{"titulo": "", "gancho": "", ' + ESQUEMA_CENAS + ', "legenda": "", "hashtags": []}'),
    "impacto": ("Frase motivacional/dinheiro forte em 3 a 6 cenas curtas (falas de 4 a 12 palavras).",
                '{"titulo": "", "gancho": "", ' + ESQUEMA_CENAS + ', "legenda": "", "hashtags": []}'),
    "top5": ("Exatamente 7 cenas: 1 abertura, 5 itens do nº 5 ao nº 1 (o nº 1 é o melhor/mais chocante), 1 fechamento. Para cada item dê 'n', 'titulo' (até 3 palavras) e 'icone' (emoji).",
             '{"titulo": "", "gancho": "", "cenas": [{"fala": "", "destaque": "", "emoji": "", "enfase": [], "broll": "", "n": 0, "titulo": "", "icone": ""}], "legenda": "", "hashtags": []}'),
    "quiz": ("Uma pergunta de conhecimento sobre o tema com 3 opções (só 1 certa). 'fala_pergunta': o narrador puxa o assunto em 1 frase, faz a pergunta e lê as 3 opções. 'fala_revela': revela a resposta e explica em 2 ou 3 frases com uma curiosidade, terminando com 'comenta quantas você acertou'.",
             '{"titulo": "", "gancho": "", "pergunta": "", "opcoes": ["", "", ""], "certa": 0, "fala_pergunta": "", "fala_revela": "", "legenda": "", "hashtags": []}'),
    "noticia": ("Notícia em tom de plantão (sobre o tema, sem inventar fato real específico se não tiver certeza: use 'rumores', 'dizem'). 4 a 6 cenas. Até 3 'numeros' com rotulo e valor curto.",
                '{"titulo": "", "gancho": "", "faixa": "URGENTE", "manchete": "", ' + ESQUEMA_CENAS + ', "numeros": [{"rotulo": "", "valor": ""}], "legenda": "", "hashtags": []}'),
    "versus": ("Compare A contra B em 3 a 4 quesitos com notas de 0 a 10 e diga quem vence. Cada cena = 1 quesito (mais abertura e veredito).",
               '{"titulo": "", "gancho": "", "a": "", "b": "", "ia": "emoji", "ib": "emoji", "quesitos": [{"rotulo": "", "va": 0, "vb": 0, "fala": ""}], "abertura": "", "veredito": "", "vencedor": "a", "legenda": "", "hashtags": []}'),
    "conversa": ("Conversa de WhatsApp engraçada/tensa entre 'eu' e um contato, com 12 a 18 mensagens (de 3 a 20 palavras cada), que cresce até uma reviravolta forte no fim. Em 'de' use só 'eu' ou 'outro'. Sem narração.",
                 '{"titulo": "", "gancho": "", "contato": "nome do contato", "mensagens": [{"de": "eu", "texto": ""}], "legenda": "", "hashtags": []}'),
}


def _llm(prompt: str, cfg, temperatura: float = 0.8) -> dict:
    ultimo = None
    for modelo in [cfg.llm_modelo, cfg.llm_planejador or cfg.llm_modelo]:
        try:
            r = httpx.post(cfg.llm_base + "/chat/completions", headers={"Authorization": f"Bearer {cfg.llm_key}"}, timeout=180,
                           json={"model": modelo, "temperature": temperatura, "max_tokens": 3500, "response_format": {"type": "json_object"},
                                 "chat_template_kwargs": {"enable_thinking": False}, "messages": [{"role": "user", "content": prompt}]})
            r.raise_for_status()
            return _json(r.json()["choices"][0]["message"]["content"])
        except Exception as e:  # noqa: BLE001
            ultimo = e
            log.warning("diretor %s falhou: %s", modelo, str(e)[:200])
    raise RuntimeError(f"diretor sem resposta: {ultimo}")


def escolher_formato(ideia: str) -> str:
    t = ideia.lower()
    for f, chaves in (("top5", ("top", "ranking", "melhores", "piores", "5 ")), ("quiz", ("quiz", "adivinh", "pergunta")),
                      ("versus", (" vs ", " x ", "contra", "versus", "melhor:")), ("conversa", ("conversa", "whats", "mensagem")),
                      ("noticia", ("notícia", "noticia", "urgente", "vazou", "lançamento")), ("impacto", ("motiva", "frase", "mentalidade")),
                      ("historia", ("história", "historia", "aconteceu", "conto", "terror"))):
        if any(c in t for c in chaves):
            return f
    return "curiosidade"


def roteiro(ideia: str, formato: str, segundos: int, cfg) -> dict:
    formato = formato if formato in FORMATOS else escolher_formato(ideia)
    segundos = max(20, min(90, int(segundos or 61)))
    extra, esquema = EXTRA[formato]
    limite = int(segundos * 2.6)  # palavras que cabem no tempo (voz a +12%)
    prompt = BASE.format(ideia=ideia, segundos=segundos, palavras=limite, formato=FORMATOS[formato][0], desc=FORMATOS[formato][1],
                         extra=extra, esquema=esquema)
    j = _llm(prompt, cfg)
    j["formato"], j["segundos"] = formato, segundos
    r = validar(j)
    if palavras(r) > limite * 1.3:  # passou do tempo: o diretor reescreve 1 vez, mais curto
        try:
            j2 = _llm(prompt + chr(10) * 2 + f"ATENÇÃO: o vídeo tem {segundos} segundos. Use NO MÁXIMO {limite} palavras de fala no total (some todas as falas).", cfg, 0.6)
            j2["formato"], j2["segundos"] = formato, segundos
            r2 = validar(j2)
            if palavras(r2) < palavras(r):
                r = r2
        except Exception:  # noqa: BLE001
            pass
    if palavras(r) > limite * 1.3 and formato in ("historia", "curiosidade", "impacto", "noticia"):
        while palavras(r) > limite * 1.15 and len(r["cenas"]) > 3:  # tira cenas do meio; gancho e chamada final ficam
            r["cenas"].pop(len(r["cenas"]) // 2)
    return r


def palavras(r: dict) -> int:
    n = sum(len(c.get("fala", "").split()) for c in r.get("cenas") or [])
    if r.get("conversa"):
        n = sum(len(m["texto"].split()) for m in r["conversa"]["mensagens"]) // 2
    return n


def _txt(v, n: int = 300) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()[:n]


def validar(j: dict) -> dict:
    """Esquema fechado: o que o molde não conhece é jogado fora; o que falta ganha valor padrão.
    Idempotente: aceita tanto a resposta crua do diretor quanto um roteiro já validado (o app manda de volta o que mostrou)."""
    j = dict(j)
    if isinstance(j.get("quiz"), dict):
        q = j["quiz"]
        j.setdefault("pergunta", q.get("pergunta")); j.setdefault("opcoes", q.get("opcoes")); j.setdefault("certa", q.get("certa"))
        j.setdefault("fala_pergunta", q.get("fala_pergunta")); j.setdefault("fala_revela", q.get("fala_revela"))
    if isinstance(j.get("conversa"), dict):
        j.setdefault("contato", j["conversa"].get("nome")); j.setdefault("mensagens", j["conversa"].get("mensagens"))
    if isinstance(j.get("noticia"), dict):
        for k in ("faixa", "manchete", "numeros"):
            j.setdefault(k, j["noticia"].get(k))
    if isinstance(j.get("versus"), dict) and not j.get("quesitos"):
        v = j["versus"]
        for k in ("a", "b", "ia", "ib", "vencedor"):
            j.setdefault(k, v.get(k))
        falas = [c.get("fala") for c in j.get("cenas") or []]
        j["quesitos"] = [{**it, "fala": falas[i + 1] if i + 1 < len(falas) else it.get("rotulo")} for i, it in enumerate(v.get("itens") or [])]
        j.setdefault("abertura", falas[0] if falas else ""); j.setdefault("veredito", falas[-1] if falas else "")
    f = j.get("formato") if j.get("formato") in FORMATOS else "curiosidade"
    out = {"formato": f, "segundos": max(20, min(90, int(j.get("segundos") or 61))), "titulo": _txt(j.get("titulo"), 80),
           "gancho": " ".join(_txt(j.get("gancho"), 60).upper().split()[:7]), "legenda": _txt(j.get("legenda"), 600),
           "hashtags": [("#" + _txt(h, 30).lstrip("#")) for h in (j.get("hashtags") or [])][:8]}
    cenas = []
    for c in j.get("cenas") or []:
        if not isinstance(c, dict) or not _txt(c.get("fala")):
            continue
        cenas.append({"fala": _txt(c.get("fala"), 400), "destaque": _txt(c.get("destaque") or c.get("titulo"), 40).upper(),
                      "emoji": _txt(c.get("emoji") or c.get("icone"), 8), "enfase": [_txt(x, 20).lower() for x in (c.get("enfase") or [])][:2],
                      "broll": _txt(c.get("broll"), 60), "n": int(c.get("n") or 0) if str(c.get("n") or "").isdigit() else 0,
                      "titulo": _txt(c.get("titulo"), 40), "icone": _txt(c.get("icone"), 8)})
    if f == "quiz":
        ops = [_txt(o, 40) for o in (j.get("opcoes") or [])][:4]
        out["quiz"] = {"pergunta": _txt(j.get("pergunta"), 160), "opcoes": ops or ["A", "B", "C"],
                       "certa": max(0, min(len(ops) - 1, int(j.get("certa") or 0))) if ops else 0,
                       "fala_pergunta": _txt(j.get("fala_pergunta") or j.get("pergunta"), 400), "fala_revela": _txt(j.get("fala_revela"), 300)}
        cenas = [{"fala": out["quiz"]["fala_pergunta"], "destaque": "", "emoji": "🤔"}, {"fala": out["quiz"]["fala_revela"] or "Acertou?", "destaque": "", "emoji": "✅"}]
    if f == "versus":
        qs = [q for q in (j.get("quesitos") or []) if isinstance(q, dict)][:5]
        out["versus"] = {"a": _txt(j.get("a"), 30), "b": _txt(j.get("b"), 30), "ia": _txt(j.get("ia"), 8), "ib": _txt(j.get("ib"), 8),
                         "vencedor": "b" if j.get("vencedor") == "b" else "a",
                         "itens": [{"rotulo": _txt(q.get("rotulo"), 30), "va": _num(q.get("va")), "vb": _num(q.get("vb"))} for q in qs]}
        cenas = ([{"fala": _txt(j.get("abertura"), 300) or out["gancho"], "destaque": ""}] +
                 [{"fala": _txt(q.get("fala"), 300) or _txt(q.get("rotulo")), "destaque": ""} for q in qs] +
                 [{"fala": _txt(j.get("veredito"), 300) or "E aí, concorda?", "destaque": ""}])
    if f == "noticia":
        out["noticia"] = {"faixa": _txt(j.get("faixa") or "URGENTE", 20).upper(), "manchete": _txt(j.get("manchete") or out["gancho"], 90),
                          "numeros": [{"rotulo": _txt(n.get("rotulo"), 30), "valor": _txt(n.get("valor"), 12)} for n in (j.get("numeros") or []) if isinstance(n, dict)][:3]}
    if f == "conversa":
        msgs = [{"de": "eu" if str(m.get("de")).lower() == "eu" else "outro", "texto": _txt(m.get("texto"), 140)} for m in (j.get("mensagens") or [])
                if isinstance(m, dict) and _txt(m.get("texto"))][:16]
        out["conversa"] = {"nome": _txt(j.get("contato") or "Contato", 24), "mensagens": msgs}
        cenas = [{"fala": "", "destaque": ""}]
    if not cenas:
        raise ValueError("roteiro sem cenas")
    out["cenas"] = cenas[:12]
    return out


def _num(v) -> float:
    try:
        return max(0.0, min(10.0, float(v)))
    except (TypeError, ValueError):
        return 5.0


# ---------------------------------------------------------------- voz
def narrar(partes: list[tuple[str, float]], voz: str, destino: Path) -> tuple[list[dict], list[tuple[float, float]]]:
    """Narra cada parte (texto, pausa depois) e junta. -> (palavras com tempo, [(ini, fim) de cada parte])."""
    import edge_tts
    pasta = destino.parent
    arquivos, palavras, faixas, t = [], [], [], 0.0

    async def um(texto: str, arq: Path) -> list[dict]:
        com = edge_tts.Communicate(texto, voz, rate="+12%", boundary="WordBoundary")
        ws = []
        with open(arq, "wb") as f:
            async for c in com.stream():
                if c["type"] == "audio":
                    f.write(c["data"])
                elif c["type"] == "WordBoundary":
                    a = c["offset"] / 1e7
                    ws.append({"t0": a, "t1": a + c["duration"] / 1e7, "w": c["text"]})
        return ws

    for i, (texto, pausa) in enumerate(partes):
        arq = pasta / f"parte{i}.mp3"
        ws = asyncio.run(um(texto, arq)) if texto.strip() else []
        from app.pipeline import duracao
        d = duracao(arq) if arq.exists() and arq.stat().st_size else 0.0
        palavras += [{"t0": round(w["t0"] + t, 3), "t1": round(w["t1"] + t, 3), "w": w["w"]} for w in ws]
        faixas.append((t, t + d))
        if arq.exists() and arq.stat().st_size:
            arquivos.append(arq)
        if pausa > 0:
            sil = pasta / f"pausa{i}.mp3"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", f"{pausa:.2f}", "-q:a", "9", str(sil)], check=True)
            arquivos.append(sil)
        t += d + pausa
    lista = pasta / "lista.txt"
    lista.write_text("".join(f"file '{a.name}'\n" for a in arquivos), encoding="utf-8")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lista), "-ar", "44100", "-ac", "1", "-b:a", "128k", str(destino)], check=True)
    for a in arquivos + [lista]:
        a.unlink(missing_ok=True)
    return palavras, faixas


# ---------------------------------------------------------------- B-roll (Pexels, quando houver chave)
def _baixar(url: str, cache: Path, destino: Path) -> str:
    cache.parent.mkdir(parents=True, exist_ok=True)
    if not cache.exists():
        tmp = cache.with_suffix(".parte")
        with httpx.stream("GET", url, timeout=60, follow_redirects=True, headers={"User-Agent": "Viralizai/1.0 (contato@rangeltech.net)"}) as s, open(tmp, "wb") as f:
            s.raise_for_status()
            for b in s.iter_bytes():
                f.write(b)
        tmp.replace(cache)
    destino = destino.with_suffix(cache.suffix)
    shutil.copy(cache, destino)
    return destino.name


def broll(busca: str, destino: Path, cfg) -> str | None:
    """Apoio visual da cena, nesta ordem: vídeo da Pixabay (chave grátis) > foto do Openverse (sem chave, só licença que
    permite uso comercial). O Pexels suspendeu chaves novas; não raspamos site nenhum (termos de uso)."""
    if not busca:
        return None
    if cfg.pixabay_key:
        try:
            r = httpx.get("https://pixabay.com/api/videos/", params={"key": cfg.pixabay_key, "q": busca[:90], "per_page": 5, "safesearch": "true"}, timeout=20)
            r.raise_for_status()
            for v in r.json().get("hits") or []:
                arq = (v.get("videos") or {}).get("medium") or (v.get("videos") or {}).get("small")
                if arq and arq.get("url"):
                    return _baixar(arq["url"], Path(cfg.dados) / "broll" / f"pixabay_{v['id']}.mp4", destino)
        except Exception as e:  # noqa: BLE001
            log.warning("broll pixabay %s: %s", busca, e)
    if os.environ.get("VIRALIZAI_BROLL_OPENVERSE") != "1":  # medido 18/11: fotos pouco ligadas à cena; desligado até melhorar a busca
        return None
    try:
        r = httpx.get("https://api.openverse.org/v1/images/", params={"q": busca[:90], "license_type": "commercial", "mature": "false",
                                                                      "page_size": 8, "aspect_ratio": "tall,square"}, timeout=20)
        r.raise_for_status()
        for im in r.json().get("results") or []:
            url = im.get("url") or ""
            if not url.lower().split("?")[0].endswith((".jpg", ".jpeg", ".png")) or (im.get("width") or 0) < 600:
                continue
            ext = ".png" if url.lower().split("?")[0].endswith(".png") else ".jpg"
            try:
                return _baixar(url, Path(cfg.dados) / "broll" / f"openverse_{im['id']}{ext}", destino)
            except Exception:  # noqa: BLE001  foto que não baixa: tenta a próxima
                continue
    except Exception as e:  # noqa: BLE001
        log.warning("broll openverse %s: %s", busca, e)
    return None


# ---------------------------------------------------------------- montar props e renderizar
def props(r: dict, voz: str, pasta: Path, perfil: dict, cfg) -> dict:
    f = r["formato"]
    sfx: list[dict] = []
    p: dict = {"formato": f, "variacao": random.randint(0, 2), "gancho": r["gancho"] or r["titulo"].upper()[:40], "arroba": perfil.get("arroba") or "",
               "cor": None, "final": "SEGUE PRA MAIS 🔥", "sfx": sfx, "palavras": [], "cenas": []}
    if f == "conversa":
        t = 1.2
        msgs = []
        mm = r["conversa"]["mensagens"]
        leitura = sum(1.0 + len(m["texto"]) * 0.045 for m in mm) or 1
        escala = max(1.0, min(2.2, (r.get("segundos", 30) - 2.7) / leitura))  # ocupa a duração pedida, sem ficar arrastado
        for m in mm:
            msgs.append({**m, "t": round(t, 2)})
            sfx.append({"t": round(t, 2), "tipo": "notif" if m["de"] == "outro" else "pop"})
            t += (1.0 + len(m["texto"]) * 0.045) * escala
        p["conversa"] = {"nome": r["conversa"]["nome"], "mensagens": msgs}
        p["duracao"] = round(t + 1.5, 2)
        p["cenas"] = [{"inicio": 0, "fim": p["duracao"], "fala": "", "destaque": ""}]
        return p
    partes: list[tuple[str, float]]
    if f == "quiz":
        partes = [(r["cenas"][0]["fala"], 5.0), (r["cenas"][1]["fala"], 0.6)]
    else:
        partes = [(c["fala"], 0.25) for c in r["cenas"]]
    if voz != "sem":
        palavras, faixas = narrar(partes, VOZES.get(voz, VOZES["masculina"]), pasta / "voz.mp3")
        p["voz"] = "voz.mp3"
    else:  # sem voz: tempo de leitura
        palavras, faixas, t = [], [], 0.0
        for texto, pausa in partes:
            ws = texto.split()
            for w in ws:
                palavras.append({"t0": round(t, 2), "t1": round(t + 0.32, 2), "w": w})
                t += 0.36
            faixas.append((faixas[-1][1] + partes[len(faixas) - 1][1] if faixas else 0.0, t))
            t += pausa
    p["palavras"] = palavras
    dur = (faixas[-1][1] if faixas else 10) + 0.6
    p["duracao"] = round(dur, 2)
    cenas = []
    for i, (c, (a, b)) in enumerate(zip(r["cenas"], faixas)):
        fim = faixas[i + 1][0] if i + 1 < len(faixas) else dur
        arq = broll(c.get("broll"), pasta / f"broll{i}.mp4", cfg) if c.get("broll") and r["formato"] in ("historia", "curiosidade", "top5", "noticia") else None
        cenas.append({"inicio": round(a, 2), "fim": round(fim, 2), "fala": c["fala"], "destaque": c.get("destaque") or "", "emoji": c.get("emoji") or "",
                      "enfase": c.get("enfase") or [], "icone": c.get("icone") or c.get("emoji") or "", **({"broll": arq} if arq else {})})
        if i:
            sfx.append({"t": max(0, round(a - 0.15, 2)), "tipo": "whoosh"})
        if c.get("destaque"):
            sfx.append({"t": round(a + 0.15, 2), "tipo": "pop"})
    p["cenas"] = cenas
    for w in palavras:  # impacto nas palavras de ênfase
        if any(e and e in w["w"].lower() for c in r["cenas"] for e in c.get("enfase") or []):
            sfx.append({"t": w["t0"], "tipo": "impacto"})
    if f == "top5":
        itens = []
        nums = [c for c in r["cenas"] if c.get("n")] or r["cenas"][1:6]
        for k, c in enumerate(nums):
            idx = r["cenas"].index(c)
            n = c.get("n") or (5 - k)
            t = cenas[idx]["inicio"]
            itens.append({"n": n, "titulo": c.get("titulo") or c.get("destaque") or "", "icone": c.get("icone") or c.get("emoji") or "", "t": t})
            if n == 1:
                sfx.append({"t": max(0, t - 1.6), "tipo": "riser"})
            sfx.append({"t": t, "tipo": "ding" if n == 1 else "impacto"})
        p["ranking"] = itens
    if f == "quiz":
        q = r["quiz"]
        p["quiz"] = {"pergunta": q["pergunta"], "opcoes": q["opcoes"], "certa": q["certa"], "t_pergunta": 0.3, "t_revela": round(faixas[1][0], 2)}
        for s in range(5):
            sfx.append({"t": round(faixas[0][1] + s, 2), "tipo": "tic"})
        sfx.append({"t": round(faixas[1][0], 2), "tipo": "ding"})
    if f == "versus":
        v = r["versus"]
        p["versus"] = {**v, "itens": [{**it, "t": cenas[i + 1]["inicio"] if i + 1 < len(cenas) else 0} for i, it in enumerate(v["itens"])]}
    if f == "noticia":
        n = r["noticia"]
        p["noticia"] = {**n, "numeros": [{**x, "t": cenas[min(i + 1, len(cenas) - 1)]["inicio"]} for i, x in enumerate(n["numeros"])]}
        sfx.append({"t": 0.1, "tipo": "riser"})
    sfx.sort(key=lambda x: x["t"])
    return p


def renderizar(p: dict, pasta: Path, destino: Path, avisar=None) -> None:
    pub = pasta
    shutil.copytree(MOTION / "public" / "sfx", pub / "sfx", dirs_exist_ok=True)
    (pasta / "props.json").write_text(json.dumps(p, ensure_ascii=False), encoding="utf-8")
    npx = "npx.cmd" if os.name == "nt" else "npx"
    cmd = [npx, "remotion", "render", "src/index.ts", "Viral", str(destino), f"--props={pasta / 'props.json'}", f"--public-dir={pub}",
           "--codec=h264", "--crf=22", f"--concurrency={os.environ.get('VIRALIZAI_RENDER_CONC', '50%')}", "--log=error"]
    r = subprocess.run(cmd, cwd=MOTION, capture_output=True, text=True, timeout=1800)
    if r.returncode != 0 or not destino.exists():
        raise RuntimeError("render: " + (r.stderr or r.stdout)[-600:])


def fazer(entrada: dict, pasta: Path, cfg, avisar) -> dict:
    pasta.mkdir(parents=True, exist_ok=True)
    r = validar(entrada["roteiro"])
    avisar("Gravando a narração", 0.15)
    p = props(r, entrada.get("voz") or "masculina", pasta, entrada.get("perfil") or {}, cfg)
    p["cor"] = (entrada.get("perfil") or {}).get("cor")
    avisar("Animando as cenas", 0.4)
    out = pasta / "animacao.mp4"
    renderizar(p, pasta, out, avisar)
    capa = pasta / "animacao.jpg"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "3", "-i", str(out), "-frames:v", "1", "-vf", "scale=360:-2", "-q:v", "4", str(capa)], check=False)
    for x in list(pasta.glob("broll*")) + [pasta / "voz.mp3"]:
        x.unlink(missing_ok=True)
    shutil.rmtree(pasta / "sfx", ignore_errors=True)
    from app.pipeline import duracao
    return {"titulo": r["titulo"] or r["gancho"], "formato": r["formato"],
            "cortes": [{"k": 1, "estado": "pronto", "arquivo": out.name, "arquivos": {"tiktok": out.name}, "capa": capa.name if capa.exists() else None,
                        "titulo": r["titulo"], "gancho": r["gancho"], "legenda": r["legenda"], "hashtags": r["hashtags"], "duracao": round(duracao(out), 1)}]}
