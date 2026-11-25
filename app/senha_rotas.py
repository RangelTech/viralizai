"""Compatibilidade: a senha e o login agora moram em produtos_core.acesso (spec 57 §5A)."""
from fastapi import HTTPException

from produtos_core.acesso import SENHA_MIN, conferir_senha, hash_senha  # noqa: F401


def _validar_nova(senha) -> str:
    senha = str(senha or "")
    if len(senha) < SENHA_MIN:
        raise HTTPException(422, f"a senha precisa de pelo menos {SENHA_MIN} caracteres")
    if len(senha) > 200:
        raise HTTPException(422, "senha longa demais")
    return senha
