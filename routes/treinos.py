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

from services import dashboard_service, auth_service, professor_service, exercise_service, workout_service, execution_service, assessment_service, push_service
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

treinos_bp = Blueprint("treinos", __name__)

@treinos_bp.route("/treinos")
@papel_requerido("ADMIN", "PROFESSOR")
def pagina_treinos():
    papel = session.get("usuario_papel")
    pessoas = database.listar_pessoas()
    professores = database.listar_professores()
    fichas = database.listar_fichas_treino()
    exercicios = [e for e in database.listar_exercicios() if e.get("ativo")]
    if papel == "PROFESSOR":
        professor = database.obter_professor_por_usuario(int(session.get("usuario_id")))
        if not professor:
            pessoas = []
            fichas = []
        else:
            vinculados = {p["id"] for p in database.listar_alunos_professor(professor["id"])}
            pessoas = [p for p in pessoas if p["id"] in vinculados]
            fichas = [f for f in fichas if f["pessoa_id"] in vinculados]
            professores = [professor]
    return render_template(
        "treinos.html",
        fichas=fichas,
        pessoas=pessoas,
        professores=professores,
        exercicios=exercicios,
        estatisticas=database.estatisticas_fichas_treino(),
    )



@treinos_bp.route("/api/fichas-treino/<int:ficha_id>", methods=["GET"])
@papel_requerido("ADMIN", "PROFESSOR")
def api_obter_ficha_treino(ficha_id):
    ficha = database.obter_ficha_treino(ficha_id)
    if not ficha:
        return jsonify({"sucesso": False, "erro": "Ficha não encontrada."}), 404
    if not professor_pode_gerir_aluno(ficha["pessoa_id"]):
        return jsonify({"sucesso": False, "erro": "Sem permissão para esta ficha."}), 403
    return jsonify({"sucesso": True, "ficha": ficha})


@treinos_bp.route("/api/fichas-treino", methods=["POST"])
@papel_requerido("ADMIN", "PROFESSOR")
def api_criar_ficha_treino():
    payload = request.get_json(silent=True) or {}
    try:
        dados = workout_service.normalizar(payload)
        if not database.obter_pessoa(dados["pessoa_id"]):
            return jsonify({"sucesso": False, "erro": "Aluno não encontrado."}), 404
        if not professor_pode_gerir_aluno(dados["pessoa_id"]):
            return jsonify({"sucesso": False, "erro": "Sem permissão para este aluno."}), 403
        ficha_id = database.criar_ficha_treino(dados, int(session.get("usuario_id")))
        database.registrar_log_admin("FICHA_TREINO_CRIADA", str(ficha_id), dados["nome"], _ip_cliente())
        if dados.get("ativo", True):
            push_service.enviar_para_aluno(
                dados["pessoa_id"], "Novo treino disponível",
                f"Sua ficha {dados['nome']} foi liberada.", {"url": "/treino", "tipo": "NOVA_FICHA"}
            )
        return jsonify({"sucesso": True, "id": ficha_id})
    except ValueError as exc:
        return jsonify({"sucesso": False, "erro": str(exc)}), 400
    except database.IntegrityError:
        return jsonify({"sucesso": False, "erro": "A ficha contém aluno, professor ou exercício inválido."}), 400
    except Exception:
        return jsonify({"sucesso": False, "erro": "Não foi possível criar a ficha."}), 500


@treinos_bp.route("/api/fichas-treino/<int:ficha_id>/duplicar", methods=["POST"])
@papel_requerido("ADMIN","PROFESSOR")
def api_duplicar_ficha_treino(ficha_id):
    original=database.obter_ficha_treino(ficha_id)
    if not original or not professor_pode_gerir_aluno(original["pessoa_id"]):
        return jsonify({"sucesso":False,"erro":"Ficha não encontrada ou sem permissão."}),404
    payload=request.get_json(silent=True) or {}
    try: pessoa_id=int(payload.get("pessoa_id"))
    except (TypeError,ValueError): return jsonify({"sucesso":False,"erro":"Selecione o aluno de destino."}),400
    if not professor_pode_gerir_aluno(pessoa_id):
        return jsonify({"sucesso":False,"erro":"Sem permissão para o aluno de destino."}),403
    professor_id=original.get("professor_id")
    if session.get("usuario_papel")=="PROFESSOR":
        prof=database.obter_professor_por_usuario(int(session.get("usuario_id")))
        professor_id=prof["id"] if prof else professor_id
    try:
        novo=database.duplicar_ficha_treino(ficha_id,pessoa_id,professor_id,int(session.get("usuario_id")))
        database.registrar_log_admin("FICHA_TREINO_DUPLICADA",str(novo),f"origem:{ficha_id}",_ip_cliente())
        return jsonify({"sucesso":True,"id":novo})
    except ValueError as exc: return jsonify({"sucesso":False,"erro":str(exc)}),400


@treinos_bp.route("/api/fichas-treino/<int:ficha_id>", methods=["PUT"])
@papel_requerido("ADMIN", "PROFESSOR")
def api_atualizar_ficha_treino(ficha_id):
    atual = database.obter_ficha_treino(ficha_id)
    if not atual:
        return jsonify({"sucesso": False, "erro": "Ficha não encontrada."}), 404
    if not professor_pode_gerir_aluno(atual["pessoa_id"]):
        return jsonify({"sucesso": False, "erro": "Sem permissão para esta ficha."}), 403
    payload = request.get_json(silent=True) or {}
    try:
        dados = workout_service.normalizar(payload)
        if not professor_pode_gerir_aluno(dados["pessoa_id"]):
            return jsonify({"sucesso": False, "erro": "Sem permissão para este aluno."}), 403
        database.atualizar_ficha_treino(ficha_id, dados)
        database.registrar_log_admin("FICHA_TREINO_ATUALIZADA", str(ficha_id), dados["nome"], _ip_cliente())
        return jsonify({"sucesso": True})
    except ValueError as exc:
        return jsonify({"sucesso": False, "erro": str(exc)}), 400
    except database.IntegrityError:
        return jsonify({"sucesso": False, "erro": "A ficha contém aluno, professor ou exercício inválido."}), 400
    except Exception:
        return jsonify({"sucesso": False, "erro": "Não foi possível atualizar a ficha."}), 500


