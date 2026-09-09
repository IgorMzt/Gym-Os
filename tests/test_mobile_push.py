import os
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

import numpy as np
from flask import Flask

os.environ.setdefault("SECRET_KEY", "test-secret-key-mobile-push")

import database
from routes.api import api_auth_bp, api_notificacoes_bp
from services import auth_service


class MobilePushTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original_path = database.DB_PATH
        self.original_backend = database.DATABASE_BACKEND
        database.DATABASE_BACKEND = "sqlite"
        database.DB_PATH = Path(self.tmp.name) / "mobile-push.db"
        database.criar_tabelas()

        plano = database.listar_planos(True)[0]
        self.pessoa_id = database.adicionar_pessoa({
            "nome": "Push Aluno",
            "cpf": "52998224725",
            "matricula": "MOBPUSH",
            "plano": plano["nome"],
            "plano_id": plano["id"],
            "data_inicio": date.today().isoformat(),
            "data_vencimento": (date.today() + timedelta(days=30)).isoformat(),
            "status_financeiro": "EM_DIA",
            "liberado": True,
        }, encodings=[np.zeros(128, dtype=float)])
        database.salvar_acesso_aluno(
            self.pessoa_id,
            "pushaluno",
            auth_service.hash_senha("123456"),
            True,
        )

        app = Flask(__name__)
        app.secret_key = "segredo-de-teste-mobile-push-com-tamanho-suficiente"
        app.register_blueprint(api_auth_bp)
        app.register_blueprint(api_notificacoes_bp)
        self.client = app.test_client()

        login = self.client.post(
            "/api/v1/auth/login",
            json={"login": "pushaluno", "senha": "123456"},
        )
        self.assertEqual(login.status_code, 200, login.get_data(as_text=True))
        access_token = login.get_json()["access_token"]
        self.headers = {"Authorization": f"Bearer {access_token}"}

    def tearDown(self):
        database.DB_PATH = self.original_path
        database.DATABASE_BACKEND = self.original_backend
        self.tmp.cleanup()

    def test_schema_21(self):
        self.assertEqual(database.SCHEMA_VERSION, 21)
        conn = database.conectar()
        try:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='mobile_push_devices'"
            ).fetchone()
            self.assertIsNotNone(row)
        finally:
            conn.close()

    def test_registra_e_remove_device(self):
        token = "ExponentPushToken[teste123]"
        resposta = self.client.post(
            "/api/v1/aluno/notificacoes/device",
            headers=self.headers,
            json={"expo_push_token": token, "plataforma": "ios"},
        )
        self.assertEqual(resposta.status_code, 200, resposta.get_data(as_text=True))
        self.assertEqual(len(database.listar_push_devices_pessoa(self.pessoa_id)), 1)

        resposta = self.client.delete(
            "/api/v1/aluno/notificacoes/device",
            headers=self.headers,
            json={"expo_push_token": token},
        )
        self.assertEqual(resposta.status_code, 200, resposta.get_data(as_text=True))
        self.assertEqual(database.listar_push_devices_pessoa(self.pessoa_id), [])

    def test_push_exige_bearer(self):
        resposta = self.client.post("/api/v1/aluno/notificacoes/device", json={})
        self.assertEqual(resposta.status_code, 401)


if __name__ == "__main__":
    unittest.main()
