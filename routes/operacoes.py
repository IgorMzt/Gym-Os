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

from services import dashboard_service, auth_service, professor_service, exercise_service, workout_service, execution_service, assessment_service, push_service
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

operacoes_bp = Blueprint("operacoes", __name__)

@operacoes_bp.route("/catraca")
def pagina_catraca():
    return render_template("verificacao.html", config_catraca=dados_config_catraca())


@operacoes_bp.route("/verificacao")
def pagina_verificacao():
    return redirect(url_for("operacoes.pagina_catraca"))


@operacoes_bp.route("/cadastro")
@papel_requerido("ADMIN","RECEPCAO")
def pagina_cadastro():
    return render_template("cadastro.html", hoje=date.today().isoformat(), planos=database.listar_planos(True), cadastro_redirect_ms=max(0, min(30000, cfg_int("cadastro_redirect_ms", 3000))), cadastro_preparacao_captura_ms=max(0, min(5000, cfg_int("cadastro_preparacao_captura_ms", 550))), cadastro_intervalo_captura_ms=max(0, min(5000, cfg_int("cadastro_intervalo_captura_ms", 450))))


@operacoes_bp.route("/gerenciar")
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
        return redirect(url_for("operacoes.pagina_gerenciar"))
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


@operacoes_bp.route("/alunos/<int:pessoa_id>")
@papel_requerido("ADMIN","RECEPCAO")
def pagina_aluno(pessoa_id):
    return _render_aluno(pessoa_id)


@operacoes_bp.route("/alunos/<int:pessoa_id>/editar")
@papel_requerido("ADMIN","RECEPCAO")
def pagina_editar_aluno(pessoa_id):
    return _render_aluno(pessoa_id)


@operacoes_bp.route("/api/pessoas/<int:pessoa_id>/cobrancas/pix", methods=["POST"])
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

@operacoes_bp.route("/webhooks/asaas", methods=["POST"])
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
            if evento in {"PAYMENT_RECEIVED", "PAYMENT_CONFIRMED"}:
                push_service.enviar_para_aluno(
                    cobranca["pessoa_id"], "Pagamento confirmado",
                    "Seu pagamento foi confirmado. Obrigado!", {"url": "/financeiro", "tipo": "PAGAMENTO_CONFIRMADO"}
                )
            elif evento == "PAYMENT_OVERDUE":
                push_service.enviar_para_aluno(
                    cobranca["pessoa_id"], "Mensalidade vencida",
                    "Sua mensalidade venceu. Consulte o Financeiro no Gym OS.", {"url": "/financeiro", "tipo": "MENSALIDADE_VENCIDA"}
                )
        database.concluir_evento_webhook(event_id)
        return jsonify({"ok": True})
    except Exception as exc:
        database.falhar_evento_webhook(event_id, exc)
        current_app.logger.exception("Falha ao processar webhook Asaas %s", event_id)
        return jsonify({"ok": False, "erro": "Falha interna ao processar evento."}), 500


@operacoes_bp.route("/historico")
@papel_requerido("ADMIN","RECEPCAO")
def pagina_historico():
    filtros = filtros_historico_seguros(request.args)
    logs = database.listar_logs(500, filtros)
    return render_template("historico.html", logs=logs, filtros=filtros, catracas=database.listar_catracas(True))


@operacoes_bp.route("/planos")
@papel_requerido("ADMIN")
def pagina_planos():
    return render_template("planos.html", planos=database.listar_planos())


@operacoes_bp.route("/configuracoes")
@papel_requerido("ADMIN")
def pagina_configuracoes():
    return render_template("configuracoes.html", configuracoes=database.obter_configuracoes(), catracas=database.listar_catracas())


# ---------- APIs da catraca ----------

@operacoes_bp.route("/api/config/catraca")
def api_config_catraca():
    return jsonify({"sucesso": True, "config": dados_config_catraca()})


@operacoes_bp.route("/api/presenca", methods=["POST"])
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


@operacoes_bp.route("/api/verificar", methods=["POST"])
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


@operacoes_bp.route("/api/catracas/<int:catraca_id>/testar", methods=["POST"])
@papel_requerido("ADMIN")
def api_testar_catraca(catraca_id):
    """Teste administrativo; nunca e chamado pelo navegador da catraca."""
    catraca = database.obter_catraca(catraca_id)
    try:
        return jsonify(device_manager.acionar(catraca))
    except device_manager.DeviceError as exc:
        return jsonify({"sucesso": False, "erro": str(exc)}), 400


@operacoes_bp.route("/api/busca-global")
@papel_requerido("ADMIN","RECEPCAO")
def api_busca_global():
    termo=(request.args.get("q") or "").strip()
    return jsonify({"sucesso":True,"resultados":database.buscar_alunos_global(termo,8)})


# ---------- APIs administrativas ----------

