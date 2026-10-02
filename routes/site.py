"""Portal comercial, checkout e branding da V6.14."""
from __future__ import annotations

import mimetypes
import re
from pathlib import Path

from flask import Blueprint, current_app, redirect, render_template, request, session, url_for

import database
from services import auth_service, saas_service, storage_service
from services.permissions import papel_requerido


site_bp = Blueprint("site", __name__)


def _site_context():
    return {
        "conteudo": saas_service.site_conteudo(),
        "planos": saas_service.listar_planos(publicos=True, ativos=True),
    }


@site_bp.route("/site")
def home():
    return render_template("site_home.html", **_site_context())


@site_bp.route("/site/planos")
def planos():
    return render_template("site_planos.html", **_site_context())


@site_bp.route("/site/recursos")
def recursos():
    ctx = _site_context()
    ctx["recursos"] = saas_service.listar_recursos()
    return render_template("site_recursos.html", **ctx)


@site_bp.route("/site/cadastro/<slug>", methods=["GET", "POST"])
def cadastro(slug):
    plano = saas_service.obter_plano(slug=slug)
    if not plano or not plano.get("ativo") or not plano.get("publico"):
        return "Plano não encontrado.", 404
    erro = None
    if request.method == "POST":
        nome = (request.form.get("academia_nome") or "").strip()
        codigo = (request.form.get("academia_slug") or "").strip()
        admin_nome = (request.form.get("admin_nome") or "").strip()
        admin_login = (request.form.get("admin_login") or "").strip()
        admin_email = (request.form.get("admin_email") or "").strip().lower()
        senha = request.form.get("senha") or ""
        confirmar = request.form.get("confirmar_senha") or ""
        if len(nome) < 3:
            erro = "Informe o nome da academia."
        elif not re.fullmatch(r"[A-Za-z0-9._@-]{3,80}", admin_login):
            erro = "O usuário do administrador deve ter de 3 a 80 caracteres."
        elif "@" not in admin_email or "." not in admin_email.split("@")[-1]:
            erro = "Informe um e-mail válido."
        elif len(senha) < 8:
            erro = "A senha precisa ter pelo menos 8 caracteres."
        elif senha != confirmar:
            erro = "As senhas não coincidem."
        else:
            try:
                checkout = saas_service.criar_checkout(
                    plano_id=int(plano["id"]),
                    ciclo=request.form.get("ciclo") or "MENSAL",
                    academia_nome=nome,
                    academia_slug=codigo,
                    admin_nome=admin_nome,
                    admin_login=admin_login,
                    admin_email=admin_email,
                    admin_senha_hash=auth_service.hash_senha(senha),
                    telefone=request.form.get("telefone") or "",
                    documento=request.form.get("documento") or "",
                    cupom=request.form.get("cupom") or "",
                )
                return redirect(url_for("site.checkout", token=checkout["token"]))
            except Exception as exc:
                erro = str(exc)
    return render_template("site_cadastro.html", plano=plano, erro=erro, conteudo=saas_service.site_conteudo())


@site_bp.route("/site/checkout/<token>", methods=["GET", "POST"])
def checkout(token):
    dados = saas_service.obter_checkout(token)
    if not dados:
        return "Checkout não encontrado.", 404
    erro = None
    if request.method == "POST":
        modo = current_app.config["GYM_SETTINGS"].saas_checkout_mode
        if modo == "disabled":
            erro = "Novas contratações estão temporariamente desativadas."
        elif modo == "manual":
            erro = "Checkout em modo manual. A contratação precisa ser aprovada pelo Super Admin."
        else:
            try:
                saas_service.provisionar_checkout(token)
                return redirect(url_for("site.sucesso", token=token))
            except Exception as exc:
                erro = str(exc)
    return render_template("site_checkout.html", checkout=dados, erro=erro, modo=current_app.config["GYM_SETTINGS"].saas_checkout_mode)


@site_bp.route("/site/sucesso/<token>")
def sucesso(token):
    dados = saas_service.obter_checkout(token)
    if not dados or dados.get("status") != "CONCLUIDO":
        return redirect(url_for("site.checkout", token=token))
    return render_template("site_sucesso.html", checkout=dados)


def _upload(file, categoria, owner_id):
    if not file or not file.filename:
        return None
    data = file.read()
    if not data:
        return None
    if len(data) > 4 * 1024 * 1024:
        raise ValueError("Imagem maior que 4 MB.")
    ext = Path(file.filename).suffix.lower()
    if ext not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise ValueError("Formato de imagem não suportado.")
    content_type = file.mimetype or mimetypes.guess_type(file.filename)[0] or "application/octet-stream"
    return storage_service.salvar_upload(data, ext, categoria=categoria, content_type=content_type, owner_type="academia_branding", owner_id=int(owner_id))


@site_bp.route("/aparencia", methods=["GET", "POST"])
@papel_requerido("ADMIN")
def aparencia():
    academia_id = database.academia_atual_id()
    if not saas_service.feature_enabled(academia_id, "branding"):
        return render_template("recurso_indisponivel.html", recurso="Personalização visual / Branding"), 403
    erro = None
    atual = saas_service.branding(academia_id)
    if request.method == "POST":
        try:
            dados = dict(atual)
            for campo in ("nome_exibicao", "cor_primaria", "cor_secundaria", "cor_destaque", "tema"):
                if campo in request.form:
                    dados[campo] = request.form.get(campo)
            uploads = {
                "logo_ref": ("logo", "branding-logo"),
                "banner_ref": ("banner", "branding-banner"),
                "login_background_ref": ("login_background", "branding-login"),
                "favicon_ref": ("favicon", "branding-favicon"),
            }
            for campo, (form_key, categoria) in uploads.items():
                ref = _upload(request.files.get(form_key), categoria, academia_id)
                if ref:
                    dados[campo] = ref
            saas_service.salvar_branding(academia_id, dados)
            return redirect(url_for("site.aparencia", salvo="1"))
        except Exception as exc:
            erro = str(exc)
    atual = saas_service.branding(academia_id)
    visual = dict(atual)
    for campo in ("logo_ref", "banner_ref", "login_background_ref", "favicon_ref"):
        visual[campo.replace("_ref", "_url")] = storage_service.url_temporaria(atual.get(campo)) if atual.get(campo) else None
    return render_template("aparencia.html", branding=visual, erro=erro)
