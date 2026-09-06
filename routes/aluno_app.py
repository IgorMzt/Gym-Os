import base64
import csv
import hashlib
import hmac
import io
import os
import re
import secrets
import sqlite3
import tempfile
import time
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

import cv2
import face_recognition
import numpy as np
from flask import Blueprint, Response, abort, current_app, jsonify, redirect, render_template, request, session, url_for, send_file

from services import dashboard_service, auth_service, professor_service, exercise_service, workout_service, execution_service, assessment_service
from services.permissions import login_obrigatorio, papel_requerido
from services.payments import AsaasGateway, GatewayError
import database
import config_service
import device_manager
import face_index
from validators import cpf_apenas_digitos, cpf_valido, data_iso, email_valido, parse_bool, parse_float, parse_int
from routes.common import (
    BASE_DIR, CREDENCIAL_PADRAO, DEFAULT_INTERVALO_LOG, DEFAULT_LIMIAR, DEFAULT_LIVENESS_JANELA,
    cfg_bool, cfg_float, cfg_int, decodificar_imagem, limpar_foto, salvar_foto,
    normalizar_dados_cadastro, resposta_pessoa, enriquecer_pessoa_plano,
    encontrar_melhor_pessoa, _chave_cliente, verificar_liveness, resetar_liveness,
    obter_catraca_atual, dados_config_catraca, filtros_historico_seguros,
    enriquecer_pessoa_recepcao, formatar_cpf, liveness_estado, _ip_cliente, professor_pode_gerir_aluno,
)

aluno_app_bp = Blueprint("aluno_app", __name__)

def _aluno_id_sessao():
    if session.get("usuario_papel") != "ALUNO":
        return None
    try:
        return int(session.get("aluno_id"))
    except (TypeError, ValueError):
        return None


def _dados_app_aluno(pessoa_id):
    pessoa = database.obter_pessoa(pessoa_id)
    if not pessoa:
        return None
    pessoa = enriquecer_pessoa_recepcao(pessoa, max(1,min(60,cfg_int("dias_alerta_vencimento",7))))
    ficha = database.obter_ficha_ativa_aluno(pessoa_id)
    sessao = database.obter_sessao_em_andamento_aluno(pessoa_id)
    professor = database.obter_professor_ativo_do_aluno(pessoa_id)
    sessoes = database.listar_sessoes_treino([pessoa_id], 8)
    avaliacoes = database.listar_avaliacoes_fisicas(pessoa_id)
    cobrancas = database.listar_cobrancas_pessoa(pessoa_id, 50)
    cobranca_aberta = database.obter_cobranca_aberta(pessoa_id)
    plano = database.obter_plano(pessoa.get("plano_id")) if pessoa.get("plano_id") else None
    return {
        "pessoa": pessoa, "ficha": ficha, "sessao": sessao,
        "professor": professor, "sessoes": sessoes,
        "avaliacoes": avaliacoes,
        "plano": plano, "cobrancas": cobrancas,
        "cobranca_aberta": cobranca_aberta,
        "asaas_configurado": AsaasGateway().configurado,
        "proximo_treino": database.proximo_treino_aluno(pessoa_id),
    }


@aluno_app_bp.route("/app")
@papel_requerido("ALUNO")
def aluno_app_inicio():
    pessoa_id = _aluno_id_sessao()
    dados = _dados_app_aluno(pessoa_id)
    if not dados:
        session.clear()
        return redirect(url_for("auth.pagina_login"))
    return render_template("aluno_app_inicio.html", **dados)


@aluno_app_bp.route("/app/treino")
@papel_requerido("ALUNO")
def aluno_app_treino():
    pessoa_id = _aluno_id_sessao()
    dados = _dados_app_aluno(pessoa_id)
    return render_template("aluno_app_treino.html", **dados)


