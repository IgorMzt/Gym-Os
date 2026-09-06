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

exercicios_bp = Blueprint("exercicios", __name__)

@exercicios_bp.route("/exercicios")
@papel_requerido("ADMIN", "PROFESSOR")
def pagina_exercicios():
    exercicios = database.listar_exercicios()
    grupos = sorted({e["grupo_muscular"] for e in exercicios if e.get("grupo_muscular")}, key=str.casefold)
    equipamentos = sorted({e["equipamento"] for e in exercicios if e.get("equipamento")}, key=str.casefold)
    return render_template(
        "exercicios.html",
        exercicios=exercicios,
        estatisticas=database.estatisticas_exercicios(),
        grupos=grupos,
        equipamentos=equipamentos,
        tipos_exercicio=exercise_service.TIPOS,
        dificuldades_exercicio=exercise_service.DIFICULDADES,
    )


def _aplicar_imagem_exercicio(dados, normalizado, atual=None):
    imagem_base64 = dados.get("imagem_base64")
    remover = parse_bool(dados.get("remover_imagem"), False)
    antiga = (atual or {}).get("imagem_path")
    if remover:
        normalizado["imagem_path"] = None
        return antiga, None
    if imagem_base64:
        _, binario = decodificar_imagem(imagem_base64)
        nova = salvar_foto(binario)
        normalizado["imagem_path"] = nova
        return antiga, nova
    return None, None


@exercicios_bp.route("/api/exercicios/<int:exercicio_id>", methods=["GET"])
@papel_requerido("ADMIN", "PROFESSOR")
def api_obter_exercicio(exercicio_id):
    exercicio = database.obter_exercicio(exercicio_id)
    if not exercicio:
        return jsonify({"sucesso": False, "erro": "Exercício não encontrado."}), 404
    return jsonify({"sucesso": True, "exercicio": exercicio})


@exercicios_bp.route("/api/exercicios", methods=["POST"])
@papel_requerido("ADMIN", "PROFESSOR")
def api_criar_exercicio():
    dados = request.get_json(silent=True) or {}
    nova_imagem = None
    try:
        normalizado = exercise_service.normalizar(dados)
        _, nova_imagem = _aplicar_imagem_exercicio(dados, normalizado)
        exercicio_id = database.criar_exercicio(normalizado, int(session.get("usuario_id")))
        database.registrar_log_admin(
            "EXERCICIO_CRIADO", str(exercicio_id), normalizado["nome"], _ip_cliente()
        )
        return jsonify({"sucesso": True, "id": exercicio_id})
    except ValueError as exc:
        if nova_imagem:
            limpar_foto(nova_imagem)
        return jsonify({"sucesso": False, "erro": str(exc)}), 400
    except Exception as exc:
        if nova_imagem:
            limpar_foto(nova_imagem)
        if "UNIQUE constraint failed" in str(exc):
            return jsonify({"sucesso": False, "erro": "Já existe um exercício com esse nome."}), 409
        return jsonify({"sucesso": False, "erro": "Não foi possível cadastrar o exercício."}), 500


@exercicios_bp.route("/api/exercicios/<int:exercicio_id>", methods=["PUT"])
@papel_requerido("ADMIN", "PROFESSOR")
def api_editar_exercicio(exercicio_id):
    atual = database.obter_exercicio(exercicio_id)
    if not atual:
        return jsonify({"sucesso": False, "erro": "Exercício não encontrado."}), 404
    dados = request.get_json(silent=True) or {}
    antiga_imagem = nova_imagem = None
    try:
        normalizado = exercise_service.normalizar(dados, atual)
        antiga_imagem, nova_imagem = _aplicar_imagem_exercicio(dados, normalizado, atual)
        database.atualizar_exercicio(exercicio_id, normalizado)
        if antiga_imagem and (nova_imagem or parse_bool(dados.get("remover_imagem"), False)):
            limpar_foto(antiga_imagem)
        database.registrar_log_admin(
            "EXERCICIO_ATUALIZADO", str(exercicio_id), normalizado["nome"], _ip_cliente()
        )
        return jsonify({"sucesso": True})
    except ValueError as exc:
        if nova_imagem:
            limpar_foto(nova_imagem)
        return jsonify({"sucesso": False, "erro": str(exc)}), 400
    except Exception as exc:
        if nova_imagem:
            limpar_foto(nova_imagem)
        if "UNIQUE constraint failed" in str(exc):
            return jsonify({"sucesso": False, "erro": "Já existe um exercício com esse nome."}), 409
        return jsonify({"sucesso": False, "erro": "Não foi possível atualizar o exercício."}), 500


