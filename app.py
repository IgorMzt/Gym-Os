"""Aplicacao Flask do Gym OS.

V6.9: app factory, configuracao por ambiente, logging, health/readiness e base
para separar backend cloud do futuro agente local da academia.
"""

from __future__ import annotations

import hmac
import os
import secrets
import uuid
from datetime import date, timedelta

from dotenv import load_dotenv

# O .env precisa ser carregado antes dos modulos locais que leem configuracao.
load_dotenv()

from flask import Flask, g, jsonify, request, session
from werkzeug.middleware.proxy_fix import ProxyFix

import config_service
import database
from core.logging_config import configure_logging
from core.settings import Settings
from routes.aluno_app import aluno_app_bp
from routes.auth import auth_bp
from routes.avaliacoes import avaliacoes_bp
from routes.dashboard import dashboard_bp
from routes.exercicios import exercicios_bp
from routes.execucoes import execucoes_bp
from routes.operacoes import operacoes_bp
from routes.professores import professores_bp
from routes.system import system_bp
from routes.treinos import treinos_bp
from routes.usuarios import usuarios_bp
from routes.api import (
    api_agent_bp,
    api_aluno_bp,
    api_auth_bp,
    api_evolucao_bp,
    api_experiencia_bp,
    api_financeiro_bp,
    api_historico_bp,
    api_notificacoes_bp,
    api_treinos_bp,
)
from services import auth_service


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


def create_app(settings: Settings | None = None) -> Flask:
    settings = settings or Settings.from_env()
    settings.validate()

    app = Flask(__name__)
    app.secret_key = settings.secret_key
    app.config["GYM_SETTINGS"] = settings
    app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=settings.secure_cookies,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        PREFERRED_URL_SCHEME="https" if settings.production else "http",
    )

    if settings.trust_proxy:
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=settings.proxy_hops,
            x_proto=settings.proxy_hops,
            x_host=settings.proxy_hops,
            x_port=settings.proxy_hops,
        )

    configure_logging(settings, app.logger)
    database.configure_runtime(settings)

    if settings.auto_init_db:
        database.criar_tabelas()
        auth_service.garantir_admin_bootstrap(settings.admin_user, settings.admin_password)

    def csrf_token():
        token = session.get("_csrf_token")
        if not token:
            token = secrets.token_urlsafe(32)
            session["_csrf_token"] = token
        return token

    def csrf_valido():
        esperado = session.get("_csrf_token")
        recebido = request.headers.get("X-CSRF-Token") or request.form.get("_csrf_token")
        return bool(esperado and recebido and hmac.compare_digest(str(esperado), str(recebido)))

    @app.context_processor
    def contexto_global():
        return {
            "tema_padrao": config_service.get("tema_padrao", "system"),
            "csrf_token": csrf_token(),
            "credencial_padrao": settings.admin_user == "admin" and settings.admin_password == "admin123",
            "papeis_usuario": auth_service.ROTULOS_PAPEL,
            "gym_version": settings.app_version,
            "gym_environment": settings.environment,
        }

    @app.before_request
    def protecoes_globais():
        recebido = (request.headers.get("X-Request-ID") or "").strip()
        g.request_id = recebido[:80] if recebido and len(recebido) <= 80 else uuid.uuid4().hex

        # A catraca publica precisa continuar POSTando para APIs operacionais locais.
        if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
            return None
        if request.path.startswith("/api/v1/"):
            return None
        if request.endpoint in {"auth.pagina_login", "operacoes.api_verificar", "operacoes.api_presenca", "operacoes.webhook_asaas"}:
            return None
        if session.get("usuario_logado") and not csrf_valido():
            if request.path.startswith("/api/"):
                return jsonify({"sucesso": False, "erro": "Sessao de seguranca expirada. Recarregue a pagina."}), 403
            return "Token de seguranca invalido.", 403
        return None

    @app.after_request
    def cabecalhos_seguranca(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=()")
        response.headers["X-Request-ID"] = getattr(g, "request_id", uuid.uuid4().hex)
        if request.path.startswith("/api/v1/") or request.path.startswith("/admin/") or session.get("usuario_logado"):
            response.headers.setdefault("Cache-Control", "no-store")
        if settings.production and settings.secure_cookies:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

    @app.errorhandler(500)
    def erro_interno(exc):
        request_id = getattr(g, "request_id", uuid.uuid4().hex)
        app.logger.exception("request_id=%s erro_interno path=%s", request_id, request.path)
        if request.path.startswith("/api/"):
            return jsonify({
                "sucesso": False,
                "codigo": "ERRO_INTERNO",
                "erro": "Erro interno do servidor.",
                "request_id": request_id,
            }), 500
        return "Erro interno do servidor.", 500

    @app.template_filter("moeda")
    def moeda_filter(valor):
        return formatar_moeda_centavos(valor)

    @app.template_filter("data_br")
    def data_br_filter(valor):
        return formatar_data_br(valor)

    # System primeiro: health checks nao dependem das paginas do painel.
    app.register_blueprint(system_bp)
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
    app.register_blueprint(api_historico_bp)
    app.register_blueprint(api_evolucao_bp)
    app.register_blueprint(api_financeiro_bp)
    app.register_blueprint(api_notificacoes_bp)
    app.register_blueprint(api_experiencia_bp)
    app.register_blueprint(api_agent_bp)

    app.logger.info(
        "Gym OS %s iniciado environment=%s role=%s database=%s storage=%s",
        settings.app_version,
        settings.environment,
        settings.role,
        settings.database_backend,
        settings.storage_backend,
    )
    return app


# Compatibilidade com `python app.py`, Flask CLI e imports existentes.
app = create_app()


if __name__ == "__main__":
    cfg = app.config["GYM_SETTINGS"]
    app.run(host=cfg.host, debug=cfg.debug, port=cfg.port)
