"""Coleta dos sinais de um vídeo SEM baixar o vídeo (spec 47c §2): metadados, legenda automática com o tempo de cada
palavra (json3), chat replay, "mais repetidos" (heatmap), capítulos e comentários com tempo.

Tudo pelo yt-dlp. No servidor a saída do YouTube passa pelo WARP (cfg.proxy) com os cookies de uma conta (cfg.yt_cookies).
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

log = logging.getLogger("viralizai.fonte")


class ErroFonte(Exception):
    """Erro mostrável ao cliente (link privado, playlist, ao vivo...)."""


def chave_rapida(url: str) -> str | None:
    """Chave do cache sem rede (YouTube e Twitch VOD). None = descobrir pelo yt-dlp."""
    u = url.strip()
    m = re.search(r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|live/|shorts/|embed/)|youtu\.be/)([\w-]{11})", u)
    if m:
        return "yt:" + m.group(1)
    m = re.search(r"twitch\.tv/videos/(\d+)", u)
    if m:
        return "tw:" + m.group(1)
    return None


def chave_de_info(info: dict) -> str:
    ext = (info.get("extractor_key") or info.get("extractor") or "x").lower()
    pref = {"youtube": "yt", "twitchvod": "tw", "kick": "kk"}.get(ext, ext[:8])
    return f"{pref}:{info.get('id')}"


def _opcoes(cfg, pasta: Path | None = None) -> dict:
    o = {"quiet": True, "no_warnings": True, "noprogress": True, "noplaylist": True, "socket_timeout": 30, "retries": 3}
    if getattr(cfg, "proxy", ""):
        o["proxy"] = cfg.proxy
    ck = getattr(cfg, "yt_cookies", "")
    if ck and Path(ck).is_file():
        o["cookiefile"] = ck
    if pasta:
        o["outtmpl"] = str(pasta / "fonte.%(ext)s")
    return o


def info(url: str, cfg) -> dict:
    import yt_dlp
    try:
        with yt_dlp.YoutubeDL({**_opcoes(cfg), "skip_download": True}) as y:
            i = y.extract_info(url, download=False)
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        log.warning("info falhou: %s", msg[:300])
        if "Private" in msg or "members" in msg.lower():
            raise ErroFonte("Esse vídeo é privado ou só para membros. Use um link público ou suba o vídeo.") from e
        raise ErroFonte("Esse link não abriu. Confere se é público ou suba o vídeo.") from e
    if i.get("_type") == "playlist":
        raise ErroFonte("Esse link é de uma playlist. Mande o link de um vídeo só.")
    return i


def lingua_legenda(i: dict) -> tuple[str | None, bool]:
    """Escolhe UMA legenda: manual na língua do vídeo > automática original (xx-orig) > automática xx.
    Nunca pede tradução (pt-PT etc.): cada pedido extra dá 429."""
    lang = (i.get("language") or "pt").split("-")[0]
    subs = i.get("subtitles") or {}
    for k in subs:
        if k != "live_chat" and k.split("-")[0] == lang:
            return k, False
    auto = i.get("automatic_captions") or {}
    for k in (f"{lang}-orig", lang):
        if k in auto:
            return k, True
    orig = next((k for k in auto if k.endswith("-orig")), None)
    return (orig, True) if orig else (None, False)


def baixar_textos(url: str, i: dict, pasta: Path, cfg) -> dict:
    """Legenda json3 + chat replay, sem vídeo. Devolve caminhos (ou None)."""
    import yt_dlp
    pasta.mkdir(parents=True, exist_ok=True)
    lang, automatica = lingua_legenda(i)
    langs = [x for x in (lang, "live_chat" if "live_chat" in (i.get("subtitles") or {}) else None) if x]
    if not langs:
        return {"legenda": None, "chat": None}
    o = {**_opcoes(cfg, pasta), "skip_download": True, "writesubtitles": True, "writeautomaticsub": automatica,
         "subtitleslangs": langs, "subtitlesformat": "json3", "ignoreerrors": True}
    try:
        with yt_dlp.YoutubeDL(o) as y:
            y.process_ie_result(dict(i), download=True)
    except Exception as e:  # noqa: BLE001  legenda/chat faltando não derruba: Whisper e áudio cobrem
        log.warning("textos falharam: %s", str(e)[:300])
    leg = next(iter(pasta.glob(f"fonte.{lang}.json3")), None) if lang else None
    chat = next(iter(pasta.glob("fonte.live_chat.json")), None)
    return {"legenda": leg, "chat": chat, "lingua": lang}


# ---------------------------------------------------------------- parse
def palavras_json3(caminho: Path) -> list[dict]:
    """json3 do YouTube -> [{start, end, word}] com o tempo de cada palavra."""
    j = json.loads(Path(caminho).read_text(encoding="utf-8"))
    out: list[dict] = []
    for ev in j.get("events") or []:
        segs = ev.get("segs") or []
        t0 = (ev.get("tStartMs") or 0) / 1000
        fim_ev = t0 + (ev.get("dDurationMs") or 0) / 1000
        itens = [(t0 + (s.get("tOffsetMs") or 0) / 1000, (s.get("utf8") or "").strip()) for s in segs]
        itens = [(t, w) for t, w in itens if w and w != "\n" and not re.fullmatch(r"\[.*\]", w)]
        for k, (t, w) in enumerate(itens):
            fim = itens[k + 1][0] if k + 1 < len(itens) else (fim_ev if fim_ev > t else t + 0.5)
            pedacos = [x for x in w.split() if not re.fullmatch(r"[>\-–—]+", x)]
            if not pedacos:
                continue
            # bloco com várias palavras (legenda manual / sem tempo por palavra): espalha no tempo do bloco, proporcional ao tamanho
            fim = max(fim, t + 0.25 * len(pedacos))
            pesos = [len(x) + 2 for x in pedacos]; tot, acc = sum(pesos), 0.0
            for x, peso in zip(pedacos, pesos):
                a0 = t + (fim - t) * acc / tot; acc += peso
                out.append({"start": round(a0, 2), "end": round(t + (fim - t) * acc / tot, 2), "word": x})
    out.sort(key=lambda w: w["start"])
    # eventos sobrepostos da legenda "rolante": tira duplicatas e corrige o fim
    limpo: list[dict] = []
    for w in out:
        if limpo and abs(limpo[-1]["start"] - w["start"]) < 0.01 and limpo[-1]["word"] == w["word"]:
            continue
        if limpo and limpo[-1]["end"] > w["start"]:
            limpo[-1]["end"] = max(limpo[-1]["start"] + 0.1, w["start"])
        limpo.append(w)
    return limpo


def frases(palavras: list[dict], pausa: float = 0.7, max_s: float = 12.0) -> list[dict]:
    """Agrupa palavras em frases (pausa, pontuação ou 12 s) no formato de segmento do Whisper."""
    segs, atual = [], []
    for k, w in enumerate(palavras):
        atual.append(w)
        prox = palavras[k + 1] if k + 1 < len(palavras) else None
        if (not prox or prox["start"] - w["end"] > pausa or re.search(r"[.!?]$", w["word"])
                or w["end"] - atual[0]["start"] > max_s):
            segs.append({"start": atual[0]["start"], "end": atual[-1]["end"], "text": " ".join(x["word"] for x in atual)})
            atual = []
    return segs


DINHEIRO = ("liveChatPaidMessageRenderer", "liveChatPaidStickerRenderer", "liveChatMembershipItemRenderer",
            "liveChatSponsorshipsGiftPurchaseAnnouncementRenderer")


def chat_youtube(caminho: Path) -> list[dict]:
    """live_chat.json (uma ação por linha) -> [{t, texto, autor, pago}]"""
    msgs = []
    for linha in Path(caminho).read_text(encoding="utf-8").splitlines():
        try:
            o = json.loads(linha)
        except ValueError:
            continue
        rep = o.get("replayChatItemAction") or {}
        t = int(rep.get("videoOffsetTimeMsec") or 0) / 1000
        for a in rep.get("actions") or []:
            item = (a.get("addChatItemAction") or {}).get("item") or {}
            for tipo, r in item.items():
                if tipo not in ("liveChatTextMessageRenderer",) + DINHEIRO:
                    continue
                runs = ((r.get("message") or r.get("headerSubtext") or {}).get("runs")) or []
                texto = "".join(x.get("text") or ((x.get("emoji") or {}).get("shortcuts") or [""])[0] for x in runs)
                autor = ((r.get("authorName") or {}).get("simpleText")) or r.get("authorExternalChannelId") or ""
                msgs.append({"t": t, "texto": texto, "autor": autor, "pago": tipo in DINHEIRO})
    return msgs


_TEMPO = re.compile(r"(?<![\d:])(?:(\d{1,2}):)?(\d{1,2}):(\d{2})(?![\d:])")


def comentarios_com_tempo(i: dict, dur: float) -> list[dict]:
    """Comentários que apontam um momento ("12:34 kkkk"). Peso = curtidas + 1."""
    out = []
    for c in i.get("comments") or []:
        txt = c.get("text") or ""
        for m in _TEMPO.finditer(txt):
            h, mi, s = int(m.group(1) or 0), int(m.group(2)), int(m.group(3))
            if s >= 60 or (m.group(1) and mi >= 60):
                continue
            t = h * 3600 + mi * 60 + s
            if 0 < t < dur:
                out.append({"t": float(t), "peso": 1 + int(c.get("like_count") or 0), "texto": txt[:140]})
    return out


def comentarios(url: str, cfg, maximo: int = 300) -> list[dict]:
    """Os comentários mais curtidos (só para achar tempos citados). Falha = lista vazia."""
    import yt_dlp
    o = {**_opcoes(cfg), "skip_download": True, "getcomments": True,
         "extractor_args": {"youtube": {"max_comments": [str(maximo), "all", "0"], "comment_sort": ["top"]}}}
    try:
        with yt_dlp.YoutubeDL(o) as y:
            return y.extract_info(url, download=False).get("comments") or []
    except Exception as e:  # noqa: BLE001
        log.warning("comentarios falharam: %s", str(e)[:200])
        return []


def contexto(i: dict) -> dict:
    """Metadados que definem o tipo do vídeo e os pesos (47c S7)."""
    return {
        "titulo": i.get("title") or "vídeo", "canal": i.get("uploader") or i.get("channel") or "",
        "duracao": float(i.get("duration") or 0), "views": int(i.get("view_count") or 0),
        "categorias": i.get("categories") or [], "tags": (i.get("tags") or [])[:30],
        "descricao": (i.get("description") or "")[:600], "plataforma": i.get("extractor_key") or "",
        "ao_vivo": bool(i.get("is_live")), "era_live": bool(i.get("was_live")), "url": i.get("webpage_url") or i.get("original_url") or "",
        "capa": i.get("thumbnail") or "", "id": i.get("id"),
        "heatmap": [{"a": float(h["start_time"]), "b": float(h["end_time"]), "v": float(h["value"])} for h in i.get("heatmap") or []],
        "capitulos": [{"a": float(c["start_time"]), "b": float(c["end_time"]), "t": c.get("title") or ""} for c in i.get("chapters") or []],
    }
