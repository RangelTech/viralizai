"""Orquestra o motor (47c) com CACHE ABSOLUTO (47 §6): cada vídeo é analisado uma vez só.

  pasta da fonte (dados/fontes/<chave>/):
    sinais.json          contexto + palavras + chat + comentários com tempo + áudio (o caro; nunca refeito sozinho)
    julgados_<obj>.json  candidatos julgados para um objetivo (tiktok | viral | reels)
    cortes/<ini>_<fim>/  trecho baixado + corte base 9:16 sem texto (vitrine)

Etapas independentes: legenda, chat, comentários e áudio rodam juntos; um que falhe não derruba o pedido.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

import httpx
import numpy as np

from app.motor import audio, candidatos, fonte, juiz, sinais

log = logging.getLogger("viralizai.analise")
VERSAO = 1
_travas: dict[str, threading.Lock] = {}
_trava_geral = threading.Lock()


def trava(chave: str) -> threading.Lock:
    """Mesmo vídeo pedido por 2 pessoas ao mesmo tempo = 1 análise (a 2ª espera e reaproveita)."""
    with _trava_geral:
        return _travas.setdefault(chave, threading.Lock())


def pasta_fonte(dados: str, chave: str) -> Path:
    return Path(dados) / "fontes" / re.sub(r"[^\w.-]", "_", chave)


def _ler(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _salvar(p: Path, obj) -> None:
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def coletar_sinais(url: str, pasta: Path, cfg, avisar: Callable[[str, float], None], info_pronta: dict | None = None,
                   arquivo_local: Path | None = None) -> dict:
    """O passo caro. Para upload, `arquivo_local` é o vídeo do cliente (nunca vai para a vitrine)."""
    cache = _ler(pasta / "sinais.json")
    if cache and cache.get("versao") == VERSAO:
        return cache
    pasta.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    if arquivo_local:
        from app.pipeline import duracao as dur_arq
        i = {"title": arquivo_local.stem, "duration": dur_arq(arquivo_local), "extractor_key": "upload", "id": arquivo_local.stem}
    else:
        avisar("Lendo o vídeo", 0.03)
        i = info_pronta or fonte.info(url, cfg)
    ctx = fonte.contexto(i)
    if ctx["ao_vivo"]:
        raise fonte.ErroFonte("Essa live está acontecendo agora. Mande o link quando ela terminar (ou use o Vigia ao Vivo).")
    if ctx["duracao"] and ctx["duracao"] > cfg.max_duracao_s:
        raise fonte.ErroFonte(f"O vídeo tem {int(ctx['duracao'] // 60)} minutos. O limite é {cfg.max_duracao_s // 60} minutos.")
    youtube = ctx["plataforma"].lower() == "youtube"
    avisar("Ouvindo o vídeo e lendo o chat", 0.08)
    res: dict = {"textos": {}, "comentarios": [], "audio": None, "arq_audio": None}

    def textos():
        res["textos"] = fonte.baixar_textos(url, i, pasta, cfg) if youtube else {}

    def coments():
        if youtube and ctx["views"] >= 5000 and ctx["duracao"] >= 300:
            res["comentarios"] = fonte.comentarios_com_tempo({"comments": fonte.comentarios(url, cfg)}, ctx["duracao"])

    def som():
        arq = arquivo_local or audio.baixar_audio(url, pasta, cfg)
        res["arq_audio"] = str(arq)
        res["audio"] = audio.analisar(arq)

    erros = {}
    with ThreadPoolExecutor(3) as ex:
        fut = {"textos": ex.submit(textos), "comentarios": ex.submit(coments), "audio": ex.submit(som)}
        for nome, f in fut.items():
            try:
                f.result()
            except Exception as e:  # noqa: BLE001  etapa com problema é pulada
                log.warning("sinal %s falhou: %s", nome, str(e)[:300])
                erros[nome] = str(e)[:200]
    if res["audio"] is None and not res["textos"].get("legenda"):
        raise RuntimeError("sem áudio e sem legenda: " + json.dumps(erros, ensure_ascii=False))
    leg = res["textos"].get("legenda")
    palavras = fonte.palavras_json3(leg) if leg else []
    chat = fonte.chat_youtube(res["textos"]["chat"]) if res["textos"].get("chat") else []
    if not ctx["duracao"] and res["audio"]:
        ctx["duracao"] = float(len(res["audio"]["db"]))
    s = {"versao": VERSAO, "url": url, "ctx": ctx, "lingua": res["textos"].get("lingua") or (i.get("language") or "pt"),
         "legenda": "auto" if palavras else "nenhuma", "palavras": palavras, "chat": chat, "comentarios": res["comentarios"],
         "audio": res["audio"], "arq_audio": res["arq_audio"], "erros": erros, "segundos": round(time.time() - t0, 1)}
    _salvar(pasta / "sinais.json", s)
    return s


def julgar(s: dict, pasta: Path, objetivo: str, quantos: int, cfg, avisar: Callable[[str, float], None]) -> list[dict]:
    """Candidatos julgados para o objetivo (cache). Sem legenda: Whisper em CPU só nas janelas candidatas."""
    arq = pasta / f"julgados_{objetivo}.json"
    cache = _ler(arq)
    if cache and len(cache) >= min(quantos, 3):
        return cache
    ctx = s["ctx"]
    dur = int(ctx["duracao"]) or len((s.get("audio") or {}).get("db") or [])
    palavras = s["palavras"]
    silencios = [tuple(x) for x in (s.get("audio") or {}).get("silencios") or []]
    avisar("Achando os melhores momentos", 0.35)
    lt = sinais.linha_do_tempo(ctx, dur, palavras, s["chat"], s["comentarios"], s.get("audio"))
    segs = fonte.frases(palavras) if palavras else []
    n_cand = max(6, min(15, quantos * 3))
    cands = candidatos.gerar(lt["nota"], segs, silencios, n_cand, objetivo, ctx.get("capitulos"))[:n_cand]
    if not palavras and cands and s.get("arq_audio"):
        avisar("Ouvindo os melhores momentos", 0.45)
        from app.motor import whisper_cpu
        janelas = [(max(0, c["inicio"] - 15), c["fim"] + 15) for c in cands]
        palavras = whisper_cpu.transcrever(Path(s["arq_audio"]), janelas, (s.get("lingua") or "pt")[:2])
        segs = fonte.frases(palavras)
        lt = sinais.linha_do_tempo(ctx, dur, palavras, s["chat"], s["comentarios"], s.get("audio"))
        cands = candidatos.gerar(lt["nota"], segs, silencios, n_cand, objetivo, ctx.get("capitulos"))[:n_cand]
        s["palavras_whisper"] = palavras
        _salvar(pasta / "sinais.json", s)
    if not cands:
        raise fonte.ErroFonte("Não achei momentos fortes nesse vídeo. Tenta outro vídeo ou uma live mais longa.")
    avisar("Escolhendo os melhores cortes", 0.55)
    with httpx.Client() as cliente:
        julgados = juiz.julgar(cands, segs, ctx, lt["tipo"], objetivo, lambda a, b: sinais.resumo_sinais(lt, a, b), cfg, cliente)
    for c in julgados:  # ajuste fino do juiz, de volta nas bordas de frase
        if c.get("ajuste_inicio") or c.get("ajuste_fim"):
            ini = candidatos._encaixar_inicio(c["inicio"] + c["ajuste_inicio"], segs, silencios, 3)
            fim = candidatos._encaixar_fim(c["fim"] + c["ajuste_fim"], segs, silencios, 3)
            mn, mx = candidatos.OBJETIVOS[objetivo][:2]
            if mn * 0.85 <= fim - ini <= mx + 5:
                c["inicio"], c["fim"] = round(ini, 2), round(fim, 2)
        c["tipo"] = lt["tipo"]
    _salvar(arq, julgados)
    _salvar(pasta / "nota.json", [round(float(x), 3) for x in np.asarray(lt["nota"])[::2]])  # para o gráfico do admin
    return julgados


def palavras_do_trecho(s: dict, ini: float, fim: float) -> list[dict]:
    """Palavras do corte com tempo relativo ao início do corte."""
    todas = s.get("palavras") or s.get("palavras_whisper") or []
    return [{"start": round(w["start"] - ini, 2), "end": round(w["end"] - ini, 2), "word": w["word"]}
            for w in todas if w["end"] > ini and w["start"] < fim]
