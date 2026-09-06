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

avaliacoes_bp = Blueprint("avaliacoes", __name__)

def _escopo_avaliacoes():
    if session.get("usuario_papel") == "ADMIN":
        return None
    professor = database.obter_professor_por_usuario(int(session.get("usuario_id")))
    return [p["id"] for p in database.listar_alunos_professor(professor["id"])] if professor else []


@avaliacoes_bp.route("/avaliacoes")
@papel_requerido("ADMIN", "PROFESSOR")
def pagina_avaliacoes():
    pessoa_ids = _escopo_avaliacoes()
    return render_template(
        "avaliacoes.html",
        alunos=database.resumo_avaliacoes_alunos(pessoa_ids),
        estatisticas=database.estatisticas_avaliacoes(pessoa_ids),
    )


@avaliacoes_bp.route("/avaliacoes/<int:pessoa_id>")
@papel_requerido("ADMIN", "PROFESSOR")
def pagina_avaliacoes_aluno(pessoa_id):
    if not professor_pode_gerir_aluno(pessoa_id):
        abort(403)
    pessoa = database.obter_pessoa(pessoa_id)
    if not pessoa:
        abort(404)
    avaliacoes = database.listar_avaliacoes_fisicas(pessoa_id)
    return render_template(
        "avaliacoes_aluno.html",
        pessoa=pessoa,
        avaliacoes=avaliacoes,
        comparacao=assessment_service.comparacao(avaliacoes),
    )


def _salvar_fotos_avaliacao(payload, atual=None):
    atual = atual or {}
    resultado = {
        "foto_frontal_path": atual.get("foto_frontal_path"),
        "foto_lateral_path": atual.get("foto_lateral_path"),
        "foto_costas_path": atual.get("foto_costas_path"),
    }
    novas = []
    antigas_remover = []
    for chave, campo in [
        ("foto_frontal_base64","foto_frontal_path"),
        ("foto_lateral_base64","foto_lateral_path"),
        ("foto_costas_base64","foto_costas_path"),
    ]:
        remover = parse_bool(payload.get("remover_" + campo), False)
        if remover and resultado.get(campo):
            antigas_remover.append(resultado[campo])
            resultado[campo] = None
        if payload.get(chave):
            _, binario = decodificar_imagem(payload[chave])
            nova = salvar_foto(binario)
            novas.append(nova)
            if resultado.get(campo):
                antigas_remover.append(resultado[campo])
            resultado[campo] = nova
    return resultado, novas, antigas_remover


@avaliacoes_bp.route("/api/avaliacoes/<int:pessoa_id>", methods=["POST"])
@papel_requerido("ADMIN", "PROFESSOR")
def api_criar_avaliacao(pessoa_id):
    if not professor_pode_gerir_aluno(pessoa_id):
        return jsonify({"sucesso":False,"erro":"Sem permissão para este aluno."}),403
    if not database.obter_pessoa(pessoa_id):
        return jsonify({"sucesso":False,"erro":"Aluno não encontrado."}),404
    payload=request.get_json(silent=True) or {}
    novas=[]
    try:
        professor_id=None
        if session.get("usuario_papel")=="PROFESSOR":
            professor=database.obter_professor_por_usuario(int(session.get("usuario_id")))
            professor_id=professor["id"] if professor else None
        fotos,novas,_=_salvar_fotos_avaliacao(payload)
        dados=assessment_service.normalizar(payload,pessoa_id,professor_id,fotos)
        avaliacao_id=database.criar_avaliacao_fisica(dados,int(session.get("usuario_id")))
        database.registrar_log_admin("AVALIACAO_FISICA_CRIADA",str(avaliacao_id),f"aluno:{pessoa_id}",_ip_cliente())
        return jsonify({"sucesso":True,"id":avaliacao_id})
    except ValueError as exc:
        for p in novas: limpar_foto(p)
        return jsonify({"sucesso":False,"erro":str(exc)}),400
    except Exception:
        for p in novas: limpar_foto(p)
        return jsonify({"sucesso":False,"erro":"Não foi possível salvar a avaliação."}),500


@avaliacoes_bp.route("/api/avaliacoes/detalhe/<int:avaliacao_id>", methods=["GET","PUT"])
@papel_requerido("ADMIN", "PROFESSOR")
def api_avaliacao_detalhe(avaliacao_id):
    atual=database.obter_avaliacao_fisica(avaliacao_id)
    if not atual:
        return jsonify({"sucesso":False,"erro":"Avaliação não encontrada."}),404
    if not professor_pode_gerir_aluno(atual["pessoa_id"]):
        return jsonify({"sucesso":False,"erro":"Sem permissão."}),403
    if request.method=="GET":
        return jsonify({"sucesso":True,"avaliacao":atual})
    payload=request.get_json(silent=True) or {}
    novas=[]
    try:
        fotos,novas,antigas=_salvar_fotos_avaliacao(payload,atual)
        dados=assessment_service.normalizar(payload,atual["pessoa_id"],atual.get("professor_id"),fotos)
        database.atualizar_avaliacao_fisica(avaliacao_id,dados)
        for p in antigas:
            if p not in novas: limpar_foto(p)
        database.registrar_log_admin("AVALIACAO_FISICA_ATUALIZADA",str(avaliacao_id),f"aluno:{atual['pessoa_id']}",_ip_cliente())
        return jsonify({"sucesso":True})
    except ValueError as exc:
        for p in novas: limpar_foto(p)
        return jsonify({"sucesso":False,"erro":str(exc)}),400
    except Exception:
        for p in novas: limpar_foto(p)
        return jsonify({"sucesso":False,"erro":"Não foi possível atualizar a avaliação."}),500


