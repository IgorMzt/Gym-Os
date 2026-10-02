from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for
import database
from services import communication_service
from services.permissions import login_obrigatorio, papel_requerido

comunicacao_bp=Blueprint('comunicacao',__name__)

@comunicacao_bp.get('/comunicacao')
@login_obrigatorio
def pagina_comunicacao():
    communication_service.processar_agendados()
    return render_template('comunicacao.html',comunicados=database.listar_comunicados(),alunos=database.listar_pessoas())

@comunicacao_bp.post('/api/comunicacao')
@papel_requerido('ADMIN','RECEPCAO')
def criar_comunicado():
    d=request.get_json(silent=True) or {}; d['status']='RASCUNHO'
    try:
        cid=communication_service.criar(d,int(session.get('usuario_id'))); database.registrar_log_admin('COMUNICADO_CRIADO',str(cid),d.get('titulo'),request.remote_addr); return jsonify({'sucesso':True,'id':cid})
    except ValueError as e: return jsonify({'sucesso':False,'erro':str(e)}),400

@comunicacao_bp.put('/api/comunicacao/<int:cid>')
@papel_requerido('ADMIN','RECEPCAO')
def editar_comunicado(cid):
    if not database.obter_comunicado(cid): return jsonify({'sucesso':False,'erro':'Comunicado nao encontrado.'}),404
    try: communication_service.atualizar(cid,request.get_json(silent=True) or {}); return jsonify({'sucesso':True})
    except ValueError as e: return jsonify({'sucesso':False,'erro':str(e)}),400

@comunicacao_bp.post('/api/comunicacao/<int:cid>/publicar')
@papel_requerido('ADMIN','RECEPCAO')
def publicar_comunicado(cid):
    try:
        r=communication_service.publicar(cid); database.registrar_log_admin('COMUNICADO_PUBLICADO',str(cid),f"{r['notificacoes']} notificacoes",request.remote_addr); return jsonify({'sucesso':True,**r})
    except ValueError as e: return jsonify({'sucesso':False,'erro':str(e)}),400

@comunicacao_bp.post('/api/comunicacao/<int:cid>/agendar')
@papel_requerido('ADMIN','RECEPCAO')
def agendar_comunicado(cid):
    c=database.obter_comunicado(cid); d=request.get_json(silent=True) or {}
    if not c: return jsonify({'sucesso':False,'erro':'Comunicado nao encontrado.'}),404
    c.update(d); c['status']='AGENDADO'
    try: communication_service.atualizar(cid,c); return jsonify({'sucesso':True})
    except ValueError as e: return jsonify({'sucesso':False,'erro':str(e)}),400

@comunicacao_bp.delete('/api/comunicacao/<int:cid>')
@papel_requerido('ADMIN')
def excluir_comunicado(cid):
    database.excluir_comunicado(cid); database.registrar_log_admin('COMUNICADO_EXCLUIDO',str(cid),None,request.remote_addr); return jsonify({'sucesso':True})

@comunicacao_bp.post('/api/professor/alunos/<int:pessoa_id>/mensagem')
@papel_requerido('PROFESSOR')
def professor_mensagem(pessoa_id):
    from services import professor_service
    if not professor_service.pode_acessar_aluno(int(session.get('usuario_id')),pessoa_id): return jsonify({'sucesso':False,'erro':'Aluno indisponivel.'}),403
    d=request.get_json(silent=True) or {}; corpo=str(d.get('corpo') or '').strip()
    if len(corpo)<2: return jsonify({'sucesso':False,'erro':'Digite uma mensagem.'}),400
    r=communication_service.notificar_aluno(pessoa_id,'Mensagem do seu professor',corpo,categoria='TREINO',tipo='PROFESSOR',url='/notificacoes')
    return jsonify({'sucesso':True,**r})
