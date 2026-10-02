import unittest
from unittest.mock import patch
from datetime import datetime, timedelta
from services import intelligence_service

class IntelligenceV616Tests(unittest.TestCase):
    @patch('services.intelligence_service.database.acessos_pessoa_recentes')
    @patch('services.intelligence_service.database.listar_pessoas_inteligencia')
    def test_detecta_inatividade(self,pessoas,acessos):
        pessoas.return_value=[{'id':1,'nome':'Ana','liberado':1,'status_financeiro':'EM_DIA','data_vencimento':None}]
        acessos.return_value=[{'status':'LIBERADO','data_hora':(datetime.now()-timedelta(days=31)).isoformat()}]
        itens=intelligence_service.analisar(persistir=False)
        self.assertEqual(itens[0]['regra_codigo'],'RISCO_INATIVIDADE'); self.assertEqual(itens[0]['severidade'],'ALTA')

    @patch('services.intelligence_service.database.acessos_pessoa_recentes',return_value=[])
    @patch('services.intelligence_service.database.listar_pessoas_inteligencia')
    def test_detecta_financeiro(self,pessoas,_):
        pessoas.return_value=[{'id':2,'nome':'Bia','liberado':1,'status_financeiro':'ATRASADO','data_vencimento':None}]
        codigos={x['regra_codigo'] for x in intelligence_service.analisar(persistir=False)}
        self.assertIn('RISCO_FINANCEIRO',codigos)

    @patch('services.intelligence_service.database.substituir_insights_inteligencia')
    @patch('services.intelligence_service.database.acessos_pessoa_recentes',return_value=[])
    @patch('services.intelligence_service.database.listar_pessoas_inteligencia',return_value=[])
    def test_persiste_analise(self,_,__,salvar):
        intelligence_service.analisar(persistir=True); salvar.assert_called_once_with([])

    @patch('services.intelligence_service.communication_service.notificar_aluno',return_value={'criada':True})
    @patch('services.intelligence_service.database.registrar_execucao_automacao')
    @patch('services.intelligence_service.database.listar_insights_inteligencia')
    def test_acao_notifica(self,listar,registrar,notificar):
        listar.return_value=[{'id':9,'pessoa_id':4,'regra_codigo':'RISCO_INATIVIDADE','titulo':'Risco'}]
        r=intelligence_service.executar_acao(9); self.assertTrue(r['criada']); notificar.assert_called_once(); registrar.assert_called_once()

if __name__=='__main__': unittest.main()
