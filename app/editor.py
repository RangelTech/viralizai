"""Editar meu vídeo (spec 47b §5.9, versão de lançamento): sobe um vídeo (ou usa um pronto) e sai com a cara do cliente:
legenda automática (Whisper em CPU), gancho no topo, @, velocidade, formato 9:16, e "esticar pra 1 min" (repete com
'parte 2' até passar de 61 s, para entrar na monetização do TikTok)."""
from __future__ import annotations

import secrets
import subprocess
from pathlib import Path

from fastapi import HTTPException

from app import estilo
from app.pipeline import duracao

EXT = (".mp4", ".mov", ".webm", ".mkv", ".m4v")


async def receber(request, pasta: Path, uid: int) -> Path:
    nome = request.headers.get("x-arquivo") or "video.mp4"
    ext = ("." + nome.rsplit(".", 1)[-1].lower()) if "." in nome else ".mp4"
    if ext not in EXT:
        raise HTTPException(422, "Manda um vídeo MP4, MOV ou WEBM.")
    pasta.mkdir(parents=True, exist_ok=True)
    dest = pasta / f"ed_{uid}_{secrets.token_hex(6)}{ext}"
    total = 0
    with open(dest, "wb") as f:
        async for parte in request.stream():
            total += len(parte)
            if total > 1024**3:
                f.close(); dest.unlink(missing_ok=True)
                raise HTTPException(413, "O vídeo passa de 1 GB.")
            f.write(parte)
    if total < 10_000 or duracao(dest) <= 0:
        dest.unlink(missing_ok=True)
        raise HTTPException(422, "Não consegui ler esse vídeo; exporta em MP4 e tenta de novo.")
    if duracao(dest) > 15 * 60:
        dest.unlink(missing_ok=True)
        raise HTTPException(422, "Pra editar, o vídeo pode ter até 15 minutos. Pra lives, usa o Cortar live.")
    return dest


def arquivo_do_pedido(pasta: Path, res: dict, k: int) -> Path:
    c = next((x for x in res.get("cortes", []) if x.get("k") == k and x.get("estado") == "pronto"), None)
    if not c or not (pasta / c["arquivo"]).exists():
        raise HTTPException(404, "Vídeo não encontrado.")
    return pasta / c["arquivo"]


def opcoes(q: dict) -> dict:
    vel = q.get("velocidade") or "1"
    return {"gancho": str(q.get("gancho") or "")[:60], "legenda": q.get("legenda", "1") == "1", "esticar": q.get("esticar") == "1",
            "velocidade": float(vel) if vel in ("0.5", "0.75", "1", "1.25", "1.5", "2") else 1.0, "aparar_inicio": float(q.get("aparar_inicio") or 0),
            "aparar_fim": float(q.get("aparar_fim") or 0)}


def fazer(entrada: dict, pasta: Path, cfg, avisar) -> dict:
    pasta.mkdir(parents=True, exist_ok=True)
    o = entrada["opcoes"]
    src = Path(entrada["arquivo"])
    dur = duracao(src)
    a, z = max(0.0, o["aparar_inicio"]), max(0.0, o["aparar_fim"])
    if dur - a - z < 3:
        from app.fila import ErroUsuario
        raise ErroUsuario("O vídeo ficaria curto demais.")
    palavras = []
    if o["legenda"]:
        avisar("Escrevendo a legenda", 0.2)
        from app.motor import whisper_cpu
        palavras = [{**w, "start": w["start"] - a, "end": w["end"] - a} for w in whisper_cpu.transcrever(src, [(a, dur - z)])]
    base = pasta / "ed_base.mp4"
    vel = o["velocidade"]
    filtros_v = f"scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,setpts=PTS/{vel}"
    filtros_a = _atempo(vel)
    avisar("Montando", 0.5)
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{a:.2f}", "-to", f"{dur - z:.2f}", "-i", str(src), "-vf", filtros_v, "-af", filtros_a,
                        "-c:v", "libx264", "-preset", "superfast", "-crf", "23", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", str(base)], capture_output=True, text=True)
    if r.returncode != 0:
        r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{a:.2f}", "-to", f"{dur - z:.2f}", "-i", str(src), "-vf", filtros_v, "-an",
                            "-c:v", "libx264", "-preset", "superfast", "-crf", "23", "-pix_fmt", "yuv420p", str(base)], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError("editor: " + r.stderr[-300:])
    palavras = [{**w, "start": w["start"] / vel, "end": w["end"] / vel} for w in palavras]
    if o["esticar"] and duracao(base) < 61:  # repete com "PARTE 2" até passar de 61 s
        d = duracao(base)
        vezes = int(61 // d) + 1
        lista = pasta / "lista.txt"
        lista.write_text("".join(f"file '{base.name}'\n" for _ in range(vezes)), encoding="utf-8")
        longo = pasta / "ed_longo.mp4"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lista), "-c", "copy", str(longo)], check=True)
        lista.unlink(missing_ok=True)
        palavras = [{**w, "start": w["start"] + k * d, "end": w["end"] + k * d} for k in range(vezes) for w in palavras]
        base.unlink(missing_ok=True)
        longo.rename(base)
    perfil = entrada.get("perfil") or {}
    avisar("Colocando sua cara no vídeo", 0.8)
    ass = pasta / "ed.ass"
    ass.write_text(estilo.ass(palavras, duracao(base), o["gancho"], "tiktok", perfil.get("arroba") or "", perfil.get("cor") or estilo.COR_PADRAO, o["legenda"]),
                   encoding="utf-8")
    final = pasta / "editado.mp4"
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(base), "-vf", estilo._filtro(ass), "-c:v", "libx264", "-preset", "superfast", "-crf", "23",
                        "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", str(final)], capture_output=True, text=True)
    ass.unlink(missing_ok=True)
    if r.returncode != 0:
        raise RuntimeError("editor final: " + r.stderr[-300:])
    base.unlink(missing_ok=True)
    capa = pasta / "editado.jpg"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "1", "-i", str(final), "-frames:v", "1", "-vf", "scale=360:-2", str(capa)], check=False)
    if src.parent.name == "uploads":
        src.unlink(missing_ok=True)
    return {"titulo": o["gancho"] or "Vídeo editado", "cortes": [{"k": 1, "estado": "pronto", "arquivo": final.name, "arquivos": {"tiktok": final.name},
            "capa": capa.name if capa.exists() else None, "titulo": o["gancho"] or "Vídeo editado", "gancho": o["gancho"], "duracao": round(duracao(final), 1),
            "legenda": "", "hashtags": []}]}


def _atempo(v: float) -> str:
    partes, x = [], v
    while x > 2.0:
        partes.append("atempo=2.0"); x /= 2
    while x < 0.5:
        partes.append("atempo=0.5"); x /= 0.5
    partes.append(f"atempo={x:.3f}")
    return ",".join(partes)
