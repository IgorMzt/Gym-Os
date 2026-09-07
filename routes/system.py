"""Endpoints leves de liveness/readiness independentes do painel operacional."""

from flask import Blueprint, jsonify

from services import runtime_service

system_bp = Blueprint("system", __name__)


@system_bp.get("/health/live")
def health_live():
    cfg = runtime_service.settings()
    return jsonify({"status": "ok", "version": cfg.app_version, "role": cfg.role})


@system_bp.get("/health/ready")
def health_ready():
    relatorio = runtime_service.readiness_report()
    return jsonify(relatorio), 200 if relatorio["ready"] else 503


@system_bp.get("/health")
def health_legacy():
    relatorio = runtime_service.readiness_report()
    return jsonify({
        "status": relatorio["status"],
        "database": "ok" if relatorio["database"].get("ok") else "erro",
        "schema_version": relatorio["database"].get("schema_version"),
        "role": relatorio["role"],
    }), 200 if relatorio["database"].get("ok") else 503