@aluno_app_bp.route("/app/execucao/<int:sessao_id>")
@papel_requerido("ALUNO")
def aluno_app_execucao(sessao_id):
    sessao = database.obter_sessao_treino(sessao_id)
    if not sessao or int(sessao["pessoa_id"]) != int(_aluno_id_sessao()):
        abort(404)
    for item in sessao.get("itens", []):
        item["ultima_execucao"] = database.ultima_execucao_exercicio(
            int(sessao["pessoa_id"]), int(item["exercicio_id"])
        ) if item.get("exercicio_id") else None
    return render_template("aluno_app_execucao.html", sessao=sessao)


@aluno_app_bp.route("/app/historico")
@papel_requerido("ALUNO")
def aluno_app_historico():
    pessoa_id = _aluno_id_sessao()
    pessoa = database.obter_pessoa(pessoa_id)
    sessoes = database.listar_sessoes_treino([pessoa_id], 100)
    cargas = database.listar_ultimas_cargas_aluno(pessoa_id, 12)
    return render_template("aluno_app_historico.html", pessoa=pessoa, sessoes=sessoes, cargas=cargas)


@aluno_app_bp.route("/app/evolucao")
@papel_requerido("ALUNO")
def aluno_app_evolucao():
    pessoa_id = _aluno_id_sessao()
    pessoa = database.obter_pessoa(pessoa_id)
    avaliacoes = database.listar_avaliacoes_fisicas(pessoa_id)
    return render_template(
        "aluno_app_evolucao.html",
        pessoa=pessoa, avaliacoes=avaliacoes,
        comparacao=assessment_service.comparacao(avaliacoes)
    )


@aluno_app_bp.route("/app/perfil")
@papel_requerido("ALUNO")
def aluno_app_perfil():
    pessoa_id = _aluno_id_sessao()
    dados = _dados_app_aluno(pessoa_id)
    return render_template("aluno_app_perfil.html", **dados)


@aluno_app_bp.route("/app/financeiro")
@papel_requerido("ALUNO")
def aluno_app_financeiro():
    pessoa_id = _aluno_id_sessao()
    dados = _dados_app_aluno(pessoa_id)
    return render_template("aluno_app_financeiro.html", **dados)


@aluno_app_bp.route("/api/app/financeiro/status")
@papel_requerido("ALUNO")
def api_app_financeiro_status():
    pessoa_id = _aluno_id_sessao()
    pessoa = database.obter_pessoa(pessoa_id)
    if not pessoa:
        return jsonify({"sucesso":False,"erro":"Aluno não encontrado."}),404
    pessoa = enriquecer_pessoa_recepcao(
        pessoa, max(1,min(60,cfg_int("dias_alerta_vencimento",7)))
    )
    cobranca = database.obter_cobranca_aberta(pessoa_id)
    return jsonify({
        "sucesso":True,
        "status_financeiro":pessoa.get("status_financeiro"),
        "status_financeiro_efetivo":pessoa.get("status_financeiro_efetivo"),
        "status_operacional":pessoa.get("status_operacional"),
        "data_vencimento":pessoa.get("data_vencimento"),
        "cobranca": {
            "id":cobranca.get("id"),
            "status":cobranca.get("status"),
            "valor_centavos":cobranca.get("valor_centavos"),
            "vencimento":cobranca.get("vencimento_original"),
            "pix_payload":cobranca.get("pix_payload"),
            "pix_qr_base64":cobranca.get("pix_qr_base64"),
        } if cobranca else None
    })


