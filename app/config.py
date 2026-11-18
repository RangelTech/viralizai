"""Configuração por variável de ambiente (segredos em /opt/platform/secrets/viralizai.env na VPS).
Prefixo VIRALIZAI_; aceita CORTAI_ como reserva durante a migração."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field


def _e(nome: str, padrao: str = "") -> str:
    for pref in ("VIRALIZAI_", "CORTAI_"):
        v = os.environ.get(pref + nome)
        if v is not None:
            return v
    return padrao


@dataclass
class Config:
    dados: str = "/data"
    base_url: str = "https://viralizai.rangeltech.net"
    llm_base: str = "https://qwen.rangeltech.net/v1"
    llm_key: str = ""
    llm_modelo: str = "qwen-abliterated"
    llm_planejador: str = "rt-planejar"
    llm_visao: str = "visao"
    validar: bool = False
    segredo_sessao: str = "dev"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_senha: str = ""
    smtp_from: str = "Viralizaí <contato@rangeltech.net>"
    cakto_segredo: str = ""
    checkout_mensal: str = ""
    max_duracao_s: int = 6 * 3600
    max_cortes: int = 10
    workers: int = 2
    guardar_dias: int = 30
    proxy: str = ""
    yt_cookies: str = "/data/yt_cookies.txt"
    dev: bool = False
    checkouts: dict = field(default_factory=dict)          # {"corte": url, "animacao": url, ..., "m5": url}
    planos_por_produto: dict = field(default_factory=dict)  # {"<id do produto Cakto>": "corte" | "m5" ...}
    lancamento_ate: str = "2026-12-31"
    admin_key: str = ""
    demo_email: str = ""
    demo_senha: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    estudio_base: str = "https://qwen.rangeltech.net/v1"    # llm-access (Vídeo com IA pela Runware)
    estudio_efeito: str = "video-viral"
    imagem_modelo: str = "cx/gpt-image-2"
    pexels_key: str = ""
    pixabay_key: str = ""
    atende_webhook: str = ""                                 # aviso no WhatsApp quando o vídeo fica pronto
    posta_base: str = "https://postaai.rangeltech.net"
    pn_url: str = "http://perfil-navegador:8000"   # perfil-navegador (rede interna): login e publicação nas redes
    pn_token: str = ""


def carregar() -> Config:
    return Config(
        dados=_e("DADOS", "/data"),
        base_url=_e("BASE_URL", "https://viralizai.rangeltech.net").rstrip("/"),
        llm_base=_e("LLM_BASE", "https://qwen.rangeltech.net/v1").rstrip("/"),
        llm_key=_e("LLM_KEY", ""),
        llm_modelo=_e("LLM_MODELO", "qwen-abliterated"),
        llm_planejador=_e("LLM_PLANEJADOR", "rt-planejar"),
        llm_visao=_e("LLM_VISAO", "visao"),
        validar=_e("VALIDAR", "0") == "1",
        segredo_sessao=_e("SEGREDO_SESSAO", "dev"),
        smtp_host=os.environ.get("SMTP_HOST", ""),
        smtp_port=int(os.environ.get("SMTP_PORT", "587") or 587),
        smtp_user=os.environ.get("SMTP_USER", ""),
        smtp_senha=os.environ.get("SMTP_PASSWORD", ""),
        smtp_from=_e("SMTP_FROM", "Viralizaí <contato@rangeltech.net>"),
        cakto_segredo=_e("CAKTO_SEGREDO", ""),
        max_duracao_s=int(_e("MAX_DURACAO_S", str(6 * 3600))),
        max_cortes=int(_e("MAX_CORTES", "10")),
        workers=int(_e("WORKERS", "2")),
        guardar_dias=int(_e("GUARDAR_DIAS", "30")),
        proxy=_e("PROXY", ""),
        yt_cookies=_e("YT_COOKIES", "/data/yt_cookies.txt"),
        dev=_e("DEV", "") == "1",
        checkouts=json.loads(_e("CHECKOUTS", "") or "{}"),
        planos_por_produto=json.loads(_e("PLANOS_CAKTO", "") or "{}"),
        lancamento_ate=_e("LANCAMENTO_ATE", "2026-12-31"),
        admin_key=_e("ADMIN_KEY", ""),
        demo_email=_e("DEMO_EMAIL", ""),
        demo_senha=_e("DEMO_SENHA", ""),
        google_client_id=_e("GOOGLE_CLIENT_ID", ""),
        google_client_secret=_e("GOOGLE_CLIENT_SECRET", ""),
        estudio_base=_e("ESTUDIO_BASE", _e("LLM_BASE", "https://qwen.rangeltech.net/v1")).rstrip("/"),
        estudio_efeito=_e("ESTUDIO_EFEITO", "video-viral"),
        pexels_key=_e("PEXELS_KEY", ""),
        pixabay_key=_e("PIXABAY_KEY", ""),
        atende_webhook=_e("ATENDE_WEBHOOK", ""),
        posta_base=_e("POSTA_BASE", "https://postaai.rangeltech.net").rstrip("/"),
        pn_url=_e("PN_URL", "http://perfil-navegador:8000").rstrip("/"),
        pn_token=_e("PN_TOKEN", ""),
    )
