import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

import numpy as np
from flask import Flask

import database
from routes.api import api_aluno_bp, api_auth_bp
from services import auth_service


class MobileApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original_path = database.DB_PATH
        database.DB_PATH = Path(self.tmp.name) / "mobile-api.db"
        database.criar_tabelas()

        plano = database.listar_planos(True)[0]
        self.pessoa_id = database.adicionar_pessoa({
            "nome": "Aluno Mobile",
            "cpf": "52998224725",
            "matricula": "MOB001",
            "plano": plano["nome"],
            "plano_id": plano["id"],
            "data_inicio": date.today().isoformat(),
            "data_vencimento": (date.today() + timedelta(days=30)).isoformat(),
            "status_financeiro": "EM_DIA",
            "liberado": True,
        }, encodings=[np.zeros(128, dtype=float)])
        database.salvar_acesso_aluno(
            self.pessoa_id,
            "alunomobile",
            auth_service.hash_senha("senha123"),
            True,
        )

        app = Flask(__name__)
        app.secret_key = "segredo-de-teste-mobile-com-tamanho-suficiente"
        app.register_blueprint(api_auth_bp)
        app.register_blueprint(api_aluno_bp)
        self.client = app.test_client()

    def tearDown(self):
        database.DB_PATH = self.original_path
        self.tmp.cleanup()

    def _login(self):
        resposta = self.client.post(
            "/api/v1/auth/login",
            json={"login": "alunomobile", "senha": "senha123"},
        )
        self.assertEqual(resposta.status_code, 200, resposta.get_data(as_text=True))
        return resposta.get_json()

    def test_schema_20(self):
        self.assertEqual(database.SCHEMA_VERSION, 20)
        conn = database.conectar()
        try:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='mobile_refresh_tokens'"
            ).fetchone()
            self.assertIsNotNone(row)
        finally:
            conn.close()

    def test_login_me_refresh_e_rotacao(self):
        login = self._login()
        self.assertTrue(login["sucesso"])
        self.assertTrue(login["access_token"])
        self.assertTrue(login["refresh_token"])

        me = self.client.get(
            "/api/v1/aluno/me",
            headers={"Authorization": f"Bearer {login['access_token']}"},
        )
        self.assertEqual(me.status_code, 200, me.get_data(as_text=True))
        self.assertEqual(me.get_json()["aluno"]["matricula"], "MOB001")

        refresh = self.client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": login["refresh_token"]},
        )
        self.assertEqual(refresh.status_code, 200, refresh.get_data(as_text=True))
        novo = refresh.get_json()
        self.assertNotEqual(novo["refresh_token"], login["refresh_token"])

        reuso = self.client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": login["refresh_token"]},
        )
        self.assertEqual(reuso.status_code, 401)

    def test_api_rejeita_conta_de_equipe(self):
        database.garantir_usuario_bootstrap(
            login="adminmobile",
            nome="Admin Mobile",
            senha_hash=auth_service.hash_senha("senha123"),
        )
        resposta = self.client.post(
            "/api/v1/auth/login",
            json={"login": "adminmobile", "senha": "senha123"},
        )
        self.assertEqual(resposta.status_code, 401)

    def test_me_exige_bearer(self):
        resposta = self.client.get("/api/v1/aluno/me")
        self.assertEqual(resposta.status_code, 401)
        self.assertEqual(resposta.get_json()["codigo"], "TOKEN_AUSENTE")


if __name__ == "__main__":
    unittest.main()
