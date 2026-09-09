import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

import numpy as np
from flask import Flask

import database
from routes.api import api_auth_bp, api_aluno_bp, api_treinos_bp, api_experiencia_bp
from services import auth_service


class MobileExperienceApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original_path = database.DB_PATH
        self.original_backend = database.DATABASE_BACKEND
        database.DATABASE_BACKEND = "sqlite"
        database.DB_PATH = Path(self.tmp.name) / "mobile-experience.db"
        database.criar_tabelas()
        plano = database.listar_planos(True)[0]
        self.pessoa_id = database.adicionar_pessoa({
            "nome": "Aluno Experiencia", "cpf": "52998224725", "matricula": "MOBEXP",
            "plano": plano["nome"], "plano_id": plano["id"], "data_inicio": date.today().isoformat(),
            "data_vencimento": (date.today() + timedelta(days=30)).isoformat(),
            "status_financeiro": "EM_DIA", "liberado": True,
        }, encodings=[np.zeros(128, dtype=float)])
        database.salvar_acesso_aluno(self.pessoa_id, "mobileexp", auth_service.hash_senha("senha123"), True)
        exercicio_id = database.criar_exercicio({"nome":"Agachamento guiado","grupo_muscular":"Pernas","ativo":True})
        ficha_id = database.criar_ficha_treino({
            "pessoa_id": self.pessoa_id, "nome":"Ficha Experiencia", "ativo":True,
            "treinos":[{"nome":"Treino A","exercicios":[{"exercicio_id":exercicio_id,"series":3,"repeticoes":"10","carga":"40 kg","descanso_segundos":60}]}],
        })
        self.treino_id = database.obter_ficha_treino(ficha_id)["treinos"][0]["id"]
        self.sessao_id, _ = database.criar_sessao_treino(self.pessoa_id, self.treino_id, None, "ALUNO_APP")
        sessao = database.obter_sessao_treino(self.sessao_id)
        database.atualizar_item_sessao(sessao["itens"][0]["id"], {
            "concluido": True, "series_realizadas": 3, "repeticoes_realizadas": "10", "carga_realizada": "45 kg"
        })
        database.concluir_sessao_treino(self.sessao_id, "Treino bom")

        app = Flask(__name__)
        app.secret_key = "segredo-mobile-experience"
        app.register_blueprint(api_auth_bp)
        app.register_blueprint(api_aluno_bp)
        app.register_blueprint(api_treinos_bp)
        app.register_blueprint(api_experiencia_bp)
        self.client = app.test_client()
        login = self.client.post("/api/v1/auth/login", json={"login":"mobileexp","senha":"senha123"}).get_json()
        self.headers = {"Authorization": f"Bearer {login['access_token']}"}

    def tearDown(self):
        database.DB_PATH = self.original_path
        database.DATABASE_BACKEND = self.original_backend
        self.tmp.cleanup()

    def test_schema_21(self):
        self.assertEqual(database.SCHEMA_VERSION, 21)
        conn = database.conectar()
        try:
            tabela = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mobile_aluno_preferencias'").fetchone()
            self.assertIsNotNone(tabela)
            colunas = {r[1] for r in conn.execute("PRAGMA table_info(treino_sessoes)")}
            self.assertIn("percepcao_esforco", colunas)
            self.assertIn("feedback_mobile", colunas)
        finally:
            conn.close()

    def test_home_inteligente_e_preferencias(self):
        resp = self.client.get("/api/v1/aluno/experiencia", headers=self.headers)
        self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
        dados = resp.get_json()
        self.assertEqual(dados["semana"]["realizados"], 1)
        self.assertEqual(dados["semana"]["meta"], 4)
        self.assertEqual(dados["total_treinos"], 1)
        self.assertEqual(dados["proximo_treino"]["id"], self.treino_id)

        salvo = self.client.put("/api/v1/aluno/preferencias", headers=self.headers, json={
            "meta_semanal": 5, "lembrete_treino_ativo": True, "lembrete_treino_hora": "20:30"
        })
        self.assertEqual(salvo.status_code, 200, salvo.get_data(as_text=True))
        prefs = salvo.get_json()["preferencias"]
        self.assertEqual(prefs["meta_semanal"], 5)
        self.assertEqual(prefs["lembrete_treino_ativo"], 1)
        self.assertEqual(prefs["lembrete_treino_hora"], "20:30")

    def test_resumo_e_feedback_pos_treino(self):
        resumo = self.client.get(f"/api/v1/aluno/execucoes/{self.sessao_id}/resumo", headers=self.headers)
        self.assertEqual(resumo.status_code, 200, resumo.get_data(as_text=True))
        self.assertGreater(resumo.get_json()["resumo"]["volume_kg"], 0)

        feedback = self.client.post(f"/api/v1/aluno/execucoes/{self.sessao_id}/feedback", headers=self.headers, json={
            "percepcao_esforco": 4, "comentario": "Treino forte e controlado"
        })
        self.assertEqual(feedback.status_code, 200, feedback.get_data(as_text=True))
        atualizado = database.obter_sessao_treino(self.sessao_id)
        self.assertEqual(atualizado["percepcao_esforco"], 4)
        self.assertEqual(atualizado["feedback_mobile"], "Treino forte e controlado")

    def test_experiencia_exige_bearer(self):
        self.assertEqual(self.client.get("/api/v1/aluno/experiencia").status_code, 401)
        self.assertEqual(self.client.get("/api/v1/aluno/preferencias").status_code, 401)


if __name__ == "__main__":
    unittest.main()
