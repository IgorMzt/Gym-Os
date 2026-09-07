"""Home inteligente, preferencias e experiencia do aluno mobile."""

import re
from flask import Blueprint, g, jsonify, request

import database
from services import mobile_experience_service
from .common import aluno_token_obrigatorio, resposta_erro

api_experiencia_bp = Blueprint("api_experiencia", __name__, url_prefix="/api/v1/aluno")


@api_experiencia_bp.get("/experiencia")
@aluno_token_obrigatorio
def experiencia():
    return jsonify({"sucesso": True, **mobile_experience_service.resumo_aluno(g.aluno_id)})


@api_experiencia_bp.get("/preferencias")
@aluno_token_obrigatorio
def preferencias():
    return jsonify({"sucesso": True, "preferencias": database.obter_preferencias_mobile(g.aluno_id)})


@api_experiencia_bp.put("/preferencias")
@aluno_token_obrigatorio
def salvar_preferencias():
    dados = request.get_json(silent=True) or {}
    try:
        meta = int(dados.get("meta_semanal", 4))
    except (TypeError, ValueError):
        return resposta_erro("Meta semanal invalida.", 400, "META_INVALIDA")
    if not 1 <= meta <= 14:
        return resposta_erro("A meta semanal deve ficar entre 1 e 14 treinos.", 400, "META_INVALIDA")
    hora = str(dados.get("lembrete_treino_hora") or "19:00").strip()
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", hora):
        return resposta_erro("Horario de lembrete invalido.", 400, "HORARIO_INVALIDO")
    ativo = dados.get("lembrete_treino_ativo", False)
    if not isinstance(ativo, bool):
        ativo = str(ativo).lower() in {"1", "true", "sim", "on", "yes"}
    prefs = database.salvar_preferencias_mobile(g.aluno_id, meta, ativo, hora)
    return jsonify({"sucesso": True, "preferencias": prefs})
