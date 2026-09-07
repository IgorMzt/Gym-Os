"""Canal inicial entre o backend central e o futuro agente local da academia."""

import hmac

from flask import Blueprint, current_app, jsonify, request

api_agent_bp = Blueprint("api_agent", __name__, url_prefix="/api/v1/agent")


def _autorizado() -> bool:
    esperado = (current_app.config["GYM_SETTINGS"].agent_api_token or "").strip()
    if not esperado:
        return False
    recebido = request.headers.get("Authorization", "")
    prefixo = "Bearer "
    return recebido.startswith(prefixo) and hmac.compare_digest(recebido[len(prefixo):].strip(), esperado)


@api_agent_bp.post("/heartbeat")
def heartbeat():
    cfg = current_app.config["GYM_SETTINGS"]
    if not cfg.agent_api_token:
        return jsonify({"sucesso": False, "codigo": "AGENT_NAO_CONFIGURADO"}), 503
    if not _autorizado():
        return jsonify({"sucesso": False, "codigo": "AGENT_NAO_AUTORIZADO"}), 401
    dados = request.get_json(silent=True) or {}
    return jsonify({
        "sucesso": True,
        "agent_id": str(dados.get("agent_id") or "desconhecido")[:80],
        "server_version": cfg.app_version,
        "hardware_expected": cfg.role == "cloud",
    })
