import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import database
from core import database_backend
from core.settings import Settings
from services.database_migration_service import inspect_sqlite_source


class DatabaseV610Tests(unittest.TestCase):
    def test_schema_20_e_auditoria_sqlite(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_path = database.DB_PATH
            old_backend = database.DATABASE_BACKEND
            database.DATABASE_BACKEND = "sqlite"
            database.DB_PATH = Path(tmp) / "v610.db"
            try:
                database.criar_tabelas()
                self.assertEqual(database.SCHEMA_VERSION, 20)
                conn = database.conectar()
                try:
                    row = conn.execute(
                        "SELECT migration_key FROM database_migrations WHERE migration_key='schema-20-dual-database'"
                    ).fetchone()
                    self.assertIsNotNone(row)
                    versao = conn.execute(
                        "SELECT valor FROM schema_meta WHERE chave='schema_version'"
                    ).fetchone()[0]
                    self.assertEqual(versao, "20")
                finally:
                    conn.close()
            finally:
                database.DB_PATH = old_path
                database.DATABASE_BACKEND = old_backend

    def test_tradutor_qmark_preserva_literal(self):
        sql = database_backend.translate_postgresql_sql("SELECT '?' AS literal FROM pessoas WHERE id=?")
        self.assertIn("'?'", sql)
        self.assertIn("id=%s", sql)

    def test_tradutor_insert_or_ignore(self):
        sql = database_backend.translate_postgresql_sql(
            "INSERT OR IGNORE INTO configuracoes(chave,valor) VALUES(?,?)"
        )
        self.assertTrue(sql.startswith("INSERT INTO configuracoes"))
        self.assertIn("ON CONFLICT DO NOTHING", sql)
        self.assertEqual(sql.count("%s"), 2)

    def test_tradutor_current_timestamp_em_dml(self):
        sql = database_backend.translate_postgresql_sql(
            "UPDATE configuracoes SET data_atualizacao=CURRENT_TIMESTAMP WHERE chave=?"
        )
        self.assertIn("to_char(CURRENT_TIMESTAMP", sql)
        self.assertIn("chave=%s", sql)

    def test_postgresql_exige_database_url(self):
        with patch.dict(os.environ, {
            "APP_ENV": "testing",
            "DATABASE_BACKEND": "postgresql",
            "DATABASE_URL": "",
        }, clear=False):
            cfg = Settings.from_env()
            with self.assertRaises(ValueError):
                cfg.validate()

    def test_cloud_postgresql_remove_bloqueio_de_banco(self):
        with patch.dict(os.environ, {
            "APP_ENV": "testing",
            "APP_ROLE": "cloud",
            "DATABASE_BACKEND": "postgresql",
            "DATABASE_URL": "postgresql://gymos:senha@127.0.0.1:5432/gymos",
            "STORAGE_BACKEND": "local",
            "ENABLE_LOCAL_HARDWARE": "0",
            "AGENT_API_TOKEN": "token-seguro-de-teste",
        }, clear=False):
            cfg = Settings.from_env()
            cfg.validate()
            blockers = cfg.readiness_blockers()
            self.assertNotIn("database_postgresql_pendente", blockers)
            self.assertIn("storage_objeto_pendente", blockers)

    def test_inspecao_de_origem_sqlite(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_path = database.DB_PATH
            old_backend = database.DATABASE_BACKEND
            path = Path(tmp) / "origem.db"
            database.DATABASE_BACKEND = "sqlite"
            database.DB_PATH = path
            try:
                database.criar_tabelas()
                report = inspect_sqlite_source(path)
                self.assertEqual(report["quick_check"], "ok")
                self.assertEqual(str(report["schema_version"]), "20")
                self.assertIn("pessoas", report["rows"])
            finally:
                database.DB_PATH = old_path
                database.DATABASE_BACKEND = old_backend


if __name__ == "__main__":
    unittest.main()
