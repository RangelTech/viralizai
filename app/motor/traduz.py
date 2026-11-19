"""Legenda sempre em português (47e §1): corte de vídeo gringo tem a fala traduzida frase a frase pelo Qwen e as palavras
traduzidas ocupam o tempo da frase original (proporcional ao tamanho de cada palavra), para o karaokê continuar no ritmo."""
from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path

import httpx

log = logging.getLogger("viralizai.traduz")


def precisa(lingua: str | None) -> bool:
    return not (lingua or "pt").lower().startswith("pt")


def frases(palavras: list[dict]) -> list[list[dict]]:
    """Quebra em frases curtas: pontuação, pausa > 0,6 s ou 12 palavras."""
    out, atual = [], []
    for k, w in enumerate(palavras):
        if not str(w["word"]).strip():
            continue
        atual.append(w)
        prox = palavras[k + 1] if k + 1 < len(palavras) else None
        if re.search(r"[.!?]$", str(w["word"]).strip()) or len(atual) >= 12 or not prox or prox["start"] - w["end"] > 0.6:
            out.append(atual)
            atual = []
    if atual:
        out.append(atual)
    return out


def _pedir(textos: list[str], lingua: str, cfg) -> list[str]:
    prompt = ("Traduza cada frase abaixo (fala de vídeo em '" + lingua + "') para português do Brasil, do jeito que um brasileiro falaria, "
              "curto, natural, mantendo gíria e emoção. Não explique nada. Responda só JSON {\"t\": [...]} com EXATAMENTE "
              f"{len(textos)} frases, na mesma ordem.\n\n" + "\n".join(f"{i + 1}. {t}" for i, t in enumerate(textos)))
    with httpx.Client(timeout=180) as c:
        for _ in range(2):
            r = c.post(cfg.llm_base + "/chat/completions", headers={"Authorization": f"Bearer {cfg.llm_key}"},
                       json={"model": cfg.llm_modelo, "temperature": 0.2, "max_tokens": 4000, "chat_template_kwargs": {"enable_thinking": False},
                             "messages": [{"role": "user", "content": prompt}]})
            r.raise_for_status()
            txt = r.json()["choices"][0]["message"].get("content") or ""
            txt = re.sub(r"<think>.*?</think>", "", txt, flags=re.S)
            m = re.search(r"\{.*\}", txt, re.S)
            try:
                t = json.loads(m.group(0))["t"] if m else []
            except Exception:
                t = []
            if len(t) == len(textos):
                return [str(x).strip() for x in t]
    raise RuntimeError("tradução veio incompleta")


def para_pt(palavras: list[dict], lingua: str | None, cfg, cache: Path | None = None) -> list[dict]:
    """Devolve as palavras em português com tempos. Se a fala já é PT, devolve igual. Se a IA falhar, devolve o original."""
    if not precisa(lingua) or not palavras:
        return palavras
    grupos = frases(palavras)
    textos = [" ".join(str(w["word"]).strip() for w in g) for g in grupos]
    chave = hashlib.sha256(json.dumps(textos).encode()).hexdigest()[:16]
    arq = cache / f"pt_{chave}.json" if cache else None
    trad = None
    if arq and arq.exists():
        try:
            trad = json.loads(arq.read_text(encoding="utf-8"))
        except Exception:
            trad = None
    if trad is None:
        try:
            trad = []
            for i in range(0, len(textos), 15):  # lotes de 15 frases; lote que volta errado é traduzido frase a frase
                lote = textos[i:i + 15]
                try:
                    trad += _pedir(lote, lingua or "en", cfg)
                except Exception:  # noqa: BLE001
                    trad += [(_pedir([x], lingua or "en", cfg) or [x])[0] for x in lote]
            if arq:
                arq.parent.mkdir(parents=True, exist_ok=True)
                arq.write_text(json.dumps(trad, ensure_ascii=False), encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            log.warning("tradução falhou (%s); legenda fica no original", e)
            return palavras
    out = []
    for g, t in zip(grupos, trad):
        ws = t.split()
        if not ws:
            continue
        a, b = g[0]["start"], g[-1]["end"]
        pesos = [len(w) + 2 for w in ws]
        tot, acc = sum(pesos), 0.0
        for w, p in zip(ws, pesos):
            ini = a + (b - a) * acc / tot
            acc += p
            out.append({"start": round(ini, 2), "end": round(a + (b - a) * acc / tot, 2), "word": w})
    return out
