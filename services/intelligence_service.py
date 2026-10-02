"""V6.16 — inteligencia operacional explicavel e automacoes seguras."""
from datetime import datetime, timedelta
import database
from services import communication_service


def _dt(v):
    if not v: return None
    try: return datetime.fromisoformat(str(v).replace('Z','+00:00')).replace(tzinfo=None)
    except ValueError: return None


def analisar(*, persistir=True):
    agora=datetime.now(); insights=[]
    for p in database.listar_pessoas_inteligencia():
        acessos=database.acessos_pessoa_recentes(p['id'],100)
        datas=[_dt(a.get('data_hora')) for a in acessos if str(a.get('status') or '').upper() in {'LIBERADO','OK','APROVADO'}]
        datas=[d for d in datas if d]
        ultimo=max(datas) if datas else None
        dias=(agora-ultimo).days if ultimo else 999
        if dias >= 21:
            score=min(100,55 + min(dias,45))
            insights.append({'pessoa_id':p['id'],'regra_codigo':'RISCO_INATIVIDADE','severidade':'ALTA' if dias>=30 else 'MEDIA','score':score,'titulo':'Risco de abandono','descricao':f"{p['nome']} esta sem acesso registrado ha {dias if dias<999 else 'mais de 90'} dias.",'dados':{'dias_sem_acesso':dias}})
        elif len([d for d in datas if d >= agora-timedelta(days=14)]) <= 1 and len([d for d in datas if agora-timedelta(days=28) <= d < agora-timedelta(days=14)]) >= 3:
            insights.append({'pessoa_id':p['id'],'regra_codigo':'QUEDA_FREQUENCIA','severidade':'MEDIA','score':65,'titulo':'Queda de frequencia','descricao':f"{p['nome']} reduziu significativamente a frequencia nas ultimas duas semanas.",'dados':{}})
        if str(p.get('status_financeiro') or '').upper() not in {'EM_DIA','PAGO','OK',''}:
            insights.append({'pessoa_id':p['id'],'regra_codigo':'RISCO_FINANCEIRO','severidade':'ALTA','score':80,'titulo':'Atencao financeira','descricao':f"{p['nome']} possui status financeiro {p.get('status_financeiro')}.",'dados':{'status':p.get('status_financeiro')}})
    if persistir: database.substituir_insights_inteligencia(insights)
    return sorted(insights,key=lambda x:x['score'],reverse=True)


def executar_acao(insight_id:int, acao='NOTIFICAR'):
    item=next((x for x in database.listar_insights_inteligencia(500) if int(x['id'])==int(insight_id)),None)
    if not item: raise ValueError('Insight nao encontrado.')
    if acao!='NOTIFICAR': raise ValueError('Acao nao suportada.')
    if not item.get('pessoa_id'): raise ValueError('Insight sem aluno associado.')
    r=communication_service.notificar_aluno(int(item['pessoa_id']),'Sentimos sua falta', 'Percebemos uma mudanca na sua rotina. Se precisar de ajuda para retomar seus treinos, fale com nossa equipe.',categoria='GERAL',tipo='AUTOMACAO',url='/notificacoes')
    database.registrar_execucao_automacao(item['regra_codigo'],item['pessoa_id'],acao,'OK' if r.get('criada') else 'IGNORADA',item['titulo'])
    return r


def resumo():
    itens=database.listar_insights_inteligencia(200)
    return {'total':len(itens),'alta':sum(1 for x in itens if x['severidade']=='ALTA'),'media':sum(1 for x in itens if x['severidade']=='MEDIA'),'itens':itens}
