"""Baixa SÓ o trecho de um vídeo do YouTube (47c §5: "baixar pouco").

O caminho comum (`--download-sections`/ffmpeg com -ss na URL) lê o stream picado e o YouTube entrega em ~2x o tempo real:
um corte de 90 s levava ~60 s. Aqui lemos o índice do DASH (caixa `sidx` do MP4 fragmentado), calculamos os bytes dos
fragmentos que cobrem o trecho e baixamos esses bytes em pedaços paralelos pelo próprio yt-dlp (mesmos cabeçalhos,
cookies, proxy e PO token). Init + fragmentos = MP4 tocável; o ffmpeg junta vídeo e áudio sem reencodar.
Se algo falhar (formato sem sidx, WebM...), cai no download de seção do yt-dlp.
"""
from __future__ import annotations

import logging
import struct
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

log = logging.getLogger("viralizai.trecho")
FORMATO = "bv*[height<=720][vcodec^=avc1][protocol=https]+ba[ext=m4a][protocol=https]/bv*[height<=720][protocol=https]+ba[protocol=https]"
PEDACO = 2 * 1024 * 1024


def _ler(y, url: str, a: int, b: int, headers: dict) -> bytes:
    from yt_dlp.networking import Request
    sep = "&" if "?" in url else "?"
    with y.urlopen(Request(f"{url}{sep}range={a}-{b}", headers=headers)) as r:
        return r.read()


def _caixas(buf: bytes, ini: int = 0):
    i = ini
    while i + 8 <= len(buf):
        tam, tipo = struct.unpack(">I4s", buf[i:i + 8])
        cab = 8
        if tam == 1:
            tam = struct.unpack(">Q", buf[i + 8:i + 16])[0]
            cab = 16
        if tam < 8:
            break
        yield tipo.decode("latin-1"), i, tam, cab
        i += tam


def _sidx(buf: bytes, pos: int, cab: int) -> tuple[int, list[tuple[int, int, float, float]]]:
    """-> (escala, [(byte_ini, byte_fim, t_ini, t_fim)])"""
    p = pos + cab
    versao = buf[p]
    p += 4 + 4  # versão/flags + reference_ID
    escala = struct.unpack(">I", buf[p:p + 4])[0]; p += 4
    if versao == 0:
        t0, first = struct.unpack(">II", buf[p:p + 8]); p += 8
    else:
        t0, first = struct.unpack(">QQ", buf[p:p + 16]); p += 16
    p += 2
    n = struct.unpack(">H", buf[p:p + 2])[0]; p += 2
    off = pos + struct.unpack(">I", buf[pos:pos + 4])[0] + first  # primeiro byte depois do sidx
    t = t0
    refs = []
    for _ in range(n):
        r, dur, _sap = struct.unpack(">III", buf[p:p + 12]); p += 12
        tam = r & 0x7FFFFFFF
        refs.append((off, off + tam - 1, t / escala, (t + dur) / escala))
        off += tam
        t += dur
    return escala, refs


def _baixar_formato(y, fmt: dict, ini: float, fim: float, destino: Path) -> float:
    """Init + fragmentos que cobrem [ini, fim]. Devolve o tempo (s) em que o arquivo começa."""
    url, hdr = fmt["url"], fmt.get("http_headers") or {}
    cabeca = _ler(y, url, 0, 256 * 1024 - 1, hdr)
    sidx = next(((p, c) for t, p, _, c in _caixas(cabeca) if t == "sidx"), None)
    if not sidx:
        raise RuntimeError("sem sidx")
    _, refs = _sidx(cabeca, *sidx)
    init_fim = sidx[0]  # ftyp + moov vão até o começo do sidx
    usados = [r for r in refs if r[3] > ini and r[2] < fim]
    if not usados:
        raise RuntimeError("trecho fora do índice")
    a, b = usados[0][0], usados[-1][1]
    partes = [(x, min(b, x + PEDACO - 1)) for x in range(a, b + 1, PEDACO)]
    with ThreadPoolExecutor(6) as ex:
        dados = list(ex.map(lambda ab: _ler(y, url, ab[0], ab[1], hdr), partes))
    with open(destino, "wb") as f:
        f.write(cabeca[:init_fim])
        for d in dados:
            f.write(d)
    return usados[0][2]


def baixar(url: str, ini: float, fim: float, destino: Path, cfg, margem: float = 3.0) -> dict:
    """Arquivo MP4 com o trecho [ini-margem, fim+margem]. Devolve {"arquivo", "desloc"}: desloc = tempo do vídeo original
    no segundo 0 do arquivo (para converter os tempos do corte)."""
    import yt_dlp
    from app.motor.fonte import _opcoes
    destino.parent.mkdir(parents=True, exist_ok=True)
    a, b = max(0.0, ini - margem), fim + margem
    o = {**_opcoes(cfg), "format": FORMATO}
    try:
        with yt_dlp.YoutubeDL(o) as y:
            i = y.extract_info(url, download=False)
            fmts = i.get("requested_formats") or [i]
            if len(fmts) != 2:
                raise RuntimeError("sem DASH separado")
            import time
            espera = max(float(f.get("available_at") or 0) for f in fmts) - time.time()
            if espera > 0:  # URLs do cliente TV só valem alguns segundos depois de emitidas
                time.sleep(min(espera + 0.5, 30))
            v, au = destino.with_suffix(".v.mp4"), destino.with_suffix(".a.m4a")
            with ThreadPoolExecutor(2) as ex:
                fv = ex.submit(_baixar_formato, y, fmts[0], a, b, v)
                fa = ex.submit(_baixar_formato, y, fmts[1], a, b, au)
                tv, ta = fv.result(), fa.result()
        # o vídeo manda no tempo; o áudio começa onde começou o fragmento dele
        r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(v), "-itsoffset", f"{ta - tv:.3f}", "-i", str(au),
                            "-map", "0:v", "-map", "1:a", "-c", "copy", "-movflags", "+faststart", str(destino)], capture_output=True, text=True)
        v.unlink(missing_ok=True); au.unlink(missing_ok=True)
        if r.returncode != 0:
            raise RuntimeError("ffmpeg junta: " + r.stderr[-200:])
        inicio = _inicio_real(destino)  # fMP4 guarda o tempo original (tfdt); o ffmpeg pode ou não zerar
        return {"arquivo": destino, "desloc": tv - inicio if inicio < 1 else 0.0, "metodo": "sidx"}
    except Exception as e:  # noqa: BLE001
        log.warning("trecho por sidx falhou (%s); usando seção do yt-dlp", str(e)[:200])
    from yt_dlp.utils import download_range_func
    o = {**_opcoes(cfg), "format": FORMATO.replace("[protocol=https]", "") + "/b[height<=720]", "outtmpl": str(destino.with_suffix(".%(ext)s")),
         "merge_output_format": "mp4", "download_ranges": download_range_func(None, [(a, b)]), "force_keyframes_at_cuts": False}
    with yt_dlp.YoutubeDL(o) as y:
        y.download([url])
    return {"arquivo": destino, "desloc": a, "metodo": "secao"}


def _inicio_real(arq: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=start_time", "-of", "csv=p=0", str(arq)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0
