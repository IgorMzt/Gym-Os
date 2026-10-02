"""Comandos operacionais para preparar deploy, banco e diagnosticar ambiente."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import database
from core.settings import Settings
from services import auth_service, storage_service, saas_service
from services.database_migration_service import inspect_sqlite_source, migrate_sqlite_to_postgresql


def _configured_settings() -> Settings:
    cfg = Settings.from_env()
    cfg.validate()
    database.configure_runtime(cfg)
    return cfg


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
        "database_pool": {
            "min": cfg.database_pool_min,
            "max": cfg.database_pool_max,
            "timeout": cfg.database_pool_timeout,
        },
        "timezone": cfg.app_timezone,
        "storage_backend": cfg.storage_backend,
        "readiness_blockers": cfg.readiness_blockers(),
    }, indent=2, ensure_ascii=False))
    return 0


def init_db() -> int:
    cfg = _configured_settings()
    database.criar_tabelas()
    auth_service.garantir_admin_bootstrap(cfg.admin_user, cfg.admin_password)
    print(f"Banco {database.backend_banco()} inicializado. Schema {database.SCHEMA_VERSION}.")
    return 0


def db_status() -> int:
    _configured_settings()
    status = database.healthcheck_banco()
    try:
        integridade = database.verificar_integridade() if status.get("ok") else None
    except Exception as exc:
        integridade = {"ok": False, "erro": str(exc)}
    print(json.dumps({"database": status, "integridade": integridade}, indent=2, ensure_ascii=False))
    return 0 if status.get("ok") else 1


def migrate_sqlite(args) -> int:
    cfg = _configured_settings()
    if cfg.database_backend != "postgresql":
        print("CONFIG ERROR: para migrar, defina DATABASE_BACKEND=postgresql e DATABASE_URL no ambiente.")
        return 1
    source = Path(args.source)
    try:
        if args.inspect:
            print(json.dumps(inspect_sqlite_source(source), indent=2, ensure_ascii=False))
            return 0
        result = migrate_sqlite_to_postgresql(
            source,
            allow_existing=bool(args.allow_existing),
            dry_run=bool(args.dry_run),
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f"MIGRATION ERROR: {exc}")
        return 1



def storage_status() -> int:
    _configured_settings()
    database.criar_tabelas()
    health = storage_service.healthcheck()
    ativos = database.listar_storage_objects(status="ACTIVE")
    excluidos = database.listar_storage_objects(status="DELETED")
    print(json.dumps({
        "storage": health,
        "objects": {"active": len(ativos), "deleted": len(excluidos)},
    }, indent=2, ensure_ascii=False))
    return 0 if health.get("ok") else 1


def storage_migrate_legacy(args) -> int:
    _configured_settings()
    database.criar_tabelas()
    result = storage_service.migrar_uploads_legados(dry_run=bool(args.dry_run))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("ok") else 1


def storage_purge(args) -> int:
    _configured_settings()
    database.criar_tabelas()
    result = storage_service.purgar_expirados(dry_run=bool(args.dry_run))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("ok") else 1


def agent_status() -> int:
    _configured_settings()
    database.criar_tabelas()
    print(json.dumps({
        "ok": True,
        "version": "6.14",
        "agents": database.listar_agentes(),
    }, indent=2, ensure_ascii=False))
    return 0




def saas_status() -> int:
    _configured_settings()
    database.criar_tabelas()
    print(json.dumps({
        "ok": True,
        "version": "6.14",
        "schema": database.SCHEMA_VERSION,
        "metrics": saas_service.dashboard_saas(),
        "plans": saas_service.listar_planos(),
    }, indent=2, ensure_ascii=False))
    return 0

def tenant_status() -> int:
    _configured_settings()
    database.criar_tabelas()
    academias = database.listar_academias()
    saida = []
    for academia in academias:
        saida.append({
            **academia,
            "unidades": database.listar_unidades(int(academia["id"])),
        })
    print(json.dumps({"ok": True, "schema": database.SCHEMA_VERSION, "academias": saida}, indent=2, ensure_ascii=False))
    return 0


def tenant_create_academia(args) -> int:
    _configured_settings()
    database.criar_tabelas()
    try:
        academia = database.criar_academia(args.nome, args.codigo)
        print(json.dumps({"ok": True, "academia": academia, "unidades": database.listar_unidades(academia["id"])}, indent=2, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f"TENANT ERROR: {exc}")
        return 1


def tenant_create_unidade(args) -> int:
    _configured_settings()
    database.criar_tabelas()
    academia = database.obter_academia_por_slug(args.academia)
    if not academia:
        print("TENANT ERROR: academia nao encontrada.")
        return 1
    try:
        unidade = database.criar_unidade(int(academia["id"]), args.nome, args.codigo, endereco=args.endereco)
        print(json.dumps({"ok": True, "academia": academia, "unidade": unidade}, indent=2, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f"TENANT ERROR: {exc}")
        return 1


def tenant_create_admin(args) -> int:
    _configured_settings()
    database.criar_tabelas()
    tenant = database.resolver_tenant(args.academia, args.unidade)
    if not tenant:
        print("TENANT ERROR: academia/unidade nao encontrada.")
        return 1
    database.set_tenant_context(tenant["academia"]["id"], tenant["unidade"]["id"])
    try:
        uid = database.criar_usuario(args.login, args.nome or "Administrador", auth_service.hash_senha(args.senha), "ADMIN", True)
        print(json.dumps({"ok": True, "usuario_id": uid, "academia": tenant["academia"]["slug"], "unidade": tenant["unidade"]["codigo"]}, indent=2, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f"TENANT ERROR: {exc}")
        return 1

def main() -> int:
    parser = argparse.ArgumentParser(prog="python manage.py")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check-config", help="Valida configuracao por ambiente.")
    sub.add_parser("init-db", help="Cria/atualiza o schema no backend configurado.")
    sub.add_parser("db-status", help="Testa conexao, schema e integridade do banco.")
    sub.add_parser("agent-status", help="Lista agentes locais e estado de heartbeat.")
    sub.add_parser("storage-status", help="Testa storage privado e mostra contagem de objetos.")
    sub.add_parser("tenant-status", help="Lista academias e unidades.")
    sub.add_parser("saas-status", help="Mostra metricas, planos e estado SaaS da V6.14.")
    ta = sub.add_parser("tenant-create-academia", help="Cria uma academia e sua unidade principal.")
    ta.add_argument("--nome", required=True)
    ta.add_argument("--codigo", required=True, help="Slug/codigo unico da academia.")
    tu = sub.add_parser("tenant-create-unidade", help="Cria uma unidade dentro de uma academia.")
    tu.add_argument("--academia", required=True, help="Codigo/slug da academia.")
    tu.add_argument("--nome", required=True)
    tu.add_argument("--codigo", required=True)
    tu.add_argument("--endereco")
    tadm = sub.add_parser("tenant-create-admin", help="Cria um administrador em uma academia/unidade.")
    tadm.add_argument("--academia", required=True)
    tadm.add_argument("--unidade", default="principal")
    tadm.add_argument("--login", required=True)
    tadm.add_argument("--senha", required=True)
    tadm.add_argument("--nome")
    purge = sub.add_parser("storage-purge", help="Remove objetos privados cuja retencao venceu.")
    purge.add_argument("--dry-run", action="store_true", help="Mostra candidatos sem remover arquivos.")
    legacy = sub.add_parser("storage-migrate-legacy", help="Move uploads publicos legados para storage privado.")
    legacy.add_argument("--dry-run", action="store_true", help="Mostra candidatos sem mover arquivos nem atualizar o banco.")

    mig = sub.add_parser("migrate-sqlite", help="Migra perfis.db para PostgreSQL.")
    mig.add_argument("--source", default="perfis.db", help="Caminho do banco SQLite de origem.")
    mig.add_argument("--dry-run", action="store_true", help="Valida a origem e mostra contagens sem gravar.")
    mig.add_argument("--inspect", action="store_true", help="Inspeciona apenas o SQLite, sem conectar/copiar dados.")
    mig.add_argument(
        "--allow-existing",
        action="store_true",
        help="Permite upsert em PostgreSQL que ja possui dados de negocio. Use com cautela.",
    )

    args = parser.parse_args()
    if args.command == "check-config":
        return check_config()
    if args.command == "init-db":
        return init_db()
    if args.command == "db-status":
        return db_status()
    if args.command == "agent-status":
        return agent_status()
    if args.command == "storage-status":
        return storage_status()
    if args.command == "storage-purge":
        return storage_purge(args)
    if args.command == "storage-migrate-legacy":
        return storage_migrate_legacy(args)
    if args.command == "tenant-status":
        return tenant_status()
    if args.command == "saas-status":
        return saas_status()
    if args.command == "tenant-create-academia":
        return tenant_create_academia(args)
    if args.command == "tenant-create-unidade":
        return tenant_create_unidade(args)
    if args.command == "tenant-create-admin":
        return tenant_create_admin(args)
    return migrate_sqlite(args)


if __name__ == "__main__":
    raise SystemExit(main())
