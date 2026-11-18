"""Avisos: sino no app, e-mail e (se o cliente deu o número) WhatsApp pelo Atende AI."""
from __future__ import annotations

import json
import logging
import threading

import httpx

from app import mailer
from app.db import Banco, agora

log = logging.getLogger("viralizai.avisos")


def novo(db: Banco, usuario: int, texto: str, link: str = "") -> None:
    db.exec("INSERT INTO avisos(usuario,texto,link,quando) VALUES(?,?,?,?)", (usuario, texto[:200], link, agora()))


def pronto(db: Banco, cfg, t: dict, n: int, titulo: str) -> None:
    tipo = t["tipo"]
    if tipo in ("cortes", "vitrine"):
        texto = f"Seus {n} cortes de {titulo[:60]} ficaram prontos 🔥" if n > 1 else f"Seu corte de {titulo[:60]} ficou pronto 🔥"
    elif tipo == "animacao":
        texto = "Sua animação ficou pronta ✨"
    elif tipo == "video_ia":
        texto = "Seu vídeo com IA ficou pronto 🤖"
    else:
        texto = "Seu vídeo editado ficou pronto 🎬"
    link = f"/app#/pedido/{t['id']}"
    novo(db, t["usuario"], texto, link)
    u = db.um("SELECT email, whatsapp, estilo FROM usuarios WHERE id=?", (t["usuario"],))
    if not u:
        return

    def mandar():
        try:
            mailer.pronto(cfg, u["email"], n, titulo[:80], "animacao" if tipo == "animacao" else "cortes")
        except Exception:  # noqa: BLE001
            log.exception("email pronto")
        quer_zap = (json.loads(u.get("estilo") or "{}") or {}).get("avisar_whatsapp", True)
        if cfg.atende_webhook and u.get("whatsapp") and quer_zap:
            try:
                httpx.post(cfg.atende_webhook, json={"telefone": u["whatsapp"], "texto": f"{texto}\n{cfg.base_url}{link}", "produto": "viralizai"}, timeout=15)
            except Exception:  # noqa: BLE001
                log.exception("whatsapp pronto")
    threading.Thread(target=mandar, daemon=True).start()
