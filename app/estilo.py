"""Marca e redes: cada corte sai em uma versão por rede (TikTok, Instagram, YouTube Shorts), com legenda e gancho fora da área que a
interface de cada app cobre, o @ do cliente no vídeo e a cor da marca no gancho. O corte "limpo" (sem texto) fica guardado para editar.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

W, H = 720, 1280
FONTES = Path(__file__).resolve().parent.parent / "static" / "fonts"

# Áreas seguras (em pixels de 1280 de altura): o TikTok cobre mais embaixo e à direita (botões, nome, descrição).
REDES = {
    "tiktok": {"nome": "TikTok", "leg_mv": 430, "gancho_mv": 175, "marca_mv": 112, "margem_d": 150, "margem_e": 40},
    "instagram": {"nome": "Instagram", "leg_mv": 360, "gancho_mv": 165, "marca_mv": 104, "margem_d": 90, "margem_e": 40},
    "youtube": {"nome": "YouTube Shorts", "leg_mv": 380, "gancho_mv": 165, "marca_mv": 104, "margem_d": 110, "margem_e": 40},
}
COR_PADRAO = "#ff3d6e"


def cor_ass(hexa: str, alfa: str = "00") -> str:
    """#rrggbb -> &HAABBGGRR do ASS."""
    m = re.fullmatch(r"#?([0-9a-fA-F]{6})", hexa or "")
    h = (m.group(1) if m else COR_PADRAO[1:]).lower()
    return f"&H{alfa}{h[4:6]}{h[2:4]}{h[0:2]}".upper()


def tempo(t: float) -> str:
    t = max(0.0, t)
    hh, r = divmod(t, 3600)
    mm, ss = divmod(r, 60)
    return f"{int(hh)}:{int(mm):02d}:{ss:05.2f}"


def _txt(t: str) -> str:
    return t.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def ass(palavras_rel: list[dict], dur: float, gancho: str, rede: str, arroba: str = "", cor: str = COR_PADRAO, legenda: bool = True) -> str:
    """Legenda palavra a palavra (2-3 por vez), gancho nos 3 primeiros s e o @ do cliente, com as margens da rede."""
    r = REDES.get(rede) or REDES["instagram"]
    c = cor_ass(cor)
    cab = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Leg,Montserrat ExtraBold,58,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,5,2,2,{r['margem_e']},{r['margem_d']},{r['leg_mv']},1
