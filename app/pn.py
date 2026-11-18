"""Cliente do perfil-navegador (rede interna). A sessão da conta fica lá, cifrada; aqui só a chave "postaai:<id>"."""
from __future__ import annotations

import base64
import os

import httpx


class PNErro(Exception):
    def __init__(self, status: int, mensagem: str):
        super().__init__(f"{status} {mensagem}")
        self.status = status
        self.mensagem = mensagem


class PN:
    def __init__(self, url: str, token: str, transport: httpx.BaseTransport | None = None):
        self.url, self.token, self.transport = url.rstrip("/"), token, transport

    def _r(self, metodo: str, caminho: str, json: dict | None = None, timeout: float = 150) -> dict:
        if not self.token:
            raise PNErro(503, "serviço de conexão não configurado")
        try:
            with httpx.Client(transport=self.transport, timeout=timeout) as h:
                r = h.request(metodo, self.url + caminho, json=json, headers={"Authorization": f"Bearer {self.token}"})
        except httpx.HTTPError:
            raise PNErro(503, "o serviço de conexão não respondeu; tente de novo")
        try:
            corpo = r.json()
        except ValueError:
            corpo = {}
        if r.status_code >= 400:
            raise PNErro(r.status_code, str(corpo.get("detail") or "erro"))
        return corpo

    def login(self, rede: str, conta: str, usuario: str, senha: str) -> dict:
        return self._r("POST", "/logins", {"rede": rede, "conta": conta, "usuario": usuario, "senha": senha})

    def login_status(self, lid: str) -> dict:
        return self._r("GET", f"/logins/{lid}")

    def responder(self, lid: str, valor: str) -> dict:
        return self._r("POST", f"/logins/{lid}/responder", {"valor": valor})

    def cancelar(self, lid: str) -> dict:
        return self._r("POST", f"/logins/{lid}/cancelar")

    def publicar(self, conta: str, tipo: str, legenda: str, caminhos: list[str]) -> dict:
        arqs = [{"nome": os.path.basename(c), "base64": base64.b64encode(open(c, "rb").read()).decode()} for c in caminhos]
        return self._r("POST", f"/contas/{conta}/publicar", {"tipo": tipo, "legenda": legenda, "arquivos": arqs}, timeout=600)

    def apagar(self, conta: str) -> dict:
        return self._r("DELETE", f"/contas/{conta}")
