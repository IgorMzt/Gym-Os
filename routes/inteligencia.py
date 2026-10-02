from flask import Blueprint, jsonify, render_template, request
import database
from services import intelligence_service
from services.permissions import papel_requerido

inteligencia_bp=Blueprint('inteligencia',__name__)

@inteligencia_bp.get('/inteligencia')
@papel_requerido('ADMIN','RECEPCAO')
def pagina():
    return render_template('inteligencia.html',resumo=intelligence_service.resumo())

@inteligencia_bp.post('/api/inteligencia/analisar')
@papel_requerido('ADMIN')
def analisar():
    itens=intelligence_service.analisar(persistir=True)
    database.registrar_log_admin('INTELIGENCIA_ANALISADA',None,f'{len(itens)} insights',request.remote_addr)
    return jsonify({'sucesso':True,'total':len(itens),'insights':itens})

@inteligencia_bp.post('/api/inteligencia/<int:iid>/acao')
@papel_requerido('ADMIN','RECEPCAO')
def acao(iid):
    try: return jsonify({'sucesso':True,**intelligence_service.executar_acao(iid,(request.get_json(silent=True) or {}).get('acao','NOTIFICAR'))})
    except ValueError as e: return jsonify({'sucesso':False,'erro':str(e)}),400
