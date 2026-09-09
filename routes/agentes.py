"""Painel administrativo dos agentes locais."""

from flask import Blueprint, jsonify, render_template, request

import database
from services.permissions import papel_requerido

agentes_bp = Blueprint("agentes", __name__)


@agentes_bp.get("/agentes")
@papel_requerido("ADMIN")
def pagina_agentes():
    return render_template("agentes.html", agentes=database.listar_agentes())


@agentes_bp.get("/api/agentes")
@papel_requerido("ADMIN")
def api_agentes():
    return jsonify({"sucesso": True, "agentes": database.listar_agentes()})


@agentes_bp.get("/api/agentes/<int:agent_id>")
@papel_requerido("ADMIN")
def api_agente_detalhe(agent_id):
    agente = database.obter_agente(agent_id)
    if not agente:
        return jsonify({"sucesso": False, "erro": "Agente nao encontrado."}), 404
    agente.pop("token_hash", None)
    return jsonify({
        "sucesso": True,
        "agente": agente,
        "comandos": database.listar_comandos_agente(agent_id, 30),
        "eventos": database.listar_eventos_agente(agent_id, 30),
    })


@agentes_bp.post("/api/agentes/<int:agent_id>/comandos")
@papel_requerido("ADMIN")
def api_criar_comando(agent_id):
    if not database.obter_agente(agent_id):
        return jsonify({"sucesso": False, "erro": "Agente nao encontrado."}), 404
    dados = request.get_json(silent=True) or {}
    tipo = str(dados.get("tipo") or "").strip().upper()
    permitidos = {"PING", "SYNC_ACCESS", "REFRESH_CONFIG", "TEST_TURNSTILE"}
    if tipo not in permitidos:
        return jsonify({"sucesso": False, "erro": "Comando invalido."}), 400
    comando = database.criar_comando_agente(agent_id, tipo, dados.get("payload") or {})
    return jsonify({"sucesso": True, "comando": comando}), 201


@agentes_bp.post("/api/agentes/<int:agent_id>/revogar")
@papel_requerido("ADMIN")
def api_revogar_agente(agent_id):
    if not database.revogar_agente(agent_id):
        return jsonify({"sucesso": False, "erro": "Agente nao encontrado."}), 404
    database.registrar_log_admin("AGENT_REVOGADO", str(agent_id), "Token individual invalidado.")
    return jsonify({"sucesso": True})
