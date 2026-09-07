import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

import numpy as np
from flask import Flask

import database
from routes.api import api_auth_bp, api_aluno_bp, api_historico_bp, api_evolucao_bp
from services import auth_service


class MobileHistoryEvolutionApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original_path = database.DB_PATH
        database.DB_PATH = Path(self.tmp.name) / "mobile-history-evolution.db"
        database.criar_tabelas()
        plano = database.listar_planos(True)[0]
        self.pessoa_id = database.adicionar_pessoa({
            "nome": "Aluno Evolucao Mobile", "cpf": "52998224725", "matricula": "MOBEVO",
            "plano": plano["nome"], "plano_id": plano["id"], "data_inicio": date.today().isoformat(),
            "data_vencimento": (date.today() + timedelta(days=30)).isoformat(),
            "status_financeiro": "EM_DIA", "liberado": True,
        }, encodings=[np.zeros(128, dtype=float)])
        database.salvar_acesso_aluno(self.pessoa_id, "mobileevo", auth_service.hash_senha("senha123"), True)
        exercicio_id = database.criar_exercicio({"nome":"Remada teste","grupo_muscular":"Costas","ativo":True})
        ficha_id = database.criar_ficha_treino({
            "pessoa_id": self.pessoa_id, "nome":"Ficha Evolucao", "ativo":True,
            "treinos":[{"nome":"Treino B","exercicios":[{"exercicio_id":exercicio_id,"series":3,"repeticoes":"12","carga":"30 kg","descanso_segundos":45}]}],
        })
        treino_id = database.obter_ficha_treino(ficha_id)["treinos"][0]["id"]
        self.sessao_id, _ = database.criar_sessao_treino(self.pessoa_id, treino_id, None, "ALUNO_APP")
        sessao = database.obter_sessao_treino(self.sessao_id)
        database.atualizar_item_sessao(sessao["itens"][0]["id"], {"concluido":True,"series_realizadas":3,"repeticoes_realizadas":"12","carga_realizada":"32 kg"})
        database.concluir_sessao_treino(self.sessao_id, "Treino concluido")
        self.av1 = database.criar_avaliacao_fisica({"pessoa_id":self.pessoa_id,"data_avaliacao":"2026-08-01","peso_kg":84.0,"altura_cm":196.0,"imc":21.87,"gordura_percentual":14.0,"massa_gorda_kg":11.76,"massa_magra_kg":72.24,"braco_cm":36.0,"cintura_cm":82.0,"coxa_cm":58.0})
        self.av2 = database.criar_avaliacao_fisica({"pessoa_id":self.pessoa_id,"data_avaliacao":"2026-09-01","peso_kg":85.0,"altura_cm":196.0,"imc":22.13,"gordura_percentual":13.0,"massa_gorda_kg":11.05,"massa_magra_kg":73.95,"braco_cm":37.0,"cintura_cm":80.0,"coxa_cm":59.0})
        app = Flask(__name__); app.secret_key = "segredo-mobile-history"
        app.register_blueprint(api_auth_bp); app.register_blueprint(api_aluno_bp); app.register_blueprint(api_historico_bp); app.register_blueprint(api_evolucao_bp)
        self.client = app.test_client()
        login = self.client.post("/api/v1/auth/login", json={"login":"mobileevo","senha":"senha123"}).get_json()
        self.headers = {"Authorization": f"Bearer {login['access_token']}"}

    def tearDown(self):
        database.DB_PATH = self.original_path
        self.tmp.cleanup()

    def test_historico_e_detalhe(self):
        resp = self.client.get("/api/v1/aluno/historico", headers=self.headers)
        self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
        dados = resp.get_json()
        self.assertEqual(dados["estatisticas"]["concluidos"], 1)
        self.assertEqual(dados["sessoes"][0]["id"], self.sessao_id)
        detalhe = self.client.get(f"/api/v1/aluno/historico/{self.sessao_id}", headers=self.headers)
        self.assertEqual(detalhe.status_code, 200, detalhe.get_data(as_text=True))
        self.assertEqual(detalhe.get_json()["sessao"]["itens"][0]["carga_realizada"], "32 kg")

    def test_evolucao_e_comparacao(self):
        resp = self.client.get("/api/v1/aluno/evolucao", headers=self.headers)
        self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
        dados = resp.get_json()
        self.assertEqual(len(dados["avaliacoes"]), 2)
        self.assertEqual(dados["comparacao"]["peso_kg"]["delta"], 1.0)
        detalhe = self.client.get(f"/api/v1/aluno/evolucao/{self.av2}", headers=self.headers)
        self.assertEqual(detalhe.status_code, 200)
        self.assertEqual(detalhe.get_json()["avaliacao"]["peso_kg"], 85.0)

    def test_endpoints_exigem_bearer(self):
        self.assertEqual(self.client.get("/api/v1/aluno/historico").status_code, 401)
        self.assertEqual(self.client.get("/api/v1/aluno/evolucao").status_code, 401)


if __name__ == "__main__":
    unittest.main()
