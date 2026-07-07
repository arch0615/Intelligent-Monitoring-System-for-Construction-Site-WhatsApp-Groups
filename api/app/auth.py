"""Autenticação do painel: hash de senha (stdlib, sem dependência nativa),
sessão por cookie e dependência que exige login."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os

from fastapi import HTTPException, Request, status

from . import db

_ITERACOES = 200_000


def hash_senha(senha: str) -> str:
    """Gera 'pbkdf2$<salt>$<hash>' (sha256). Salt aleatório por senha."""
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", senha.encode(), salt, _ITERACOES)
    return "pbkdf2$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(dk).decode()


def verificar_senha(senha: str, guardado: str) -> bool:
    try:
        _algo, salt_b64, dk_b64 = guardado.split("$")
        salt = base64.b64decode(salt_b64)
        esperado = base64.b64decode(dk_b64)
        atual = hashlib.pbkdf2_hmac("sha256", senha.encode(), salt, _ITERACOES)
        return hmac.compare_digest(atual, esperado)
    except Exception:  # noqa: BLE001
        return False


def usuario_logado(request: Request) -> dict | None:
    """Retorna o usuário da sessão, ou None."""
    uid = request.session.get("user_id")
    return db.buscar_usuario_por_id(uid) if uid else None


def requer_login(request: Request) -> dict:
    """Dependência para páginas protegidas: redireciona ao /login se não logado."""
    usuario = usuario_logado(request)
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login"},
        )
    return usuario
