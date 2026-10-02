"""Painel privado de administracao SaaS da V6.14."""
from __future__ import annotations

import hmac
import secrets
from functools import wraps

from flask import Blueprint, current_app, redirect, render_template, request, session, url_for

import database
from services import saas_service, storage_service


saas_bp = Blueprint("saas", __name__, url_prefix="/saas")


def _csrf():
    token = session.get("_saas_csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_saas_csrf"] = token
    return token


def _csrf_ok():
    esperado = session.get("_saas_csrf")
    recebido = request.form.get("_saas_csrf") or request.headers.get("X-SaaS-CSRF")
    return bool(esperado and recebido and hmac.compare_digest(str(esperado), str(recebido)))


def superadmin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("saas_admin"):
            return redirect(url_for("saas.login", proxima=request.path))
        return view(*args, **kwargs)
    return wrapper


@saas_bp.context_processor
def contexto_saas():
    return {"saas_csrf": _csrf()}


@saas_bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("saas_admin"):
        return redirect(url_for("saas.dashboard"))
    erro = None
    if request.method == "POST":
        cfg = current_app.config["GYM_SETTINGS"]
        usuario = (request.form.get("usuario") or "").strip()
        senha = request.form.get("senha") or ""
        if hmac.compare_digest(usuario, cfg.saas_admin_user) and hmac.compare_digest(senha, cfg.saas_admin_password):
            session.clear()
            session.permanent = True
            session["saas_admin"] = True
            session["saas_admin_user"] = usuario
            _csrf()
            saas_service.registrar_auditoria("SAAS_LOGIN", usuario, ip=request.remote_addr or "")
            return redirect(url_for("saas.dashboard"))
        erro = "Credenciais inválidas."
    return render_template("saas_login.html", erro=erro)


@saas_bp.route("/logout")
def logout():
    usuario = session.get("saas_admin_user", "-")
    if session.get("saas_admin"):
        saas_service.registrar_auditoria("SAAS_LOGOUT", usuario, ip=request.remote_addr or "")
    session.clear()
    return redirect(url_for("saas.login"))


@saas_bp.route("")
@saas_bp.route("/")
@superadmin_required
def dashboard():
    return render_template(
        "saas_dashboard.html",
        metricas=saas_service.dashboard_saas(),
        academias=saas_service.listar_academias_saas()[:8],
        assinaturas=saas_service.listar_assinaturas()[:8],
    )


@saas_bp.route("/academias")
@superadmin_required
def academias():
    return render_template("saas_academias.html", academias=saas_service.listar_academias_saas(), planos=saas_service.listar_planos(ativos=True))


@saas_bp.route("/academias/<int:academia_id>/status", methods=["POST"])
@superadmin_required
def academia_status(academia_id):
    if not _csrf_ok():
        return "Token de segurança inválido.", 403
    ativa = request.form.get("ativa") == "1"
    try:
        saas_service.set_academia_ativa(academia_id, ativa)
        saas_service.registrar_auditoria("ACADEMIA_STATUS", str(academia_id), {"ativa": ativa}, request.remote_addr or "")
    except ValueError as exc:
        return str(exc), 400
    return redirect(url_for("saas.academias"))


@saas_bp.route("/academias/<int:academia_id>/plano", methods=["POST"])
@superadmin_required
def academia_plano(academia_id):
    if not _csrf_ok():
        return "Token de segurança inválido.", 403
    try:
        assinatura_id = saas_service.trocar_plano(academia_id, int(request.form.get("plano_id") or 0), request.form.get("ciclo") or "MENSAL")
        saas_service.registrar_auditoria("TROCA_PLANO", str(academia_id), {"assinatura_id": assinatura_id}, request.remote_addr or "")
    except (TypeError, ValueError) as exc:
        return str(exc), 400
    return redirect(url_for("saas.academias"))


@saas_bp.route("/planos", methods=["GET", "POST"])
@superadmin_required
def planos():
    erro = None
    if request.method == "POST":
        if not _csrf_ok():
            return "Token de segurança inválido.", 403
        try:
            plano_id = int(request.form["plano_id"]) if request.form.get("plano_id") else None
            dados = {
                "nome": request.form.get("nome"),
                "slug": request.form.get("slug"),
                "descricao": request.form.get("descricao"),
                "preco_mensal_centavos": request.form.get("preco_mensal_centavos"),
                "preco_anual_centavos": request.form.get("preco_anual_centavos"),
                "trial_dias": request.form.get("trial_dias"),
                "max_alunos": request.form.get("max_alunos"),
                "max_unidades": request.form.get("max_unidades"),
                "max_professores": request.form.get("max_professores"),
                "max_agentes": request.form.get("max_agentes"),
                "destaque": request.form.get("destaque") == "1",
                "publico": request.form.get("publico") == "1",
                "ativo": request.form.get("ativo") == "1",
                "ordem": request.form.get("ordem"),
            }
            pid = saas_service.salvar_plano(dados, plano_id)
            saas_service.salvar_recursos_plano(pid, request.form.getlist("recursos"))
            saas_service.registrar_auditoria("PLANO_SALVO", str(pid), {"nome": dados["nome"]}, request.remote_addr or "")
            return redirect(url_for("saas.planos"))
        except Exception as exc:
            erro = str(exc)
    return render_template("saas_planos.html", planos=saas_service.listar_planos(), recursos=saas_service.listar_recursos(), erro=erro)


