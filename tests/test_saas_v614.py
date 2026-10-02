import tempfile
import unittest
from pathlib import Path

import numpy as np

import database
from services import saas_service


class SaaSV614Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.DATABASE_BACKEND = "sqlite"
        database.DB_PATH = Path(self.tmp.name) / "gym-v614.db"
        database.set_tenant_context(1, 1)
        database.criar_tabelas()

    def tearDown(self):
        database.set_tenant_context(1, 1)
        self.tmp.cleanup()

    def _checkout(self, slug="pro", academia="Academia SaaS", codigo="academia-saas"):
        plano = saas_service.obter_plano(slug=slug)
        return saas_service.criar_checkout(
            plano_id=plano["id"],
            ciclo="MENSAL",
            academia_nome=academia,
            academia_slug=codigo,
            admin_nome="Admin SaaS",
            admin_login=f"admin-{codigo}",
            admin_email=f"{codigo}@example.com",
            admin_senha_hash="hash-teste",
        )

    def test_schema_24_e_seeds_saas(self):
        self.assertEqual(database.SCHEMA_VERSION, 24)
        planos = saas_service.listar_planos(publicos=True, ativos=True)
        self.assertEqual([p["slug"] for p in planos], ["start", "pro", "enterprise"])
        self.assertTrue(any(r["codigo"] == "branding" for r in saas_service.listar_recursos()))
        conn = database.conectar()
        try:
            versao = conn.execute("SELECT valor FROM schema_meta WHERE chave='schema_version'").fetchone()[0]
            migracao = conn.execute("SELECT 1 FROM database_migrations WHERE migration_key='schema-24-saas'").fetchone()
        finally:
            conn.close()
        self.assertEqual(str(versao), "24")
        self.assertIsNotNone(migracao)

    def test_checkout_provisiona_tenant_admin_e_assinatura(self):
        checkout = self._checkout()
        result = saas_service.provisionar_checkout(checkout["token"])
        academia_id = result["academia"]["id"]
        self.assertEqual(result["status"], "TRIAL")
        self.assertEqual(result["unidade"]["codigo"], "principal")
        assinatura = saas_service.assinatura_atual(academia_id)
        self.assertEqual(assinatura["plano_slug"], "pro")
        self.assertEqual(assinatura["status"], "TRIAL")
        database.set_tenant_context(academia_id, result["unidade"]["id"])
        usuarios = database.listar_usuarios()
        self.assertEqual(len(usuarios), 1)
        self.assertEqual(usuarios[0]["papel"], "ADMIN")

    def test_feature_flags_seguem_plano_e_legado_permanece_liberado(self):
        start = self._checkout("start", "Start Gym", "start-gym")
        start_result = saas_service.provisionar_checkout(start["token"])
        aid = start_result["academia"]["id"]
        self.assertTrue(saas_service.feature_enabled(aid, "financeiro"))
        self.assertFalse(saas_service.feature_enabled(aid, "biometria"))
        self.assertFalse(saas_service.feature_enabled(aid, "branding"))

        legado = database.criar_academia("Tenant Legado", "tenant-legado")
        self.assertTrue(saas_service.feature_enabled(legado["id"], "branding"))
        self.assertTrue(saas_service.feature_enabled(legado["id"], "agents"))

    def test_limite_de_alunos_do_plano_e_aplicado(self):
        start = saas_service.obter_plano(slug="start")
        saas_service.salvar_plano({**start, "max_alunos": 1, "publico": True, "ativo": True}, start["id"])
        checkout = self._checkout("start", "Limit Gym", "limit-gym")
        result = saas_service.provisionar_checkout(checkout["token"])
        database.set_tenant_context(result["academia"]["id"], result["unidade"]["id"])
        plano_operacional = database.listar_planos(ativos_apenas=True)[0]
        dados = {
            "nome": "Aluno 1", "cpf": "111", "data_nascimento": None, "sexo": None,
            "telefone": None, "email": None, "matricula": "L001", "plano": plano_operacional["nome"],
            "plano_id": plano_operacional["id"], "data_inicio": None, "data_vencimento": None,
            "status_financeiro": "EM_DIA", "observacoes": None, "liberado": True,
        }
        database.adicionar_pessoa(dados, [np.zeros(128)])
        dados2 = dict(dados, nome="Aluno 2", cpf="222", matricula="L002")
        with self.assertRaises(ValueError):
            database.adicionar_pessoa(dados2, [np.ones(128)])

    def test_cupom_cms_e_branding(self):
        pro = saas_service.obter_plano(slug="pro")
        saas_service.salvar_cupom({"codigo": "GYM20", "tipo": "PERCENTUAL", "valor": 20, "plano_id": pro["id"], "ativo": True})
        valor, cupom = saas_service.aplicar_cupom("gym20", pro["id"], 10000)
        self.assertEqual(valor, 8000)
        self.assertEqual(cupom["codigo"], "GYM20")

        saas_service.salvar_site_conteudo("hero_titulo", "Nova headline")
        self.assertEqual(saas_service.site_conteudo()["hero_titulo"], "Nova headline")

        saas_service.salvar_branding(1, {
            "nome_exibicao": "Iron Gym", "cor_primaria": "#112233", "cor_secundaria": "#223344",
            "cor_destaque": "#334455", "tema": "dark",
        })
        brand = saas_service.branding(1)
        self.assertEqual(brand["nome_exibicao"], "Iron Gym")
        self.assertEqual(brand["cor_primaria"], "#112233")

    def test_troca_de_plano_cria_historico(self):
        checkout = self._checkout("start", "Upgrade Gym", "upgrade-gym")
        result = saas_service.provisionar_checkout(checkout["token"])
        pro = saas_service.obter_plano(slug="pro")
        novo_id = saas_service.trocar_plano(result["academia"]["id"], pro["id"], "ANUAL")
        atual = saas_service.assinatura_atual(result["academia"]["id"])
        self.assertEqual(atual["id"], novo_id)
        self.assertEqual(atual["plano_slug"], "pro")
        self.assertEqual(atual["ciclo"], "ANUAL")
        historico = [s for s in saas_service.listar_assinaturas() if s["academia_id"] == result["academia"]["id"]]
        self.assertEqual(len(historico), 2)
        self.assertTrue(any(s["status"] == "CANCELADA" for s in historico))


if __name__ == "__main__":
    unittest.main()
