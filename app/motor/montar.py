"""Montagem dos cortes.

- `garantir_trecho`: baixa (uma vez) só o pedaço do vídeo com margem de 3 s e guarda no cache da fonte.
- `base`: corte 9:16 sem texto (é o que vai para "Prontos pra postar"; nunca tem a marca de ninguém).
- `personalizado`: a versão do cliente, com variação automática (anti-duplicado do TikTok: bordas +-2 s, leve zoom e
  cor) + legenda, gancho e @ por rede (estilo.versoes).
"""
from __future__ import annotations

import hashlib
import json
import logging
import random
import subprocess
from pathlib import Path

from app import estilo
from app.pipeline import H, W, _seguir_rosto, duracao

log = logging.getLogger("viralizai.montar")
MARGEM = 3.0


def pasta_corte(pasta_fonte: Path, ini: float, fim: float) -> Path:
    return pasta_fonte / "cortes" / f"{ini:.2f}_{fim:.2f}".replace(".", "-")


def garantir_trecho(s: dict, pasta_fonte: Path, ini: float, fim: float, cfg) -> tuple[Path, float]:
    """-> (arquivo do trecho, tempo do vídeo original no segundo 0 do arquivo). Cache em trecho.json.
    Trava por trecho: 3 clientes pedindo o mesmo corte ao mesmo tempo = 1 download (os outros esperam)."""
    from app.motor.analise import trava
    pc = pasta_corte(pasta_fonte, ini, fim)
    pc.mkdir(parents=True, exist_ok=True)
    meta = pc / "trecho.json"
    arq = pc / "trecho.mp4"
    with trava("trecho:" + str(pc)):
        if meta.exists() and arq.exists():
            return arq, json.loads(meta.read_text())["desloc"]
        tmp = pc / "trecho.baixando.mp4"
        local = s.get("arquivo_local")
        if local:  # upload: corta do arquivo do cliente
            a = max(0.0, ini - MARGEM)
            r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{a:.2f}", "-to", f"{fim + MARGEM:.2f}", "-i", local, "-c", "copy",
                                "-avoid_negative_ts", "make_zero", str(tmp)], capture_output=True, text=True)
            if r.returncode != 0:
                raise RuntimeError("ffmpeg trecho: " + r.stderr[-200:])
            desloc = a
        else:
            from app.motor import trecho
            desloc = trecho.baixar(s["url"], ini, fim, tmp, cfg, MARGEM)["desloc"]
        _conferir(tmp)
        tmp.replace(arq)
        meta.write_text(json.dumps({"desloc": desloc}))
        return arq, desloc


