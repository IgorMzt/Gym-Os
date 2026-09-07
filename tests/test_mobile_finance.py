import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

import numpy as np
from flask import Flask

import database
from routes.api import api_auth_bp, api_aluno_bp, api_financeiro_bp
from services import auth_service


class MobileFinanceApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original_path = database.DB_PATH
        database.DB_PATH = Path(self.tmp.name) / "mobile-finance.db"
        database.criar_tabelas()
        plano = database.listar_planos(True)[0]
        self.plano = plano
        self.pessoa_id = database.adicionar_pessoa({
            "nome": "Aluno Financeiro Mobile", "cpf": "52998224725", "matricula": "MOBFIN",
            "plano": plano["nome"], "plano_id": plano["id"], "data_inicio": date.today().isoformat(),
            "data_vencimento": (date.today() + timedelta(days=10)).isoformat(),
            "status_financeiro": "EM_DIA", "liberado": True,
        }, encodings=[np.zeros(128, dtype=float)])
        database.salvar_acesso_aluno(self.pessoa_id, "mobilefin", auth_service.hash_senha("senha123"), True)
        app = Flask(__name__); app.secret_key = "segredo-mobile-finance"
        app.register_blueprint(api_auth_bp); app.register_blueprint(api_aluno_bp); app.register_blueprint(api_financeiro_bp)
        self.client = app.test_client()
        login = self.client.post("/api/v1/auth/login", json={"login":"mobilefin","senha":"senha123"}).get_json()
        self.headers = {"Authorization": f"Bearer {login['access_token']}"}

    def tearDown(self):
        database.DB_PATH = self.original_path
        self.tmp.cleanup()

    def test_status_financeiro_mobile(self):
        resp = self.client.get("/api/v1/aluno/financeiro", headers=self.headers)
        self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
        dados = resp.get_json()
        self.assertEqual(dados["status_financeiro_efetivo"], "EM_DIA")
        self.assertEqual(dados["plano"]["id"], self.plano["id"])
        self.assertEqual(dados["cobrancas"], [])

    def test_pix_reutiliza_cobranca_existente(self):
        database.criar_cobranca_local(
            self.pessoa_id, self.plano["id"], "pay_mobile_teste", "cus_mobile_teste",
            int(self.plano["valor_centavos"]), (date.today() + timedelta(days=10)).isoformat(),
            "000201PIXTESTE", "aW1hZ2Vt",
        )
        resp = self.client.post("/api/v1/aluno/financeiro/pix", headers=self.headers)
        self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
        dados = resp.get_json()
        self.assertTrue(dados["existente"])
        self.assertEqual(dados["cobranca"]["pix_payload"], "000201PIXTESTE")
        self.assertEqual(len(database.listar_cobrancas_pessoa(self.pessoa_id)), 1)

    def test_financeiro_exige_bearer(self):
        self.assertEqual(self.client.get("/api/v1/aluno/financeiro").status_code, 401)
        self.assertEqual(self.client.post("/api/v1/aluno/financeiro/pix").status_code, 401)


if __name__ == "__main__":
    unittest.main()