Style: Gancho,Montserrat ExtraBold,54,&H00FFFFFF,&H00FFFFFF,{c},{c},1,0,0,0,100,100,0,0,3,14,0,8,{r['margem_e'] + 20},{r['margem_d']},{r['gancho_mv']},1
Style: Marca,Montserrat ExtraBold,28,&H30FFFFFF,&H30FFFFFF,&H90000000,&H00000000,1,0,0,0,100,100,0,0,1,2,0,8,{r['margem_e']},{r['margem_d']},{r['marca_mv']},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    linhas = []
    ms = int(dur * 1000)
    # barra de progresso fina no topo, na cor da marca (dá o "acabamento de motion" e segura a pessoa até o fim)
    linhas.append(f"Dialogue: 3,{tempo(0)},{tempo(dur)},Marca,,0,0,0,,{{\\an7\\pos(0,0)\\p1\\bord0\\shad0\\1c{c}\\1a&H00&\\fscx0\\t(0,{ms},\\fscx100)}}"
                  f"m 0 0 l {W} 0 {W} 7 0 7{{\\p0}}")
    if arroba:
        linhas.append(f"Dialogue: 2,{tempo(0)},{tempo(dur)},Marca,,0,0,0,,{_txt('@' + arroba.lstrip('@'))}")
    if gancho:
        # título grande em caixa o vídeo todo: entra com um "pulo" e fica
        anim = "{\\fad(160,0)\\fscx72\\fscy72\\t(0,200,\\fscx107\\fscy107)\\t(200,320,\\fscx100\\fscy100)}"
        linhas.append(f"Dialogue: 1,{tempo(0)},{tempo(dur)},Gancho,,0,0,0,,{anim}{_txt(gancho.upper())}")
    if legenda:
        destaque = "&H0000E6FF" if cor == COR_PADRAO else c  # amarelo clássico, ou a cor da marca do cliente
        dentro = [w for w in palavras_rel if w["end"] > 0 and w["start"] < dur and str(w["word"]).strip()]
        grupo: list[dict] = []
        ultimo_fim = 0.0
        dentro.sort(key=lambda w: w["start"])
        for k, w in enumerate(dentro):
            grupo.append(w)
            prox = dentro[k + 1] if k + 1 < len(dentro) else None
            if len(grupo) >= 3 or re.search(r"[.!?,;:]$", w["word"]) or not prox or prox["start"] - w["end"] > 0.6 or sum(len(x["word"]) for x in grupo) > 16:
                fim_grupo = prox["start"] if prox and prox["start"] - grupo[-1]["end"] < 0.6 else grupo[-1]["end"]
                pal = [re.sub(r"[.,;:]+$", "", str(x["word"]).strip().upper()) for x in grupo]
                # karaokê: uma linha por palavra falada, a palavra da vez em destaque e maior; o grupo entra com um pulo
                for j, x in enumerate(grupo):
                    a = max(0.0, x["start"] if j else grupo[0]["start"], ultimo_fim)
                    b = grupo[j + 1]["start"] if j + 1 < len(grupo) else fim_grupo
                    b = min(dur, max(b, a + 0.12))
                    ultimo_fim = b
                    partes = [(f"{{\\1c{destaque}\\fscx112\\fscy112}}{_txt(p)}{{\\r}}" if i == j else _txt(p)) for i, p in enumerate(pal)]
                    entrada = "{\\fscx88\\fscy88\\t(0,90,\\fscx100\\fscy100)}" if j == 0 else ""
                    linhas.append(f"Dialogue: 0,{tempo(a)},{tempo(b)},Leg,,0,0,0,,{entrada}{' '.join(partes)}")
                grupo = []
    return cab + "\n".join(linhas) + "\n"


def _filtro(ass_arq: Path) -> str:
    p = str(ass_arq).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    f = str(FONTES).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    return f"subtitles='{p}':fontsdir='{f}'"


def duracao(arq) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(arq)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def versoes(limpo: Path, palavras_rel: list[dict], gancho: str, pasta: Path, base: str, perfil: dict, legenda: bool = True) -> dict:
    """Gera uma versão por rede a partir do corte limpo. Devolve {rede: nome_do_arquivo}."""
    redes = [r for r in (perfil.get("redes") or ["instagram"]) if r in REDES] or ["instagram"]
    dur = duracao(limpo)
    out = {}
    for rede in redes:
        a = pasta / f"{base}_{rede}.ass"
        a.write_text(ass(palavras_rel, dur, gancho, rede, perfil.get("arroba") or "", perfil.get("cor") or COR_PADRAO, legenda), encoding="utf-8")
        dest = pasta / f"{base}_{rede}.mp4"
        r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(limpo), "-vf", _filtro(a), "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                            "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", "-threads", "4", str(dest)], capture_output=True, text=True)
        a.unlink(missing_ok=True)
        if r.returncode != 0:
            raise RuntimeError("ffmpeg versão: " + r.stderr[-300:])
        out[rede] = dest.name
    return out


def marca_simples(video: Path, pasta: Path, base: str, perfil: dict) -> dict:
    """Para animação e clone (texto já queimado): só põe o @ do cliente, uma versão por rede."""
    return versoes(video, [], "", pasta, base, perfil, legenda=False) if perfil.get("arroba") else {r: video.name for r in (perfil.get("redes") or ["instagram"])}
