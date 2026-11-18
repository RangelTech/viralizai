"""Juiz (47c §3.4): UMA chamada de IA (Qwen pelo llm-access) recebe os candidatos com a fala e o resumo dos sinais e
devolve nota 0-100 com explicação, se a história se entende sozinha, ajuste fino das bordas, gancho, título, legenda e
hashtags. Sem IA (fora do ar), a nota vem só dos sinais: o pedido nunca cai por causa do juiz."""
from __future__ import annotations

import json
import logging
import re

import httpx

log = logging.getLogger("viralizai.juiz")

PROMPT = """Você é o editor-chefe de um canal de cortes virais (TikTok, Reels, Shorts) em português do Brasil.
Vídeo: "{titulo}" ({canal}). Tipo: {tipo}. Objetivo dos cortes: {objetivo}.

Abaixo vêm {n} trechos candidatos. Para cada um: o tempo, o que os SINAIS mostram (chat, público, áudio) e a fala transcrita
(legenda automática, pode ter erros e não tem pontuação).

Dê a cada candidato:
- "nota" de 0 a 100: potencial de viralizar (gancho forte, história que se entende sozinha, reação, humor, ação, polêmica).
  Seja exigente: abertura de live, conversa morta, "fala galera", pedido de inscrito e trecho confuso ficam abaixo de 40.
- "porque": explicação curta para o cliente (até 90 letras), citando o sinal mais forte. Ex.: "chat explodiu + risada alta na fuga da polícia".
- "sozinho": true se dá para entender sem ver o resto do vídeo.
- "ajuste_inicio" e "ajuste_fim": segundos para mexer nas bordas (negativo = antes), entre -10 e 10; 0 se estiver bom.
- "gancho": texto do topo do vídeo, até 8 palavras, MAIÚSCULAS, que faça a pessoa parar de rolar (sem mentir sobre o trecho).
- "titulo": até 60 letras.
- "legenda": legenda do post com chamada para comentar e crédito ao canal original ({canal}).
- "hashtags": 4 a 6.
- "assunto": 2 a 4 palavras do assunto (para não escolher dois cortes iguais).

Responda SÓ com JSON: {{"cortes": [{{"id": 1, "nota": 0, "porque": "", "sozinho": true, "ajuste_inicio": 0, "ajuste_fim": 0,
"gancho": "", "titulo": "", "legenda": "", "hashtags": [], "assunto": ""}}]}}

Candidatos:
{candidatos}"""

OBJETIVO_TXT = {"tiktok": "ganhar no TikTok (61 a 90 s, precisa prender até o fim)", "viral": "viralizar rápido (20 a 40 s)",
                "reels": "Reels/Shorts (até 60 s)"}


def _fala(segs: list[dict], a: float, b: float, limite: int = 1400) -> str:
    t = " ".join(s["text"] for s in segs if s["end"] > a and s["start"] < b)
    return t[:limite] + ("…" if len(t) > limite else "")


def _mmss(t: float) -> str:
    t = int(t)
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60}:{t % 60:02d}"


def _json(txt: str) -> dict:
    txt = re.sub(r"<think>.*?</think>", "", txt or "", flags=re.S)
    m = re.search(r"\{.*\}", txt, re.S)
    if not m:
        raise ValueError("sem JSON")
    bruto = m.group(0)
    try:
        return json.loads(bruto)
    except ValueError:
        pass
    # reparo leve: vírgula sobrando, aspas curvas, quebra de linha dentro de string
    s = re.sub(r",\s*([}\]])", r"\1", bruto).replace("“", "'").replace("”", "'")
    try:
        return json.loads(s, strict=False)
    except ValueError:
        # último recurso: aproveita cada objeto de corte que estiver inteiro
        itens = []
        for o in re.findall(r"\{[^{}]*\}", bruto):
            try:
                itens.append(json.loads(o, strict=False))
            except ValueError:
                continue
        if not itens:
            raise
        return {"cortes": itens}


