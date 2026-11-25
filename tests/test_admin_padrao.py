"""Admin padrão (spec 57 §5.1): o /admin do produto lista usuários, troca plano, dá dias e apaga; o usuário de QA não
some. Arquivo igual em todos os produtos (fonte: produtos-core/modelos/test_admin_padrao.py)."""
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import admin
from app.db import Banco


def _novo(db, email):
    db.exec("INSERT INTO usuarios(email, criado) VALUES(?, ?)", (email, time.time()))
    return db.um("SELECT id FROM usuarios WHERE email=?", (email,))["id"]


def test_admin_aba_usuarios(tmp_path):
    db = Banco(str(tmp_path / "admin.db"))
    try:
        admin.preparar(db)
        app = FastAPI()
        app.include_router(admin.rotas(db, "s", "SELECT email, criado, 0 ativo FROM usuarios", usuario="lucas", senha="segredo", seguro=False))
        a = TestClient(app)
        uid = _novo(db, "cliente@teste.com")
        qa = _novo(db, "demo@rangeltech.net")

        assert a.get("/api/painel/usuarios").status_code == 401
        assert a.post("/api/painel/entrar", json={"usuario": "lucas", "senha": "segredo"}).status_code == 200

        j = a.get("/api/painel/usuarios?q=cliente").json()
        assert j["total"] == 1 and j["usuarios"][0]["email"] == "cliente@teste.com" and not j["usuarios"][0]["ativo"]

        r = a.put(f"/api/painel/usuarios/{uid}", json={"plano": "pro", "dias": 30})
        assert r.status_code == 200
        u = a.get("/api/painel/usuarios?q=cliente").json()["usuarios"][0]
        assert u["plano"] == "pro" and u["ativo"] and u["ativo_ate"] > time.time() + 29 * 86400
        assert a.put(f"/api/painel/usuarios/{uid}", json={"plano": "x y;"}).status_code == 422

        assert a.delete(f"/api/painel/usuarios/{qa}").status_code == 409
        assert a.delete(f"/api/painel/usuarios/{uid}").json()["ok"]
        assert a.get("/api/painel/usuarios").json()["total"] == 1
        assert [s["email"] for s in a.get("/api/painel/usuarios").json()["usuarios"]] == ["demo@rangeltech.net"]
    finally:
        if hasattr(db, "schema") and str(db.schema).startswith("teste_"):
            db.exec(f'DROP SCHEMA "{db.schema}" CASCADE')
