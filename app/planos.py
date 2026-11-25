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
# Landing do Fael (conta Cakto do Adriano, ordem do Lucas 25/11): sem preço de lançamento, sem pacotes de vídeo
PRECOS_FAEL = {"corte": 29.90, "fael_animacao": 49.90, "piloto": 119.90}
# Landing do Fael (25/11): o 49,90 leva os limites do antigo Viral (200 cortes e 60 animações), mas NÃO posta sozinho;
# postar sozinho é do 119,90. Plano interno próprio para o limite valer de verdade (só aparece na landing do Fael).
PLANOS["fael_animacao"] = {"nome": "Corte + Animação", "preco": 49.90, "cortes_mes": 200, "animacoes_mes": 60, "postar": False, "prioridade": 3,
                           "itens": ["200 cortes por mês", "60 animações por mês", "Editar meu vídeo", "Prontos pra postar"],
                           "destaque": True, "so_fael": True}
# o que a landing do Fael mostra, nesta ordem: (código, checkout em CHECKOUTS_FAEL, troca de textos)
LISTA_FAEL = [
    ("corte", "corte", {}),
    ("fael_animacao", "animacao", {}),
    ("piloto", "piloto", {"itens": ["Tudo do Corte + Animação", "Posta sozinho no TikTok e no Instagram",
                                    "A IA acha os vídeos do seu tema", "1 post por dia em cada rede, sem repetir"]}),
]

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
