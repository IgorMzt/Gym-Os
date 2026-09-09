"""API autenticada entre Gym OS Cloud e agentes locais V6.11."""

from __future__ import annotations

import hmac
from functools import wraps

from flask import Blueprint, current_app, g, jsonify, request

import database
from services import agent_service

api_agent_bp = Blueprint("api_agent", __name__, url_prefix="/api/v1/agent")


def _bearer_token() -> str:
    recebido = request.headers.get("Authorization", "")
    prefixo = "Bearer "
    return recebido[len(prefixo):].strip() if recebido.startswith(prefixo) else ""


def _bootstrap_autorizado() -> bool:
    esperado = (current_app.config["GYM_SETTINGS"].agent_api_token or "").strip()
    recebido = _bearer_token()
    return bool(esperado and recebido and hmac.compare_digest(recebido, esperado))


def agente_token_obrigatorio(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        token = _bearer_token()
        agente = agent_service.autenticar_agente(token)
        if not agente:
            return jsonify({"sucesso": False, "codigo": "AGENT_NAO_AUTORIZADO"}), 401
        g.gym_agent = agente
        return func(*args, **kwargs)
    return wrapper


def _ip_cliente():
    return (request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or request.remote_addr or "")[:80]


@api_agent_bp.post("/register")
def register():
    cfg = current_app.config["GYM_SETTINGS"]
    if not cfg.agent_api_token:
        return jsonify({"sucesso": False, "codigo": "AGENT_BOOTSTRAP_NAO_CONFIGURADO"}), 503
    if not _bootstrap_autorizado():
        return jsonify({"sucesso": False, "codigo": "AGENT_BOOTSTRAP_INVALIDO"}), 401
    dados = request.get_json(silent=True) or {}
    try:
        agente, token = agent_service.registrar_ou_rotacionar_agente(dados, _ip_cliente())
    except ValueError as exc:
        return jsonify({"sucesso": False, "codigo": "AGENT_REGISTRO_INVALIDO", "erro": str(exc)}), 400
    database.registrar_log_admin("AGENT_REGISTRADO", agente.get("agent_uid"), agente.get("hostname"), _ip_cliente())
    publico = {k: agente.get(k) for k in ("id", "agent_uid", "nome", "hostname", "machine_id", "app_version")}
    return jsonify({"sucesso": True, "agent": publico, "agent_token": token}), 201


@api_agent_bp.post("/heartbeat")
@agente_token_obrigatorio
def heartbeat():
    dados = request.get_json(silent=True) or {}
    agente = agent_service.heartbeat(g.gym_agent, dados, _ip_cliente())
    pendentes = database.contar_comandos_pendentes_agente(int(agente["id"]))
    return jsonify({
        "sucesso": True,
        "agent_id": agente.get("agent_uid"),
        "server_version": current_app.config["GYM_SETTINGS"].app_version,
        "hardware_expected": current_app.config["GYM_SETTINGS"].role == "cloud",
        "pending_commands": pendentes,
    })


@api_agent_bp.get("/sync/access")
@agente_token_obrigatorio
def sync_access():
    return jsonify({"sucesso": True, "snapshot": agent_service.access_snapshot()})


@api_agent_bp.post("/access/check")
@agente_token_obrigatorio
def access_check():
    dados = request.get_json(silent=True) or {}
    try:
        pessoa_id = int(dados.get("pessoa_id"))
    except (TypeError, ValueError):
        return jsonify({"sucesso": False, "codigo": "PESSOA_INVALIDA"}), 400
    decisao = agent_service.decisao_acesso_online(pessoa_id)
    return jsonify({"sucesso": True, **decisao})


@api_agent_bp.post("/events")
@agente_token_obrigatorio
def events():
    dados = request.get_json(silent=True) or {}
    eventos = dados.get("events") or []
    if not isinstance(eventos, list):
        return jsonify({"sucesso": False, "codigo": "EVENTOS_INVALIDOS"}), 400
    resultado = agent_service.processar_eventos(g.gym_agent, eventos)
    return jsonify({"sucesso": True, **resultado})


@api_agent_bp.get("/commands")
@agente_token_obrigatorio
def commands():
    try:
        limite = max(1, min(int(request.args.get("limit", 20)), 50))
    except (TypeError, ValueError):
        limite = 20
    comandos = database.buscar_comandos_agente(int(g.gym_agent["id"]), limite)
    return jsonify({"sucesso": True, "commands": comandos})


@api_agent_bp.post("/commands/<command_uuid>/ack")
@agente_token_obrigatorio
def command_ack(command_uuid):
    dados = request.get_json(silent=True) or {}
    ok = bool(dados.get("ok"))
    atualizado = database.confirmar_comando_agente(
        int(g.gym_agent["id"]), command_uuid, ok=ok, result=dados.get("result") or {}
    )
    if not atualizado:
        return jsonify({"sucesso": False, "codigo": "COMANDO_NAO_ENCONTRADO"}), 404
    return jsonify({"sucesso": True})
