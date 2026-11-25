"""Spec 57 §3 item 4: planos.json é o contrato versionado dos planos; falha se o código e o arquivo divergirem."""
import importlib
import json
from pathlib import Path

CONTRATO = json.loads((Path(__file__).resolve().parent.parent / "planos.json").read_text(encoding="utf-8"))


def _planos_do_codigo(nome):
    for mod in ("app.planos", "app.marcas", "app.main"):
        try:
            m = importlib.import_module(mod)
        except Exception:  # noqa: BLE001
            continue
        if hasattr(m, nome):
            return getattr(m, nome)
    raise AssertionError(f"{nome} não encontrado no código")


def test_planos_json_bate_com_o_codigo():
    for chave, nome in (("planos", "PLANOS"), ("planos_fa", "PLANOS_FA")):
        if chave not in CONTRATO:
            continue
        codigo = _planos_do_codigo(nome)
        json_ = {p["codigo"]: p["preco"] for p in CONTRATO[chave]}
        cod = {k: float(v["preco"]) for k, v in codigo.items() if not v.get("so_fael")}
        assert cod == json_, f"{nome} no código difere do planos.json: {cod} x {json_}"
