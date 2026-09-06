"""Rotas de autenticação e primeiro acesso do Gym OS."""

import re
import secrets
import time

from flask import Blueprint, redirect, render_template, request, session, url_for

import database
from services import auth_service
from validators import cpf_apenas_digitos


auth_bp = Blueprint("auth", __name__)

LOGIN_MAX_TENTATIVAS = 5
LOGIN_JANELA_SEGUNDOS = 300
LOGIN_BLOQUEIO_SEGUNDOS = 300

_login_tentativas = {}
_primeiro_acesso_tentativas = {}


def _ip_cliente():
    return request.remote_addr or "desconhecido"


def _estado_login(ip):
    agora = time.time()
    estado = _login_tentativas.get(ip, {"tentativas": [], "bloqueado_ate": 0})
    estado["tentativas"] = [t for t in estado["tentativas"] if agora - t < LOGIN_JANELA_SEGUNDOS]
    if estado["bloqueado_ate"] <= agora:
        estado["bloqueado_ate"] = 0
    _login_tentativas[ip] = estado
    return estado


def _login_bloqueado(ip):
    estado = _estado_login(ip)
    return max(0, int(estado["bloqueado_ate"] - time.time()))


def _registrar_falha_login(ip):
    estado = _estado_login(ip)
    estado["tentativas"].append(time.time())
    if len(estado["tentativas"]) >= LOGIN_MAX_TENTATIVAS:
        estado["bloqueado_ate"] = time.time() + LOGIN_BLOQUEIO_SEGUNDOS
        estado["tentativas"] = []
    _login_tentativas[ip] = estado


def _garantir_csrf_token():
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def _local_seguro(caminho):
    if not caminho or not isinstance(caminho, str):
        return None
    if caminho.startswith("/") and not caminho.startswith("//"):
        return caminho
    return None


def _primeiro_acesso_bloqueado(ip):
    agora = time.monotonic()
    dados = _primeiro_acesso_tentativas.get(ip, [])
    dados = [x for x in dados if agora - x < 900]
    _primeiro_acesso_tentativas[ip] = dados
    return len(dados) >= 8


def _registrar_falha_primeiro_acesso(ip):
    _primeiro_acesso_tentativas.setdefault(ip, []).append(time.monotonic())


@auth_bp.route("/login", methods=["GET", "POST"])
def pagina_login():
    if session.get("usuario_logado"):
        papel = session.get("usuario_papel")
        destino = "pagina_minha_area" if papel == "PROFESSOR" else ("aluno_app_inicio" if papel == "ALUNO" else "pagina_painel")
        return redirect(url_for(destino))

    erro = None
    ip = _ip_cliente()
    restante = _login_bloqueado(ip)

    if request.method == "POST":
        if restante > 0:
            erro = f"Muitas tentativas. Tente novamente em {restante} segundos."
        else:
            login = (request.form.get("usuario") or "").strip()
            senha = request.form.get("senha") or ""
            usuario = auth_service.autenticar(login, senha)
            if usuario:
                _login_tentativas.pop(ip, None)
                session.clear()
                session.permanent = True
                session["usuario_logado"] = True
                session["usuario_id"] = usuario["id"]
                session["usuario_nome"] = usuario["nome"]
                session["usuario_login"] = usuario["login"]
                session["usuario_papel"] = usuario["papel"]
                if usuario["papel"] == "ALUNO":
                    session["aluno_id"] = usuario["pessoa_id"]
                _garantir_csrf_token()
                database.registrar_log_admin("LOGIN", usuario["login"], f"Login realizado como {usuario['papel']}.", ip)
                proxima = _local_seguro(request.form.get("proxima"))
                if not proxima or usuario["papel"] in {"PROFESSOR", "ALUNO"}:
                    proxima = url_for(auth_service.destino_inicial(usuario))
                return redirect(proxima)
            _registrar_falha_login(ip)
            database.registrar_log_admin("LOGIN_FALHOU", login or "-", "Credenciais inválidas.", ip)
            erro = "Usuário ou senha inválidos."

    return render_template("login.html", erro=erro, bloqueio_segundos=restante)


@auth_bp.route("/primeiro-acesso", methods=["GET", "POST"])
def primeiro_acesso():
    if session.get("usuario_logado"):
        return redirect(url_for(auth_service.destino_inicial({"papel": session.get("usuario_papel")})))

    erro = None
    if request.method == "POST":
        ip = _ip_cliente()
        if _primeiro_acesso_bloqueado(ip):
            erro = "Muitas tentativas. Aguarde alguns minutos e tente novamente."
        else:
            cpf = cpf_apenas_digitos(request.form.get("cpf") or "")
            matricula = (request.form.get("matricula") or "").strip().upper()
            nascimento = (request.form.get("data_nascimento") or "").strip()
            login = (request.form.get("login") or "").strip()
            senha = request.form.get("senha") or ""
            confirmar = request.form.get("confirmar_senha") or ""
            pessoa = database.obter_pessoa_por_primeiro_acesso(cpf, matricula, nascimento)
            if not pessoa:
                _registrar_falha_primeiro_acesso(ip)
                erro = "Não foi possível validar os dados informados."
            elif database.obter_acesso_aluno_por_pessoa(pessoa["id"]):
                erro = "Esta matrícula já possui acesso ao app. Entre normalmente ou procure a recepção."
            elif not re.fullmatch(r"[A-Za-z0-9._@-]{3,80}", login):
                erro = "Crie um usuário de 3 a 80 caracteres usando letras, números, ponto, hífen, _ ou @."
            elif len(senha) < 8:
                erro = "A senha precisa ter pelo menos 8 caracteres."
            elif senha != confirmar:
                erro = "As senhas não coincidem."
            else:
                try:
                    database.salvar_acesso_aluno(pessoa["id"], login, auth_service.hash_senha(senha), True)
                    _primeiro_acesso_tentativas.pop(ip, None)
                    database.registrar_log_admin("ALUNO_AUTOATIVOU_APP", str(pessoa["id"]), login, ip)
                    return redirect(url_for("auth.pagina_login", ativado="1"))
                except ValueError as exc:
                    erro = str(exc)

    return render_template("primeiro_acesso.html", erro=erro)


@auth_bp.route("/logout")
def logout():
    database.registrar_log_admin("LOGOUT", session.get("usuario_login", "-"), "Sessão encerrada.", _ip_cliente())
    session.clear()
    return redirect(url_for("auth.pagina_login"))
