import tempfile
import unittest
from pathlib import Path

import numpy as np

import database
import config_service
from services import dashboard_service


class MultiAcademiaV613Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_BACKEND = "sqlite"
        database.DB_PATH = Path(self.tmp.name) / "gym-v613.db"
        database.set_tenant_context(1, 1)
        database.criar_tabelas()
        config_service.invalidate_all()

    def tearDown(self):
        database.set_tenant_context(1, 1)
        config_service.invalidate_all()
        self.tmp.cleanup()

    def _pessoa(self, nome, cpf, matricula, plano):
        return database.adicionar_pessoa({
            "nome": nome,
            "cpf": cpf,
            "data_nascimento": None,
            "sexo": None,
            "telefone": None,
            "email": None,
            "matricula": matricula,
            "plano": plano["nome"],
            "plano_id": plano["id"],
            "data_inicio": "2026-01-01",
            "data_vencimento": "2027-01-01",
            "status_financeiro": "EM_DIA",
            "observacoes": None,
            "liberado": True,
        }, [np.zeros(128)])

    def test_schema_23_cria_academia_e_unidade_principal(self):
        self.assertEqual(database.SCHEMA_VERSION, 25)
        principal = database.obter_academia_por_slug("principal")
        self.assertIsNotNone(principal)
        unidade = database.obter_unidade_por_codigo(principal["id"], "principal")
        self.assertIsNotNone(unidade)
        conn = database.conectar()
        try:
            versao = conn.execute("SELECT valor FROM schema_meta WHERE chave='schema_version'").fetchone()[0]
            migracao = conn.execute("SELECT 1 FROM database_migrations WHERE migration_key='schema-23-multiacademia'").fetchone()
        finally:
            conn.close()
        self.assertEqual(str(versao), "25")
        self.assertIsNotNone(migracao)

    def test_alunos_usuarios_e_configuracoes_sao_isolados(self):
        plano1 = database.listar_planos(ativos_apenas=True)[0]
        p1 = self._pessoa("Aluno Principal", "111", "P001", plano1)
        database.criar_usuario("recepcao-principal", "Recepcao 1", "hash", "RECEPCAO")
        database.salvar_configuracoes({"tempo_resultado_ms": "1111"})

        academia2 = database.criar_academia("Academia Dois", "academia-dois")
        unidade2 = database.listar_unidades(academia2["id"])[0]
        database.set_tenant_context(academia2["id"], unidade2["id"])
        plano2_id = database.salvar_plano({
            "nome": "Mensal Academia Dois",
            "valor_centavos": 9900,
            "duracao_dias": 30,
            "descricao": None,
            "ativo": True,
        })
        plano2 = database.obter_plano(plano2_id)
        p2 = self._pessoa("Aluno Dois", "222", "D001", plano2)
        database.criar_usuario("recepcao-dois", "Recepcao 2", "hash", "RECEPCAO")
        database.salvar_configuracoes({"tempo_resultado_ms": "2222"})

        self.assertEqual([p["id"] for p in database.listar_pessoas()], [p2])
        self.assertEqual([u["login"] for u in database.listar_usuarios()], ["recepcao-dois"])
        self.assertEqual(database.obter_configuracao("tempo_resultado_ms"), "2222")
        self.assertIsNone(database.obter_pessoa(p1))

        database.set_tenant_context(1, 1)
        self.assertEqual([p["id"] for p in database.listar_pessoas()], [p1])
        self.assertEqual([u["login"] for u in database.listar_usuarios()], ["recepcao-principal"])
        self.assertEqual(database.obter_configuracao("tempo_resultado_ms"), "1111")
        self.assertIsNone(database.obter_pessoa(p2))

    def test_agent_fica_vinculado_a_unidade(self):
        academia2 = database.criar_academia("Academia Agent", "agent-gym")
        unidade2 = database.listar_unidades(academia2["id"])[0]
        database.set_tenant_context(academia2["id"], unidade2["id"])
        agente = database.registrar_agente(
            agent_uid="pc-agent-gym",
            nome="PC Agent Gym",
            token_hash="hash-token",
            academia_id=academia2["id"],
            unidade_id=unidade2["id"],
        )
        self.assertEqual(agente["academia_id"], academia2["id"])
        self.assertEqual(agente["unidade_id"], unidade2["id"])
        self.assertEqual(len(database.listar_agentes()), 1)
        database.set_tenant_context(1, 1)
        self.assertEqual(database.listar_agentes(), [])

    def test_refresh_mobile_preserva_tenant_da_sessao(self):
        academia2 = database.criar_academia("Academia Mobile", "mobile-gym")
        unidade2 = database.listar_unidades(academia2["id"])[0]
        database.set_tenant_context(academia2["id"], unidade2["id"])
        plano = database.listar_planos(ativos_apenas=True)[0]
        pessoa_id = self._pessoa("Aluno Mobile", "333", "M001", plano)
        acesso_id = database.salvar_acesso_aluno(pessoa_id, "aluno-mobile", "hash-senha")
        database.criar_refresh_token_mobile(acesso_id, pessoa_id, "hash-antigo", "2999-01-01T00:00:00+00:00")

        # Simula request de refresh chegando sem contexto previamente resolvido.
        database.set_tenant_context(1, 1)
        sessao = database.rotacionar_refresh_token_mobile(
            "hash-antigo", "hash-novo", "2999-01-02T00:00:00+00:00"
        )
        self.assertIsNotNone(sessao)
        self.assertEqual(sessao["academia_id"], academia2["id"])
        self.assertEqual(sessao["unidade_id"], unidade2["id"])

    def test_dashboard_fluxo_e_financeiro_respeitam_tenant(self):
        plano1 = database.listar_planos(ativos_apenas=True)[0]
        p1 = self._pessoa("Aluno Financeiro Principal", "444", "F001", plano1)
        database.registrar_log(p1, "Aluno Financeiro Principal", "LIBERADO", "Teste", janela_segundos=0)
        cobranca1 = database.criar_cobranca_local(p1, plano1["id"], "pay-principal", "cus-principal", 12345, "2026-12-01", None, None)
        conn = database.conectar()
        try:
            conn.execute("UPDATE cobrancas SET status='PAGO', data_pagamento=CURRENT_TIMESTAMP WHERE id=?", (cobranca1,))
            conn.commit()
        finally:
            conn.close()

        academia2 = database.criar_academia("Academia Dashboard", "dashboard-gym")
        unidade2 = database.listar_unidades(academia2["id"])[0]
        database.set_tenant_context(academia2["id"], unidade2["id"])
        dash2 = dashboard_service.obter_dashboard()
        self.assertEqual(dash2["kpis"]["tentativas_hoje"], 0)
        self.assertEqual(dash2["feed"], [])
        self.assertEqual(dash2["financeiro"]["receita_hoje_centavos"], 0)
        self.assertEqual(dash2["financeiro"]["pagamentos_recentes"], [])

        database.set_tenant_context(1, 1)
        dash1 = dashboard_service.obter_dashboard()
        self.assertGreaterEqual(dash1["kpis"]["tentativas_hoje"], 1)
        self.assertTrue(any(item["pessoa_id"] == p1 for item in dash1["feed"]))
        self.assertGreaterEqual(dash1["financeiro"]["receita_hoje_centavos"], 12345)
        self.assertTrue(any(item["pessoa_id"] == p1 for item in dash1["financeiro"]["pagamentos_recentes"]))


if __name__ == "__main__":
    unittest.main()
