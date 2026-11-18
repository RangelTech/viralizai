"""Planos, limites e moedas (spec 47 §3). Preço >= 4x o custo, menos Vídeo com IA (repasse quase a custo)."""
from __future__ import annotations

PLANOS = {
    "corte": {"nome": "Corte", "preco": 29.90, "lancamento": 19.90, "cortes_mes": 30, "animacoes_mes": 0, "postar": False, "prioridade": 5,
              "itens": ["30 cortes por mês", "Editar meu vídeo", "Prontos pra postar"]},
    "animacao": {"nome": "Corte + Animação", "preco": 49.90, "cortes_mes": 100, "animacoes_mes": 30, "postar": False, "prioridade": 4,
                 "itens": ["100 cortes por mês", "30 animações por mês", "Editar meu vídeo", "Prontos pra postar"], "destaque": True},
    "viral": {"nome": "Viral", "preco": 79.90, "cortes_mes": 200, "animacoes_mes": 60, "postar": True, "prioridade": 3,
              "itens": ["Tudo do Corte + Animação", "200 cortes e 60 animações por mês", "Posta sozinho no TikTok e no Instagram"]},
    "piloto": {"nome": "Piloto Automático", "preco": 197.00, "cortes_mes": 600, "animacoes_mes": 120, "postar": True, "prioridade": 2,
               "itens": ["Tudo do Viral", "A IA acha os vídeos do seu tema", "1 post por dia em cada rede, sem repetir"]},
}
ADICIONAIS = {
    "cacador": {"nome": "Caçador", "preco": 29.90, "itens": ["A IA acha vídeos do seu tema sozinha"]},
    "vigia": {"nome": "Vigia ao Vivo", "preco": 49.90, "itens": ["Corta a live enquanto acontece (10 h por mês)"]},
}
PACOTES_MOEDAS = {
    "m5": {"moedas": 5, "preco": 9.90},
    "m15": {"moedas": 15, "preco": 24.90},
    "m35": {"moedas": 35, "preco": 49.90, "destaque": "melhor preço"},
}
TESTE = {"cortes": 1}  # teste grátis: 1 prévia de 1 corte (não baixa, não posta)
LIMITE_USOS_DIA = 20   # vitrine: cada corte base pode ser usado até 20x por dia (anti-duplicado)
QUANTOS = (1, 3, 5, 10)


def plano_ativo(u: dict, agora: float) -> str:
    return u["plano"] if u.get("ativo_ate", 0) > agora and u.get("plano") in PLANOS else "teste"


def limites(plano: str) -> dict:
    p = PLANOS.get(plano)
    if not p:
        return {"cortes_mes": TESTE["cortes"], "animacoes_mes": 0, "postar": False, "prioridade": 9}
    return {k: p[k] for k in ("cortes_mes", "animacoes_mes", "postar", "prioridade")}


def plano_minimo(recurso: str) -> str:
    """Primeiro plano que libera um recurso (para o paywall contextual)."""
    return {"animacao": "animacao", "postar": "viral", "cortes": "corte", "baixar": "corte", "piloto": "piloto"}.get(recurso, "corte")
