import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask

import database
from core.settings import Settings
from routes.api.agent import api_agent_bp
from routes.system import system_bp
from services import storage_service


class ProductionRuntimeTests(unittest.TestCase):
    def _settings(self, **env):
        base = {
            "APP_ENV": "testing",
            "APP_ROLE": "local",
            "FLASK_DEBUG": "0",
            "DATABASE_BACKEND": "sqlite",
            "STORAGE_BACKEND": "local",
            "ENABLE_LOCAL_HARDWARE": "1",
        }
        base.update(env)
        with patch.dict(os.environ, base, clear=False):
            return Settings.from_env()

    def test_producao_rejeita_credenciais_padrao(self):
        cfg = self._settings(
            APP_ENV="production",
            SECRET_KEY="troque-esta-secret-key-em-producao",
            ADMIN_PASSWORD="admin123",
            SESSION_COOKIE_SECURE="1",
            ENABLE_LOCAL_HARDWARE="1",
        )
        with self.assertRaises(ValueError):
            cfg.validate()

    def test_cloud_expoe_bloqueios_de_migracao(self):
        cfg = self._settings(
            APP_ROLE="cloud",
            ENABLE_LOCAL_HARDWARE="0",
            DATABASE_BACKEND="sqlite",
            DATABASE_URL="",
            STORAGE_BACKEND="local",
        )
        cfg.validate()
        self.assertIn("database_postgresql_pendente", cfg.readiness_blockers())
        self.assertIn("storage_objeto_pendente", cfg.readiness_blockers())

    def test_storage_local_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {
            "STORAGE_BACKEND": "local",
            "STORAGE_LOCAL_DIR": tmp,
        }, clear=False):
            caminho = storage_service.salvar_upload(b"gym-os", ".bin")
            self.assertTrue((Path(tmp) / Path(caminho).name).exists())
            self.assertTrue(storage_service.healthcheck()["ok"])
            storage_service.remover_upload(caminho)
            self.assertFalse((Path(tmp) / Path(caminho).name).exists())

    def test_health_live_e_ready_local(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {
            "STORAGE_BACKEND": "local",
            "STORAGE_LOCAL_DIR": str(Path(tmp) / "uploads"),
        }, clear=False):
            original = database.DB_PATH
            database.DB_PATH = Path(tmp) / "health.db"
            try:
                database.criar_tabelas()
                app = Flask(__name__)
                app.config["GYM_SETTINGS"] = self._settings()
                app.register_blueprint(system_bp)
                client = app.test_client()
                self.assertEqual(client.get("/health/live").status_code, 200)
                ready = client.get("/health/ready")
                self.assertEqual(ready.status_code, 200, ready.get_data(as_text=True))
                self.assertTrue(ready.get_json()["ready"])
            finally:
                database.DB_PATH = original

    def test_agent_heartbeat_exige_token(self):
        cfg = self._settings(AGENT_API_TOKEN="token-de-teste-123")
        app = Flask(__name__)
        app.config["GYM_SETTINGS"] = cfg
        app.register_blueprint(api_agent_bp)
        client = app.test_client()
        self.assertEqual(client.post("/api/v1/agent/heartbeat", json={"agent_id": "pc-1"}).status_code, 401)
        ok = client.post(
            "/api/v1/agent/heartbeat",
            json={"agent_id": "pc-1"},
            headers={"Authorization": "Bearer token-de-teste-123"},
        )
        self.assertEqual(ok.status_code, 200, ok.get_data(as_text=True))
        self.assertTrue(ok.get_json()["sucesso"])


if __name__ == "__main__":
    unittest.main()
