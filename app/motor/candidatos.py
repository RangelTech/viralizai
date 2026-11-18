"""Candidatos (47c §3.3): picos da nota -> janela da história (contexto antes, reação depois) -> duração do objetivo
-> bordas exatas em começo/fim de frase, de preferência num silêncio."""
from __future__ import annotations

import numpy as np

# objetivo -> (mínimo, máximo, alvo) em segundos; fração do corte que vem ANTES do clímax
OBJETIVOS = {
    "tiktok": (61, 90, 72, 0.70),   # ganhar no TikTok: passa de 1 min
    "viral": (20, 40, 30, 0.45),    # viralizar rápido: começa perto do clímax
    "reels": (30, 60, 45, 0.60),    # Reels / Shorts
}


def picos(nota: np.ndarray, n: int, raio: int, minimo_pct: float = 75) -> list[int]:
    """Os n maiores picos, a pelo menos `raio` segundos uns dos outros (sem dois cortes do mesmo momento)."""
    if not len(nota):
        return []
    piso = np.percentile(nota, minimo_pct)
    v = nota.copy()
    out: list[int] = []
    while len(out) < n:
        i = int(np.argmax(v))
        if v[i] <= piso or v[i] <= 0:
            break
        out.append(i)
        v[max(0, i - raio):i + raio] = -1
    return out


def fim_da_reacao(nota: np.ndarray, p: int, limite: int) -> int:
    """Segue depois do pico até a nota voltar ao normal por 3 s seguidos (a reação acabou)."""
    base = float(np.median(nota)) + 0.25 * (float(nota[p]) - float(np.median(nota)))
    calmo = 0
    for t in range(p + 1, min(len(nota), p + limite)):
        calmo = calmo + 1 if nota[t] <= base else 0
        if calmo >= 3:
            return t
    return min(len(nota) - 1, p + limite)


def _encaixar_inicio(t: float, segs: list[dict], sil: list[tuple[float, float]], folga: float = 6.0) -> float:
    """Começo de frase em até `folga` s antes de t; prefere frase precedida de pausa (começo de assunto)."""
    if not segs:
        return _no_silencio(t, sil, folga)
    opcoes = [s for s in segs if t - folga <= s["start"] <= t + 1.5]
    if not opcoes:
        antes = [s for s in segs if s["start"] <= t]
        return antes[-1]["start"] if antes else segs[0]["start"]
    idx = {id(s): k for k, s in enumerate(segs)}

    def pausa_antes(s):
        k = idx[id(s)]
        return s["start"] - segs[k - 1]["end"] if k else 9.0
    melhor = max(opcoes, key=lambda s: (min(pausa_antes(s), 2.0), -abs(s["start"] - t)))
    return max(0.0, melhor["start"] - 0.15)


def _encaixar_fim(t: float, segs: list[dict], sil: list[tuple[float, float]], folga: float = 8.0) -> float:
    if not segs:
        return _no_silencio(t, sil, folga)
    opcoes = [s for s in segs if t - 1.5 <= s["end"] <= t + folga]
    if not opcoes:
        depois = [s for s in segs if s["end"] >= t]
        return depois[0]["end"] if depois else segs[-1]["end"]
    idx = {id(s): k for k, s in enumerate(segs)}

    def pausa_depois(s):
        k = idx[id(s)]
        return segs[k + 1]["start"] - s["end"] if k + 1 < len(segs) else 9.0
    melhor = max(opcoes, key=lambda s: (min(pausa_depois(s), 2.0), -abs(s["end"] - t)))
    return melhor["end"] + 0.25


def _no_silencio(t: float, sil: list[tuple[float, float]], folga: float) -> float:
    perto = [(a, b) for a, b in sil if abs((a + b) / 2 - t) <= folga]
    if not perto:
        return t
    a, b = min(perto, key=lambda x: abs((x[0] + x[1]) / 2 - t))
    return (a + b) / 2


def gerar(nota: np.ndarray, segs: list[dict], silencios: list[tuple[float, float]], quantos: int, objetivo: str = "tiktok",
          capitulos: list[dict] | None = None) -> list[dict]:
    mn, mx, alvo, antes = OBJETIVOS.get(objetivo, OBJETIVOS["tiktok"])
    dur = len(nota)
    out: list[dict] = []
    for p in picos(nota, max(3, quantos * 3), raio=int(mx * 0.8)):
        fim = fim_da_reacao(nota, p, int(mx * 0.45)) + 2
        ini = fim - alvo
        ini = min(ini, p - alvo * antes * 0.6)  # contexto antes do clímax
        if capitulos:  # não volta para o capítulo anterior (outro assunto)
            cap = next((c for c in capitulos if c["a"] <= p < c["b"]), None)
            if cap and ini < cap["a"] and p - cap["a"] >= mn * 0.5:
                ini = cap["a"]
        ini = max(0.0, ini)
        ini = _encaixar_inicio(ini, segs, silencios)
        fim = _encaixar_fim(max(fim, ini + mn), segs, silencios)
        if fim - ini > mx:  # longo demais: aperta pelo começo (o clímax e a reação ficam)
            ini = _encaixar_inicio(fim - mx + 4, segs, silencios, folga=3)
            if fim - ini > mx:
                ini = fim - mx
        if fim - ini < mn:
            fim = _encaixar_fim(ini + mn, segs, silencios)
        fim = min(fim, dur)
        if fim - ini < mn * 0.85:
            continue
        if any(not (fim <= o["inicio"] or ini >= o["fim"]) for o in out):
            continue
        out.append({"inicio": round(ini, 2), "fim": round(fim, 2), "pico": p, "nota_sinal": round(float(nota[p]), 3)})
    return out
