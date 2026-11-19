"""Animação v3 (desenho programado): plano normalizado, gerador determinístico válido, validador pega erro."""
import shutil

import pytest

from app import cinema

PLANO = {"titulo": "Teste", "gancho": "SUSTO", "legenda": "x", "hashtags": ["terror", "#medo"], "formato": "desenho",
         "cenas": [
             {"fala": "Três da manhã, a porta abriu.", "cenario": "quarto_noite", "opcoes": {"armario": 0.8}, "camera": "empurra",
              "atores": [{"quem": "heroi", "acao": "deitado", "humor": "medo"}], "objetos": ["relogio"], "efeitos": ["vinheta"], "som": "riser"},
             {"fala": "Ele pegou a lanterna.", "cenario": "CASTELO_INEXISTENTE", "camera": "voar",
              "atores": [{"quem": "dragao", "acao": "voar", "humor": "x", "segura": "lanterna", "de_onde": "direita", "para_onde": "esquerda"}],
              "objetos": ["porta", "foguete"], "efeitos": ["chuva", "laser"], "transicao": "fade"},
         ]}


def test_plano_normalizado_para_o_kit():
    p = cinema.validar_plano(PLANO)
    c = p["cenas"][1]
    assert c["cenario"] == "palco" and c["camera"] == "empurra"
    assert c["atores"][0]["quem"] == "heroi" and c["atores"][0]["acao"] == "parado" and c["atores"][0]["segura"] == "lanterna"
    assert c["objetos"] == ["porta"] and c["efeitos"] == ["chuva"]
    assert p["hashtags"] == ["#terror", "#medo"]
    assert cinema.validar_plano(p) == p  # idempotente


@pytest.mark.skipif(not shutil.which("node"), reason="sem node")
def test_gerador_deterministico_passa_no_validador(tmp_path):
    p = cinema.validar_plano(PLANO)
    cod = cinema.shots_deterministico(p, [(0.0, 3.0), (3.0, 6.5)])
    v = cinema.validar_codigo(cod, tmp_path)
    assert v["ok"], v
    assert v["planos"] == 2 and abs(v["dur"] - 6.5) < 1e-6


@pytest.mark.skipif(not shutil.which("node"), reason="sem node")
def test_validador_pega_erro_de_codigo(tmp_path):
    ruim = "const SHOTS = []; SHOTS.push({ start: 0, end: 2, tr: 'cut', draw(ctx, lt, t, dur) { funcaoQueNaoExiste(ctx); } });"
    v = cinema.validar_codigo(ruim, tmp_path)
    assert not v["ok"] and "funcaoQueNaoExiste" in " ".join(v["erros"])


def test_ajusta_tempos_exatos():
    cod = "SHOTS.push({ start: 0, end: 3.1, tr:'cut' }); SHOTS.push({ start: 3.1, end: 7, tr:'cut' });"
    out = cinema._ajusta_tempos(cod, [(0.0, 3.25), (3.25, 7.4)])
    assert "start: 0.00, end: 3.25" in out and "start: 3.25, end: 7.40" in out
