"""Avaliacoes fisicas e evolucao do aluno para o aplicativo mobile."""

from flask import Blueprint, g, jsonify

import database
from services import assessment_service
from .common import aluno_token_obrigatorio, resposta_erro

api_evolucao_bp = Blueprint("api_evolucao", __name__, url_prefix="/api/v1/aluno")


@api_evolucao_bp.get("/evolucao")
@aluno_token_obrigatorio
def evolucao():
    avaliacoes = database.listar_avaliacoes_fisicas(g.aluno_id)
    return jsonify({
        "sucesso": True,
        "avaliacoes": avaliacoes,
        "comparacao": assessment_service.comparacao(avaliacoes),
    })


@api_evolucao_bp.get("/evolucao/<int:avaliacao_id>")
@aluno_token_obrigatorio
def detalhe_evolucao(avaliacao_id: int):
    avaliacao = database.obter_avaliacao_fisica(avaliacao_id)
    if not avaliacao or int(avaliacao["pessoa_id"]) != int(g.aluno_id):
        return resposta_erro("Avaliacao nao encontrada.", 404, "AVALIACAO_NAO_ENCONTRADA")
    return jsonify({"sucesso": True, "avaliacao": avaliacao})
