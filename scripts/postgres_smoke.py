"""Smoke test opcional contra um PostgreSQL real configurado no .env."""
from dotenv import load_dotenv
load_dotenv()

import database
from core.settings import Settings

cfg = Settings.from_env()
if cfg.database_backend != "postgresql":
    raise SystemExit("Defina DATABASE_BACKEND=postgresql e DATABASE_URL antes deste smoke test.")
cfg.validate()
database.configure_runtime(cfg)
database.criar_tabelas()
print(database.healthcheck_banco())
print(database.verificar_integridade())
