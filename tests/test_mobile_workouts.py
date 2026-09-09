import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

import numpy as np
from flask import Flask

import database
from routes.api import api_auth_bp, api_aluno_bp, api_treinos_bp
from services import auth_service


class MobileWorkoutApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original_path = database.DB_PATH
        self.original_backend = database.DATABASE_BACKEND
        database.DATABASE_BACKEND = "sqlite"
        database.DB_PATH = Path(self.tmp.name) / "mobile-workout.db"
        database.criar_tabelas()
        plano = database.listar_planos(True)[0]
        self.pessoa_id = database.adicionar_pessoa({
            "nome": "Aluno Treino Mobile", "cpf": "52998224725", "matricula": "MOBFIT",
            "plano": plano["nome"], "plano_id": plano["id"], "data_inicio": date.today().isoformat(),
            "data_vencimento": (date.today() + timedelta(days=30)).isoformat(),
            "status_financeiro": "EM_DIA", "liberado": True,
        }, encodings=[np.zeros(128, dtype=float)])
        database.salvar_acesso_aluno(self.pessoa_id, "mobilefit", auth_service.hash_senha("senha123"), True)
        exercicio_id = database.criar_exercicio({"nome":"Supino teste","grupo_muscular":"Peitoral","ativo":True})
        self.ficha_id = database.criar_ficha_treino({
            "pessoa_id": self.pessoa_id, "nome":"Ficha Mobile", "ativo":True,
            "treinos":[{"nome":"Treino A","exercicios":[{"exercicio_id":exercicio_id,"series":3,"repeticoes":"10","carga":"20 kg","descanso_segundos":60}]}],
        })
        self.treino_id = database.obter_ficha_treino(self.ficha_id)["treinos"][0]["id"]
        app = Flask(__name__); app.secret_key = "segredo-de-teste-mobile-workout"
        app.register_blueprint(api_auth_bp); app.register_blueprint(api_aluno_bp); app.register_blueprint(api_treinos_bp)
        self.client = app.test_client()
        login = self.client.post("/api/v1/auth/login", json={"login":"mobilefit","senha":"senha123"}).get_json()
        self.headers = {"Authorization": f"Bearer {login['access_token']}"}

    def tearDown(self):
        database.DB_PATH = self.original_path
        database.DATABASE_BACKEND = self.original_backend
        self.tmp.cleanup()

    def test_fluxo_completo_treino_mobile(self):
        lista = self.client.get("/api/v1/aluno/treinos", headers=self.headers)
        self.assertEqual(lista.status_code, 200)
        self.assertEqual(lista.get_json()["ficha"]["nome"], "Ficha Mobile")
        self.assertEqual(lista.get_json()["proximo_treino_id"], self.treino_id)

        inicio = self.client.post("/api/v1/aluno/execucoes", headers=self.headers, json={"treino_id":self.treino_id})
        self.assertEqual(inicio.status_code, 200, inicio.get_data(as_text=True))
        sessao_id = inicio.get_json()["id"]
        sessao = self.client.get(f"/api/v1/aluno/execucoes/{sessao_id}", headers=self.headers).get_json()["sessao"]
        item_id = sessao["itens"][0]["id"]

        salvo = self.client.put(f"/api/v1/aluno/execucoes/itens/{item_id}", headers=self.headers, json={
            "concluido": True, "series_realizadas": 3, "repeticoes_realizadas": "10", "carga_realizada": "22 kg"
        })
        self.assertEqual(salvo.status_code, 200, salvo.get_data(as_text=True))
        fim = self.client.post(f"/api/v1/aluno/execucoes/{sessao_id}/concluir", headers=self.headers, json={"observacoes":"Bom treino"})
        self.assertEqual(fim.status_code, 200, fim.get_data(as_text=True))
        self.assertEqual(database.obter_sessao_treino(sessao_id)["status"], "CONCLUIDO")

    def test_treinos_exige_bearer(self):
        resposta = self.client.get("/api/v1/aluno/treinos")
        self.assertEqual(resposta.status_code, 401)


if __name__ == "__main__":
    unittest.main()
