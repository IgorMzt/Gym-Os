"""Utilitarios compartilhados pelas rotas da API mobile."""

from functools import wraps

from flask import g, jsonify, request

import database
from services.mobile_token_service import TokenError, TokenExpired, validar_access_token


def resposta_erro(mensagem: str, status: int, codigo: str):
    return jsonify({"sucesso": False, "erro": mensagem, "codigo": codigo}), status


def _bearer_token():
    cabecalho = (request.headers.get("Authorization") or "").strip()
    partes = cabecalho.split(None, 1)
    if len(partes) != 2 or partes[0].lower() != "bearer":
        return None
    return partes[1].strip()


def aluno_token_obrigatorio(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        token = _bearer_token()
        if not token:
            return resposta_erro("Token de acesso ausente.", 401, "TOKEN_AUSENTE")
        try:
            payload = validar_access_token(token)
        except TokenExpired:
            return resposta_erro("Token de acesso expirado.", 401, "TOKEN_EXPIRADO")
        except TokenError:
            return resposta_erro("Token de acesso invalido.", 401, "TOKEN_INVALIDO")

        acesso = database.obter_acesso_aluno_api(payload["acesso_id"], payload["pessoa_id"])
        if not acesso or not acesso.get("ativo"):
            return resposta_erro("Acesso do aluno indisponivel.", 401, "ACESSO_INATIVO")

        g.mobile_token = payload
        g.aluno_acesso = acesso
        g.aluno_id = int(acesso["pessoa_id"])
        return func(*args, **kwargs)

    return wrapper
