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

execucoes_bp = Blueprint("execucoes", __name__)

@execucoes_bp.route("/execucoes")
@papel_requerido("ADMIN", "PROFESSOR")
def pagina_execucoes():
    pessoa_ids = None
    if session.get("usuario_papel") == "PROFESSOR":
        professor = database.obter_professor_por_usuario(int(session.get("usuario_id")))
        pessoa_ids = [p["id"] for p in database.listar_alunos_professor(professor["id"])] if professor else []
    disponiveis = database.listar_treinos_disponiveis_para_execucao(pessoa_ids)
    sessoes = database.listar_sessoes_treino(pessoa_ids, 100)
    return render_template(
        "execucoes.html",
        disponiveis=disponiveis,
        sessoes=sessoes,
        estatisticas=database.estatisticas_execucoes(pessoa_ids),
    )


@execucoes_bp.route("/execucoes/<int:sessao_id>")
@papel_requerido("ADMIN", "PROFESSOR")
def pagina_execucao(sessao_id):
    sessao = database.obter_sessao_treino(sessao_id)
    if not sessao:
        abort(404)
    if not professor_pode_gerir_aluno(sessao["pessoa_id"]):
        abort(403)
    return render_template("execucao_treino.html", sessao=sessao)


@execucoes_bp.route("/api/execucoes/iniciar", methods=["POST"])
@papel_requerido("ADMIN", "PROFESSOR")
def api_iniciar_execucao():
    payload = request.get_json(silent=True) or {}
    try:
        pessoa_id = int(payload.get("pessoa_id"))
        treino_id = int(payload.get("treino_id"))
    except (TypeError, ValueError):
        return jsonify({"sucesso":False,"erro":"Aluno ou treino inválido."}),400
    if not professor_pode_gerir_aluno(pessoa_id):
        return jsonify({"sucesso":False,"erro":"Sem permissão para este aluno."}),403
    sessao_id, erro = database.criar_sessao_treino(
        pessoa_id, treino_id, int(session.get("usuario_id")), "PAINEL"
    )
    if not sessao_id:
        return jsonify({"sucesso":False,"erro":erro}),400
    if erro == "JA_EXISTE":
        return jsonify({"sucesso":True,"id":sessao_id,"reutilizada":True})
    database.registrar_log_admin("TREINO_INICIADO",str(sessao_id),f"Aluno {pessoa_id} · treino {treino_id}",_ip_cliente())
    return jsonify({"sucesso":True,"id":sessao_id})


@execucoes_bp.route("/api/execucoes/<int:sessao_id>", methods=["GET"])
@papel_requerido("ADMIN", "PROFESSOR")
def api_obter_execucao(sessao_id):
    sessao=database.obter_sessao_treino(sessao_id)
    if not sessao:
        return jsonify({"sucesso":False,"erro":"Sessão não encontrada."}),404
    if not professor_pode_gerir_aluno(sessao["pessoa_id"]):
        return jsonify({"sucesso":False,"erro":"Sem permissão."}),403
    return jsonify({"sucesso":True,"sessao":sessao})


@execucoes_bp.route("/api/execucoes/itens/<int:item_id>", methods=["PUT"])
@papel_requerido("ADMIN", "PROFESSOR")
def api_atualizar_item_execucao(item_id):
    payload=request.get_json(silent=True) or {}
    try:
        dados=execution_service.normalizar_item(payload)
    except ValueError as exc:
        return jsonify({"sucesso":False,"erro":str(exc)}),400
    # resolve a sessão antes de gravar para validar permissão
    conn=database.conectar()
    try:
        row=conn.execute("SELECT sessao_id FROM treino_sessao_itens WHERE id=?",(item_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        return jsonify({"sucesso":False,"erro":"Item não encontrado."}),404
    sessao=database.obter_sessao_treino(row["sessao_id"])
    if not sessao or not professor_pode_gerir_aluno(sessao["pessoa_id"]):
        return jsonify({"sucesso":False,"erro":"Sem permissão."}),403
    ok,erro,_=database.atualizar_item_sessao(item_id,dados)
    if not ok:
        return jsonify({"sucesso":False,"erro":erro}),409
    return jsonify({"sucesso":True})


@execucoes_bp.route("/api/execucoes/<int:sessao_id>/concluir", methods=["POST"])
@papel_requerido("ADMIN", "PROFESSOR")
def api_concluir_execucao(sessao_id):
    sessao=database.obter_sessao_treino(sessao_id)
    if not sessao:
        return jsonify({"sucesso":False,"erro":"Sessão não encontrada."}),404
    if not professor_pode_gerir_aluno(sessao["pessoa_id"]):
        return jsonify({"sucesso":False,"erro":"Sem permissão."}),403
    obs=execution_service.normalizar_observacao(request.get_json(silent=True) or {})
    ok,erro=database.concluir_sessao_treino(sessao_id,obs)
    if not ok:
        return jsonify({"sucesso":False,"erro":erro}),409
    database.registrar_log_admin("TREINO_CONCLUIDO",str(sessao_id),sessao["treino_nome"],_ip_cliente())
    return jsonify({"sucesso":True})


@execucoes_bp.route("/api/execucoes/<int:sessao_id>/cancelar", methods=["POST"])
@papel_requerido("ADMIN", "PROFESSOR")
def api_cancelar_execucao(sessao_id):
    sessao=database.obter_sessao_treino(sessao_id)
    if not sessao:
        return jsonify({"sucesso":False,"erro":"Sessão não encontrada."}),404
    if not professor_pode_gerir_aluno(sessao["pessoa_id"]):
        return jsonify({"sucesso":False,"erro":"Sem permissão."}),403
    obs=execution_service.normalizar_observacao(request.get_json(silent=True) or {})
    ok,erro=database.cancelar_sessao_treino(sessao_id,obs)
    if not ok:
        return jsonify({"sucesso":False,"erro":erro}),409
    database.registrar_log_admin("TREINO_CANCELADO",str(sessao_id),sessao["treino_nome"],_ip_cliente())
    return jsonify({"sucesso":True})