def julgar(cands: list[dict], segs: list[dict], ctx: dict, tipo: str, objetivo: str, resumo_de, cfg, cliente: httpx.Client,
           modelos: list[str] | None = None) -> list[dict]:
    """Devolve os candidatos com os campos do juiz (ou nota dos sinais, se a IA falhar), ordenados pela nota."""
    linhas = []
    for k, c in enumerate(cands, 1):
        c["sinais"] = resumo_de(c["inicio"], c["fim"])
        linhas.append(f"#{k} [{_mmss(c['inicio'])} a {_mmss(c['fim'])}, {c['fim'] - c['inicio']:.0f}s] SINAIS: {c['sinais']}\n"
                      f"FALA: {_fala(segs, c['inicio'], c['fim']) or '(sem fala)'}")
    prompt = PROMPT.format(titulo=ctx.get("titulo", ""), canal=ctx.get("canal", "") or "canal original", tipo=tipo,
                           objetivo=OBJETIVO_TXT.get(objetivo, objetivo), n=len(cands), candidatos="\n\n".join(linhas))
    respostas = {}
    for modelo in modelos or [cfg.llm_modelo, cfg.llm_modelo]:  # 2 tentativas
        try:
            r = cliente.post(cfg.llm_base + "/chat/completions", headers={"Authorization": f"Bearer {cfg.llm_key}"}, timeout=240,
                             json={"model": modelo, "temperature": 0.3, "max_tokens": 6000, "chat_template_kwargs": {"enable_thinking": False},
                                   "response_format": {"type": "json_object"},
                                   "messages": [{"role": "user", "content": prompt}]})
            r.raise_for_status()
            j = _json(r.json()["choices"][0]["message"]["content"])
            respostas = {_id(x, k): x for k, x in enumerate(j.get("cortes") or [], 1) if isinstance(x, dict)}
            if respostas:
                break
        except Exception as e:  # noqa: BLE001
            log.warning("juiz %s falhou: %s", modelo, str(e)[:200])
    out = []
    for k, c in enumerate(cands, 1):
        x = respostas.get(k)
        if x:
            try:
                nota = max(0, min(100, int(float(x.get("nota") or 0))))
            except (TypeError, ValueError):
                nota = 50
            tags = x.get("hashtags") or []
            if isinstance(tags, str):
                tags = re.findall(r"#?\w+", tags)
            c.update({
                "nota": nota, "porque": str(x.get("porque") or c["sinais"])[:120], "sozinho": bool(x.get("sozinho", True)),
                "ajuste_inicio": _lim(x.get("ajuste_inicio")), "ajuste_fim": _lim(x.get("ajuste_fim")),
                "gancho": str(x.get("gancho") or "").upper()[:60], "titulo": str(x.get("titulo") or "")[:80],
                "legenda": str(x.get("legenda") or "")[:600], "assunto": str(x.get("assunto") or "")[:40],
                "hashtags": [("#" + str(t).lstrip("#"))[:30] for t in tags][:6], "juiz": True,
            })
        else:  # sem IA: nota pelos sinais, textos neutros
            c.update({"nota": int(40 + 50 * min(1.0, c.get("nota_sinal", 0))), "porque": c["sinais"][:120], "sozinho": True,
                      "ajuste_inicio": 0, "ajuste_fim": 0, "gancho": "", "titulo": ctx.get("titulo", "")[:60], "assunto": "",
                      "legenda": f"Créditos: {ctx.get('canal', '')}", "hashtags": [], "juiz": False})
        if not c["sozinho"]:
            c["nota"] = max(0, c["nota"] - 15)
        out.append(c)
    return sorted(out, key=lambda c: -c["nota"])


def _id(x: dict, k: int) -> int:
    m = re.search(r"\d+", str(x.get("id") or ""))
    return int(m.group(0)) if m else k


def _lim(v) -> float:
    try:
        return max(-10.0, min(10.0, float(v or 0)))
    except (TypeError, ValueError):
        return 0.0


def variados(julgados: list[dict], n: int) -> list[dict]:
    """Os melhores por nota, sem repetir assunto (47c §3.4 seleção final)."""
    escolhidos, assuntos = [], set()
    for c in julgados:
        a = re.sub(r"\W+", " ", c.get("assunto", "").lower()).strip()
        if a and a in assuntos:
            continue
        escolhidos.append(c)
        if a:
            assuntos.add(a)
        if len(escolhidos) >= n:
            break
    if len(escolhidos) < n:  # faltou: completa com os que sobraram
        escolhidos += [c for c in julgados if c not in escolhidos][:n - len(escolhidos)]
    return escolhidos
