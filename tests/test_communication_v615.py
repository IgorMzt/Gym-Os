import tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import database
from services import communication_service

class CommunicationV615Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.ob=database.DATABASE_BACKEND; self.op=database.DB_PATH
        database.DATABASE_BACKEND='sqlite'; database.DB_PATH=Path(self.tmp.name)/'v615.db'; database.set_tenant_context(1,1); database.criar_tabelas()
        plano=database.listar_planos(True)[0]
        self.aluno=database.adicionar_pessoa({'nome':'Aluno Com','cpf':'52998224725','matricula':'COM1','plano':plano['nome'],'plano_id':plano['id'],'data_inicio':'2026-10-01','data_vencimento':'2026-11-01','status_financeiro':'EM_DIA','liberado':True},[np.zeros(128)])
    def tearDown(self): database.DATABASE_BACKEND=self.ob; database.DB_PATH=self.op; database.set_tenant_context(1,1); self.tmp.cleanup()
    def test_schema_25(self):
        self.assertEqual(database.SCHEMA_VERSION,25); c=database.conectar()
        try:
            self.assertIsNotNone(c.execute("SELECT 1 FROM database_migrations WHERE migration_key='schema-25-comunicacao'").fetchone())
            self.assertIsNotNone(c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='notificacoes'").fetchone())
        finally:c.close()
    @patch('services.communication_service.push_service.enviar_para_aluno',return_value={'enviadas':1})
    def test_publicacao_cria_central_e_push(self,push):
        cid=communication_service.criar({'titulo':'Feriado','corpo':'Horario especial','categoria':'GERAL','publico_tipo':'TODOS'},1)
        r=communication_service.publicar(cid); self.assertEqual(r['notificacoes'],1); self.assertEqual(database.contar_notificacoes_nao_lidas(self.aluno),1); push.assert_called_once()
    def test_ler_notificacao(self):
        nid=database.criar_notificacao(self.aluno,'Oi','Mensagem'); self.assertEqual(database.contar_notificacoes_nao_lidas(self.aluno),1); database.marcar_notificacao_lida(self.aluno,nid); self.assertEqual(database.contar_notificacoes_nao_lidas(self.aluno),0)
    @patch('services.communication_service.push_service.enviar_para_aluno',return_value={'enviadas':1})
    def test_preferencia_bloqueia_categoria(self,push):
        database.salvar_preferencias_notificacao(self.aluno,{'comunicados':True,'financeiro':False,'treino':True,'sistema':True,'push':True}); r=communication_service.notificar_aluno(self.aluno,'Cobrança','Teste',categoria='FINANCEIRO'); self.assertFalse(r['criada']); push.assert_not_called()
    def test_isolamento_tenant(self):
        cid=communication_service.criar({'titulo':'Tenant 1','corpo':'Somente aqui'},1); a2=database.criar_academia('Outra','outra'); u2=database.listar_unidades(a2['id'])[0]; database.set_tenant_context(a2['id'],u2['id']); self.assertIsNone(database.obter_comunicado(cid)); self.assertEqual(database.listar_comunicados(),[])
if __name__=='__main__':unittest.main()