@operacoes_bp.route("/api/cadastrar", methods=["POST"])
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
        return jsonify({"sucesso": True, "mensagem": f"{cadastro['nome']} cadastrado com sucesso.", "pessoa_id": pessoa_id, "matricula": cadastro["matricula"], "amostras": len(encodings), "redirect_url": url_for("operacoes.pagina_gerenciar"), "redirect_ms": max(0, min(30000, cfg_int("cadastro_redirect_ms", 3000)))})
    except ValueError as exc:
        return jsonify({"sucesso": False, "erro": str(exc)}), 400
    except Exception as exc:
        if "UNIQUE constraint failed" in str(exc):
            return jsonify({"sucesso": False, "erro": "CPF ou matricula ja cadastrado."}), 409
        return jsonify({"sucesso": False, "erro": "Nao foi possivel concluir o cadastro."}), 500


@operacoes_bp.route("/api/pessoas/<int:pessoa_id>", methods=["GET", "PUT"])
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


@operacoes_bp.route("/api/pessoas/<int:pessoa_id>/renovar", methods=["POST"])
@papel_requerido("ADMIN","RECEPCAO")
def api_renovar(pessoa_id):
    dados = request.get_json(silent=True) or {}
    try:
        novo_vencimento = database.renovar_plano(pessoa_id, int(dados["plano_id"]) if dados.get("plano_id") else None)
        face_index.invalidate()
        return jsonify({"sucesso": True, "mensagem": "Plano renovado com sucesso.", "data_vencimento": novo_vencimento})
    except (ValueError, TypeError) as exc:
        return jsonify({"sucesso": False, "erro": str(exc)}), 400


@operacoes_bp.route("/api/pessoas/<int:pessoa_id>/biometria", methods=["POST"])
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


@operacoes_bp.route("/api/pessoas/<int:pessoa_id>/status-financeiro", methods=["POST"])
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


@operacoes_bp.route("/api/pessoas/<int:pessoa_id>/liberar", methods=["POST"])
@papel_requerido("ADMIN","RECEPCAO")
def api_liberar(pessoa_id):
    ok = database.atualizar_liberacao(pessoa_id, True)
    if ok:
        face_index.invalidate()
    return jsonify({"sucesso": ok, "erro": None if ok else "Pessoa nao encontrada."}), 200 if ok else 404


@operacoes_bp.route("/api/pessoas/<int:pessoa_id>/bloquear", methods=["POST"])
@papel_requerido("ADMIN","RECEPCAO")
def api_bloquear(pessoa_id):
    ok = database.atualizar_liberacao(pessoa_id, False)
    if ok:
        face_index.invalidate()
    return jsonify({"sucesso": ok, "erro": None if ok else "Pessoa nao encontrada."}), 200 if ok else 404


@operacoes_bp.route("/api/pessoas/<int:pessoa_id>/remover", methods=["POST"])
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


@operacoes_bp.route("/api/historico")
def api_historico():
    if session.get("usuario_papel") in {"ADMIN", "RECEPCAO"}:
        logs = database.listar_logs(100)
    else:
        logs = database.listar_logs_publicos(8)
    return jsonify({"sucesso": True, "logs": logs})


# ---------- Planos ----------

@operacoes_bp.route("/api/planos", methods=["POST"])
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


@operacoes_bp.route("/api/planos/<int:plano_id>", methods=["PUT"])
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

@operacoes_bp.route("/api/configuracoes", methods=["GET", "PUT"])
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


@operacoes_bp.route("/api/catracas", methods=["POST"])
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



@operacoes_bp.route("/health")
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


@operacoes_bp.route("/diagnostico")
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


@operacoes_bp.route("/backup")
@papel_requerido("ADMIN")
def baixar_backup():
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    destino = Path(tempfile.gettempdir()) / f"panobianco-backup-{stamp}.db"
    database.criar_backup(destino)
    database.registrar_log_admin("BACKUP", destino.name, "Backup manual criado.", _ip_cliente())
    return send_file(destino, as_attachment=True, download_name=destino.name, mimetype="application/octet-stream")


@operacoes_bp.route("/restaurar-backup", methods=["POST"])
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


@operacoes_bp.route("/api/integridade")
@papel_requerido("ADMIN")
def api_integridade():
    return jsonify({"sucesso": True, "integridade": database.verificar_integridade()})


@operacoes_bp.route("/historico.csv")
@papel_requerido("ADMIN","RECEPCAO")
def exportar_historico_csv():
    logs = database.listar_logs(10000, _filtros_historico_request())
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["Data/hora", "Aluno", "CPF", "Matricula", "Resultado", "Motivo", "Catraca"])
    for log in logs:
        writer.writerow([log.get("data_hora"), log.get("nome"), log.get("cpf"), log.get("matricula"), log.get("status"), log.get("motivo"), log.get("catraca_nome")])
    return Response("\ufeff" + output.getvalue(), mimetype="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=historico-acessos.csv"})


@operacoes_bp.route("/historico.pdf")
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


