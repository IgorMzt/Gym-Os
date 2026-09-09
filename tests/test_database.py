import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import database


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original_path = database.DB_PATH
        self.original_backend = database.DATABASE_BACKEND
        database.DATABASE_BACKEND = "sqlite"
        database.DB_PATH = Path(self.tmp.name) / "teste.db"
        database.criar_tabelas()

    def tearDown(self):
        database.DB_PATH = self.original_path
        database.DATABASE_BACKEND = self.original_backend
        self.tmp.cleanup()

    def _pessoa(self, **overrides):
        base = {
            "liberado": True,
            "status_financeiro": "EM_DIA",
            "data_vencimento": (date.today() + timedelta(days=10)).isoformat(),
        }
        base.update(overrides)
        return base

    def test_acesso_permitido(self):
        ok, _ = database.acesso_permitido(self._pessoa())
        self.assertTrue(ok)
        ok, motivo = database.acesso_permitido(self._pessoa(liberado=False))
        self.assertFalse(ok)
        self.assertIn("bloqueado", motivo.lower())

    def test_plano_vencido_dentro_da_tolerancia_permite(self):
        ok, _ = database.acesso_permitido(
            self._pessoa(data_vencimento=(date.today() - timedelta(days=1)).isoformat())
        )
        self.assertTrue(ok)

    def test_plano_vencido_apos_tolerancia_bloqueia(self):
        ok, motivo = database.acesso_permitido(
            self._pessoa(data_vencimento=(date.today() - timedelta(days=6)).isoformat())
        )
        self.assertFalse(ok)
        self.assertIn("vencido", motivo.lower())

    def test_deduplicacao_logs(self):
        self.assertTrue(database.registrar_log(None, "Desconhecido", "NEGADO", "Teste", janela_segundos=5, catraca_id=1, catraca_nome="Catraca"))
        self.assertFalse(database.registrar_log(None, "Desconhecido", "NEGADO", "Teste", janela_segundos=5, catraca_id=1, catraca_nome="Catraca"))

    def test_multiplas_amostras_faciais(self):
        plano = database.listar_planos(True)[0]
        dados = {
            "nome": "Aluno Teste", "cpf": "52998224725", "matricula": "000001",
            "plano": plano["nome"], "plano_id": plano["id"], "data_inicio": date.today().isoformat(),
            "data_vencimento": (date.today()+timedelta(days=30)).isoformat(), "status_financeiro": "EM_DIA",
            "liberado": True,
        }
        enc = [np.zeros(128), np.ones(128)]
        pid = database.adicionar_pessoa(dados, encodings=enc)
        self.assertEqual(len(database.listar_amostras_faciais()[pid]), 2)


if __name__ == "__main__":
    unittest.main()
