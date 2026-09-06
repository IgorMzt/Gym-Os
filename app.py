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

from flask import Flask, Response, abort, jsonify, redirect, render_template, request, session, url_for, send_file

from services import dashboard_service, auth_service, professor_service, exercise_service, workout_service, execution_service, assessment_service
from services.permissions import login_obrigatorio, papel_requerido
from services.payments import AsaasGateway, GatewayError
from routes.auth import auth_bp
import database
import config_service
import device_manager
import face_index
from validators import cpf_apenas_digitos, cpf_valido, data_iso, email_valido, parse_bool, parse_float, parse_int

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "troque-esta-secret-key-em-producao")
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
)

BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@app.context_processor
def contexto_global():
    return {
        "tema_padrao": config_service.get("tema_padrao", "system"),
        "csrf_token": csrf_token(),
        "credencial_padrao": CREDENCIAL_PADRAO,
        "papeis_usuario": auth_service.ROTULOS_PAPEL,
    }


DEFAULT_RESULTADO_MS = 2800
DEFAULT_INTERVALO_LOG = 5
DEFAULT_LIMIAR = 0.50
DEFAULT_LIVENESS_JANELA = 4

ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
CREDENCIAL_PADRAO = ADMIN_USER == "admin" and ADMIN_PASSWORD == "admin123"
liveness_estado = {}

# Banco e conta administrativa de bootstrap. A senha permanece controlada por ADMIN_PASSWORD.
database.criar_tabelas()
auth_service.garantir_admin_bootstrap(ADMIN_USER, ADMIN_PASSWORD)



