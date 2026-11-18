"""Transcrição em CPU (faster-whisper int8), SÓ nas janelas candidatas (decisão do Lucas, 18/11: sem GPU no projeto).
Usada quando não há legenda (Twitch, Kick, upload, YouTube sem legenda automática). Uma live de 4 h vira ~20 a 30 min
de áudio para transcrever. Cada janela é independente: uma que falhe não derruba as outras."""
from __future__ import annotations

import logging
import os
import subprocess
import threading
from pathlib import Path

import numpy as np

log = logging.getLogger("viralizai.whisper")
_modelo = None
_trava = threading.Lock()
MODELO = os.environ.get("VIRALIZAI_WHISPER", "small")


def _carregar():
    global _modelo
    with _trava:
        if _modelo is None:
            from faster_whisper import WhisperModel
            raiz = os.environ.get("VIRALIZAI_MODELOS", str(Path(os.environ.get("VIRALIZAI_DADOS", "/data")) / "modelos"))
            _modelo = WhisperModel(MODELO, device="cpu", compute_type="int8", cpu_threads=int(os.environ.get("VIRALIZAI_WHISPER_THREADS", "4")),
                                   download_root=raiz)
    return _modelo


def juntar_janelas(janelas: list[tuple[float, float]], folga: float = 3.0) -> list[tuple[float, float]]:
    out: list[list[float]] = []
    for a, b in sorted(janelas):
        if out and a <= out[-1][1] + folga:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def _pcm(arquivo: Path, a: float, b: float) -> np.ndarray:
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{a:.2f}", "-to", f"{b:.2f}", "-i", str(arquivo), "-vn", "-ac", "1", "-ar", "16000",
                        "-f", "f32le", "-"], capture_output=True)
    return np.frombuffer(r.stdout, dtype=np.float32)


def transcrever(arquivo: Path, janelas: list[tuple[float, float]], lingua: str | None = "pt") -> list[dict]:
    """-> palavras [{start, end, word}] com tempo ABSOLUTO no vídeo."""
    m = _carregar()
    palavras: list[dict] = []
    for a, b in juntar_janelas(janelas):
        try:
            x = _pcm(arquivo, a, b)
            if len(x) < 16000:
                continue
            segs, _ = m.transcribe(x, language=lingua, word_timestamps=True, vad_filter=True, beam_size=1,
                                   condition_on_previous_text=False)
            for s in segs:
                for w in s.words or []:
                    t = w.word.strip()
                    if t:
                        palavras.append({"start": round(a + w.start, 2), "end": round(a + w.end, 2), "word": t})
        except Exception as e:  # noqa: BLE001
            log.warning("whisper janela %.0f-%.0f falhou: %s", a, b, e)
    return sorted(palavras, key=lambda w: w["start"])
