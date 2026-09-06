"""Autenticacao da API v1 utilizada pelo aplicativo mobile."""

import time

from flask import Blueprint, jsonify, request

import database
from services import auth_service
from services.mobile_token_service import TokenError, emitir_par_tokens, revogar_refresh_token, rotacionar_refresh_token
from .common import aluno_token_obrigatorio, resposta_erro


api_auth_bp = Blueprint("api_auth", __name__, url_prefix="/api/v1/auth")

LOGIN_MAX_TENTATIVAS = 5
LOGIN_JANELA_SEGUNDOS = 300
LOGIN_BLOQUEIO_SEGUNDOS = 300
_login_tentativas = {}


def _ip_cliente():
    return request.remote_addr or "desconhecido"


def _estado_login(ip):
    agora = time.time()
    estado = _login_tentativas.get(ip, {"tentativas": [], "bloqueado_ate": 0})
    estado["tentativas"] = [t for t in estado["tentativas"] if agora - t < LOGIN_JANELA_SEGUNDOS]
    if estado["bloqueado_ate"] <= agora:
        estado["bloqueado_ate"] = 0
    _login_tentativas[ip] = estado
    return estado


def _login_bloqueado(ip):
    return max(0, int(_estado_login(ip)["bloqueado_ate"] - time.time()))


def _registrar_falha(ip):
    estado = _estado_login(ip)
    estado["tentativas"].append(time.time())
    if len(estado["tentativas"]) >= LOGIN_MAX_TENTATIVAS:
        estado["bloqueado_ate"] = time.time() + LOGIN_BLOQUEIO_SEGUNDOS
        estado["tentativas"] = []
    _login_tentativas[ip] = estado


def _json():
    return request.get_json(silent=True) or {}


def _user_agent():
    return (request.headers.get("User-Agent") or "")[:500] or None


@api_auth_bp.post("/login")
def login():
    ip = _ip_cliente()
    restante = _login_bloqueado(ip)
    if restante > 0:
        return resposta_erro(
            f"Muitas tentativas. Tente novamente em {restante} segundos.",
            429,
            "MUITAS_TENTATIVAS",
        )

    dados = _json()
    login_informado = str(dados.get("login") or dados.get("usuario") or "").strip()
    senha = str(dados.get("senha") or "")
    if not login_informado or not senha:
        return resposta_erro("Informe login e senha.", 400, "CAMPOS_OBRIGATORIOS")

    usuario = auth_service.autenticar_aluno(login_informado, senha)
    if not usuario:
        _registrar_falha(ip)
        database.registrar_log_admin("API_LOGIN_FALHOU", login_informado or "-", "Credenciais invalidas.", ip)
        return resposta_erro("Usuario ou senha invalidos.", 401, "CREDENCIAIS_INVALIDAS")

    _login_tentativas.pop(ip, None)
    tokens = emitir_par_tokens(usuario, ip=ip, user_agent=_user_agent())
    database.registrar_log_admin("API_LOGIN", usuario["login"], "Login mobile realizado.", ip)
    return jsonify({
        "sucesso": True,
        **tokens,
        "aluno": {
            "id": int(usuario["pessoa_id"]),
            "nome": usuario["nome"],
            "login": usuario["login"],
            "matricula": usuario.get("matricula"),
        },
    })


@api_auth_bp.post("/refresh")
def refresh():
    refresh_token = str(_json().get("refresh_token") or "").strip()
    try:
        tokens = rotacionar_refresh_token(refresh_token, ip=_ip_cliente(), user_agent=_user_agent())
    except TokenError:
        return resposta_erro("Refresh token invalido ou expirado.", 401, "REFRESH_INVALIDO")
    return jsonify({"sucesso": True, **tokens})


@api_auth_bp.post("/logout")
@aluno_token_obrigatorio
def logout():
    refresh_token = str(_json().get("refresh_token") or "").strip()
    revogado = revogar_refresh_token(refresh_token) if refresh_token else False
    database.registrar_log_admin(
        "API_LOGOUT",
        str(request.headers.get("X-Client-Id") or "mobile"),
        "Refresh token revogado." if revogado else "Sessao mobile encerrada sem refresh token valido.",
        _ip_cliente(),
    )
    return jsonify({"sucesso": True})