def _ip_cliente():
    return request.remote_addr or "desconhecido"


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
    if request.endpoint in {"auth.pagina_login", "api_verificar", "api_presenca", "webhook_asaas"}:
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
    if request.path.startswith("/admin/") or session.get("usuario_logado"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


def cfg_int(chave, padrao):
    return config_service.get_int(chave, padrao)


def cfg_float(chave, padrao):
    return config_service.get_float(chave, padrao)


def cfg_bool(chave, padrao=True):
    return config_service.get_bool(chave, padrao)


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



def normalizar_dados_cadastro(dados, edicao=False, pessoa=None):
    nome = (dados.get("nome") or "").strip()
    cpf = cpf_apenas_digitos(dados.get("cpf") or "")
    plano_id = dados.get("plano_id")
    if plano_id in (None, ""):
        plano_id = None
    else:
        try:
            plano_id = int(plano_id)
        except ValueError:
            raise ValueError("Plano invalido.")
    plano = database.obter_plano(plano_id) if plano_id else None
    if not plano or not plano["ativo"]:
        raise ValueError("Selecione um plano ativo.")

    data_inicio = (dados.get("data_inicio") or "").strip()
    data_vencimento = (dados.get("data_vencimento") or "").strip()
    if not nome:
        raise ValueError("Informe o nome completo.")
    if not cpf_valido(cpf):
        raise ValueError("Informe um CPF valido.")
    if not data_inicio or not data_vencimento:
        raise ValueError("Informe o inicio e o vencimento do plano.")
    inicio = data_iso(data_inicio, "Data de inicio")
    vencimento = data_iso(data_vencimento, "Data de vencimento")
    if vencimento < inicio:
        raise ValueError("O vencimento nao pode ser anterior ao inicio.")

    nascimento_texto = (dados.get("data_nascimento") or "").strip()
    if nascimento_texto:
        nascimento = data_iso(nascimento_texto, "Data de nascimento")
        if nascimento > date.today():
            raise ValueError("A data de nascimento nao pode estar no futuro.")
    email = (dados.get("email") or "").strip() or None
    if not email_valido(email):
        raise ValueError("Informe um e-mail valido.")

    status_financeiro = (dados.get("status_financeiro") or "EM_DIA").upper()
    if status_financeiro not in {"EM_DIA", "PENDENTE", "VENCIDO"}:
        raise ValueError("Status financeiro invalido.")

    return {
        "nome": nome,
        "cpf": cpf,
        "data_nascimento": nascimento_texto or None,
        "sexo": (dados.get("sexo") or "").strip() or None,
        "telefone": (dados.get("telefone") or "").strip() or None,
        "email": email,
        "matricula": (pessoa or {}).get("matricula") if edicao else database.gerar_proxima_matricula(),
        "plano": plano["nome"],
        "plano_id": plano["id"],
        "data_inicio": data_inicio,
        "data_vencimento": data_vencimento,
        "status_financeiro": status_financeiro,
        "observacoes": (dados.get("observacoes") or "").strip() or None,
        "liberado": parse_bool(dados.get("liberado"), True),
    }


def decodificar_imagem(data_url):
    if not isinstance(data_url, str) or "," not in data_url:
        raise ValueError("Formato da imagem invalido.")
    _, conteudo = data_url.split(",", 1)
    dados_binarios = base64.b64decode(conteudo, validate=True)
    array_bytes = np.frombuffer(dados_binarios, dtype=np.uint8)
    imagem_bgr = cv2.imdecode(array_bytes, cv2.IMREAD_COLOR)
    if imagem_bgr is None:
        raise ValueError("Imagem invalida.")
    return cv2.cvtColor(imagem_bgr, cv2.COLOR_BGR2RGB), dados_binarios


def salvar_foto(dados_binarios):
    nome_arquivo = f"{uuid.uuid4().hex}.jpg"
    caminho = UPLOAD_DIR / nome_arquivo
    array = np.frombuffer(dados_binarios, dtype=np.uint8)
    imagem = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if imagem is None:
        raise ValueError("Nao foi possivel salvar a foto.")
    ok, encoded = cv2.imencode(".jpg", imagem, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
    if not ok:
        raise ValueError("Nao foi possivel salvar a foto.")
    caminho.write_bytes(encoded.tobytes())
    return f"uploads/{nome_arquivo}"


def limpar_foto(foto_path):
    if not foto_path:
        return
    caminho = BASE_DIR / "static" / foto_path
    try:
        if caminho.exists():
            caminho.unlink()
    except OSError:
        pass


def formatar_cpf(cpf):
    numeros = cpf_apenas_digitos(cpf or "")
    if len(numeros) != 11:
        return cpf or "-"
    return f"{numeros[:3]}.{numeros[3:6]}.{numeros[6:9]}-{numeros[9:]}"


def resposta_pessoa(pessoa, status, motivo):
    financeiro = database.status_financeiro_efetivo(pessoa)
    return {
        "id": pessoa["id"],
        "nome": pessoa["nome"],
        "cpf": formatar_cpf(pessoa.get("cpf")),
        "matricula": pessoa.get("matricula"),
        "plano": pessoa.get("plano") or "-",
        "plano_id": pessoa.get("plano_id"),
        "valor_plano": None,
        "data_vencimento": pessoa.get("data_vencimento") or "-",
        "status_financeiro": financeiro,
        "foto": url_for("static", filename=pessoa["foto_path"]) if pessoa.get("foto_path") else None,
        "status": status,
        "motivo": motivo,
    }


def enriquecer_pessoa_plano(pessoa):
    pessoa = dict(pessoa)
    pessoa["status_financeiro_efetivo"] = database.status_financeiro_efetivo(pessoa)
    if pessoa.get("plano_id"):
        plano = database.obter_plano(pessoa["plano_id"])
    else:
        plano = database.obter_plano_por_nome(pessoa.get("plano") or "")
    if plano:
        pessoa["valor_plano"] = plano["valor_centavos"]
        pessoa["duracao_plano"] = plano["duracao_dias"]
    return pessoa


def encontrar_melhor_pessoa(encoding_detectado, pessoas, amostras):
    melhor_pessoa = None
    melhor_distancia = None
    for pessoa in pessoas:
        encodings = amostras.get(pessoa["id"], [])
        if not encodings and pessoa.get("encoding") is not None:
            encodings = [pessoa["encoding"]]
        if not encodings:
            continue
        distancias = face_recognition.face_distance(encodings, encoding_detectado)
        distancia_pessoa = float(np.min(distancias))
        if melhor_distancia is None or distancia_pessoa < melhor_distancia:
            melhor_distancia = distancia_pessoa
            melhor_pessoa = pessoa
    return melhor_pessoa, melhor_distancia


def _chave_cliente(catraca_id=None):
    return f"{request.remote_addr or 'local'}:{catraca_id or 'sem-catraca'}"


def verificar_liveness(location, catraca_id=None):
    agora = time.monotonic()
    top, right, bottom, left = location
    centro = ((left + right) / 2, (top + bottom) / 2)
    area = max(1, (right - left) * (bottom - top))
    chave = _chave_cliente(catraca_id)
    anterior = liveness_estado.get(chave)
    liveness_estado[chave] = {"centro": centro, "area": area, "quando": agora}
    if not anterior or agora - anterior["quando"] > cfg_int("liveness_janela_segundos", DEFAULT_LIVENESS_JANELA):
        return False
    distancia_centro = float(np.hypot(centro[0] - anterior["centro"][0], centro[1] - anterior["centro"][1]))
    escala = max((right - left + bottom - top) / 2, 1)
    variacao_area = abs(area - anterior["area"]) / max(anterior["area"], 1)
    return distancia_centro / escala >= 0.08 or variacao_area >= 0.12


def resetar_liveness(catraca_id=None):
    liveness_estado.pop(_chave_cliente(catraca_id), None)


def obter_catraca_atual():
    catracas = database.listar_catracas(apenas_ativas=True)
    padrao_id = cfg_int("catraca_padrao_id", 1)
    return database.obter_catraca(padrao_id) or (catracas[0] if catracas else None)


def dados_config_catraca():
    catraca = obter_catraca_atual()
    catraca_publica = None
    if catraca:
        catraca_publica = {k: catraca.get(k) for k in ("id", "nome", "local", "modo", "ativa")}
    return {
        "tempo_resultado_ms": cfg_int("tempo_resultado_ms", DEFAULT_RESULTADO_MS),
        "intervalo_ms": max(500, min(5000, cfg_int("intervalo_reconhecimento_ms", 850))),
        "presenca_modo": config_service.get("presenca_modo", "inteligente"),
        "standby_sem_presenca_ms": max(5000, min(300000, cfg_int("standby_sem_presenca_ms", 30000))),
        "atraso_apos_presenca_ms": max(0, min(5000, cfg_int("atraso_apos_presenca_ms", 700))),
        "cooldown_proxima_pessoa_ms": max(0, min(60000, cfg_int("cooldown_proxima_pessoa_ms", 1000))),
        "ausencia_rearmar_ms": max(0, min(30000, cfg_int("ausencia_rearmar_ms", 1200))),
        "max_espera_saida_ms": max(0, min(120000, cfg_int("max_espera_saida_ms", 0))),
        "sensibilidade_presenca": config_service.get("sensibilidade_presenca", "media"),
        "erro_recuperacao_ms": max(500, min(30000, cfg_int("erro_recuperacao_ms", 2500))),
        "intervalo_detector_presenca_ms": max(100, min(5000, cfg_int("intervalo_detector_presenca_ms", 500))),
        "intervalo_historico_ms": max(1000, min(60000, cfg_int("intervalo_historico_ms", 5000))),
        "som_ativo": cfg_bool("som_ativo", True),
        "liveness_ativo": cfg_bool("liveness_ativo", True),
        "catraca": catraca_publica,
    }


def filtros_historico_seguros(origem):
    filtros = {k: str(origem.get(k, "") or "").strip() for k in ("data_inicio", "data_fim", "status", "termo", "catraca_id")}
    if filtros["status"] and filtros["status"] not in {"LIBERADO", "BLOQUEADO", "NEGADO", "ERRO"}:
        filtros["status"] = ""
    for chave in ("data_inicio", "data_fim"):
        if filtros[chave]:
            try:
                data_iso(filtros[chave], "Data")
            except ValueError:
                filtros[chave] = ""
    if filtros["catraca_id"]:
        try:
            filtros["catraca_id"] = str(parse_int(filtros["catraca_id"], "Catraca", minimo=1))
        except ValueError:
            filtros["catraca_id"] = ""
    filtros["termo"] = filtros["termo"][:100]
    return filtros



# Rotas de autenticação foram extraídas para o Blueprint auth.
app.register_blueprint(auth_bp)


# ---------- Paginas ----------

def enriquecer_pessoa_recepcao(pessoa, dias_alerta=7):
    pessoa = enriquecer_pessoa_plano(pessoa)
    hoje = date.today()
    vencimento = None
    dias_para_vencer = None
    if pessoa.get("data_vencimento"):
        try:
            vencimento = date.fromisoformat(str(pessoa["data_vencimento"])[:10])
            dias_para_vencer = (vencimento - hoje).days
        except ValueError:
            pass

    financeiro = (pessoa.get("status_financeiro") or "EM_DIA").upper()
    financeiro_efetivo = pessoa.get("status_financeiro_efetivo") or database.status_financeiro_efetivo(pessoa)
    bloqueado = not bool(pessoa.get("liberado"))
    vencido = financeiro_efetivo == "VENCIDO"
    vencendo = vencimento is not None and not vencido and 0 <= dias_para_vencer <= int(dias_alerta)
    inadimplente = financeiro == "PENDENTE"
    ativo = database.acesso_permitido(pessoa)[0]

    if bloqueado:
        status_operacional = "BLOQUEADO"
    elif vencido:
        status_operacional = "VENCIDO"
    elif inadimplente:
        status_operacional = "INADIMPLENTE"
    elif vencendo:
        status_operacional = "VENCENDO"
    else:
        status_operacional = "ATIVO" if ativo else "RESTRITO"

    pessoa.update({
        "status_operacional": status_operacional,
        "dias_para_vencer": dias_para_vencer,
        "filtro_ativo": ativo,
        "filtro_vencendo": vencendo,
        "filtro_vencido": vencido,
        "filtro_bloqueado": bloqueado,
        "filtro_inadimplente": inadimplente,
    })
    return pessoa

@app.route("/")
@papel_requerido("ADMIN","RECEPCAO")
def pagina_painel():
    return render_template("index.html", dash=dashboard_service.obter_dashboard())


@app.route("/api/dashboard")
@papel_requerido("ADMIN","RECEPCAO")
def api_dashboard():
    return jsonify({"sucesso": True, "dashboard": dashboard_service.obter_dashboard()})



@app.route("/minha-area")
@login_obrigatorio
def pagina_minha_area():
    papel = session.get("usuario_papel")
    if papel != "PROFESSOR":
        return redirect(url_for("pagina_painel"))
    professor = database.obter_professor_por_usuario(int(session.get("usuario_id")))
    if not professor:
        return render_template("minha_area.html", professor=None, alunos=[], disponiveis=[], fichas_pendentes=0)
    alunos = database.listar_alunos_professor(professor["id"])
    disponiveis = database.listar_alunos_disponiveis()
    return render_template("minha_area.html", professor=professor, alunos=alunos,
                           disponiveis=disponiveis,
                           fichas_pendentes=database.contar_fichas_pendentes_professor(professor["id"]),
                           metricas=database.metricas_professor(professor["id"]))


@app.route("/professores")
@papel_requerido("ADMIN")
def pagina_professores():
    return render_template(
        "professores.html",
        professores=database.listar_professores(),
        usuarios_professor=database.listar_usuarios_professor(),
    )


@app.route("/professores/<int:professor_id>")
@papel_requerido("ADMIN")
def pagina_professor(professor_id):
    professor = database.obter_professor(professor_id)
    if not professor:
        return redirect(url_for("pagina_professores"))
    vinculados = database.listar_alunos_professor(professor_id)
    vinculados_ids = {a["id"] for a in vinculados}
    disponiveis = [p for p in database.listar_pessoas() if p["id"] not in vinculados_ids]
    return render_template(
        "professor.html", professor=professor, alunos=vinculados, alunos_disponiveis=disponiveis,
        usuarios_professor=database.listar_usuarios_professor(),
    )


def _normalizar_professor(dados, atual=None):
    nome = (dados.get("nome") or "").strip()
    if len(nome) < 2 or len(nome) > 120:
        raise ValueError("Informe um nome válido.")
    cpf = cpf_apenas_digitos(dados.get("cpf") or "") or None
    if cpf and not cpf_valido(cpf):
        raise ValueError("CPF inválido.")
    email = (dados.get("email") or "").strip() or None
    if email and not email_valido(email):
        raise ValueError("E-mail inválido.")
    cref = (dados.get("cref") or "").strip().upper() or None
    if cref and len(cref) > 40:
        raise ValueError("CREF muito longo.")
    usuario_id = dados.get("usuario_id")
    usuario_id = int(usuario_id) if str(usuario_id or "").isdigit() else None
    if usuario_id and not database.usuario_professor_disponivel(usuario_id, (atual or {}).get("id")):
        raise ValueError("Essa conta não é de professor ou já está vinculada a outro professor.")
    return {
        "usuario_id": usuario_id,
        "nome": nome,
        "cpf": cpf,
        "cref": cref,
        "telefone": (dados.get("telefone") or "").strip() or None,
        "email": email,
        "especialidade": (dados.get("especialidade") or "").strip() or None,
        "observacoes": (dados.get("observacoes") or "").strip() or None,
        "ativo": parse_bool(dados.get("ativo"), True),
        "foto_path": (atual or {}).get("foto_path"),
    }


def _aplicar_foto_professor(dados, normalizado, atual=None):
    foto_base64 = dados.get("foto_base64")
    remover = parse_bool(dados.get("remover_foto"), False)
    antiga = (atual or {}).get("foto_path")
    if remover:
        normalizado["foto_path"] = None
        return antiga, None
    if foto_base64:
        _, binario = decodificar_imagem(foto_base64)
        nova = salvar_foto(binario)
        normalizado["foto_path"] = nova
        return antiga, nova
    return None, None


@app.route("/api/professores", methods=["POST"])
@papel_requerido("ADMIN")
def api_criar_professor():
    dados = request.get_json(silent=True) or {}
    nova_foto = None
    try:
        normalizado = _normalizar_professor(dados)
        _, nova_foto = _aplicar_foto_professor(dados, normalizado)
        professor_id = database.criar_professor(normalizado)
        database.registrar_log_admin("PROFESSOR_CRIADO", str(professor_id), normalizado["nome"], _ip_cliente())
        return jsonify({"sucesso": True, "id": professor_id, "redirect_url": url_for("pagina_professor", professor_id=professor_id)})
    except ValueError as exc:
        if nova_foto: limpar_foto(nova_foto)
        return jsonify({"sucesso": False, "erro": str(exc)}), 400
    except Exception as exc:
        if nova_foto: limpar_foto(nova_foto)
        if "UNIQUE constraint failed" in str(exc):
            return jsonify({"sucesso": False, "erro": "CPF, CREF ou conta de usuário já vinculados a outro professor."}), 409
        return jsonify({"sucesso": False, "erro": "Não foi possível cadastrar o professor."}), 500


@app.route("/api/professores/<int:professor_id>", methods=["PUT"])
@papel_requerido("ADMIN")
def api_editar_professor(professor_id):
    atual = database.obter_professor(professor_id)
    if not atual:
        return jsonify({"sucesso": False, "erro": "Professor não encontrado."}), 404
    dados = request.get_json(silent=True) or {}
    antiga_foto = nova_foto = None
    try:
        normalizado = _normalizar_professor(dados, atual)
        antiga_foto, nova_foto = _aplicar_foto_professor(dados, normalizado, atual)
        database.atualizar_professor(professor_id, normalizado)
        if antiga_foto and (nova_foto or parse_bool(dados.get("remover_foto"), False)):
            limpar_foto(antiga_foto)
        database.registrar_log_admin("PROFESSOR_ATUALIZADO", str(professor_id), normalizado["nome"], _ip_cliente())
        return jsonify({"sucesso": True})
    except ValueError as exc:
        if nova_foto: limpar_foto(nova_foto)
        return jsonify({"sucesso": False, "erro": str(exc)}), 400
    except Exception as exc:
        if nova_foto: limpar_foto(nova_foto)
        if "UNIQUE constraint failed" in str(exc):
            return jsonify({"sucesso": False, "erro": "CPF, CREF ou conta de usuário já vinculados a outro professor."}), 409
        return jsonify({"sucesso": False, "erro": "Não foi possível atualizar o professor."}), 500


@app.route("/api/professores/<int:professor_id>/alunos/<int:pessoa_id>", methods=["POST", "DELETE"])
@papel_requerido("ADMIN")
def api_vinculo_professor_aluno(professor_id, pessoa_id):
    try:
        if request.method == "POST":
            database.vincular_aluno_professor(professor_id, pessoa_id)
            acao = "PROFESSOR_ALUNO_VINCULADO"
        else:
            database.desvincular_aluno_professor(professor_id, pessoa_id)
            acao = "PROFESSOR_ALUNO_DESVINCULADO"
        database.registrar_log_admin(acao, str(professor_id), f"aluno:{pessoa_id}", _ip_cliente())
        return jsonify({"sucesso": True})
    except ValueError as exc:
        return jsonify({"sucesso": False, "erro": str(exc)}), 400


@app.route("/minha-area/alunos/<int:pessoa_id>")
@papel_requerido("PROFESSOR")
def pagina_aluno_professor(pessoa_id):
    usuario_id = int(session.get("usuario_id"))
    if not professor_service.pode_acessar_aluno(usuario_id, pessoa_id):
        return redirect(url_for("pagina_minha_area"))
    pessoa = database.obter_pessoa(pessoa_id)
    if not pessoa:
        return redirect(url_for("pagina_minha_area"))
    avaliacoes = database.listar_avaliacoes_fisicas(pessoa_id)
    return render_template(
        "aluno_professor.html",
        pessoa=pessoa,
        historico=database.listar_logs_pessoa(pessoa_id, 20),
        professores=database.listar_professores_aluno(pessoa_id),
        avaliacoes=avaliacoes,
        comparacao_avaliacao=assessment_service.comparacao(avaliacoes),
    )


@app.route("/api/professor/alunos/<int:pessoa_id>/assumir", methods=["POST"])
@papel_requerido("PROFESSOR")
def api_professor_assumir_aluno(pessoa_id):
    professor=database.obter_professor_por_usuario(int(session.get("usuario_id")))
    if not professor:
        return jsonify({"sucesso":False,"erro":"Seu usuário não está vinculado a um cadastro de professor."}),403
    ok,erro=database.assumir_aluno_professor(professor["id"],pessoa_id)
    if not ok: return jsonify({"sucesso":False,"erro":erro}),409
    pessoa=database.obter_pessoa(pessoa_id)
    database.registrar_log_admin("PROFESSOR_ASSUMIU_ALUNO",str(pessoa_id),
        f"{professor['nome']} assumiu {pessoa['nome'] if pessoa else pessoa_id}",_ip_cliente())
    return jsonify({"sucesso":True})

@app.route("/api/professor/alunos/<int:pessoa_id>/liberar", methods=["POST"])
@papel_requerido("PROFESSOR")
def api_professor_liberar_aluno(pessoa_id):
    professor=database.obter_professor_por_usuario(int(session.get("usuario_id")))
    if not professor:
        return jsonify({"sucesso":False,"erro":"Seu usuário não está vinculado a um cadastro de professor."}),403
    ok,erro=database.liberar_aluno_professor(professor["id"],pessoa_id)
    if not ok: return jsonify({"sucesso":False,"erro":erro}),409
    pessoa=database.obter_pessoa(pessoa_id)
    database.registrar_log_admin("PROFESSOR_LIBEROU_ALUNO",str(pessoa_id),
        f"{professor['nome']} liberou {pessoa['nome'] if pessoa else pessoa_id}",_ip_cliente())
    return jsonify({"sucesso":True})


@app.route("/api/pessoas/<int:pessoa_id>/acesso-app", methods=["POST"])
@papel_requerido("ADMIN")
def api_salvar_acesso_app_aluno(pessoa_id):
    payload = request.get_json(silent=True) or {}
    pessoa = database.obter_pessoa(pessoa_id)
    if not pessoa:
        return jsonify({"sucesso":False,"erro":"Aluno não encontrado."}),404
    login = (payload.get("login") or "").strip()
    senha = payload.get("senha") or ""
    ativo = parse_bool(payload.get("ativo"), True)
    atual = database.obter_acesso_aluno_por_pessoa(pessoa_id)
    if len(login) < 3 or len(login) > 80:
        return jsonify({"sucesso":False,"erro":"O login deve ter entre 3 e 80 caracteres."}),400
    if not re.fullmatch(r"[A-Za-z0-9._@-]+", login):
        return jsonify({"sucesso":False,"erro":"Use apenas letras, números, ponto, hífen, _ ou @ no login."}),400
    if not atual and len(senha) < 6:
        return jsonify({"sucesso":False,"erro":"A senha inicial deve ter pelo menos 6 caracteres."}),400
    if senha and len(senha) < 6:
        return jsonify({"sucesso":False,"erro":"A nova senha deve ter pelo menos 6 caracteres."}),400
    try:
        acesso_id = database.salvar_acesso_aluno(
            pessoa_id, login,
            auth_service.hash_senha(senha) if senha else None,
            ativo
        )
        database.registrar_log_admin(
            "ACESSO_APP_ALUNO_ATUALIZADO", str(pessoa_id),
            f"login:{login};ativo:{1 if ativo else 0}", _ip_cliente()
        )
        return jsonify({"sucesso":True,"id":acesso_id,"login":login,"ativo":ativo})
    except ValueError as exc:
        return jsonify({"sucesso":False,"erro":str(exc)}),409
    except sqlite3.IntegrityError:
        return jsonify({"sucesso":False,"erro":"Este login já está em uso."}),409


def _aluno_id_sessao():
    if session.get("usuario_papel") != "ALUNO":
        return None
    try:
        return int(session.get("aluno_id"))
    except (TypeError, ValueError):
        return None


def _dados_app_aluno(pessoa_id):
    pessoa = database.obter_pessoa(pessoa_id)
    if not pessoa:
        return None
    pessoa = enriquecer_pessoa_recepcao(pessoa, max(1,min(60,cfg_int("dias_alerta_vencimento",7))))
    ficha = database.obter_ficha_ativa_aluno(pessoa_id)
    sessao = database.obter_sessao_em_andamento_aluno(pessoa_id)
    professor = database.obter_professor_ativo_do_aluno(pessoa_id)
    sessoes = database.listar_sessoes_treino([pessoa_id], 8)
    avaliacoes = database.listar_avaliacoes_fisicas(pessoa_id)
    cobrancas = database.listar_cobrancas_pessoa(pessoa_id, 50)
    cobranca_aberta = database.obter_cobranca_aberta(pessoa_id)
    plano = database.obter_plano(pessoa.get("plano_id")) if pessoa.get("plano_id") else None
    return {
        "pessoa": pessoa, "ficha": ficha, "sessao": sessao,
        "professor": professor, "sessoes": sessoes,
        "avaliacoes": avaliacoes,
        "plano": plano, "cobrancas": cobrancas,
        "cobranca_aberta": cobranca_aberta,
        "asaas_configurado": AsaasGateway().configurado,
        "proximo_treino": database.proximo_treino_aluno(pessoa_id),
    }


@app.route("/app")
@papel_requerido("ALUNO")
def aluno_app_inicio():
    pessoa_id = _aluno_id_sessao()
    dados = _dados_app_aluno(pessoa_id)
    if not dados:
        session.clear()
        return redirect(url_for("auth.pagina_login"))
    return render_template("aluno_app_inicio.html", **dados)


@app.route("/app/treino")
@papel_requerido("ALUNO")
def aluno_app_treino():
    pessoa_id = _aluno_id_sessao()
    dados = _dados_app_aluno(pessoa_id)
    return render_template("aluno_app_treino.html", **dados)


@app.route("/app/execucao/<int:sessao_id>")
@papel_requerido("ALUNO")
def aluno_app_execucao(sessao_id):
    sessao = database.obter_sessao_treino(sessao_id)
    if not sessao or int(sessao["pessoa_id"]) != int(_aluno_id_sessao()):
        abort(404)
    for item in sessao.get("itens", []):
        item["ultima_execucao"] = database.ultima_execucao_exercicio(
            int(sessao["pessoa_id"]), int(item["exercicio_id"])
        ) if item.get("exercicio_id") else None
    return render_template("aluno_app_execucao.html", sessao=sessao)


@app.route("/app/historico")
@papel_requerido("ALUNO")
def aluno_app_historico():
    pessoa_id = _aluno_id_sessao()
    pessoa = database.obter_pessoa(pessoa_id)
    sessoes = database.listar_sessoes_treino([pessoa_id], 100)
    cargas = database.listar_ultimas_cargas_aluno(pessoa_id, 12)
    return render_template("aluno_app_historico.html", pessoa=pessoa, sessoes=sessoes, cargas=cargas)


@app.route("/app/evolucao")
@papel_requerido("ALUNO")
def aluno_app_evolucao():
    pessoa_id = _aluno_id_sessao()
    pessoa = database.obter_pessoa(pessoa_id)
    avaliacoes = database.listar_avaliacoes_fisicas(pessoa_id)
    return render_template(
        "aluno_app_evolucao.html",
        pessoa=pessoa, avaliacoes=avaliacoes,
        comparacao=assessment_service.comparacao(avaliacoes)
    )


@app.route("/app/perfil")
@papel_requerido("ALUNO")
def aluno_app_perfil():
    pessoa_id = _aluno_id_sessao()
    dados = _dados_app_aluno(pessoa_id)
    return render_template("aluno_app_perfil.html", **dados)


@app.route("/app/financeiro")
@papel_requerido("ALUNO")
def aluno_app_financeiro():
    pessoa_id = _aluno_id_sessao()
    dados = _dados_app_aluno(pessoa_id)
    return render_template("aluno_app_financeiro.html", **dados)


@app.route("/api/app/financeiro/status")
@papel_requerido("ALUNO")
def api_app_financeiro_status():
    pessoa_id = _aluno_id_sessao()
    pessoa = database.obter_pessoa(pessoa_id)
    if not pessoa:
        return jsonify({"sucesso":False,"erro":"Aluno não encontrado."}),404
    pessoa = enriquecer_pessoa_recepcao(
        pessoa, max(1,min(60,cfg_int("dias_alerta_vencimento",7)))
    )
    cobranca = database.obter_cobranca_aberta(pessoa_id)
    return jsonify({
        "sucesso":True,
        "status_financeiro":pessoa.get("status_financeiro"),
        "status_financeiro_efetivo":pessoa.get("status_financeiro_efetivo"),
        "status_operacional":pessoa.get("status_operacional"),
        "data_vencimento":pessoa.get("data_vencimento"),
        "cobranca": {
            "id":cobranca.get("id"),
            "status":cobranca.get("status"),
            "valor_centavos":cobranca.get("valor_centavos"),
            "vencimento":cobranca.get("vencimento_original"),
            "pix_payload":cobranca.get("pix_payload"),
            "pix_qr_base64":cobranca.get("pix_qr_base64"),
        } if cobranca else None
    })


@app.route("/api/app/financeiro/pix", methods=["POST"])
@papel_requerido("ALUNO")
def api_app_gerar_pix():
    pessoa_id = _aluno_id_sessao()
    pessoa = database.obter_pessoa(pessoa_id)
    if not pessoa:
        return jsonify({"sucesso":False,"erro":"Aluno não encontrado."}),404
    plano = database.obter_plano(pessoa.get("plano_id")) if pessoa.get("plano_id") else None
    if not plano:
        return jsonify({"sucesso":False,"erro":"Seu cadastro está sem plano válido. Procure a recepção."}),400
    if not pessoa.get("cpf"):
        return jsonify({"sucesso":False,"erro":"Seu cadastro está sem CPF. Procure a recepção."}),400
    if not pessoa.get("data_vencimento"):
        return jsonify({"sucesso":False,"erro":"Seu cadastro está sem vencimento. Procure a recepção."}),400

    aberta = database.obter_cobranca_aberta(pessoa_id, pessoa.get("data_vencimento"))
    if aberta:
        return jsonify({
            "sucesso":True,"existente":True,
            "payment_id":aberta.get("gateway_payment_id"),
            "valor_centavos":aberta.get("valor_centavos"),
            "vencimento":aberta.get("vencimento_original"),
            "status":aberta.get("status"),
            "payload":aberta.get("pix_payload"),
            "encodedImage":aberta.get("pix_qr_base64")
        })

    gateway = AsaasGateway()
    try:
        customer_id = database.obter_gateway_cliente(pessoa_id)
        if not customer_id:
            existente = gateway.localizar_cliente(pessoa_id)
            cliente = existente or gateway.criar_cliente(pessoa)
            customer_id = cliente["id"]
            database.salvar_gateway_cliente(pessoa_id,customer_id)
        referencia = f"PANO-APP-{pessoa_id}-{int(time.time())}"
        pg = gateway.criar_cobranca_pix(
            customer_id,int(plano["valor_centavos"]),
            pessoa["data_vencimento"],referencia
        )
        pix = gateway.obter_pix(pg["id"])
        database.criar_cobranca_local(
            pessoa_id,plano["id"],pg["id"],customer_id,
            int(plano["valor_centavos"]),pessoa["data_vencimento"],
            pix.get("payload"),pix.get("encodedImage")
        )
        database.registrar_log_admin(
            "COBRANCA_PIX_CRIADA_ALUNO_APP",str(pessoa_id),pg["id"],_ip_cliente()
        )
        return jsonify({
            "sucesso":True,"existente":False,"payment_id":pg["id"],
            "valor_centavos":plano["valor_centavos"],
            "vencimento":pessoa["data_vencimento"],
            "status":"PENDENTE","payload":pix.get("payload"),
            "encodedImage":pix.get("encodedImage")
        })
    except GatewayError as exc:
        return jsonify({"sucesso":False,"erro":str(exc)}),502
    except Exception as exc:
        app.logger.exception("Falha ao gerar PIX pelo app do aluno")
        return jsonify({"sucesso":False,"erro":"Não foi possível gerar o PIX agora. Tente novamente ou procure a recepção."}),500


@app.route("/app/exercicios/<int:exercicio_id>")
@papel_requerido("ALUNO")
def aluno_app_exercicio(exercicio_id):
    pessoa_id=_aluno_id_sessao()
    historico=database.historico_exercicio_aluno(pessoa_id,exercicio_id,40)
    if not historico: abort(404)
    return render_template("aluno_app_exercicio.html",pessoa=database.obter_pessoa(pessoa_id),
                           historico=historico,exercicio_id=exercicio_id)


@app.route("/api/app/senha", methods=["POST"])
@papel_requerido("ALUNO")
def api_app_trocar_senha():
    acesso=database.obter_acesso_aluno_por_pessoa(_aluno_id_sessao())
    payload=request.get_json(silent=True) or {}
    atual=payload.get("senha_atual") or ""; nova=payload.get("nova_senha") or ""
    if not acesso or not auth_service.check_password_hash(acesso.get("senha_hash") or "",atual):
        return jsonify({"sucesso":False,"erro":"Senha atual incorreta."}),400
    if len(nova)<8:
        return jsonify({"sucesso":False,"erro":"A nova senha precisa ter pelo menos 8 caracteres."}),400
    database.salvar_acesso_aluno(acesso["pessoa_id"],acesso["login"],auth_service.hash_senha(nova),bool(acesso["ativo"]))
    database.registrar_log_admin("ALUNO_TROCOU_SENHA",str(acesso["pessoa_id"]),acesso["login"],_ip_cliente())
    return jsonify({"sucesso":True})


@app.route("/api/app/execucoes/iniciar", methods=["POST"])
@papel_requerido("ALUNO")
def api_app_iniciar_execucao():
    pessoa_id = _aluno_id_sessao()
    payload = request.get_json(silent=True) or {}
    try:
        treino_id = int(payload.get("treino_id"))
    except (TypeError,ValueError):
        return jsonify({"sucesso":False,"erro":"Treino inválido."}),400
    sessao_id,erro = database.criar_sessao_treino(
        pessoa_id,treino_id,int(session.get("usuario_id")),"ALUNO_APP"
    )
    if not sessao_id:
        return jsonify({"sucesso":False,"erro":erro}),400
    if erro != "JA_EXISTE":
        database.registrar_log_admin("TREINO_INICIADO_ALUNO_APP",str(sessao_id),f"aluno:{pessoa_id}",_ip_cliente())
    return jsonify({"sucesso":True,"id":sessao_id,"reutilizada":erro=="JA_EXISTE"})


@app.route("/api/app/execucoes/<int:sessao_id>", methods=["GET"])
@papel_requerido("ALUNO")
def api_app_obter_execucao(sessao_id):
    sessao = database.obter_sessao_treino(sessao_id)
    if not sessao or int(sessao["pessoa_id"]) != int(_aluno_id_sessao()):
        return jsonify({"sucesso":False,"erro":"Sessão não encontrada."}),404
    return jsonify({"sucesso":True,"sessao":sessao})


@app.route("/api/app/execucoes/itens/<int:item_id>", methods=["PUT"])
@papel_requerido("ALUNO")
def api_app_atualizar_item(item_id):
    conn = database.conectar()
    try:
        row = conn.execute("SELECT sessao_id FROM treino_sessao_itens WHERE id=?",(item_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        return jsonify({"sucesso":False,"erro":"Item não encontrado."}),404
    sessao = database.obter_sessao_treino(row["sessao_id"])
    if not sessao or int(sessao["pessoa_id"]) != int(_aluno_id_sessao()):
        return jsonify({"sucesso":False,"erro":"Sem permissão."}),403
    try:
        dados = execution_service.normalizar_item(request.get_json(silent=True) or {})
    except ValueError as exc:
        return jsonify({"sucesso":False,"erro":str(exc)}),400
    ok,erro,_ = database.atualizar_item_sessao(item_id,dados)
    return jsonify({"sucesso":ok,"erro":erro}) if ok else (jsonify({"sucesso":False,"erro":erro}),409)


@app.route("/api/app/execucoes/<int:sessao_id>/concluir", methods=["POST"])
@papel_requerido("ALUNO")
def api_app_concluir_execucao(sessao_id):
    sessao = database.obter_sessao_treino(sessao_id)
    if not sessao or int(sessao["pessoa_id"]) != int(_aluno_id_sessao()):
        return jsonify({"sucesso":False,"erro":"Sessão não encontrada."}),404
    obs = execution_service.normalizar_observacao(request.get_json(silent=True) or {})
    ok,erro = database.concluir_sessao_treino(sessao_id,obs)
    if not ok:
        return jsonify({"sucesso":False,"erro":erro}),409
    database.registrar_log_admin("TREINO_CONCLUIDO_ALUNO_APP",str(sessao_id),sessao["treino_nome"],_ip_cliente())
    return jsonify({"sucesso":True})


@app.route("/api/app/execucoes/<int:sessao_id>/cancelar", methods=["POST"])
@papel_requerido("ALUNO")
def api_app_cancelar_execucao(sessao_id):
    sessao = database.obter_sessao_treino(sessao_id)
    if not sessao or int(sessao["pessoa_id"]) != int(_aluno_id_sessao()):
        return jsonify({"sucesso":False,"erro":"Sessão não encontrada."}),404
    obs = execution_service.normalizar_observacao(request.get_json(silent=True) or {})
    ok,erro = database.cancelar_sessao_treino(sessao_id,obs)
    return jsonify({"sucesso":True}) if ok else (jsonify({"sucesso":False,"erro":erro}),409)


@app.route("/sw.js")
def aluno_service_worker():
    response = send_file(BASE_DIR / "static" / "sw.js", mimetype="application/javascript")
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache"
    return response


def _escopo_avaliacoes():
    if session.get("usuario_papel") == "ADMIN":
        return None
    professor = database.obter_professor_por_usuario(int(session.get("usuario_id")))
    return [p["id"] for p in database.listar_alunos_professor(professor["id"])] if professor else []


@app.route("/avaliacoes")
@papel_requerido("ADMIN", "PROFESSOR")
def pagina_avaliacoes():
    pessoa_ids = _escopo_avaliacoes()
    return render_template(
        "avaliacoes.html",
        alunos=database.resumo_avaliacoes_alunos(pessoa_ids),
        estatisticas=database.estatisticas_avaliacoes(pessoa_ids),
    )


@app.route("/avaliacoes/<int:pessoa_id>")
@papel_requerido("ADMIN", "PROFESSOR")
def pagina_avaliacoes_aluno(pessoa_id):
    if not _professor_pode_gerir_aluno(pessoa_id):
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


@app.route("/api/avaliacoes/<int:pessoa_id>", methods=["POST"])
@papel_requerido("ADMIN", "PROFESSOR")
def api_criar_avaliacao(pessoa_id):
    if not _professor_pode_gerir_aluno(pessoa_id):
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


@app.route("/api/avaliacoes/detalhe/<int:avaliacao_id>", methods=["GET","PUT"])
@papel_requerido("ADMIN", "PROFESSOR")
def api_avaliacao_detalhe(avaliacao_id):
    atual=database.obter_avaliacao_fisica(avaliacao_id)
    if not atual:
        return jsonify({"sucesso":False,"erro":"Avaliação não encontrada."}),404
    if not _professor_pode_gerir_aluno(atual["pessoa_id"]):
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


@app.route("/execucoes")
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


@app.route("/execucoes/<int:sessao_id>")
@papel_requerido("ADMIN", "PROFESSOR")
def pagina_execucao(sessao_id):
    sessao = database.obter_sessao_treino(sessao_id)
    if not sessao:
        abort(404)
    if not _professor_pode_gerir_aluno(sessao["pessoa_id"]):
        abort(403)
    return render_template("execucao_treino.html", sessao=sessao)


@app.route("/api/execucoes/iniciar", methods=["POST"])
@papel_requerido("ADMIN", "PROFESSOR")
def api_iniciar_execucao():
    payload = request.get_json(silent=True) or {}
    try:
        pessoa_id = int(payload.get("pessoa_id"))
        treino_id = int(payload.get("treino_id"))
    except (TypeError, ValueError):
        return jsonify({"sucesso":False,"erro":"Aluno ou treino inválido."}),400
    if not _professor_pode_gerir_aluno(pessoa_id):
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


@app.route("/api/execucoes/<int:sessao_id>", methods=["GET"])
@papel_requerido("ADMIN", "PROFESSOR")
def api_obter_execucao(sessao_id):
    sessao=database.obter_sessao_treino(sessao_id)
    if not sessao:
        return jsonify({"sucesso":False,"erro":"Sessão não encontrada."}),404
    if not _professor_pode_gerir_aluno(sessao["pessoa_id"]):
        return jsonify({"sucesso":False,"erro":"Sem permissão."}),403
    return jsonify({"sucesso":True,"sessao":sessao})


@app.route("/api/execucoes/itens/<int:item_id>", methods=["PUT"])
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
    if not sessao or not _professor_pode_gerir_aluno(sessao["pessoa_id"]):
        return jsonify({"sucesso":False,"erro":"Sem permissão."}),403
    ok,erro,_=database.atualizar_item_sessao(item_id,dados)
    if not ok:
        return jsonify({"sucesso":False,"erro":erro}),409
    return jsonify({"sucesso":True})


@app.route("/api/execucoes/<int:sessao_id>/concluir", methods=["POST"])
@papel_requerido("ADMIN", "PROFESSOR")
def api_concluir_execucao(sessao_id):
    sessao=database.obter_sessao_treino(sessao_id)
    if not sessao:
        return jsonify({"sucesso":False,"erro":"Sessão não encontrada."}),404
    if not _professor_pode_gerir_aluno(sessao["pessoa_id"]):
        return jsonify({"sucesso":False,"erro":"Sem permissão."}),403
    obs=execution_service.normalizar_observacao(request.get_json(silent=True) or {})
    ok,erro=database.concluir_sessao_treino(sessao_id,obs)
    if not ok:
        return jsonify({"sucesso":False,"erro":erro}),409
    database.registrar_log_admin("TREINO_CONCLUIDO",str(sessao_id),sessao["treino_nome"],_ip_cliente())
    return jsonify({"sucesso":True})


@app.route("/api/execucoes/<int:sessao_id>/cancelar", methods=["POST"])
@papel_requerido("ADMIN", "PROFESSOR")
def api_cancelar_execucao(sessao_id):
    sessao=database.obter_sessao_treino(sessao_id)
    if not sessao:
        return jsonify({"sucesso":False,"erro":"Sessão não encontrada."}),404
    if not _professor_pode_gerir_aluno(sessao["pessoa_id"]):
        return jsonify({"sucesso":False,"erro":"Sem permissão."}),403
    obs=execution_service.normalizar_observacao(request.get_json(silent=True) or {})
    ok,erro=database.cancelar_sessao_treino(sessao_id,obs)
    if not ok:
        return jsonify({"sucesso":False,"erro":erro}),409
    database.registrar_log_admin("TREINO_CANCELADO",str(sessao_id),sessao["treino_nome"],_ip_cliente())
    return jsonify({"sucesso":True})


@app.route("/treinos")
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


def _professor_pode_gerir_aluno(pessoa_id):
    if session.get("usuario_papel") == "ADMIN":
        return True
    professor = database.obter_professor_por_usuario(int(session.get("usuario_id")))
    if not professor:
        return False
    return any(p["id"] == int(pessoa_id) for p in database.listar_alunos_professor(professor["id"]))


@app.route("/api/fichas-treino/<int:ficha_id>", methods=["GET"])
@papel_requerido("ADMIN", "PROFESSOR")
def api_obter_ficha_treino(ficha_id):
    ficha = database.obter_ficha_treino(ficha_id)
    if not ficha:
        return jsonify({"sucesso": False, "erro": "Ficha não encontrada."}), 404
    if not _professor_pode_gerir_aluno(ficha["pessoa_id"]):
        return jsonify({"sucesso": False, "erro": "Sem permissão para esta ficha."}), 403
    return jsonify({"sucesso": True, "ficha": ficha})


@app.route("/api/fichas-treino", methods=["POST"])
@papel_requerido("ADMIN", "PROFESSOR")
def api_criar_ficha_treino():
    payload = request.get_json(silent=True) or {}
    try:
        dados = workout_service.normalizar(payload)
        if not database.obter_pessoa(dados["pessoa_id"]):
            return jsonify({"sucesso": False, "erro": "Aluno não encontrado."}), 404
        if not _professor_pode_gerir_aluno(dados["pessoa_id"]):
            return jsonify({"sucesso": False, "erro": "Sem permissão para este aluno."}), 403
        ficha_id = database.criar_ficha_treino(dados, int(session.get("usuario_id")))
        database.registrar_log_admin("FICHA_TREINO_CRIADA", str(ficha_id), dados["nome"], _ip_cliente())
        return jsonify({"sucesso": True, "id": ficha_id})
    except ValueError as exc:
        return jsonify({"sucesso": False, "erro": str(exc)}), 400
    except sqlite3.IntegrityError:
        return jsonify({"sucesso": False, "erro": "A ficha contém aluno, professor ou exercício inválido."}), 400
    except Exception:
        return jsonify({"sucesso": False, "erro": "Não foi possível criar a ficha."}), 500


@app.route("/api/fichas-treino/<int:ficha_id>/duplicar", methods=["POST"])
@papel_requerido("ADMIN","PROFESSOR")
def api_duplicar_ficha_treino(ficha_id):
    original=database.obter_ficha_treino(ficha_id)
    if not original or not _professor_pode_gerir_aluno(original["pessoa_id"]):
        return jsonify({"sucesso":False,"erro":"Ficha não encontrada ou sem permissão."}),404
    payload=request.get_json(silent=True) or {}
    try: pessoa_id=int(payload.get("pessoa_id"))
    except (TypeError,ValueError): return jsonify({"sucesso":False,"erro":"Selecione o aluno de destino."}),400
    if not _professor_pode_gerir_aluno(pessoa_id):
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


@app.route("/api/fichas-treino/<int:ficha_id>", methods=["PUT"])
@papel_requerido("ADMIN", "PROFESSOR")
def api_atualizar_ficha_treino(ficha_id):
    atual = database.obter_ficha_treino(ficha_id)
    if not atual:
        return jsonify({"sucesso": False, "erro": "Ficha não encontrada."}), 404
    if not _professor_pode_gerir_aluno(atual["pessoa_id"]):
        return jsonify({"sucesso": False, "erro": "Sem permissão para esta ficha."}), 403
    payload = request.get_json(silent=True) or {}
    try:
        dados = workout_service.normalizar(payload)
        if not _professor_pode_gerir_aluno(dados["pessoa_id"]):
            return jsonify({"sucesso": False, "erro": "Sem permissão para este aluno."}), 403
        database.atualizar_ficha_treino(ficha_id, dados)
        database.registrar_log_admin("FICHA_TREINO_ATUALIZADA", str(ficha_id), dados["nome"], _ip_cliente())
        return jsonify({"sucesso": True})
    except ValueError as exc:
        return jsonify({"sucesso": False, "erro": str(exc)}), 400
    except sqlite3.IntegrityError:
        return jsonify({"sucesso": False, "erro": "A ficha contém aluno, professor ou exercício inválido."}), 400
    except Exception:
        return jsonify({"sucesso": False, "erro": "Não foi possível atualizar a ficha."}), 500


@app.route("/exercicios")
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


@app.route("/api/exercicios/<int:exercicio_id>", methods=["GET"])
@papel_requerido("ADMIN", "PROFESSOR")
def api_obter_exercicio(exercicio_id):
    exercicio = database.obter_exercicio(exercicio_id)
    if not exercicio:
        return jsonify({"sucesso": False, "erro": "Exercício não encontrado."}), 404
    return jsonify({"sucesso": True, "exercicio": exercicio})


@app.route("/api/exercicios", methods=["POST"])
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


@app.route("/api/exercicios/<int:exercicio_id>", methods=["PUT"])
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


@app.route("/usuarios")
@papel_requerido("ADMIN")
def pagina_usuarios():
    return render_template("usuarios.html", usuarios=database.listar_usuarios(), papeis=auth_service.ROTULOS_PAPEL)


@app.route("/api/usuarios", methods=["POST"])
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


@app.route("/api/usuarios/<int:usuario_id>", methods=["PUT"])
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


@app.route("/catraca")
def pagina_catraca():
    return render_template("verificacao.html", config_catraca=dados_config_catraca())


@app.route("/verificacao")
def pagina_verificacao():
    return redirect(url_for("pagina_catraca"))


@app.route("/cadastro")
@papel_requerido("ADMIN","RECEPCAO")
def pagina_cadastro():
    return render_template("cadastro.html", hoje=date.today().isoformat(), planos=database.listar_planos(True), cadastro_redirect_ms=max(0, min(30000, cfg_int("cadastro_redirect_ms", 3000))), cadastro_preparacao_captura_ms=max(0, min(5000, cfg_int("cadastro_preparacao_captura_ms", 550))), cadastro_intervalo_captura_ms=max(0, min(5000, cfg_int("cadastro_intervalo_captura_ms", 450))))


@app.route("/gerenciar")
@papel_requerido("ADMIN","RECEPCAO")
def pagina_gerenciar():
    dias_alerta = max(1, min(60, cfg_int("dias_alerta_vencimento", 7)))
    pessoas = database.listar_pessoas()
    ultimos = {p["id"]: p.get("ultimo_acesso") for p in database.listar_pessoas_com_ultimo_acesso()}
    pessoas = [dict(p, ultimo_acesso=ultimos.get(p["id"])) for p in pessoas]
    pessoas = [enriquecer_pessoa_recepcao(p, dias_alerta) for p in pessoas]
    resumo = {
        "total": len(pessoas),
        "ativos": sum(1 for p in pessoas if p["filtro_ativo"]),
        "vencendo": sum(1 for p in pessoas if p["filtro_vencendo"]),
        "vencidos": sum(1 for p in pessoas if p["filtro_vencido"]),
        "bloqueados": sum(1 for p in pessoas if p["filtro_bloqueado"]),
        "inadimplentes": sum(1 for p in pessoas if p["filtro_inadimplente"]),
    }
    return render_template("gerenciar.html", pessoas=pessoas, resumo=resumo, dias_alerta=dias_alerta)


def _render_aluno(pessoa_id):
    pessoa = database.obter_pessoa(pessoa_id)
    if not pessoa:
        return redirect(url_for("pagina_gerenciar"))
    dias_alerta = max(1, min(60, cfg_int("dias_alerta_vencimento", 7)))
    pessoa = enriquecer_pessoa_recepcao(pessoa, dias_alerta)
    historico = database.listar_logs_pessoa(pessoa_id, 20)
    return render_template(
        "aluno.html",
        pessoa=pessoa,
        planos=database.listar_planos(True),
        historico=historico,
        cobrancas=database.listar_cobrancas_pessoa(pessoa_id),
        eventos_financeiros=database.listar_eventos_financeiros_pessoa(pessoa_id),
        cobranca_aberta=database.obter_cobranca_aberta(pessoa_id),
        asaas_configurado=AsaasGateway().configurado,
        acesso_app=database.obter_acesso_aluno_por_pessoa(pessoa_id),
        cadastro_preparacao_captura_ms=max(0, min(5000, cfg_int("cadastro_preparacao_captura_ms", 550))),
        cadastro_intervalo_captura_ms=max(0, min(5000, cfg_int("cadastro_intervalo_captura_ms", 450))),
    )


@app.route("/alunos/<int:pessoa_id>")
@papel_requerido("ADMIN","RECEPCAO")
def pagina_aluno(pessoa_id):
    return _render_aluno(pessoa_id)


@app.route("/alunos/<int:pessoa_id>/editar")
@papel_requerido("ADMIN","RECEPCAO")
def pagina_editar_aluno(pessoa_id):
    return _render_aluno(pessoa_id)


@app.route("/api/pessoas/<int:pessoa_id>/cobrancas/pix", methods=["POST"])
@papel_requerido("ADMIN","RECEPCAO")
def api_gerar_cobranca_pix(pessoa_id):
    pessoa=database.obter_pessoa(pessoa_id)
    if not pessoa: return jsonify({"sucesso":False,"erro":"Aluno não encontrado."}),404
    plano=database.obter_plano(pessoa.get("plano_id")) if pessoa.get("plano_id") else None
    if not plano: return jsonify({"sucesso":False,"erro":"Aluno sem plano válido."}),400
    if not pessoa.get("cpf"): return jsonify({"sucesso":False,"erro":"Cadastre o CPF do aluno antes de gerar a cobrança."}),400
    if not pessoa.get("data_vencimento"): return jsonify({"sucesso":False,"erro":"Aluno sem data de vencimento."}),400
    aberta = database.obter_cobranca_aberta(pessoa_id, pessoa.get("data_vencimento"))
    if aberta:
        return jsonify({"sucesso":False,"erro":"Já existe uma cobrança aberta para este vencimento.","payment_id":aberta.get("gateway_payment_id")}),409
    gateway=AsaasGateway()
    try:
        customer_id=database.obter_gateway_cliente(pessoa_id)
        if not customer_id:
            existente=gateway.localizar_cliente(pessoa_id)
            cliente=existente or gateway.criar_cliente(pessoa)
            customer_id=cliente["id"]; database.salvar_gateway_cliente(pessoa_id,customer_id)
        referencia=f"PANO-{pessoa_id}-{int(time.time())}"
        pg=gateway.criar_cobranca_pix(customer_id,int(plano["valor_centavos"]),pessoa["data_vencimento"],referencia)
        pix=gateway.obter_pix(pg["id"])
        database.criar_cobranca_local(pessoa_id,plano["id"],pg["id"],customer_id,int(plano["valor_centavos"]),pessoa["data_vencimento"],pix.get("payload"),pix.get("encodedImage"))
        database.registrar_log_admin("COBRANCA_PIX_CRIADA",str(pessoa_id),pg["id"],_ip_cliente())
        return jsonify({"sucesso":True,"payment_id":pg["id"],"valor_centavos":plano["valor_centavos"],"vencimento":pessoa["data_vencimento"],"payload":pix.get("payload"),"encodedImage":pix.get("encodedImage")})
    except GatewayError as exc: return jsonify({"sucesso":False,"erro":str(exc)}),502
    except Exception as exc: return jsonify({"sucesso":False,"erro":f"Não foi possível gerar a cobrança: {exc}"}),500

@app.route("/webhooks/asaas", methods=["POST"])
def webhook_asaas():
    token_esperado = os.getenv("ASAAS_WEBHOOK_TOKEN", "").strip()
    token_recebido = request.headers.get("asaas-access-token", "")
    if not token_esperado or not hmac.compare_digest(token_esperado, token_recebido):
        return jsonify({"ok": False}), 401

    dados = request.get_json(silent=True) or {}
    event_id = str(dados.get("id") or "")
    evento = str(dados.get("event") or "")
    payment = dados.get("payment") or {}
    payment_id = payment.get("id")
    data_evento = payment.get("paymentDate") or payment.get("confirmedDate") or payment.get("dueDate")
    if not event_id:
        return jsonify({"ok": False, "erro": "Evento sem id"}), 400
    if not database.registrar_evento_webhook(event_id, evento, payment_id):
        return jsonify({"ok": True, "duplicado": True})

    try:
        cobranca = None
        if payment_id and evento in {"PAYMENT_RECEIVED", "PAYMENT_CONFIRMED"}:
            cobranca = database.confirmar_cobranca(payment_id, data_evento, event_id, evento)
            face_index.invalidate()
            acao = "PAGAMENTO_CONFIRMADO"
        elif payment_id and evento == "PAYMENT_OVERDUE":
            cobranca = database.marcar_cobranca_vencida(payment_id, event_id, data_evento)
            face_index.invalidate()
            acao = "COBRANCA_VENCIDA"
        elif payment_id and evento in {"PAYMENT_REFUNDED", "PAYMENT_PARTIALLY_REFUNDED"}:
            cobranca = database.estornar_cobranca(payment_id, event_id, data_evento)
            face_index.invalidate()
            acao = "PAGAMENTO_ESTORNADO"
        elif payment_id and evento == "PAYMENT_DELETED":
            cobranca = database.cancelar_cobranca(payment_id, event_id, data_evento)
            face_index.invalidate()
            acao = "COBRANCA_CANCELADA"
        else:
            cobranca = database.registrar_evento_cobranca_sem_acao(payment_id, event_id, evento, data_evento)
            acao = "WEBHOOK_ASAAS"

        if cobranca:
            database.registrar_log_admin(acao, str(cobranca["pessoa_id"]), f"{evento}:{payment_id}", _ip_cliente())
        database.concluir_evento_webhook(event_id)
        return jsonify({"ok": True})
    except Exception as exc:
        database.falhar_evento_webhook(event_id, exc)
        app.logger.exception("Falha ao processar webhook Asaas %s", event_id)
        return jsonify({"ok": False, "erro": "Falha interna ao processar evento."}), 500


@app.route("/historico")
@papel_requerido("ADMIN","RECEPCAO")
def pagina_historico():
    filtros = filtros_historico_seguros(request.args)
    logs = database.listar_logs(500, filtros)
    return render_template("historico.html", logs=logs, filtros=filtros, catracas=database.listar_catracas(True))


@app.route("/planos")
@papel_requerido("ADMIN")
def pagina_planos():
    return render_template("planos.html", planos=database.listar_planos())


@app.route("/configuracoes")
@papel_requerido("ADMIN")
def pagina_configuracoes():
    return render_template("configuracoes.html", configuracoes=database.obter_configuracoes(), catracas=database.listar_catracas())


# ---------- APIs da catraca ----------

@app.route("/api/config/catraca")
def api_config_catraca():
    return jsonify({"sucesso": True, "config": dados_config_catraca()})


@app.route("/api/presenca", methods=["POST"])
def api_presenca():
    """Deteccao leve de rosto usada apenas para rearmar a proxima leitura.

    Nao identifica aluno, nao registra log e nao aciona dispositivo.
    """
    dados = request.get_json(silent=True) or {}
    imagem_base64 = dados.get("imagem")
    if not imagem_base64:
        return jsonify({"sucesso": False, "erro": "Nenhuma imagem recebida."}), 400
    try:
        rgb, _ = decodificar_imagem(imagem_base64)
        pequeno = cv2.resize(rgb, (0, 0), fx=0.25, fy=0.25)
        localizacoes = face_recognition.face_locations(pequeno, model="hog")
        return jsonify({"sucesso": True, "presenca": bool(localizacoes), "rostos": len(localizacoes)})
    except Exception:
        return jsonify({"sucesso": False, "erro": "Nao foi possivel verificar presenca."}), 400


@app.route("/api/verificar", methods=["POST"])
def api_verificar():
    dados = request.get_json(silent=True) or {}
    imagem_base64 = dados.get("imagem")
    if not imagem_base64:
        return jsonify({"sucesso": False, "erro": "Nenhuma imagem recebida."}), 400
    try:
        rgb, _ = decodificar_imagem(imagem_base64)
    except Exception:
        return jsonify({"sucesso": False, "erro": "Nao foi possivel ler a imagem."}), 400

    pequeno = cv2.resize(rgb, (0, 0), fx=0.35, fy=0.35)
    localizacoes = face_recognition.face_locations(pequeno, model="hog")
    try:
        catraca_id = parse_int(dados.get("catraca_id") or cfg_int("catraca_padrao_id", 1), "Catraca", minimo=1)
    except ValueError as exc:
        return jsonify({"sucesso": False, "erro": str(exc)}), 400
    catraca = database.obter_catraca(catraca_id) or obter_catraca_atual()
    catraca_id = catraca["id"] if catraca else None
    catraca_nome = catraca["nome"] if catraca else "Catraca não configurada"

    if len(localizacoes) == 0:
        estado = liveness_estado.get(_chave_cliente(catraca_id))
        if estado and time.monotonic() - estado["quando"] > cfg_int("liveness_janela_segundos", DEFAULT_LIVENESS_JANELA):
            resetar_liveness(catraca_id)
        return jsonify({"sucesso": True, "status": "SEM_ROSTO", "pessoa": None})

    if len(localizacoes) > 1:
        resetar_liveness(catraca_id)
        database.registrar_log(None, "Multiplos rostos", "NEGADO", "Deixe apenas uma pessoa no quadro", janela_segundos=cfg_int("intervalo_log", DEFAULT_INTERVALO_LOG), catraca_id=catraca_id, catraca_nome=catraca_nome)
        return jsonify({"sucesso": True, "status": "NEGADO", "pessoa": None, "motivo": "Deixe apenas uma pessoa no quadro"})

    if cfg_bool("liveness_ativo", True) and not verificar_liveness(localizacoes[0], catraca_id):
        return jsonify({"sucesso": True, "status": "PROVA_VIDA", "pessoa": None, "motivo": "Mova levemente a cabeça para continuar"})

    encodings_detectados = face_recognition.face_encodings(pequeno, localizacoes, num_jitters=1)
    if not encodings_detectados:
        return jsonify({"sucesso": True, "status": "AGUARDANDO", "pessoa": None})

    encoding_detectado = encodings_detectados[0]
    pessoas, amostras = face_index.snapshot()
    pessoa, distancia = encontrar_melhor_pessoa(encoding_detectado, pessoas, amostras)
    limiar = cfg_float("limiar_reconhecimento", DEFAULT_LIMIAR)

    if pessoa is None or distancia is None or distancia > limiar:
        motivo = "Pessoa nao reconhecida"
        database.registrar_log(None, "Desconhecido", "NEGADO", motivo, janela_segundos=cfg_int("intervalo_log", DEFAULT_INTERVALO_LOG), catraca_id=catraca_id, catraca_nome=catraca_nome)
        resetar_liveness(catraca_id)
        return jsonify({"sucesso": True, "status": "NEGADO", "pessoa": None, "motivo": motivo})

    permitido, motivo = database.acesso_permitido(pessoa)
    status = "LIBERADO" if permitido else "BLOQUEADO"
    acionamento = None
    if permitido:
        try:
            acionamento = device_manager.acionar(catraca)
        except device_manager.DeviceError as exc:
            acionamento = {"sucesso": False, "erro": str(exc), "modo": catraca.get("modo") if catraca else None}
            status = "ERRO"
            motivo = "Acesso autorizado, mas a catraca nao respondeu"

    registrado = database.registrar_log(
        pessoa["id"], pessoa["nome"], status, motivo,
        cpf=pessoa.get("cpf"), matricula=pessoa.get("matricula"),
        janela_segundos=cfg_int("intervalo_log", DEFAULT_INTERVALO_LOG),
        catraca_id=catraca_id, catraca_nome=catraca_nome,
    )

    dados_pessoa = resposta_pessoa(pessoa, status, motivo)
    dados_pessoa["registrado"] = registrado
    dados_pessoa["distancia"] = round(float(distancia), 4)
    resetar_liveness(catraca_id)
    return jsonify({"sucesso": True, "status": status, "pessoa": dados_pessoa, "motivo": motivo, "acionamento": acionamento})


@app.route("/api/catracas/<int:catraca_id>/testar", methods=["POST"])
@papel_requerido("ADMIN")
def api_testar_catraca(catraca_id):
    """Teste administrativo; nunca e chamado pelo navegador da catraca."""
    catraca = database.obter_catraca(catraca_id)
    try:
        return jsonify(device_manager.acionar(catraca))
    except device_manager.DeviceError as exc:
        return jsonify({"sucesso": False, "erro": str(exc)}), 400


@app.route("/api/busca-global")
@papel_requerido("ADMIN","RECEPCAO")
def api_busca_global():
    termo=(request.args.get("q") or "").strip()
    return jsonify({"sucesso":True,"resultados":database.buscar_alunos_global(termo,8)})


# ---------- APIs administrativas ----------

@app.route("/api/cadastrar", methods=["POST"])
@papel_requerido("ADMIN","RECEPCAO")
def api_cadastrar():
    dados = request.get_json(silent=True) or {}
    imagens = dados.get("imagens") or []
    if not imagens and dados.get("imagem"):
        imagens = [dados["imagem"]]
    if not imagens:
        return jsonify({"sucesso": False, "erro": "Nenhuma captura recebida."}), 400
    quantidade = max(3, min(5, cfg_int("quantidade_amostras", 5)))
    if not 3 <= len(imagens) <= quantidade:
        return jsonify({"sucesso": False, "erro": f"O cadastro deve receber entre 3 e {quantidade} capturas faciais."}), 400
    try:
        cadastro = normalizar_dados_cadastro(dados)
        if database.cpf_existe(cadastro["cpf"]):
            return jsonify({"sucesso": False, "erro": "Esse CPF ja esta cadastrado."}), 409
        encodings, primeiro_binario = [], None
        for indice, imagem_base64 in enumerate(imagens, 1):
            rgb, binario = decodificar_imagem(imagem_base64)
            localizacoes = face_recognition.face_locations(rgb, model="hog")
            if len(localizacoes) == 0:
                raise ValueError(f"Captura {indice}: nenhum rosto detectado.")
            if len(localizacoes) > 1:
                raise ValueError(f"Captura {indice}: apareceu mais de um rosto.")
            encodings.append(face_recognition.face_encodings(rgb, localizacoes)[0])
            primeiro_binario = primeiro_binario or binario
        foto_path = salvar_foto(primeiro_binario)
        try:
            pessoa_id = database.adicionar_pessoa(cadastro, encodings, foto_path)
            face_index.invalidate()
        except Exception:
            limpar_foto(foto_path)
            raise
        return jsonify({"sucesso": True, "mensagem": f"{cadastro['nome']} cadastrado com sucesso.", "pessoa_id": pessoa_id, "matricula": cadastro["matricula"], "amostras": len(encodings), "redirect_url": url_for("pagina_gerenciar"), "redirect_ms": max(0, min(30000, cfg_int("cadastro_redirect_ms", 3000)))})
    except ValueError as exc:
        return jsonify({"sucesso": False, "erro": str(exc)}), 400
    except Exception as exc:
        if "UNIQUE constraint failed" in str(exc):
            return jsonify({"sucesso": False, "erro": "CPF ou matricula ja cadastrado."}), 409
        return jsonify({"sucesso": False, "erro": "Nao foi possivel concluir o cadastro."}), 500


@app.route("/api/pessoas/<int:pessoa_id>", methods=["GET", "PUT"])
@papel_requerido("ADMIN","RECEPCAO")
def api_pessoa(pessoa_id):
    pessoa = database.obter_pessoa(pessoa_id)
    if not pessoa:
        return jsonify({"sucesso": False, "erro": "Pessoa nao encontrada."}), 404
    if request.method == "GET":
        dados = resposta_pessoa(pessoa, "LIBERADO" if pessoa["liberado"] else "BLOQUEADO", "")
        dados.update({k: pessoa.get(k) for k in ("data_nascimento", "sexo", "telefone", "email", "data_inicio", "observacoes", "liberado", "status_financeiro", "plano_id")})
        return jsonify({"sucesso": True, "pessoa": dados})

    dados = request.get_json(silent=True) or {}
    try:
        nova = normalizar_dados_cadastro(dados, edicao=True, pessoa=pessoa)
        if database.cpf_existe(nova["cpf"], ignorar_id=pessoa_id):
            raise ValueError("Esse CPF ja esta cadastrado.")
        database.atualizar_pessoa(pessoa_id, nova)
        face_index.invalidate()
        return jsonify({"sucesso": True, "mensagem": "Cadastro atualizado."})
    except ValueError as exc:
        return jsonify({"sucesso": False, "erro": str(exc)}), 400
    except Exception:
        return jsonify({"sucesso": False, "erro": "Nao foi possivel atualizar o cadastro."}), 500


@app.route("/api/pessoas/<int:pessoa_id>/renovar", methods=["POST"])
@papel_requerido("ADMIN","RECEPCAO")
def api_renovar(pessoa_id):
    dados = request.get_json(silent=True) or {}
    try:
        novo_vencimento = database.renovar_plano(pessoa_id, int(dados["plano_id"]) if dados.get("plano_id") else None)
        face_index.invalidate()
        return jsonify({"sucesso": True, "mensagem": "Plano renovado com sucesso.", "data_vencimento": novo_vencimento})
    except (ValueError, TypeError) as exc:
        return jsonify({"sucesso": False, "erro": str(exc)}), 400


@app.route("/api/pessoas/<int:pessoa_id>/biometria", methods=["POST"])
@papel_requerido("ADMIN","RECEPCAO")
def api_biometria(pessoa_id):
    pessoa = database.obter_pessoa(pessoa_id)
    if not pessoa:
        return jsonify({"sucesso": False, "erro": "Aluno nao encontrado."}), 404
    imagens = (request.get_json(silent=True) or {}).get("imagens") or []
    quantidade = max(3, min(5, cfg_int("quantidade_amostras", 5)))
    if not 3 <= len(imagens) <= quantidade:
        return jsonify({"sucesso": False, "erro": f"Envie entre 3 e {quantidade} capturas."}), 400
    encodings, primeiro_binario = [], None
    try:
        for indice, imagem_base64 in enumerate(imagens, 1):
            rgb, binario = decodificar_imagem(imagem_base64)
            localizacoes = face_recognition.face_locations(rgb, model="hog")
            if len(localizacoes) != 1:
                raise ValueError(f"Captura {indice}: mantenha somente um rosto no quadro.")
            encodings.append(face_recognition.face_encodings(rgb, localizacoes)[0])
            primeiro_binario = primeiro_binario or binario
        foto_nova = salvar_foto(primeiro_binario)
        foto_antiga = pessoa.get("foto_path")
        try:
            database.atualizar_amostras_e_foto(pessoa_id, encodings, foto_nova)
            face_index.invalidate()
        except Exception:
            limpar_foto(foto_nova)
            raise
        limpar_foto(foto_antiga)
        return jsonify({"sucesso": True, "mensagem": "Biometria atualizada.", "amostras": len(encodings)})
    except ValueError as exc:
        return jsonify({"sucesso": False, "erro": str(exc)}), 400


@app.route("/api/pessoas/<int:pessoa_id>/status-financeiro", methods=["POST"])
@papel_requerido("ADMIN","RECEPCAO")
def api_status_financeiro(pessoa_id):
    status = (request.get_json(silent=True) or {}).get("status_financeiro", "").upper()
    if status not in {"EM_DIA", "PENDENTE", "VENCIDO"}:
        return jsonify({"sucesso": False, "erro": "Status financeiro invalido."}), 400
    if not database.obter_pessoa(pessoa_id):
        return jsonify({"sucesso": False, "erro": "Aluno nao encontrado."}), 404
    database.atualizar_status_plano(pessoa_id, status)
    face_index.invalidate()
    return jsonify({"sucesso": True})


@app.route("/api/pessoas/<int:pessoa_id>/liberar", methods=["POST"])
@papel_requerido("ADMIN","RECEPCAO")
def api_liberar(pessoa_id):
    ok = database.atualizar_liberacao(pessoa_id, True)
    if ok:
        face_index.invalidate()
    return jsonify({"sucesso": ok, "erro": None if ok else "Pessoa nao encontrada."}), 200 if ok else 404


@app.route("/api/pessoas/<int:pessoa_id>/bloquear", methods=["POST"])
@papel_requerido("ADMIN","RECEPCAO")
def api_bloquear(pessoa_id):
    ok = database.atualizar_liberacao(pessoa_id, False)
    if ok:
        face_index.invalidate()
    return jsonify({"sucesso": ok, "erro": None if ok else "Pessoa nao encontrada."}), 200 if ok else 404


@app.route("/api/pessoas/<int:pessoa_id>/remover", methods=["POST"])
@papel_requerido("ADMIN","RECEPCAO")
def api_remover(pessoa_id):
    pessoa = database.obter_pessoa(pessoa_id)
    if not pessoa:
        return jsonify({"sucesso": False, "erro": "Pessoa nao encontrada."}), 404
    ok = database.remover_pessoa(pessoa_id)
    if ok:
        limpar_foto(pessoa.get("foto_path"))
        face_index.invalidate()
    return jsonify({"sucesso": ok})


@app.route("/api/historico")
def api_historico():
    if session.get("usuario_papel") in {"ADMIN", "RECEPCAO"}:
        logs = database.listar_logs(100)
    else:
        logs = database.listar_logs_publicos(8)
    return jsonify({"sucesso": True, "logs": logs})


# ---------- Planos ----------

@app.route("/api/planos", methods=["POST"])
@papel_requerido("ADMIN")
def api_criar_plano():
    dados = request.get_json(silent=True) or {}
    try:
        nome = (dados.get("nome") or "").strip()
        valor = int(round(float(str(dados.get("valor", 0)).replace(",", ".")) * 100))
        duracao = int(dados.get("duracao_dias"))
        if not nome or valor < 0 or duracao < 1:
            raise ValueError("Informe nome, valor e duracao validos.")
        pid = database.salvar_plano({"nome": nome, "valor_centavos": valor, "duracao_dias": duracao, "descricao": (dados.get("descricao") or "").strip(), "ativo": True})
        return jsonify({"sucesso": True, "id": pid})
    except (ValueError, TypeError) as exc:
        return jsonify({"sucesso": False, "erro": str(exc)}), 400
    except Exception:
        return jsonify({"sucesso": False, "erro": "Nao foi possivel salvar o plano."}), 409


@app.route("/api/planos/<int:plano_id>", methods=["PUT"])
@papel_requerido("ADMIN")
def api_editar_plano(plano_id):
    dados = request.get_json(silent=True) or {}
    try:
        nome = (dados.get("nome") or "").strip()
        valor = int(round(float(str(dados.get("valor", 0)).replace(",", ".")) * 100))
        duracao = int(dados.get("duracao_dias"))
        if not nome or valor < 0 or duracao < 1:
            raise ValueError("Informe nome, valor e duracao validos.")
        database.salvar_plano({"nome": nome, "valor_centavos": valor, "duracao_dias": duracao, "descricao": (dados.get("descricao") or "").strip(), "ativo": parse_bool(dados.get("ativo"), True)}, plano_id)
        return jsonify({"sucesso": True})
    except (ValueError, TypeError) as exc:
        return jsonify({"sucesso": False, "erro": str(exc)}), 400
    except Exception:
        return jsonify({"sucesso": False, "erro": "Nao foi possivel atualizar o plano."}), 409


# ---------- Configuracoes ----------

@app.route("/api/configuracoes", methods=["GET", "PUT"])
@papel_requerido("ADMIN")
def api_configuracoes():
    if request.method == "GET":
        return jsonify({"sucesso": True, "configuracoes": database.obter_configuracoes(), "catracas": database.listar_catracas()})
    dados = request.get_json(silent=True) or {}
    try:
        limpar = {}
        if "tema_padrao" in dados:
            tema = str(dados["tema_padrao"]).strip().lower()
            if tema not in {"light", "system", "dark"}:
                raise ValueError("Tema invalido.")
            limpar["tema_padrao"] = tema
        if "tempo_resultado_ms" in dados:
            limpar["tempo_resultado_ms"] = parse_int(dados["tempo_resultado_ms"], "Tempo da mensagem", 1500, 10000)
        if "intervalo_reconhecimento_ms" in dados:
            limpar["intervalo_reconhecimento_ms"] = parse_int(dados["intervalo_reconhecimento_ms"], "Intervalo de reconhecimento", 500, 5000)
        if "presenca_modo" in dados:
            modo = str(dados["presenca_modo"]).strip().lower()
            if modo not in {"sempre", "inteligente", "sensor"}:
                raise ValueError("Modo de presenca invalido.")
            limpar["presenca_modo"] = modo
        if "standby_sem_presenca_ms" in dados:
            limpar["standby_sem_presenca_ms"] = parse_int(dados["standby_sem_presenca_ms"], "Tempo para standby", 5000, 300000)
        if "atraso_apos_presenca_ms" in dados:
            limpar["atraso_apos_presenca_ms"] = parse_int(dados["atraso_apos_presenca_ms"], "Atraso apos presenca", 0, 5000)
        if "cooldown_proxima_pessoa_ms" in dados:
            limpar["cooldown_proxima_pessoa_ms"] = parse_int(dados["cooldown_proxima_pessoa_ms"], "Intervalo entre pessoas", 0, 60000)
        if "ausencia_rearmar_ms" in dados:
            limpar["ausencia_rearmar_ms"] = parse_int(dados["ausencia_rearmar_ms"], "Tempo sem rosto para rearmar", 0, 30000)
        if "max_espera_saida_ms" in dados:
            limpar["max_espera_saida_ms"] = parse_int(dados["max_espera_saida_ms"], "Espera maxima pela saida", 0, 120000)
        if "sensibilidade_presenca" in dados:
            sens = str(dados["sensibilidade_presenca"]).strip().lower()
            if sens not in {"baixa", "media", "alta"}:
                raise ValueError("Sensibilidade de presenca invalida.")
            limpar["sensibilidade_presenca"] = sens
        if "cadastro_redirect_ms" in dados:
            limpar["cadastro_redirect_ms"] = parse_int(dados["cadastro_redirect_ms"], "Tempo apos cadastro", 0, 30000)
        if "cadastro_preparacao_captura_ms" in dados:
            limpar["cadastro_preparacao_captura_ms"] = parse_int(dados["cadastro_preparacao_captura_ms"], "Preparacao da captura", 0, 5000)
        if "cadastro_intervalo_captura_ms" in dados:
            limpar["cadastro_intervalo_captura_ms"] = parse_int(dados["cadastro_intervalo_captura_ms"], "Intervalo entre capturas", 0, 5000)
        if "erro_recuperacao_ms" in dados:
            limpar["erro_recuperacao_ms"] = parse_int(dados["erro_recuperacao_ms"], "Recuperacao apos erro", 500, 30000)
        if "intervalo_detector_presenca_ms" in dados:
            limpar["intervalo_detector_presenca_ms"] = parse_int(dados["intervalo_detector_presenca_ms"], "Intervalo do detector de presenca", 100, 5000)
        if "intervalo_historico_ms" in dados:
            limpar["intervalo_historico_ms"] = parse_int(dados["intervalo_historico_ms"], "Atualizacao do historico", 1000, 60000)
        if "limiar_reconhecimento" in dados:
            limpar["limiar_reconhecimento"] = parse_float(dados["limiar_reconhecimento"], "Limiar facial", 0.3, 0.8)
        if "intervalo_log" in dados:
            limpar["intervalo_log"] = parse_int(dados["intervalo_log"], "Intervalo anti-repeticao", 2, 30)
        if "liveness_janela_segundos" in dados:
            limpar["liveness_janela_segundos"] = parse_int(dados["liveness_janela_segundos"], "Janela de prova de vida", 2, 10)
        if "quantidade_amostras" in dados:
            limpar["quantidade_amostras"] = parse_int(dados["quantidade_amostras"], "Quantidade de amostras", 3, 5)
        if "dias_alerta_vencimento" in dados:
            limpar["dias_alerta_vencimento"] = parse_int(dados["dias_alerta_vencimento"], "Dias para alerta de vencimento", 1, 60)
        if "liveness_ativo" in dados:
            limpar["liveness_ativo"] = "1" if parse_bool(dados["liveness_ativo"]) else "0"
        if "som_ativo" in dados:
            limpar["som_ativo"] = "1" if parse_bool(dados["som_ativo"]) else "0"
        if "catraca_padrao_id" in dados:
            catraca_id = parse_int(dados["catraca_padrao_id"], "Catraca padrao", minimo=1)
            catraca = database.obter_catraca(catraca_id)
            if not catraca or not catraca["ativa"]:
                raise ValueError("Selecione uma catraca ativa.")
            limpar["catraca_padrao_id"] = catraca_id
        database.salvar_configuracoes(limpar)
        config_service.invalidate()
        return jsonify({"sucesso": True, "mensagem": "Configuracoes salvas.", "configuracoes": database.obter_configuracoes()})
    except (ValueError, TypeError) as exc:
        return jsonify({"sucesso": False, "erro": str(exc)}), 400


@app.route("/api/catracas", methods=["POST"])
@papel_requerido("ADMIN")
def api_criar_catraca():
    dados = request.get_json(silent=True) or {}
    nome = (dados.get("nome") or "").strip()
    local = (dados.get("local") or "").strip() or None
    modo = str(dados.get("modo") or "SIMULADA").strip().upper()
    endpoint = (dados.get("endpoint") or "").strip() or None
    if not nome:
        return jsonify({"sucesso": False, "erro": "Informe o nome da catraca."}), 400
    if len(nome) > 80 or (local and len(local) > 120):
        return jsonify({"sucesso": False, "erro": "Nome ou local excede o limite permitido."}), 400
    if modo not in {"SIMULADA", "HTTP", "SERIAL"}:
        return jsonify({"sucesso": False, "erro": "Modo de catraca invalido."}), 400
    if modo == "HTTP" and endpoint and not endpoint.lower().startswith(("http://", "https://")):
        return jsonify({"sucesso": False, "erro": "Endpoint HTTP invalido."}), 400
    cid = database.salvar_catraca({"nome": nome, "local": local, "modo": modo, "endpoint": endpoint, "ativa": True})
    return jsonify({"sucesso": True, "id": cid})


# ---------- Exportacoes ----------

def _filtros_historico_request():
    return filtros_historico_seguros(request.args)



@app.route("/health")
def health():
    try:
        integridade = database.verificar_integridade()
        return jsonify({
            "status": "ok" if integridade["ok"] else "degradado",
            "database": "ok" if integridade["ok"] else "erro",
            "schema_version": integridade["schema_version"],
        }), 200 if integridade["ok"] else 503
    except Exception:
        return jsonify({"status": "erro", "database": "indisponivel"}), 503


@app.route("/diagnostico")
@papel_requerido("ADMIN")
def pagina_diagnostico():
    integridade = database.verificar_integridade()
    return render_template(
        "diagnostico.html",
        integridade=integridade,
        logs_admin=database.listar_logs_admin(50),
        credencial_padrao=CREDENCIAL_PADRAO,
        catracas=database.listar_catracas(),
        versao="5.2",
    )


@app.route("/backup")
@papel_requerido("ADMIN")
def baixar_backup():
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    destino = Path(tempfile.gettempdir()) / f"panobianco-backup-{stamp}.db"
    database.criar_backup(destino)
    database.registrar_log_admin("BACKUP", destino.name, "Backup manual criado.", _ip_cliente())
    return send_file(destino, as_attachment=True, download_name=destino.name, mimetype="application/octet-stream")


@app.route("/restaurar-backup", methods=["POST"])
@papel_requerido("ADMIN")
def restaurar_backup():
    arquivo = request.files.get("backup")
    if not arquivo or not arquivo.filename:
        return jsonify({"sucesso": False, "erro": "Selecione um arquivo .db."}), 400
    if not arquivo.filename.lower().endswith(".db"):
        return jsonify({"sucesso": False, "erro": "O backup deve ser um arquivo .db."}), 400

    temp = Path(tempfile.gettempdir()) / f"restore-{uuid.uuid4().hex}.db"
    try:
        arquivo.save(temp)
        # Cria um snapshot automático antes de qualquer restauração.
        pre = Path(tempfile.gettempdir()) / f"pre-restore-{datetime.now().strftime('%Y%m%d-%H%M%S')}.db"
        database.criar_backup(pre)
        database.restaurar_backup(temp)
        config_service.invalidate()
        face_index.invalidate()
        database.registrar_log_admin("RESTAURACAO", arquivo.filename, f"Backup restaurado. Snapshot anterior: {pre.name}", _ip_cliente())
        return jsonify({"sucesso": True, "mensagem": "Backup restaurado com sucesso. Recarregue o sistema."})
    except Exception as exc:
        return jsonify({"sucesso": False, "erro": str(exc)}), 400
    finally:
        try:
            temp.unlink(missing_ok=True)
        except Exception:
            pass


@app.route("/api/integridade")
@papel_requerido("ADMIN")
def api_integridade():
    return jsonify({"sucesso": True, "integridade": database.verificar_integridade()})


@app.route("/historico.csv")
@papel_requerido("ADMIN","RECEPCAO")
def exportar_historico_csv():
    logs = database.listar_logs(10000, _filtros_historico_request())
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["Data/hora", "Aluno", "CPF", "Matricula", "Resultado", "Motivo", "Catraca"])
    for log in logs:
        writer.writerow([log.get("data_hora"), log.get("nome"), log.get("cpf"), log.get("matricula"), log.get("status"), log.get("motivo"), log.get("catraca_nome")])
    return Response("\ufeff" + output.getvalue(), mimetype="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=historico-acessos.csv"})


@app.route("/historico.pdf")
@papel_requerido("ADMIN","RECEPCAO")
def exportar_historico_pdf():
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

    logs = database.listar_logs(10000, _filtros_historico_request())
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), rightMargin=10 * mm, leftMargin=10 * mm, topMargin=10 * mm, bottomMargin=10 * mm)
    styles = getSampleStyleSheet()
    elementos = [Paragraph("PANOBIANCO - RELATORIO DE ACESSOS", styles["Title"]), Spacer(1, 5 * mm)]
    dados = [["Data/hora", "Aluno", "CPF", "Matricula", "Resultado", "Motivo", "Catraca"]]
    for log in logs:
        dados.append([str(log.get("data_hora") or ""), str(log.get("nome") or "-"), str(log.get("cpf") or "-"), str(log.get("matricula") or "-"), str(log.get("status") or "-"), str(log.get("motivo") or "-"), str(log.get("catraca_nome") or "-")])
    tabela = Table(dados, repeatRows=1, colWidths=[34 * mm, 45 * mm, 33 * mm, 25 * mm, 25 * mm, 68 * mm, 38 * mm])
    tabela.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#101010")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), .25, colors.HexColor("#dddddd")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f3ef")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    elementos.append(tabela)
    doc.build(elementos)
    pdf = buf.getvalue()
    return Response(pdf, mimetype="application/pdf", headers={"Content-Disposition": "attachment; filename=historico-acessos.pdf"})


if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "0").strip().lower() in {"1", "true", "sim", "on"}
    app.run(debug=debug, port=int(os.getenv("PORT", "5000")))