@aluno_app_bp.route("/api/app/financeiro/pix", methods=["POST"])
@papel_requerido("ALUNO")
def api_app_gerar_pix():
    pessoa_id = _aluno_id_sessao()
    pessoa = database.obter_pessoa(pessoa_id)
    if not pessoa:
        return jsonify({"sucesso":False,"erro":"Aluno não encontrado."}),404
    plano = database.obter_plano(pessoa.get("plano_id")) if pessoa.get("plano_id") else None
    if not plano:
        return jsonify({"sucesso":False,"erro":"Seu cadastro está sem plano válido. Procure a recepção."}),400
    if not pessoa.get("cpf"):
        return jsonify({"sucesso":False,"erro":"Seu cadastro está sem CPF. Procure a recepção."}),400
    if not pessoa.get("data_vencimento"):
        return jsonify({"sucesso":False,"erro":"Seu cadastro está sem vencimento. Procure a recepção."}),400

    aberta = database.obter_cobranca_aberta(pessoa_id, pessoa.get("data_vencimento"))
    if aberta:
        return jsonify({
            "sucesso":True,"existente":True,
            "payment_id":aberta.get("gateway_payment_id"),
            "valor_centavos":aberta.get("valor_centavos"),
            "vencimento":aberta.get("vencimento_original"),
            "status":aberta.get("status"),
            "payload":aberta.get("pix_payload"),
            "encodedImage":aberta.get("pix_qr_base64")
        })

    gateway = AsaasGateway()
    try:
        customer_id = database.obter_gateway_cliente(pessoa_id)
        if not customer_id:
            existente = gateway.localizar_cliente(pessoa_id)
            cliente = existente or gateway.criar_cliente(pessoa)
            customer_id = cliente["id"]
            database.salvar_gateway_cliente(pessoa_id,customer_id)
        referencia = f"PANO-APP-{pessoa_id}-{int(time.time())}"
        pg = gateway.criar_cobranca_pix(
            customer_id,int(plano["valor_centavos"]),
            pessoa["data_vencimento"],referencia
        )
        pix = gateway.obter_pix(pg["id"])
        database.criar_cobranca_local(
            pessoa_id,plano["id"],pg["id"],customer_id,
            int(plano["valor_centavos"]),pessoa["data_vencimento"],
            pix.get("payload"),pix.get("encodedImage")
        )
        database.registrar_log_admin(
            "COBRANCA_PIX_CRIADA_ALUNO_APP",str(pessoa_id),pg["id"],_ip_cliente()
        )
        return jsonify({
            "sucesso":True,"existente":False,"payment_id":pg["id"],
            "valor_centavos":plano["valor_centavos"],
            "vencimento":pessoa["data_vencimento"],
            "status":"PENDENTE","payload":pix.get("payload"),
            "encodedImage":pix.get("encodedImage")
        })
    except GatewayError as exc:
        return jsonify({"sucesso":False,"erro":str(exc)}),502
    except Exception as exc:
        current_app.logger.exception("Falha ao gerar PIX pelo app do aluno")
        return jsonify({"sucesso":False,"erro":"Não foi possível gerar o PIX agora. Tente novamente ou procure a recepção."}),500


@aluno_app_bp.route("/app/exercicios/<int:exercicio_id>")
@papel_requerido("ALUNO")
def aluno_app_exercicio(exercicio_id):
    pessoa_id=_aluno_id_sessao()
    historico=database.historico_exercicio_aluno(pessoa_id,exercicio_id,40)
    if not historico: abort(404)
    return render_template("aluno_app_exercicio.html",pessoa=database.obter_pessoa(pessoa_id),
                           historico=historico,exercicio_id=exercicio_id)


@aluno_app_bp.route("/api/app/senha", methods=["POST"])
@papel_requerido("ALUNO")
def api_app_trocar_senha():
    acesso=database.obter_acesso_aluno_por_pessoa(_aluno_id_sessao())
    payload=request.get_json(silent=True) or {}
    atual=payload.get("senha_atual") or ""; nova=payload.get("nova_senha") or ""
    if not acesso or not auth_service.check_password_hash(acesso.get("senha_hash") or "",atual):
        return jsonify({"sucesso":False,"erro":"Senha atual incorreta."}),400
    if len(nova)<8:
        return jsonify({"sucesso":False,"erro":"A nova senha precisa ter pelo menos 8 caracteres."}),400
    database.salvar_acesso_aluno(acesso["pessoa_id"],acesso["login"],auth_service.hash_senha(nova),bool(acesso["ativo"]))
    database.registrar_log_admin("ALUNO_TROCOU_SENHA",str(acesso["pessoa_id"]),acesso["login"],_ip_cliente())
    return jsonify({"sucesso":True})


