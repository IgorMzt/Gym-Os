"""Registro e teste de push notifications do aplicativo mobile."""
from flask import Blueprint, g, jsonify, request
import database
from services import push_service
from .common import aluno_token_obrigatorio, resposta_erro

api_notificacoes_bp = Blueprint("api_notificacoes", __name__, url_prefix="/api/v1/aluno/notificacoes")

@api_notificacoes_bp.post("/device")
@aluno_token_obrigatorio
def registrar_device():
    dados = request.get_json(silent=True) or {}
    token = str(dados.get("expo_push_token") or "").strip()
    if not (token.startswith("ExponentPushToken[") or token.startswith("ExpoPushToken[")):
        return resposta_erro("Expo Push Token invalido.", 400, "PUSH_TOKEN_INVALIDO")
    device = database.registrar_push_device(
        g.aluno_id, token, dados.get("plataforma"), dados.get("device_name"), dados.get("app_version")
    )
    return jsonify({"sucesso": True, "device_id": int(device["id"])})

@api_notificacoes_bp.delete("/device")
@aluno_token_obrigatorio
def remover_device():
    dados = request.get_json(silent=True) or {}
    token = str(dados.get("expo_push_token") or "").strip()
    database.desativar_push_device(g.aluno_id, token)
    return jsonify({"sucesso": True})

@api_notificacoes_bp.post("/teste")
@aluno_token_obrigatorio
def teste_push():
    resultado = push_service.enviar_para_aluno(
        g.aluno_id, "Gym OS", "Notificacoes ativadas com sucesso!", {"url": "/home", "tipo": "TESTE"}
    )
    if resultado.get("erro"):
        return resposta_erro("Falha ao contatar o servico de push.", 502, "PUSH_INDISPONIVEL")
    if not resultado.get("enviadas"):
        return resposta_erro("Nenhum dispositivo ativo registrado.", 409, "SEM_DISPOSITIVO_PUSH")
    return jsonify({"sucesso": True, **resultado})
