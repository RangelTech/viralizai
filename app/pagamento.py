"""Checkout transparente (ordem do Lucas 25/11): o pagamento acontece na nossa página, pela API da Cakto da conta que vende
(landing do Fael = conta do Adriano). O cartão é tokenizado no navegador pelo SDK da Cakto (número e CVV nunca passam aqui);
o Pix volta como copia-e-cola. A liberação do plano continua pelo webhook (/api/cakto), igual à compra pela página da Cakto.
Docs: https://docs.cakto.com.br/api-reference/payments/create-pix e create-card."""
from __future__ import annotations

import re
import threading
import time
import uuid

import httpx

API = "https://api.cakto.com.br"
UA = "curl/8.5.0"  # o Cloudflare da Cakto barra o User-Agent padrão do Python (1010)
METODOS = ("pix", "credit_card")


class PagamentoErro(Exception):
    def __init__(self, msg: str, status: int = 400):
        super().__init__(msg)
        self.status = status


class Cakto:
    """Cliente da API pública da Cakto com o token em cache (vale 10 h; pedir toda hora dá 429)."""

    def __init__(self, client_id: str, client_secret: str, transport: httpx.BaseTransport | None = None):
        self.cid, self.sec = client_id, client_secret
        self.http = httpx.Client(timeout=40.0, transport=transport, headers={"User-Agent": UA})
        self._tok: tuple[str, float] | None = None
        self._trava = threading.Lock()

    @property
    def configurado(self) -> bool:
        return bool(self.cid and self.sec)

    def _token(self) -> str:
        with self._trava:
            if self._tok and self._tok[1] > time.time() + 60:
                return self._tok[0]
            r = self.http.post(API + "/public_api/token/", data={"client_id": self.cid, "client_secret": self.sec})
            if r.status_code != 200:
                raise PagamentoErro("O pagamento está indisponível agora. Tenta de novo em instantes.", 503)
            j = r.json()
            self._tok = (j["access_token"], time.time() + int(j.get("expires_in", 3600)))
            return self._tok[0]

    def criar(self, corpo: dict) -> dict:
        r = self.http.post(API + "/public_api/payments/", json=corpo, headers={
            "Authorization": "Bearer " + self._token(), "X-Idempotency-Key": str(uuid.uuid4())})
        if r.status_code >= 500:
            raise PagamentoErro("O pagamento está indisponível agora. Tenta de novo em instantes.", 503)
        j = r.json() if r.content else {}
        if r.status_code >= 300:
            raise PagamentoErro(_erro_legivel(j), 422)
        return j

    def pedido(self, pedido_id: str) -> dict:
        r = self.http.get(API + f"/public_api/orders/{pedido_id}/", headers={"Authorization": "Bearer " + self._token()})
        if r.status_code == 404:
            raise PagamentoErro("Pagamento não encontrado.", 404)
        if r.status_code >= 300:
            raise PagamentoErro("Não consegui consultar o pagamento agora.", 503)
        return r.json()


def _erro_legivel(j) -> str:
    """Erro da Cakto em português simples para a pessoa (sem jargão nem nome de campo)."""
    texto = str(j)
    if "docNumber" in texto or "cpf" in texto.lower():
        return "Confere o CPF: ele precisa ser válido."
    if "phone" in texto:
        return "Confere o WhatsApp com DDD."
    if "email" in texto:
        return "Confere o e-mail."
    if "card" in texto or "token" in texto:
        return "Não deu para usar esse cartão. Confere os dados ou tenta outro."
    return "Não deu para concluir o pagamento. Confere os dados e tenta de novo."


def so_digitos(v) -> str:
    return re.sub(r"\D", "", str(v or ""))


def cpf_valido(cpf: str) -> bool:
    c = so_digitos(cpf)
    if len(c) != 11 or c == c[0] * 11:
        return False
    for n in (9, 10):
        s = sum(int(c[i]) * (n + 1 - i) for i in range(n))
        if int(c[n]) != (s * 10 % 11) % 10:
            return False
    return True


def telefone_e164(tel: str) -> str:
    d = so_digitos(tel)
    if len(d) in (10, 11):
        d = "55" + d
    if not (12 <= len(d) <= 13 and d.startswith("55")):
        raise PagamentoErro("Confere o WhatsApp com DDD.")
    return d


def montar(oferta: str, metodo: str, cliente: dict, fingerprint: str, ip: str, card_token: str = "", antifraude: str = "",
           parcelas: int = 1) -> dict:
    """Corpo do POST /public_api/payments/ (contrato público da Cakto)."""
    if metodo not in METODOS:
        raise PagamentoErro("Escolhe Pix ou cartão.")
    nome = str(cliente.get("nome") or "").strip()[:120]
    email = str(cliente.get("email") or "").strip().lower()[:160]
    if len(nome.split()) < 2:
        raise PagamentoErro("Escreve o nome completo.")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise PagamentoErro("Confere o e-mail.")
    if not cpf_valido(cliente.get("cpf")):
        raise PagamentoErro("Confere o CPF: ele precisa ser válido.")
    if not re.fullmatch(r"[\w-]{8,120}", fingerprint or ""):
        raise PagamentoErro("Recarrega a página e tenta de novo.")
    corpo = {"paymentMethod": metodo, "items": [{"offerId": oferta, "quantity": 1}],
             "customer": {"name": nome, "email": email, "phone": telefone_e164(cliente.get("whatsapp")), "fingerprint": fingerprint,
                          "docType": "cpf", "docNumber": so_digitos(cliente.get("cpf")), **({"ip": ip} if ip else {})}}
    if metodo == "credit_card":
        if not card_token or not antifraude:
            raise PagamentoErro("Não deu para validar o cartão. Confere os dados e tenta de novo.")
        corpo["card"] = {"token": card_token}
        corpo["antifraud_profiling_attempt_reference"] = antifraude
        corpo["installments"] = max(1, min(12, int(parcelas or 1)))
    else:
        corpo["pixExpiresIn"] = 30 * 60
    return corpo


def resumo(p: dict) -> dict:
    """O que a página precisa saber do pagamento (sem dados pessoais)."""
    pix = p.get("pix") or {}
    return {"id": p.get("id"), "status": p.get("status"), "metodo": p.get("paymentMethod"), "valor": p.get("amount"),
            "pix": {"copia_e_cola": pix.get("qrCode"), "expira": pix.get("expirationDate")} if pix.get("qrCode") else None}


PAGO = ("paid", "authorized")
RECUSADO = ("refused", "declined", "canceled", "chargedback", "blocked", "acquirer_error")
