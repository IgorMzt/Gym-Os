"""Comandos operacionais simples para preparar deploy e diagnosticar ambiente."""

from __future__ import annotations

import argparse
import json

from dotenv import load_dotenv

load_dotenv()

import database
from core.settings import Settings
from services import auth_service


def check_config() -> int:
    cfg = Settings.from_env()
    try:
        cfg.validate()
    except ValueError as exc:
        print(f"CONFIG ERROR: {exc}")
        return 1
    print(json.dumps({
        "ok": True,
        "version": cfg.app_version,
        "environment": cfg.environment,
        "role": cfg.role,
        "database_backend": cfg.database_backend,
        "storage_backend": cfg.storage_backend,
        "readiness_blockers": cfg.readiness_blockers(),
    }, indent=2, ensure_ascii=False))
    return 0


def init_db() -> int:
    cfg = Settings.from_env()
    cfg.validate()
    database.configure_runtime(cfg)
    database.criar_tabelas()
    auth_service.garantir_admin_bootstrap(cfg.admin_user, cfg.admin_password)
    print(f"Banco inicializado. Schema {database.SCHEMA_VERSION}.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="python manage.py")
    parser.add_argument("command", choices=["check-config", "init-db"])
    args = parser.parse_args()
    if args.command == "check-config":
        return check_config()
    return init_db()


if __name__ == "__main__":
    raise SystemExit(main())
