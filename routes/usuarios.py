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

usuarios_bp = Blueprint("usuarios", __name__)

@usuarios_bp.route("/usuarios")
@papel_requerido("ADMIN")
def pagina_usuarios():
    return render_template("usuarios.html", usuarios=database.listar_usuarios(), papeis=auth_service.ROTULOS_PAPEL)


@usuarios_bp.route("/api/usuarios", methods=["POST"])
@papel_requerido("ADMIN")
def api_criar_usuario():
    dados = request.get_json(silent=True) or {}
    login = (dados.get("login") or "").strip()
    nome = (dados.get("nome") or "").strip()
    senha = dados.get("senha") or ""
    papel = str(dados.get("papel") or "").upper()
    ativo = parse_bool(dados.get("ativo"), True)
    if not re.fullmatch(r"[A-Za-z0-9._-]{3,40}", login):
        return jsonify({"sucesso": False, "erro": "Login deve ter 3 a 40 caracteres e usar apenas letras, números, ponto, hífen ou _."}), 400
    if len(nome) < 2 or len(nome) > 100:
        return jsonify({"sucesso": False, "erro": "Informe um nome válido."}), 400
    if len(senha) < 8:
        return jsonify({"sucesso": False, "erro": "A senha precisa ter pelo menos 8 caracteres."}), 400
    if not auth_service.papel_valido(papel):
        return jsonify({"sucesso": False, "erro": "Papel de acesso inválido."}), 400
    try:
        uid = database.criar_usuario(login, nome, auth_service.hash_senha(senha), papel, ativo)
        database.registrar_log_admin("USUARIO_CRIADO", str(uid), f"{login}:{papel}", _ip_cliente())
        return jsonify({"sucesso": True, "id": uid})
    except Exception as exc:
        if "UNIQUE constraint failed" in str(exc):
            return jsonify({"sucesso": False, "erro": "Esse login já está em uso."}), 409
        return jsonify({"sucesso": False, "erro": "Não foi possível criar o usuário."}), 500


@usuarios_bp.route("/api/usuarios/<int:usuario_id>", methods=["PUT"])
@papel_requerido("ADMIN")
def api_editar_usuario(usuario_id):
    atual = database.obter_usuario(usuario_id)
    if not atual:
        return jsonify({"sucesso": False, "erro": "Usuário não encontrado."}), 404
    if atual.get("origem") == "ENV":
        return jsonify({"sucesso": False, "erro": "A conta bootstrap é controlada por ADMIN_USER/ADMIN_PASSWORD."}), 400
    dados = request.get_json(silent=True) or {}
    login = (dados.get("login") or "").strip()
    nome = (dados.get("nome") or "").strip()
    papel = str(dados.get("papel") or "").upper()
    ativo = parse_bool(dados.get("ativo"), True)
    senha = dados.get("senha") or ""
    if not re.fullmatch(r"[A-Za-z0-9._-]{3,40}", login):
        return jsonify({"sucesso": False, "erro": "Login inválido."}), 400
    if senha and len(senha) < 8:
        return jsonify({"sucesso": False, "erro": "A nova senha precisa ter pelo menos 8 caracteres."}), 400
    if len(nome) < 2 or len(nome) > 100 or not auth_service.papel_valido(papel):
        return jsonify({"sucesso": False, "erro": "Nome ou papel inválido."}), 400
    if usuario_id == session.get("usuario_id") and not ativo:
        return jsonify({"sucesso": False, "erro": "Você não pode desativar a própria conta."}), 400
    if atual.get("papel") == "ADMIN" and (papel != "ADMIN" or not ativo) and database.contar_admins_ativos(excluir_id=usuario_id) == 0:
        return jsonify({"sucesso": False, "erro": "O sistema precisa manter pelo menos um administrador ativo."}), 400
    try:
        database.atualizar_usuario(usuario_id, login, nome, papel, ativo)
        if senha:
            database.atualizar_senha_usuario(usuario_id, auth_service.hash_senha(senha))
        if usuario_id == session.get("usuario_id"):
            session["usuario_nome"] = nome
            session["usuario_login"] = login
            session["usuario_papel"] = papel
        database.registrar_log_admin("USUARIO_EDITADO", str(usuario_id), f"{login}:{papel}:ativo={ativo}", _ip_cliente())
        return jsonify({"sucesso": True})
    except Exception as exc:
        if "UNIQUE constraint failed" in str(exc):
            return jsonify({"sucesso": False, "erro": "Esse login já está em uso."}), 409
        return jsonify({"sucesso": False, "erro": "Não foi possível atualizar o usuário."}), 500


