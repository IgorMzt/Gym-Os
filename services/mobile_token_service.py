"""Tokens de acesso da API mobile do Gym OS.

O access token e assinado e curto. O refresh token e opaco, rotativo e apenas
seu hash e persistido no banco. Isso permite revogacao sem armazenar o segredo
utilizado pelo aplicativo.
"""

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

import database

ACCESS_TOKEN_TTL_SECONDS = int(os.getenv("MOBILE_ACCESS_TOKEN_TTL_SECONDS", "900"))
REFRESH_TOKEN_TTL_DAYS = int(os.getenv("MOBILE_REFRESH_TOKEN_TTL_DAYS", "30"))
TOKEN_SALT = "gym-os-mobile-access-v1"


class TokenError(ValueError):
    """Token ausente, invalido, expirado ou revogado."""


class TokenExpired(TokenError):
    """Access token expirado."""


def _serializer():
    return URLSafeTimedSerializer(current_app.secret_key, salt=TOKEN_SALT)


def _hash_refresh(token: str) -> str:
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def _utc_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def emitir_access_token(usuario: dict) -> str:
    payload = {
        "v": 1,
        "typ": "access",
        "papel": "ALUNO",
        "acesso_id": int(usuario["id"]),
        "pessoa_id": int(usuario["pessoa_id"]),
        "jti": secrets.token_urlsafe(8),
    }
    return _serializer().dumps(payload)


def validar_access_token(token: str) -> dict:
    if not token:
        raise TokenError("Token de acesso ausente.")
    try:
        payload = _serializer().loads(token, max_age=ACCESS_TOKEN_TTL_SECONDS)
    except SignatureExpired as exc:
        raise TokenExpired("Token de acesso expirado.") from exc
    except BadSignature as exc:
        raise TokenError("Token de acesso invalido.") from exc

    if not isinstance(payload, dict) or payload.get("typ") != "access" or payload.get("papel") != "ALUNO":
        raise TokenError("Token de acesso invalido.")
    try:
        payload["acesso_id"] = int(payload["acesso_id"])
        payload["pessoa_id"] = int(payload["pessoa_id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise TokenError("Token de acesso invalido.") from exc
    return payload


def emitir_par_tokens(usuario: dict, ip: str | None = None, user_agent: str | None = None) -> dict:
    refresh_token = secrets.token_urlsafe(48)
    expira_em = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_TTL_DAYS)
    database.criar_refresh_token_mobile(
        aluno_acesso_id=int(usuario["id"]),
        pessoa_id=int(usuario["pessoa_id"]),
        token_hash=_hash_refresh(refresh_token),
        expires_at=_utc_iso(expira_em),
        ip=ip,
        user_agent=user_agent,
    )
    return {
        "access_token": emitir_access_token(usuario),
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "expires_in": ACCESS_TOKEN_TTL_SECONDS,
        "refresh_expires_in": REFRESH_TOKEN_TTL_DAYS * 86400,
    }


def rotacionar_refresh_token(refresh_token: str, ip: str | None = None, user_agent: str | None = None) -> dict:
    if not refresh_token:
        raise TokenError("Refresh token ausente.")

    novo_refresh = secrets.token_urlsafe(48)
    expira_em = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_TTL_DAYS)
    sessao = database.rotacionar_refresh_token_mobile(
        token_hash=_hash_refresh(refresh_token),
        novo_token_hash=_hash_refresh(novo_refresh),
        novo_expires_at=_utc_iso(expira_em),
        ip=ip,
        user_agent=user_agent,
    )
    if not sessao:
        raise TokenError("Refresh token invalido ou expirado.")

    usuario = {
        "id": sessao["aluno_acesso_id"],
        "pessoa_id": sessao["pessoa_id"],
    }
    return {
        "access_token": emitir_access_token(usuario),
        "refresh_token": novo_refresh,
        "token_type": "Bearer",
        "expires_in": ACCESS_TOKEN_TTL_SECONDS,
        "refresh_expires_in": REFRESH_TOKEN_TTL_DAYS * 86400,
    }


def revogar_refresh_token(refresh_token: str) -> bool:
    if not refresh_token:
        return False
    return database.revogar_refresh_token_mobile(_hash_refresh(refresh_token))