def _conferir(arq: Path) -> None:
    """Trecho quebrado (áudio ilegível, vídeo vazio) não entra no cache."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(arq), "-map", "0:a:0?", "-f", "null", "-"], capture_output=True, text=True)
    if r.returncode != 0 or "Decode error" in r.stderr or duracao(arq) < 3:
        arq.unlink(missing_ok=True)
        raise RuntimeError("trecho baixado veio quebrado: " + r.stderr[-200:])


def invalidar_trecho(pasta_fonte: Path, ini: float, fim: float) -> None:
    pc = pasta_corte(pasta_fonte, ini, fim)
    for n in ("trecho.json", "trecho.mp4"):
        (pc / n).unlink(missing_ok=True)
    for f in list(pc.glob("filtro_*.txt")) + list(pc.glob("vertical_*.mp4")):
        f.unlink(missing_ok=True)


def _filtro_trecho(origem: Path, layout: str = "auto") -> str:
    """Filtro 9:16 sobre o TRECHO INTEIRO (tempo t do trecho), guardado em filtro_<layout>.txt: o rastreio de rosto roda 1 vez."""
    cache = origem.parent / f"filtro_{layout}.txt"
    if cache.exists():
        return cache.read_text(encoding="utf-8")
    from app.pipeline import tamanho_video
    w, h = tamanho_video(str(origem))
    if h and w and h >= w:
        f = f"[0:v]fps=30,scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1[v0]"
    elif h and w and layout in ("rosto", "podcast", "react") and (pos := _seguir_rosto(str(origem), 0.0, duracao(origem), [], w, h)):
        f = pos.replace("[0:v]", "[0:v]fps=30,", 1)
    else:  # gameplay horizontal: fundo desfocado (calculado em 180x320, 16x mais barato) + jogo no meio, maior
        f = (f"[0:v]fps=30,split[a][b];[a]scale=180:320:force_original_aspect_ratio=increase,crop=180:320,boxblur=6:1,scale={W}:{H},eq=brightness=-0.12[fundo];"
             f"[b]crop='min(iw,ih*3/4)':ih,scale={W}:{int(W * 4 / 3)}[frente];[fundo][frente]overlay=(W-w)/2:(H-h)/2-70,setsar=1[v0]")
    cache.write_text(f, encoding="utf-8")
    return f


def vertical(origem: Path, layout: str = "auto") -> Path:
    """O trecho inteiro já em 9:16, SEM texto: feito 1 vez por trecho e layout (vários clientes no mesmo corte = 1 render pesado).
    Cada cliente depois só corta, varia e põe a legenda por cima (render leve)."""
    from app.motor.analise import trava
    dest = origem.parent / f"vertical_{layout}.mp4"
    with trava("vertical:" + str(dest)):
        if dest.exists() and dest.stat().st_size > 1000:
            return dest
        tmp = dest.with_suffix(".tmp.mp4")
        r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(origem), "-filter_complex", _filtro_trecho(origem, layout), "-map", "[v0]", "-map", "0:a?",
                            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "17", "-g", "30", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
                            "-movflags", "+faststart", str(tmp)], capture_output=True, text=True)
        if r.returncode != 0:
            tmp.unlink(missing_ok=True)
            raise RuntimeError("ffmpeg vertical: " + r.stderr[-400:])
        tmp.replace(dest)
    return dest


def _render(origem: Path, ini: float, fim: float, destino: Path, zoom: float = 1.0, cor: tuple[float, float] = (0.0, 1.0),
            ass: Path | None = None, layout: str = "auto", rapido: bool = False) -> None:
    """Corte do cliente a partir do vertical em cache: busca direta no tempo, variação, legenda/gancho/@, áudio normalizado."""
    vert = vertical(origem, layout)
    extra = ["setpts=PTS-STARTPTS"]
    if zoom > 1.0:
        extra.append(f"scale=iw*{zoom:.3f}:ih*{zoom:.3f},crop={W}:{H}")
    if tuple(cor) != (0.0, 1.0):
        extra.append(f"eq=brightness={cor[0]:.3f}:saturation={cor[1]:.3f}")
    if ass:
        extra.append(estilo._filtro(ass))
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{ini:.3f}", "-to", f"{fim:.3f}", "-i", str(vert), "-vf", ",".join(extra),
                        "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:v", "libx264", "-preset", "superfast", "-crf", "27" if rapido else "23",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", "-threads", "3", str(destino)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg: " + r.stderr[-400:])


def base(s: dict, pasta_fonte: Path, corte: dict, cfg) -> dict:
    """Corte base (sem texto) + capa. Cache: só faz uma vez por trecho."""
    ini, fim = corte["inicio"], corte["fim"]
    pc = pasta_corte(pasta_fonte, ini, fim)
    limpo, capa = pc / "base.mp4", pc / "capa.jpg"
    if not limpo.exists():
        arq, desloc = garantir_trecho(s, pasta_fonte, ini, fim, cfg)
        _render(arq, ini - desloc, fim - desloc, limpo, layout=corte.get("tipo") or "auto", rapido=True)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "1.5", "-i", str(limpo), "-frames:v", "1", "-q:v", "4", "-vf", "scale=360:-2", str(capa)],
                       check=False)
    previa = previa_vitrine(s, pasta_fonte, corte, cfg)
    return {"pasta": str(pc), "base": str(limpo), "previa": str(previa) if previa else str(limpo),
            "capa": str(capa) if capa.exists() else None, "duracao": round(duracao(limpo), 1)}


def palavras_corte(s: dict, pasta_fonte: Path, arq: Path, desloc: float, ini: float, fim: float) -> list[dict]:
    """Palavras do corte com tempo REAL (Whisper no áudio do trecho, cache por corte). Reserva: legendas do YouTube espalhadas."""
    from app.motor.analise import palavras_do_trecho
    cache = pasta_corte(pasta_fonte, ini, fim) / f"palavras_{ini:.2f}_{fim:.2f}.json"
    if cache.exists():
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    # 1º: transcrição do YouTube, se ela tem tempo POR PALAVRA (legenda automática: quase todo início é diferente) — instantâneo
    yt = [w for w in (s.get("palavras") or s.get("palavras_whisper") or []) if w["end"] > ini and w["start"] < fim]
    if len(yt) >= 8 and len({round(w["start"], 2) for w in yt}) / len(yt) > .85:
        return palavras_do_trecho(s, ini, fim)
    # 2º: veio em blocos (legenda manual / sem tempo por palavra): Whisper só no trecho do corte
    try:
        from app.motor import whisper_cpu
        a, b = max(0.0, ini - desloc), max(0.0, fim - desloc)
        ws = whisper_cpu.transcrever(arq, [(a, b)], (s.get("lingua") or "pt")[:2])
        ws = [{"start": round(float(w["start"]) - a, 2), "end": round(float(w["end"]) - a, 2), "word": str(w["word"]).strip()} for w in ws
              if str(w["word"]).strip() and w["end"] > a and w["start"] < b]
        if len(ws) >= 3:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(ws, ensure_ascii=False), encoding="utf-8")
            return ws
    except Exception as e:  # noqa: BLE001
        log.warning("whisper no corte falhou (%s); uso a legenda do YouTube", e)
    return palavras_do_trecho(s, ini, fim)


def previa_vitrine(s: dict, pasta_fonte: Path, corte: dict, cfg, refazer: bool = False) -> Path | None:
    """Prévia da vitrine com pós-produção (47e §1): legenda em português com karaokê, título grande em caixa, barra de progresso.
    SEM @: o corte da vitrine é reaproveitado por vários clientes (o @ entra só na versão de cada um)."""
    from app.motor import traduz
    from app.motor.analise import palavras_do_trecho
    ini, fim = corte["inicio"], corte["fim"]
    pc = pasta_corte(pasta_fonte, ini, fim)
    dest = pc / "previa.mp4"
    if dest.exists() and not refazer:
        return dest
    try:
        arq, desloc = garantir_trecho(s, pasta_fonte, ini, fim, cfg)
        palavras = traduz.para_pt(palavras_corte(s, pasta_fonte, arq, desloc, ini, fim), s.get("lingua"), cfg, pasta_fonte)
        a = pc / "previa.ass"
        a.write_text(estilo.ass(palavras, fim - ini, corte.get("gancho") or "", "tiktok", "", estilo.COR_PADRAO, True), encoding="utf-8")
        tmp = pc / "previa.tmp.mp4"
        _render(arq, ini - desloc, fim - desloc, tmp, ass=a, layout=corte.get("tipo") or "auto", rapido=True)
        tmp.replace(dest)
        a.unlink(missing_ok=True)
        return dest
    except Exception as e:  # noqa: BLE001
        log.warning("prévia da vitrine com legenda falhou (%s); fica a base limpa", e)
        return None


def variacao(semente: str, livre: bool) -> dict:
    """Vitrine (`livre`=False): cada uso sai diferente. Corte próprio do cliente: sem variação."""
    if livre:
        return {"d_ini": 0.0, "d_fim": 0.0, "zoom": 1.0, "cor": (0.0, 1.0)}
    rnd = random.Random(int(hashlib.sha256(semente.encode()).hexdigest()[:12], 16))
    return {"d_ini": round(rnd.uniform(-2, 2), 2), "d_fim": round(rnd.uniform(-2, 2), 2), "zoom": round(rnd.uniform(1.0, 1.07), 3),
            "cor": (round(rnd.uniform(-0.03, 0.03), 3), round(rnd.uniform(0.95, 1.12), 3))}


def personalizado(s: dict, pasta_fonte: Path, corte: dict, perfil: dict, destino_pasta: Path, nome: str, cfg, var: dict) -> dict:
    """Versão do cliente: variação + legenda + gancho + @, uma por rede, cada uma num passe só de ffmpeg."""
    from app.motor.analise import palavras_do_trecho
    destino_pasta.mkdir(parents=True, exist_ok=True)
    arq, desloc = garantir_trecho(s, pasta_fonte, corte["inicio"], corte["fim"], cfg)
    ini = max(corte["inicio"] + var["d_ini"], desloc)
    fim = min(corte["fim"] + var["d_fim"], desloc + duracao(arq))
    from app.motor import traduz
    palavras = traduz.para_pt(palavras_corte(s, pasta_fonte, arq, desloc, ini, fim), s.get("lingua"), cfg, pasta_fonte)  # legenda sempre em PT
    redes = [r for r in ((perfil or {}).get("redes") or ["tiktok"]) if r in estilo.REDES] or ["tiktok"]
    # 1 vídeo só, com as margens da rede mais restritiva (TikTok cobre mais): serve para todas as redes e custa 1 encode
    margem = "tiktok" if "tiktok" in redes or len(redes) > 1 else redes[0]
    a = destino_pasta / f"{nome}.ass"
    a.write_text(estilo.ass(palavras, fim - ini, corte.get("gancho") or "", margem, (perfil or {}).get("arroba") or "",
                            (perfil or {}).get("cor") or estilo.COR_PADRAO, (perfil or {}).get("legenda", True)), encoding="utf-8")
    dest = destino_pasta / f"{nome}.mp4"
    try:
        _render(arq, ini - desloc, fim - desloc, dest, var["zoom"], tuple(var["cor"]), a, layout=corte.get("tipo") or "auto")
    finally:
        a.unlink(missing_ok=True)
    arquivos = {r: dest.name for r in redes}
    principal = destino_pasta / next(iter(arquivos.values()))
    capa = destino_pasta / f"{nome}.jpg"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "1.0", "-i", str(principal), "-frames:v", "1", "-q:v", "4", "-vf", "scale=360:-2", str(capa)],
                   check=False)
    return {"arquivos": arquivos, "arquivo": principal.name, "capa": capa.name if capa.exists() else None, "palavras": palavras,
            "duracao": round(fim - ini, 1), "inicio": round(ini, 2), "fim": round(fim, 2), "variacao": var}
