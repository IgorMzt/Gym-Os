"""Historico de treinos do aluno para o aplicativo mobile."""

from flask import Blueprint, g, jsonify

import database
from .common import aluno_token_obrigatorio, resposta_erro

api_historico_bp = Blueprint("api_historico", __name__, url_prefix="/api/v1/aluno")


def _sessao_do_aluno(sessao_id: int):
    sessao = database.obter_sessao_treino(sessao_id)
    if not sessao or int(sessao["pessoa_id"]) != int(g.aluno_id):
        return None
    return sessao


@api_historico_bp.get("/historico")
@aluno_token_obrigatorio
def historico():
    sessoes = database.listar_sessoes_treino([g.aluno_id], 100)
    concluidas = [s for s in sessoes if s.get("status") == "CONCLUIDO"]
    estatisticas = database.estatisticas_execucoes([g.aluno_id])
    cargas = database.listar_ultimas_cargas_aluno(g.aluno_id, 12)
    return jsonify({
        "sucesso": True,
        "sessoes": concluidas,
        "estatisticas": estatisticas,
        "ultimas_cargas": cargas,
    })


@api_historico_bp.get("/historico/<int:sessao_id>")
@aluno_token_obrigatorio
def detalhe_historico(sessao_id: int):
    sessao = _sessao_do_aluno(sessao_id)
    if not sessao or sessao.get("status") != "CONCLUIDO":
        return resposta_erro("Treino nao encontrado.", 404, "TREINO_NAO_ENCONTRADO")
    return jsonify({"sucesso": True, "sessao": sessao})
