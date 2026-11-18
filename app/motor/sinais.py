"""Linha do tempo (47c §3.1 e §3.2): cada sinal vira uma série por segundo, normalizada dentro do próprio vídeo
(mediana e desvio robusto), suavizada, e combinada com pesos por tipo de vídeo. Sinal ausente = peso redistribuído."""
from __future__ import annotations

import re

import numpy as np

RISADA = re.compile(r"(k{3,}|K{3,}|rs(rs)+|(ha){2,}|(he){3,}|lul|kekw|omegalul|😂|🤣|:face_with_tears_of_joy:|:rolling_on_the_floor_laughing:)", re.I)
CHOQUE = re.compile(r"(\?{2,}|wtf|mano+|n[aã]o acredito|clipa|clip it|pog|pogchamp|🔥|😱|:fire:|:scream:|caraca|meu deus|slk|vish|eita)", re.I)

PESOS = {  # 47c §3.2
    "gameplay": {"chat": .25, "publico": .25, "voz": .15, "jogo": .15, "imagem": .15, "texto": .05},
    "podcast": {"chat": .25, "publico": .25, "voz": .20, "jogo": 0.0, "imagem": .05, "texto": .25},
    "react": {"chat": .25, "publico": .25, "voz": .25, "jogo": .05, "imagem": .15, "texto": .05},
}
GATILHOS = {
    "gameplay": r"pol[ií]cia|estrela|fugi|explodiu|morri|matei|preso|perseguiç|bati|capotou|roubei|assalto|tiro|banid|treta",
    "podcast": r"pol[eê]mic|nunca contei|verdade|segredo|absurdo|dinheiro|milh|briga|chorei|traiç",
    "react": r"n[aã]o acredito|olha isso|caraca|meu deus|absurdo|que isso",
}


def tipo_do_video(ctx: dict) -> str:
    txt = " ".join([ctx.get("titulo", ""), " ".join(ctx.get("categorias", [])), " ".join(ctx.get("tags", []))]).lower()
    if re.search(r"\breact|reagindo|rea[cç][aã]o|reagi\b", txt):
        return "react"
    if "gaming" in txt or re.search(r"gta|rp\b|minecraft|fortnite|free fire|cs2|valorant|gameplay|jogando|live", txt):
        return "gameplay"
    return "podcast"


def robusto(x: np.ndarray) -> np.ndarray:
    """z-score robusto (mediana/MAD), cortado em [0, 6]: só interessa o que está ACIMA do normal do vídeo."""
    if not len(x) or not np.any(x):
        return np.zeros_like(x, dtype=float)
    med = np.median(x)
    mad = np.median(np.abs(x - med)) * 1.4826
    if mad < 1e-6:
        mad = np.std(x) or 1.0
    return np.clip((x - med) / mad, 0, 6)


def suavizar(x: np.ndarray, janela: int = 5) -> np.ndarray:
    if len(x) < janela:
        return x
    k = np.ones(janela) / janela
    return np.convolve(x, k, mode="same")


def serie_chat(msgs: list[dict], dur: int, atraso: float = 6.0) -> dict:
    """Volume, risada, choque, pessoas únicas e dinheiro por segundo. Chat reage DEPOIS: desloca para trás."""
    vol, ris, cho, pago = (np.zeros(dur) for _ in range(4))
    autores: dict[int, set] = {}
    for m in msgs:
        t = int(max(0, m["t"] - atraso))
        if t >= dur:
            continue
        vol[t] += 1
        autores.setdefault(t, set()).add(m.get("autor"))
        if RISADA.search(m["texto"]):
            ris[t] += 1
        if CHOQUE.search(m["texto"]):
            cho[t] += 1
        if m.get("pago"):
            pago[t] += 1
    unicos = np.zeros(dur)
    for t, s in autores.items():
        unicos[t] = len(s)
    return {"vol": vol, "risada": ris, "choque": cho, "pago": pago, "unicos": unicos}


def serie_publico(ctx: dict, coment: list[dict], dur: int) -> np.ndarray | None:
    s = np.zeros(dur)
    tem = False
    abertura = 120 if dur > 600 else 0  # o começo sempre "é revisto": todo mundo começa do zero
    for h in ctx.get("heatmap") or []:
        a, b = max(int(h["a"]), abertura), min(dur, int(h["b"]) + 1)
        if a >= b:
            continue
        s[a:b] = np.maximum(s[a:b], h["v"])
        tem = True
    if coment:
        c = np.zeros(dur)
        for x in coment:
            t = int(x["t"])
            c[max(0, t - 5):min(dur, t + 15)] += np.log1p(x["peso"])  # quem cita o tempo aponta o começo do momento
        s = s + (c / c.max() if c.max() else c)
        tem = True
    return s if tem else None