@aluno_app_bp.route("/api/app/execucoes/iniciar", methods=["POST"])
@papel_requerido("ALUNO")
def api_app_iniciar_execucao():
    pessoa_id = _aluno_id_sessao()
    payload = request.get_json(silent=True) or {}
    try:
        treino_id = int(payload.get("treino_id"))
    except (TypeError,ValueError):
        return jsonify({"sucesso":False,"erro":"Treino inválido."}),400
    sessao_id,erro = database.criar_sessao_treino(
        pessoa_id,treino_id,int(session.get("usuario_id")),"ALUNO_APP"
    )
    if not sessao_id:
        return jsonify({"sucesso":False,"erro":erro}),400
    if erro != "JA_EXISTE":
        database.registrar_log_admin("TREINO_INICIADO_ALUNO_APP",str(sessao_id),f"aluno:{pessoa_id}",_ip_cliente())
    return jsonify({"sucesso":True,"id":sessao_id,"reutilizada":erro=="JA_EXISTE"})


@aluno_app_bp.route("/api/app/execucoes/<int:sessao_id>", methods=["GET"])
@papel_requerido("ALUNO")
def api_app_obter_execucao(sessao_id):
    sessao = database.obter_sessao_treino(sessao_id)
    if not sessao or int(sessao["pessoa_id"]) != int(_aluno_id_sessao()):
        return jsonify({"sucesso":False,"erro":"Sessão não encontrada."}),404
    return jsonify({"sucesso":True,"sessao":sessao})


@aluno_app_bp.route("/api/app/execucoes/itens/<int:item_id>", methods=["PUT"])
@papel_requerido("ALUNO")
def api_app_atualizar_item(item_id):
    conn = database.conectar()
    try:
        row = conn.execute("SELECT sessao_id FROM treino_sessao_itens WHERE id=?",(item_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        return jsonify({"sucesso":False,"erro":"Item não encontrado."}),404
    sessao = database.obter_sessao_treino(row["sessao_id"])
    if not sessao or int(sessao["pessoa_id"]) != int(_aluno_id_sessao()):
        return jsonify({"sucesso":False,"erro":"Sem permissão."}),403
    try:
        dados = execution_service.normalizar_item(request.get_json(silent=True) or {})
    except ValueError as exc:
        return jsonify({"sucesso":False,"erro":str(exc)}),400
    ok,erro,_ = database.atualizar_item_sessao(item_id,dados)
    return jsonify({"sucesso":ok,"erro":erro}) if ok else (jsonify({"sucesso":False,"erro":erro}),409)


@aluno_app_bp.route("/api/app/execucoes/<int:sessao_id>/concluir", methods=["POST"])
@papel_requerido("ALUNO")
def api_app_concluir_execucao(sessao_id):
    sessao = database.obter_sessao_treino(sessao_id)
    if not sessao or int(sessao["pessoa_id"]) != int(_aluno_id_sessao()):
        return jsonify({"sucesso":False,"erro":"Sessão não encontrada."}),404
    obs = execution_service.normalizar_observacao(request.get_json(silent=True) or {})
    ok,erro = database.concluir_sessao_treino(sessao_id,obs)
    if not ok:
        return jsonify({"sucesso":False,"erro":erro}),409
    database.registrar_log_admin("TREINO_CONCLUIDO_ALUNO_APP",str(sessao_id),sessao["treino_nome"],_ip_cliente())
    return jsonify({"sucesso":True})


@aluno_app_bp.route("/api/app/execucoes/<int:sessao_id>/cancelar", methods=["POST"])
@papel_requerido("ALUNO")
def api_app_cancelar_execucao(sessao_id):
    sessao = database.obter_sessao_treino(sessao_id)
    if not sessao or int(sessao["pessoa_id"]) != int(_aluno_id_sessao()):
        return jsonify({"sucesso":False,"erro":"Sessão não encontrada."}),404
    obs = execution_service.normalizar_observacao(request.get_json(silent=True) or {})
    ok,erro = database.cancelar_sessao_treino(sessao_id,obs)
    return jsonify({"sucesso":True}) if ok else (jsonify({"sucesso":False,"erro":erro}),409)


@aluno_app_bp.route("/sw.js")
def aluno_service_worker():
    response = send_file(BASE_DIR / "static" / "sw.js", mimetype="application/javascript")
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache"
    return response