@saas_bp.route("/planos/<int:plano_id>/excluir", methods=["POST"])
@superadmin_required
def plano_excluir(plano_id):
    if not _csrf_ok():
        return "Token de segurança inválido.", 403
    saas_service.excluir_plano(plano_id)
    saas_service.registrar_auditoria("PLANO_EXCLUIDO_OU_DESATIVADO", str(plano_id), ip=request.remote_addr or "")
    return redirect(url_for("saas.planos"))


@saas_bp.route("/assinaturas")
@superadmin_required
def assinaturas():
    return render_template("saas_assinaturas.html", assinaturas=saas_service.listar_assinaturas())


@saas_bp.route("/assinaturas/<int:assinatura_id>/status", methods=["POST"])
@superadmin_required
def assinatura_status(assinatura_id):
    if not _csrf_ok():
        return "Token de segurança inválido.", 403
    try:
        saas_service.atualizar_status_assinatura(assinatura_id, request.form.get("status") or "", request.form.get("motivo") or None)
        saas_service.registrar_auditoria("ASSINATURA_STATUS", str(assinatura_id), {"status": request.form.get("status")}, request.remote_addr or "")
    except ValueError as exc:
        return str(exc), 400
    return redirect(url_for("saas.assinaturas"))


@saas_bp.route("/cupons", methods=["GET", "POST"])
@superadmin_required
def cupons():
    erro = None
    if request.method == "POST":
        if not _csrf_ok():
            return "Token de segurança inválido.", 403
        try:
            dados = {
                "codigo": request.form.get("codigo"),
                "tipo": request.form.get("tipo"),
                "valor": request.form.get("valor"),
                "plano_id": request.form.get("plano_id"),
                "max_usos": request.form.get("max_usos"),
                "valido_ate": request.form.get("valido_ate"),
                "ativo": request.form.get("ativo") == "1",
            }
            cid = saas_service.salvar_cupom(dados)
            saas_service.registrar_auditoria("CUPOM_SALVO", str(cid), {"codigo": dados["codigo"]}, request.remote_addr or "")
            return redirect(url_for("saas.cupons"))
        except Exception as exc:
            erro = str(exc)
    return render_template("saas_cupons.html", cupons=saas_service.listar_cupons(), planos=saas_service.listar_planos(ativos=True), erro=erro)




@saas_bp.route("/checkouts")
@superadmin_required
def checkouts():
    return render_template("saas_checkouts.html", checkouts=saas_service.listar_checkouts())


@saas_bp.route("/checkouts/<token>/aprovar", methods=["POST"])
@superadmin_required
def checkout_aprovar(token):
    if not _csrf_ok():
        return "Token de segurança inválido.", 403
    try:
        resultado = saas_service.provisionar_checkout(token)
        saas_service.registrar_auditoria("CHECKOUT_APROVADO", token, {"academia_id": resultado["academia"]["id"]}, request.remote_addr or "")
    except ValueError as exc:
        return str(exc), 400
    return redirect(url_for("saas.checkouts"))


@saas_bp.route("/agents")
@superadmin_required
def agents():
    return render_template("saas_agents.html", agents=saas_service.listar_agents_global())


@saas_bp.route("/agents/<int:agent_id>/status", methods=["POST"])
@superadmin_required
def agent_status(agent_id):
    if not _csrf_ok():
        return "Token de segurança inválido.", 403
    ativo = request.form.get("ativo") == "1"
    saas_service.set_agent_ativo(agent_id, ativo)
    saas_service.registrar_auditoria("AGENT_STATUS", str(agent_id), {"ativo": ativo}, request.remote_addr or "")
    return redirect(url_for("saas.agents"))


@saas_bp.route("/site", methods=["GET", "POST"])
@superadmin_required
def site_editor():
    if request.method == "POST":
        if not _csrf_ok():
            return "Token de segurança inválido.", 403
        for chave in saas_service.SITE_DEFAULTS:
            if chave in request.form:
                saas_service.salvar_site_conteudo(chave, request.form.get(chave) or "")
        for form_key, chave in (("hero_image", "hero_image_ref"), ("site_logo", "site_logo_ref")):
            arquivo = request.files.get(form_key)
            if arquivo and arquivo.filename:
                conteudo = arquivo.read()
                if len(conteudo) > 4 * 1024 * 1024:
                    return "Imagem maior que 4 MB.", 400
                extensao = "." + arquivo.filename.rsplit(".", 1)[-1].lower() if "." in arquivo.filename else ".bin"
                if extensao not in {".png", ".jpg", ".jpeg", ".webp"}:
                    return "Formato de imagem não suportado.", 400
                ref = storage_service.salvar_upload(conteudo, extensao, categoria="saas-site", content_type=arquivo.mimetype or "application/octet-stream", owner_type="saas_site", owner_id=1)
                saas_service.salvar_site_conteudo(chave, ref, "imagem")
        saas_service.registrar_auditoria("SITE_ATUALIZADO", "site", ip=request.remote_addr or "")
        return redirect(url_for("saas.site_editor"))
    conteudo = saas_service.site_conteudo()
    return render_template("saas_site_editor.html", conteudo=conteudo)


@saas_bp.route("/auditoria")
@superadmin_required
def auditoria():
    return render_template("saas_auditoria.html", eventos=saas_service.listar_auditoria())