def serie_texto(palavras: list[dict], dur: int, tipo: str) -> tuple[np.ndarray, np.ndarray]:
    """(gatilhos, velocidade da fala em palavras/s)."""
    gat, vel = np.zeros(dur), np.zeros(dur)
    rx = re.compile(GATILHOS[tipo], re.I)
    for w in palavras:
        t = int(w["start"])
        if t < dur:
            vel[t] += 1
            if rx.search(w["word"]):
                gat[t] += 1
    return gat, vel


def linha_do_tempo(ctx: dict, dur: int, palavras: list[dict], chat: list[dict], coment: list[dict], aud: dict | None) -> dict:
    """Nota de interesse por segundo (0..1) + as séries brutas para explicar a nota ao cliente."""
    tipo = tipo_do_video(ctx)
    pesos = dict(PESOS[tipo])
    comp: dict[str, np.ndarray] = {}
    ch = serie_chat(chat, dur) if chat else None
    if ch is not None and ch["vol"].sum() >= max(30, dur / 120):  # chat com volume de verdade (pelo menos 1 msg a cada 2 min)
        comp["chat"] = suavizar(robusto(ch["unicos"]) + 1.5 * robusto(ch["risada"]) + 1.5 * robusto(ch["choque"]) + 2 * np.minimum(ch["pago"], 2), 5)
    pub = serie_publico(ctx, coment, dur)
    if pub is not None:
        comp["publico"] = suavizar(pub, 5)
    if aud and aud.get("db"):
        db = np.array(aud["db"][:dur] + [min(aud["db"])] * max(0, dur - len(aud["db"])))
        ev = {g: np.array((v[:dur] + [0] * max(0, dur - len(v)))) for g, v in (aud.get("eventos") or {}).items()}
        voz = robusto(db)
        if ev:
            voz = voz + 3 * robusto(ev["risada"]) + 3 * robusto(ev["grito"])
        comp["voz"] = suavizar(voz, 3)
        if ev and pesos["jogo"]:
            comp["jogo"] = suavizar(robusto(ev["tiro"]) + robusto(ev["explosao"]) + 0.6 * robusto(ev["sirene"]) + robusto(ev["batida"]), 5)
    if palavras:
        gat, vel = serie_texto(palavras, dur, tipo)
        comp["texto"] = suavizar(2 * gat + robusto(suavizar(vel, 5)), 5)
    usados = {k: pesos[k] for k in comp if pesos.get(k)}
    total = sum(usados.values()) or 1
    nota = np.zeros(dur)
    for k, w in usados.items():
        v = comp[k]
        m = np.percentile(v, 99.5) if np.any(v) else 1
        nota += (w / total) * np.clip(v / (m or 1), 0, 1)
    return {"tipo": tipo, "nota": suavizar(nota, 3), "comp": comp, "pesos": usados, "chat": ch, "aud": aud}


def resumo_sinais(lt: dict, a: float, b: float) -> str:
    """Frase curta com os sinais do trecho, para o juiz e para a explicação da nota ("chat 6x o normal...")."""
    ia, ib = int(a), int(b)
    partes = []
    ch = lt.get("chat")
    if ch is not None and "chat" in lt["comp"]:
        base = max(0.05, float(np.mean(ch["vol"])))
        pico = float(ch["vol"][ia:ib].mean()) if ib > ia else 0
        if pico / base >= 1.8:
            partes.append(f"chat {pico / base:.0f}x o normal")
        r = int(ch["risada"][ia:ib].sum())
        if r >= 3:
            partes.append(f"{r} risadas no chat")
        c = int(ch["choque"][ia:ib].sum())
        if c >= 3:
            partes.append(f"{c} reações de choque no chat")
        if ch["pago"][ia:ib].sum():
            partes.append("doação/Super Chat no trecho")
    if "publico" in lt["comp"]:
        v = lt["comp"]["publico"]
        if ib > ia and v[ia:ib].max() >= np.percentile(v, 90):
            partes.append("o público reviu muito esse trecho")
    aud = lt.get("aud") or {}
    ev = aud.get("eventos") or {}
    nomes = {"risada": "risada alta", "grito": "grito", "tiro": "tiros", "explosao": "explosão", "sirene": "sirene de polícia", "batida": "batida/derrapagem"}
    for g, nome in nomes.items():
        v = ev.get(g)
        if v and ib > ia:
            trecho = v[ia:ib]
            if trecho and max(trecho) >= 0.35:
                seg = ia + int(np.argmax(trecho))
                partes.append(f"{nome} aos {seg - ia}s")
    if "voz" in lt["comp"] and ib > ia:
        v = lt["comp"]["voz"]
        if v[ia:ib].max() >= np.percentile(v, 97):
            partes.append("voz bem empolgada")
    return ", ".join(partes[:6]) or "fala contínua"
