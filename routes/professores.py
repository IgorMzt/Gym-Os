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

professores_bp = Blueprint("professores", __name__)

@professores_bp.route("/minha-area")
@login_obrigatorio
def pagina_minha_area():
    papel = session.get("usuario_papel")
    if papel != "PROFESSOR":
        return redirect(url_for("dashboard.pagina_painel"))
    professor = database.obter_professor_por_usuario(int(session.get("usuario_id")))
    if not professor:
        return render_template("minha_area.html", professor=None, alunos=[], disponiveis=[], fichas_pendentes=0)
    alunos = database.listar_alunos_professor(professor["id"])
    disponiveis = database.listar_alunos_disponiveis()
    return render_template("minha_area.html", professor=professor, alunos=alunos,
                           disponiveis=disponiveis,
                           fichas_pendentes=database.contar_fichas_pendentes_professor(professor["id"]),
                           metricas=database.metricas_professor(professor["id"]))


@professores_bp.route("/professores")
@papel_requerido("ADMIN")
def pagina_professores():
    return render_template(
        "professores.html",
        professores=database.listar_professores(),
        usuarios_professor=database.listar_usuarios_professor(),
    )


@professores_bp.route("/professores/<int:professor_id>")
@papel_requerido("ADMIN")
def pagina_professor(professor_id):
    professor = database.obter_professor(professor_id)
    if not professor:
        return redirect(url_for("professores.pagina_professores"))
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


@professores_bp.route("/api/professores", methods=["POST"])
@papel_requerido("ADMIN")
def api_criar_professor():
    dados = request.get_json(silent=True) or {}
    nova_foto = None
    try:
        normalizado = _normalizar_professor(dados)
        _, nova_foto = _aplicar_foto_professor(dados, normalizado)
        professor_id = database.criar_professor(normalizado)
        database.registrar_log_admin("PROFESSOR_CRIADO", str(professor_id), normalizado["nome"], _ip_cliente())
        return jsonify({"sucesso": True, "id": professor_id, "redirect_url": url_for("professores.pagina_professor", professor_id=professor_id)})
    except ValueError as exc:
        if nova_foto: limpar_foto(nova_foto)
        return jsonify({"sucesso": False, "erro": str(exc)}), 400
    except Exception as exc:
        if nova_foto: limpar_foto(nova_foto)
        if "UNIQUE constraint failed" in str(exc):
            return jsonify({"sucesso": False, "erro": "CPF, CREF ou conta de usuário já vinculados a outro professor."}), 409
        return jsonify({"sucesso": False, "erro": "Não foi possível cadastrar o professor."}), 500


@professores_bp.route("/api/professores/<int:professor_id>", methods=["PUT"])
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


@professores_bp.route("/api/professores/<int:professor_id>/alunos/<int:pessoa_id>", methods=["POST", "DELETE"])
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


@professores_bp.route("/minha-area/alunos/<int:pessoa_id>")
@papel_requerido("PROFESSOR")
def pagina_aluno_professor(pessoa_id):
    usuario_id = int(session.get("usuario_id"))
    if not professor_service.pode_acessar_aluno(usuario_id, pessoa_id):
        return redirect(url_for("professores.pagina_minha_area"))
    pessoa = database.obter_pessoa(pessoa_id)
    if not pessoa:
        return redirect(url_for("professores.pagina_minha_area"))
    avaliacoes = database.listar_avaliacoes_fisicas(pessoa_id)
    return render_template(
        "aluno_professor.html",
        pessoa=pessoa,
        historico=database.listar_logs_pessoa(pessoa_id, 20),
        professores=database.listar_professores_aluno(pessoa_id),
        avaliacoes=avaliacoes,
        comparacao_avaliacao=assessment_service.comparacao(avaliacoes),
    )


@professores_bp.route("/api/professor/alunos/<int:pessoa_id>/assumir", methods=["POST"])
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

@professores_bp.route("/api/professor/alunos/<int:pessoa_id>/liberar", methods=["POST"])
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


@professores_bp.route("/api/pessoas/<int:pessoa_id>/acesso-app", methods=["POST"])
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
    except database.IntegrityError:
        return jsonify({"sucesso":False,"erro":"Este login já está em uso."}),409


