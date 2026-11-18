"""Sinais de áudio (47c S4): energia por segundo e eventos sonoros (YAMNet, CPU) num passe só, lendo o áudio em
streaming do ffmpeg (live de 4 h não entra inteira na memória). Também acha silêncios para as bordas dos cortes.
"""
from __future__ import annotations

import csv
import logging
import subprocess
from pathlib import Path

import numpy as np

log = logging.getLogger("viralizai.audio")
SR = 16000
MODELOS = Path(__file__).resolve().parent / "modelos"

# grupo -> nomes de classe do AudioSet (yamnet_class_map.csv)
GRUPOS = {
    "risada": ["Laughter", "Giggle", "Belly laugh", "Chuckle, chortle", "Baby laughter", "Snicker"],
    "grito": ["Screaming", "Shout", "Yell", "Battle cry", "Children shouting", "Whoop"],
    "tiro": ["Gunshot, gunfire", "Machine gun", "Fusillade", "Artillery fire", "Cap gun"],
    "explosao": ["Explosion", "Boom", "Burst, pop", "Eruption"],
    "sirene": ["Siren", "Police car (siren)", "Ambulance (siren)", "Fire engine, fire truck (siren)", "Civil defense siren"],
    "batida": ["Skidding", "Tire squeal", "Smash, crash", "Vehicle horn, car horn, honking", "Car alarm", "Glass", "Shatter"],
    "torcida": ["Cheering", "Applause", "Crowd", "Clapping"],
    "musica": ["Music"],
    "fala": ["Speech", "Conversation", "Narration, monologue"],
}


def baixar_audio(url: str, pasta: Path, cfg) -> Path:
    """Só o áudio, na menor taxa (uma live de 4 h dá ~30 a 90 MB)."""
    import yt_dlp
    from app.motor.fonte import _opcoes
    o = {**_opcoes(cfg, pasta), "format": "worstaudio[abr>=40]/worstaudio/bestaudio", "outtmpl": str(pasta / "audio.%(ext)s")}
    with yt_dlp.YoutubeDL(o) as y:
        y.download([url])
    arq = next((p for p in pasta.glob("audio.*") if p.suffix not in (".part", ".ytdl")), None)
    if not arq:
        raise RuntimeError("audio nao baixou")
    return arq


class _Yamnet:
    def __init__(self):
        from ai_edge_litert.interpreter import Interpreter
        self.i = Interpreter(str(MODELOS / "yamnet.tflite"), num_threads=2)
        self.i.allocate_tensors()
        self.ent = self.i.get_input_details()[0]["index"]
        self.sai = self.i.get_output_details()[0]["index"]
        nomes = [r["display_name"] for r in csv.DictReader(open(MODELOS / "yamnet_class_map.csv", encoding="utf-8"))]
        self.idx = {g: [nomes.index(n) for n in ns if n in nomes] for g, ns in GRUPOS.items()}

    def __call__(self, x: np.ndarray) -> dict:
        self.i.set_tensor(self.ent, x[:15600].astype(np.float32))
        self.i.invoke()
        s = self.i.get_tensor(self.sai)[0]
        return {g: float(s[ix].max()) if ix else 0.0 for g, ix in self.idx.items()}


def analisar(arquivo: Path, eventos: bool = True, inicio: float = 0.0, fim: float | None = None) -> dict:
    """Por segundo: db (RMS em dB) e, com YAMNet, a nota de cada grupo de evento (0..1).
    Devolve {"db": [...], "eventos": {grupo: [...]}, "silencios": [(a, b), ...]}"""
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{inicio:.2f}"]
    if fim:
        cmd += ["-to", f"{fim:.2f}"]
    cmd += ["-i", str(arquivo), "-vn", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    yam = None
    if eventos:
        try:
            yam = _Yamnet()
        except Exception as e:  # noqa: BLE001  sem o modelo fica só a energia
            log.warning("yamnet indisponivel: %s", e)
    db: list[float] = []
    ev: dict[str, list[float]] = {g: [] for g in GRUPOS} if yam else {}
    silencios, sil_ini = [], None
    try:
        while True:
            b = p.stdout.read(SR * 4)
            if not b:
                break
            x = np.frombuffer(b, dtype=np.float32)
            rms = float(np.sqrt(np.mean(x * x)) + 1e-9)
            d = 20 * np.log10(rms)
            t = len(db)
            db.append(round(d, 2))
            # silêncio: quartos de segundo abaixo de -45 dB, guardado com resolução de 0,25 s
            for q in range(4):
                parte = x[q * SR // 4:(q + 1) * SR // 4]
                if not len(parte):
                    continue
                mudo = 20 * np.log10(float(np.sqrt(np.mean(parte * parte)) + 1e-9)) < -45
                tq = inicio + t + q / 4
                if mudo and sil_ini is None:
                    sil_ini = tq
                elif not mudo and sil_ini is not None:
                    if tq - sil_ini >= 0.25:
                        silencios.append((round(sil_ini, 2), round(tq, 2)))
                    sil_ini = None
            if yam:
                if len(x) < 15600:
                    x = np.pad(x, (0, 15600 - len(x)))
                for g, v in yam(x).items():
                    ev[g].append(round(v, 3))
    finally:
        p.stdout.close()
        p.wait()
    return {"db": db, "eventos": ev, "silencios": silencios, "inicio": inicio}
