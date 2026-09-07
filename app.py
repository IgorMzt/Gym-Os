"""Aplicacao web do controle de acesso da academia.

A aplicacao foi estruturada em quatro blocos: catraca, alunos, planos e gestao.
A comunicacao com a catraca fisica usa uma camada de dispositivo que hoje opera
em modo SIMULADA e pode ser substituida por HTTP/serial futuramente.
"""

import base64
import hashlib
import hmac
import secrets
import sqlite3
import tempfile
import csv
import io
import os
import re
import time
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

import cv2
import face_recognition
import numpy as np
from dotenv import load_dotenv

# Carrega o .env antes dos módulos locais que leem configuração de ambiente.
load_dotenv()

from flask import Flask, Response, abort, jsonify, redirect, render_template, request, session, url_for, send_file

from services import dashboard_service, auth_service, professor_service, exercise_service, workout_service, execution_service, assessment_service
from services.permissions import login_obrigatorio, papel_requerido
from services.payments import AsaasGateway, GatewayError
import database
import config_service
import device_manager
import face_index
from routes.auth import auth_bp
from routes.dashboard import dashboard_bp
from routes.professores import professores_bp
from routes.aluno_app import aluno_app_bp
from routes.avaliacoes import avaliacoes_bp
from routes.execucoes import execucoes_bp
from routes.treinos import treinos_bp
from routes.exercicios import exercicios_bp
from routes.usuarios import usuarios_bp
from routes.operacoes import operacoes_bp
from routes.api import api_auth_bp, api_aluno_bp, api_treinos_bp
from routes.common import ADMIN_USER, ADMIN_PASSWORD, CREDENCIAL_PADRAO
from validators import cpf_apenas_digitos, cpf_valido, data_iso, email_valido, parse_bool, parse_float, parse_int

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "troque-esta-secret-key-em-producao")
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
)


@app.context_processor
def contexto_global():
    return {
        "tema_padrao": config_service.get("tema_padrao", "system"),
        "csrf_token": csrf_token(),
        "credencial_padrao": CREDENCIAL_PADRAO,
        "papeis_usuario": auth_service.ROTULOS_PAPEL,
    }



# Banco e conta administrativa de bootstrap. A senha permanece controlada por ADMIN_PASSWORD.
database.criar_tabelas()
auth_service.garantir_admin_bootstrap(ADMIN_USER, ADMIN_PASSWORD)




def csrf_token():
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def _csrf_valido():
    esperado = session.get("_csrf_token")
    recebido = request.headers.get("X-CSRF-Token") or request.form.get("_csrf_token")
    return bool(esperado and recebido and hmac.compare_digest(str(esperado), str(recebido)))


@app.before_request
def protecoes_globais():
    # A catraca pública precisa continuar POSTando para APIs operacionais.
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None
    if request.path.startswith("/api/v1/"):
        return None
    if request.endpoint in {"auth.pagina_login", "operacoes.api_verificar", "operacoes.api_presenca", "operacoes.webhook_asaas"}:
        return None
    if session.get("usuario_logado") and not _csrf_valido():
        if request.path.startswith("/api/"):
            return jsonify({"sucesso": False, "erro": "Sessão de segurança expirada. Recarregue a página."}), 403
        return "Token de segurança inválido.", 403
    return None


@app.after_request
def cabecalhos_seguranca(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=()")
    if request.path.startswith("/api/v1/") or request.path.startswith("/admin/") or session.get("usuario_logado"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response



def formatar_moeda_centavos(valor):
    try:
        valor = int(valor or 0)
    except (TypeError, ValueError):
        valor = 0
    return f"R$ {valor / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def formatar_data_br(valor):
    if not valor:
        return "-"
    try:
        return date.fromisoformat(str(valor)[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return str(valor)


@app.template_filter("moeda")
def moeda_filter(valor):
    return formatar_moeda_centavos(valor)


@app.template_filter("data_br")
def data_br_filter(valor):
    return formatar_data_br(valor)





# ---------- Blueprints ----------
app.register_blueprint(auth_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(professores_bp)
app.register_blueprint(aluno_app_bp)
app.register_blueprint(avaliacoes_bp)
app.register_blueprint(execucoes_bp)
app.register_blueprint(treinos_bp)
app.register_blueprint(exercicios_bp)
app.register_blueprint(usuarios_bp)
app.register_blueprint(operacoes_bp)
app.register_blueprint(api_auth_bp)
app.register_blueprint(api_aluno_bp)
app.register_blueprint(api_treinos_bp)

if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "0").strip().lower() in {"1", "true", "sim", "on"}
    app.run(host=os.getenv("HOST", "0.0.0.0"), debug=debug, port=int(os.getenv("PORT", "5000")))
