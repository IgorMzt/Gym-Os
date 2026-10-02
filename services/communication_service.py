"""V6.15 — central de comunicacao, notificacoes e entrega push."""
from datetime import datetime
import database
from services import push_service

CATEGORIAS={'GERAL','FINANCEIRO','TREINO','SISTEMA'}
PRIORIDADES={'BAIXA','NORMAL','ALTA','URGENTE'}
PUBLICOS={'TODOS','ACADEMIA','ALUNO'}

def _bool(v): return bool(int(v)) if isinstance(v,(int,str)) and str(v).isdigit() else bool(v)

def normalizar_comunicado(dados, autor_usuario_id=None):
    titulo=str(dados.get('titulo') or '').strip(); corpo=str(dados.get('corpo') or '').strip()
    if len(titulo)<3: raise ValueError('Informe um titulo com pelo menos 3 caracteres.')
    if len(corpo)<3: raise ValueError('Informe o conteudo do comunicado.')
    categoria=str(dados.get('categoria') or 'GERAL').upper(); prioridade=str(dados.get('prioridade') or 'NORMAL').upper(); publico=str(dados.get('publico_tipo') or 'TODOS').upper(); status=str(dados.get('status') or 'RASCUNHO').upper()
    if categoria not in CATEGORIAS: raise ValueError('Categoria invalida.')
    if prioridade not in PRIORIDADES: raise ValueError('Prioridade invalida.')
    if publico not in PUBLICOS: raise ValueError('Publico invalido.')
    if status not in {'RASCUNHO','AGENDADO','PUBLICADO','EXPIRADO'}: raise ValueError('Status invalido.')
    pessoa_id=int(dados.get('pessoa_id')) if str(dados.get('pessoa_id') or '').isdigit() else None
    if publico=='ALUNO' and not pessoa_id: raise ValueError('Selecione um aluno.')
    return {'titulo':titulo,'corpo':corpo,'categoria':categoria,'prioridade':prioridade,'publico_tipo':publico,'pessoa_id':pessoa_id,'status':status,'publicar_em':dados.get('publicar_em') or None,'expirar_em':dados.get('expirar_em') or None,'autor_usuario_id':autor_usuario_id}

def criar(dados,autor_usuario_id=None): return database.criar_comunicado(normalizar_comunicado(dados,autor_usuario_id))
def atualizar(cid,dados): database.atualizar_comunicado(cid,normalizar_comunicado(dados,dados.get('autor_usuario_id')))

def _preferencia_permite(prefs,categoria):
    key={'GERAL':'comunicados','FINANCEIRO':'financeiro','TREINO':'treino','SISTEMA':'sistema'}.get(categoria,'comunicados')
    return bool(prefs.get(key,1))

def notificar_aluno(pessoa_id,titulo,corpo,*,categoria='SISTEMA',prioridade='NORMAL',url='/home',tipo='SISTEMA',comunicado_id=None):
    prefs=database.preferencias_notificacao(pessoa_id)
    if not _preferencia_permite(prefs,categoria): return {'criada':False,'push':False}
    nid=database.criar_notificacao(pessoa_id,titulo,corpo,tipo=tipo,categoria=categoria,prioridade=prioridade,url=url,comunicado_id=comunicado_id)
    enviado=False
    if prefs.get('push',1):
        r=push_service.enviar_para_aluno(pessoa_id,titulo,corpo,{'url':url,'tipo':tipo,'notificacao_id':nid,'categoria':categoria}); enviado=bool(r.get('enviadas'))
    return {'criada':True,'id':nid,'push':enviado}

def publicar(comunicado_id):
    c=database.obter_comunicado(comunicado_id)
    if not c: raise ValueError('Comunicado nao encontrado.')
    if c.get('expirar_em') and str(c['expirar_em'])[:16] < datetime.now().strftime('%Y-%m-%dT%H:%M'): raise ValueError('O comunicado ja expirou.')
    destinos=database.listar_destinatarios_comunicado(c); enviados=0
    for p in destinos:
        r=notificar_aluno(p['id'],c['titulo'],c['corpo'],categoria=c['categoria'],prioridade=c['prioridade'],url='/notificacoes',tipo='COMUNICADO',comunicado_id=c['id'])
        enviados += 1 if r.get('criada') else 0
    c['status']='PUBLICADO'; database.atualizar_comunicado(c['id'],c)
    return {'destinatarios':len(destinos),'notificacoes':enviados}

def processar_agendados():
    agora=datetime.now().strftime('%Y-%m-%dT%H:%M'); total=0
    for c in database.listar_comunicados(500):
        if c.get('status')=='AGENDADO' and c.get('publicar_em') and str(c['publicar_em'])[:16] <= agora:
            publicar(c['id']); total+=1
    return total
