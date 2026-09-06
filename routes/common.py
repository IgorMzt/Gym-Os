"""Helpers compartilhados pelas rotas web do Gym OS."""

import base64
import hmac
import os
import secrets
import tempfile
import time
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

import cv2
import face_recognition
import numpy as np
from flask import request, session, url_for

import config_service
import database
from validators import cpf_apenas_digitos, cpf_valido, data_iso, email_valido, parse_bool, parse_float, parse_int

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_RESULTADO_MS = 2800
DEFAULT_INTERVALO_LOG = 5
DEFAULT_LIMIAR = 0.50
DEFAULT_LIVENESS_JANELA = 4

ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
CREDENCIAL_PADRAO = ADMIN_USER == "admin" and ADMIN_PASSWORD == "admin123"
liveness_estado = {}

def _ip_cliente():
    return request.remote_addr or "desconhecido"

def cfg_int(chave, padrao):
    return config_service.get_int(chave, padrao)

def cfg_float(chave, padrao):
    return config_service.get_float(chave, padrao)

def cfg_bool(chave, padrao=True):
    return config_service.get_bool(chave, padrao)

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



def professor_pode_gerir_aluno(pessoa_id):
    if session.get("usuario_papel") == "ADMIN":
        return True
    professor = database.obter_professor_por_usuario(int(session.get("usuario_id")))
    if not professor:
        return False
    return any(p["id"] == int(pessoa_id) for p in database.listar_alunos_professor(professor["id"]))
