"""Checkout transparente (ordem do Lucas 25/11): pagamento na nossa página pela API da Cakto do Adriano. A Cakto é simulada."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app import pagamento

CPF = "529.982.247-25"  # CPF válido de exemplo


class FakeCakto:
    def __init__(self):
        self.pagamentos, self.status = [], "waiting_payment"

    def handler(self, req: httpx.Request) -> httpx.Response:
        p = req.url.path
        if p == "/public_api/token/":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 36000})
        assert req.headers.get("authorization") == "Bearer tok"
        if p == "/public_api/payments/" and req.method == "POST":
            assert req.headers.get("x-idempotency-key")
            corpo = json.loads(req.content)
            self.pagamentos.append(corpo)
            if corpo["paymentMethod"] == "pix":
                return httpx.Response(201, json={"id": "11111111-2222-3333-4444-555555555555", "status": "waiting_payment", "paymentMethod": "pix",
                                                 "amount": "29.90", "pix": {"qrCode": "00020126PIXCOPIAECOLA", "expirationDate": "2026-11-25 22:00:00+00:00"}})
            return httpx.Response(201, json={"id": "aaaaaaaa-2222-3333-4444-555555555555", "status": "paid", "paymentMethod": "credit_card", "amount": "29.90"})
        if p.startswith("/public_api/orders/"):
            return httpx.Response(200, json={"id": p.split("/")[-2], "status": self.status})
        return httpx.Response(404, json={})


@pytest.fixture
def ck(tmp_path):
    from app.config import Config
    from app.main import criar_app
    fake = FakeCakto()
    cfg = Config(dados=str(tmp_path), dev=True, cakto_fael_client_id="cid-adriano", cakto_fael_client_secret="sec",
                 checkouts_fael={"corte": "https://pay.cakto.com.br/3fbsha4", "animacao": "https://pay.cakto.com.br/93ikpik",
                                 "piloto": "https://pay.cakto.com.br/coma89m"})
    cfg.cakto_transport = httpx.MockTransport(fake.handler)
    return TestClient(criar_app(cfg, iniciar_fila=False)), fake


def cliente(**k):
    return {"nome": "Ana Souza", "email": "ana@exemplo.com", "whatsapp": "(62) 99999-9999", "cpf": CPF, **k}


def test_landing_do_fael_abre_o_nosso_checkout(ck):
    c, _ = ck
    pl = c.get("/api/planos", headers={"host": "viralizai.fael.rangeltech.net"}).json()["planos"]
    assert [p["checkout"] for p in pl] == ["/checkout/corte", "/checkout/fael_animacao", "/checkout/piloto"]
    assert c.get("/checkout/corte").status_code == 200 and c.get("/checkout/viral").status_code == 404
    d = c.get("/api/checkout/piloto").json()
    assert d["plano"]["preco"] == 119.90 and d["sdk_client_id"] == "cid-adriano" and d["ativo"]


def test_pix_mostra_qr_e_copia_e_cola_e_acompanha_o_status(ck):
    c, fake = ck
    r = c.post("/api/checkout/corte/pagar", json={"metodo": "pix", "cliente": cliente(), "fingerprint": "fp-abcdef123"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["pix"]["copia_e_cola"] == "00020126PIXCOPIAECOLA" and j["pix"]["qr_svg"].startswith("<svg")
    corpo = fake.pagamentos[-1]
    assert corpo["items"] == [{"offerId": "3fbsha4", "quantity": 1}] and corpo["customer"]["phone"] == "5562999999999"
    assert corpo["customer"]["docNumber"] == "52998224725" and corpo["customer"]["fingerprint"] == "fp-abcdef123"
    assert c.get(f"/api/checkout/status/{j['id']}").json() == {"status": "waiting_payment", "pago": False, "recusado": False}
    fake.status = "paid"
    assert c.get(f"/api/checkout/status/{j['id']}").json()["pago"] is True


def test_cartao_vai_com_token_e_antifraude_sem_numero_do_cartao(ck):
    c, fake = ck
    assert c.post("/api/checkout/piloto/pagar", json={"metodo": "credit_card", "cliente": cliente(), "fingerprint": "fp-abcdef123"}).status_code == 400
    r = c.post("/api/checkout/piloto/pagar", json={"metodo": "credit_card", "cliente": cliente(), "fingerprint": "fp-abcdef123",
                                                   "card_token": "ctk_1", "antifraude": "ref-1"})
    assert r.json()["status"] == "paid"
    corpo = fake.pagamentos[-1]
    assert corpo["card"] == {"token": "ctk_1"} and corpo["antifraud_profiling_attempt_reference"] == "ref-1" and corpo["items"][0]["offerId"] == "coma89m"
    assert "cardNumber" not in json.dumps(corpo) and "cvv" not in json.dumps(corpo)


def test_validacoes_e_limite_de_tentativas(ck):
    c, fake = ck
    assert "CPF" in c.post("/api/checkout/corte/pagar", json={"metodo": "pix", "cliente": cliente(cpf="111.111.111-11"), "fingerprint": "fp-abcdef123"}).json()["detail"]
    assert "nome" in c.post("/api/checkout/corte/pagar", json={"metodo": "pix", "cliente": cliente(nome="Ana"), "fingerprint": "fp-abcdef123"}).json()["detail"]
    for _ in range(6):
        c.post("/api/checkout/corte/pagar", json={"metodo": "pix", "cliente": cliente(), "fingerprint": "fp-abcdef123"})
    assert c.post("/api/checkout/corte/pagar", json={"metodo": "pix", "cliente": cliente(), "fingerprint": "fp-abcdef123"}).status_code == 429
    assert c.get("/api/checkout/status/../../x").status_code == 404


def test_cpf_e_telefone():
    assert pagamento.cpf_valido(CPF) and not pagamento.cpf_valido("123.456.789-00")
    assert pagamento.telefone_e164("62 99999-9999") == "5562999999999"
    with pytest.raises(pagamento.PagamentoErro):
        pagamento.telefone_e164("123")
