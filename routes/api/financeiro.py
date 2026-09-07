"""Financeiro do aluno para o aplicativo mobile."""

import time
from datetime import date, timedelta

from flask import Blueprint, current_app, g, jsonify

import database
from services.payments import AsaasGateway, GatewayError
from .common import aluno_token_obrigatorio, resposta_erro

api_financeiro_bp = Blueprint("api_financeiro", __name__, url_prefix="/api/v1/aluno/financeiro")


def _cobranca_publica(cobranca):
    if not cobranca:
        return None
    return {
        "id": int(cobranca["id"]),
        "status": cobranca.get("status"),
        "valor_centavos": int(cobranca.get("valor_centavos") or 0),
        "vencimento": cobranca.get("vencimento_original"),
        "data_pagamento": cobranca.get("data_pagamento"),
        "pix_payload": cobranca.get("pix_payload"),
        "pix_qr_base64": cobranca.get("pix_qr_base64"),
        "ultimo_evento": cobranca.get("ultimo_evento"),
        "data_atualizacao": cobranca.get("data_atualizacao"),
    }


def _resumo_financeiro(pessoa):
    plano = database.obter_plano(pessoa.get("plano_id")) if pessoa.get("plano_id") else None
    vencimento = pessoa.get("data_vencimento")
    tolerancia = max(0, int(database.obter_configuracao("tolerancia_financeira_dias", "5") or 5))
    status_efetivo = database.status_financeiro_efetivo(pessoa)
    dias_para_vencimento = None
    limite_tolerancia = None
    dias_tolerancia_restantes = None
    if vencimento:
        try:
            venc = date.fromisoformat(vencimento)
            hoje = date.today()
            dias_para_vencimento = (venc - hoje).days
            limite = venc + timedelta(days=tolerancia)
            limite_tolerancia = limite.isoformat()
            if hoje > venc and hoje <= limite:
                dias_tolerancia_restantes = (limite - hoje).days
        except ValueError:
            pass
    return {
        "status_financeiro": pessoa.get("status_financeiro") or "EM_DIA",
        "status_financeiro_efetivo": status_efetivo,
        "data_vencimento": vencimento,
        "dias_para_vencimento": dias_para_vencimento,
        "tolerancia_dias": tolerancia,
        "limite_tolerancia": limite_tolerancia,
        "dias_tolerancia_restantes": dias_tolerancia_restantes,
        "plano": {
            "id": int(plano["id"]), "nome": plano.get("nome"),
            "valor_centavos": int(plano.get("valor_centavos") or 0),
            "duracao_dias": int(plano.get("duracao_dias") or 0),
        } if plano else None,
    }


@api_financeiro_bp.get("")
@aluno_token_obrigatorio
def status_financeiro():
    pessoa = database.obter_pessoa(g.aluno_id)
    if not pessoa:
        return resposta_erro("Aluno nao encontrado.", 404, "ALUNO_NAO_ENCONTRADO")
    cobrancas = database.listar_cobrancas_pessoa(g.aluno_id, 30)
    aberta = database.obter_cobranca_aberta(g.aluno_id)
    return jsonify({
        "sucesso": True,
        **_resumo_financeiro(pessoa),
        "asaas_configurado": AsaasGateway().configurado,
        "cobranca_aberta": _cobranca_publica(aberta),
        "cobrancas": [_cobranca_publica(c) for c in cobrancas],
    })


@api_financeiro_bp.post("/pix")
@aluno_token_obrigatorio
def gerar_pix():
    pessoa = database.obter_pessoa(g.aluno_id)
    if not pessoa:
        return resposta_erro("Aluno nao encontrado.", 404, "ALUNO_NAO_ENCONTRADO")
    plano = database.obter_plano(pessoa.get("plano_id")) if pessoa.get("plano_id") else None
    if not plano:
        return resposta_erro("Seu cadastro esta sem plano valido. Procure a recepcao.", 400, "PLANO_NAO_ENCONTRADO")
    if not pessoa.get("cpf"):
        return resposta_erro("Seu cadastro esta sem CPF. Procure a recepcao.", 400, "CPF_NAO_INFORMADO")
    if not pessoa.get("data_vencimento"):
        return resposta_erro("Seu cadastro esta sem vencimento. Procure a recepcao.", 400, "VENCIMENTO_NAO_INFORMADO")

    aberta = database.obter_cobranca_aberta(g.aluno_id, pessoa.get("data_vencimento"))
    if aberta:
        return jsonify({"sucesso": True, "existente": True, "cobranca": _cobranca_publica(aberta)})

    gateway = AsaasGateway()
    if not gateway.configurado:
        return resposta_erro("PIX indisponivel no momento. Procure a recepcao.", 503, "ASAAS_NAO_CONFIGURADO")
    try:
        customer_id = database.obter_gateway_cliente(g.aluno_id)
        if not customer_id:
            existente = gateway.localizar_cliente(g.aluno_id)
            cliente = existente or gateway.criar_cliente(pessoa)
            customer_id = cliente["id"]
            database.salvar_gateway_cliente(g.aluno_id, customer_id)
        referencia = f"PANO-MOBILE-{g.aluno_id}-{int(time.time())}"
        pagamento = gateway.criar_cobranca_pix(
            customer_id, int(plano["valor_centavos"]), pessoa["data_vencimento"], referencia
        )
        pix = gateway.obter_pix(pagamento["id"])
        cobranca_id = database.criar_cobranca_local(
            g.aluno_id, plano["id"], pagamento["id"], customer_id,
            int(plano["valor_centavos"]), pessoa["data_vencimento"],
            pix.get("payload"), pix.get("encodedImage"),
        )
        database.registrar_log_admin("COBRANCA_PIX_CRIADA_MOBILE", str(g.aluno_id), pagamento["id"], "API_MOBILE")
        cobranca = next((c for c in database.listar_cobrancas_pessoa(g.aluno_id, 5) if int(c["id"]) == int(cobranca_id)), None)
        return jsonify({"sucesso": True, "existente": False, "cobranca": _cobranca_publica(cobranca)})
    except GatewayError as exc:
        return resposta_erro(str(exc), 502, "ASAAS_ERRO")
    except Exception:
        current_app.logger.exception("Falha ao gerar PIX pela API mobile")
        return resposta_erro("Nao foi possivel gerar o PIX agora. Tente novamente ou procure a recepcao.", 500, "PIX_NAO_GERADO")
