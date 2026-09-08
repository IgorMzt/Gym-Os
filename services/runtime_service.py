"""Estado operacional, readiness e protecoes por papel de execucao."""

from __future__ import annotations

from functools import wraps

from flask import current_app, jsonify

import database
from services import storage_service


def settings():
    return current_app.config["GYM_SETTINGS"]


def local_hardware_enabled() -> bool:
    return bool(settings().enable_local_hardware)


def local_only(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not local_hardware_enabled():
            return jsonify({
                "sucesso": False,
                "codigo": "LOCAL_AGENT_REQUIRED",
                "erro": "Esta operacao pertence ao agente local da academia.",
            }), 503
        return func(*args, **kwargs)
    return wrapper


def _database_probe() -> dict:
    return database.healthcheck_banco()


def readiness_report() -> dict:
    cfg = settings()
    db = _database_probe()
    storage = storage_service.healthcheck()
    blockers = cfg.readiness_blockers()
    componentes_ok = db.get("ok") and storage.get("ok")
    pronto = bool(componentes_ok and not blockers)
    return {
        "status": "ok" if pronto else "degradado",
        "ready": pronto,
        "version": cfg.app_version,
        "environment": cfg.environment,
        "role": cfg.role,
        "database": db,
        "storage": storage,
        "local_hardware": cfg.enable_local_hardware,
        "blockers": blockers,
    }
