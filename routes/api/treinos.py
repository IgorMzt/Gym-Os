"""Treinos e execucoes do aluno para o aplicativo mobile."""

from flask import Blueprint, g, jsonify, request

import database
from services import execution_service
from .common import aluno_token_obrigatorio, resposta_erro

api_treinos_bp = Blueprint("api_treinos", __name__, url_prefix="/api/v1/aluno")


def _sessao_do_aluno(sessao_id):
    sessao = database.obter_sessao_treino(sessao_id)
    if not sessao or int(sessao["pessoa_id"]) != int(g.aluno_id):
        return None
    return sessao


def _enriquecer_sessao(sessao):
    if not sessao:
        return None
    for item in sessao.get("itens", []):
        item["ultima_execucao"] = (
            database.ultima_execucao_exercicio(int(g.aluno_id), int(item["exercicio_id"]))
            if item.get("exercicio_id") else None
        )
    return sessao


@api_treinos_bp.get("/treinos")
@aluno_token_obrigatorio
def treinos():
    ficha = database.obter_ficha_ativa_aluno(g.aluno_id)
    sessao = database.obter_sessao_em_andamento_aluno(g.aluno_id)
    proximo = database.proximo_treino_aluno(g.aluno_id)
    return jsonify({
        "sucesso": True,
        "ficha": ficha,
        "sessao_em_andamento": _enriquecer_sessao(sessao),
        "proximo_treino_id": int(proximo["id"]) if proximo else None,
    })


@api_treinos_bp.post("/execucoes")
@aluno_token_obrigatorio
def iniciar_execucao():
    payload = request.get_json(silent=True) or {}
    try:
        treino_id = int(payload.get("treino_id"))
    except (TypeError, ValueError):
        return resposta_erro("Treino invalido.", 400, "TREINO_INVALIDO")

    sessao_id, erro = database.criar_sessao_treino(g.aluno_id, treino_id, None, "ALUNO_APP")
    if not sessao_id:
        return resposta_erro(erro or "Nao foi possivel iniciar o treino.", 400, "TREINO_NAO_INICIADO")
    return jsonify({"sucesso": True, "id": int(sessao_id), "reutilizada": erro == "JA_EXISTE"})


@api_treinos_bp.get("/execucoes/<int:sessao_id>")
@aluno_token_obrigatorio
def obter_execucao(sessao_id):
    sessao = _sessao_do_aluno(sessao_id)
    if not sessao:
        return resposta_erro("Sessao nao encontrada.", 404, "SESSAO_NAO_ENCONTRADA")
    return jsonify({"sucesso": True, "sessao": _enriquecer_sessao(sessao)})


@api_treinos_bp.put("/execucoes/itens/<int:item_id>")
@aluno_token_obrigatorio
def atualizar_item(item_id):
    conn = database.conectar()
    try:
        row = conn.execute("SELECT sessao_id FROM treino_sessao_itens WHERE id=?", (item_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        return resposta_erro("Item nao encontrado.", 404, "ITEM_NAO_ENCONTRADO")
    sessao = _sessao_do_aluno(row["sessao_id"])
    if not sessao:
        return resposta_erro("Sem permissao para este item.", 403, "SEM_PERMISSAO")
    try:
        dados = execution_service.normalizar_item(request.get_json(silent=True) or {})
    except ValueError as exc:
        return resposta_erro(str(exc), 400, "ITEM_INVALIDO")
    ok, erro, _ = database.atualizar_item_sessao(item_id, dados)
    if not ok:
        return resposta_erro(erro or "Nao foi possivel salvar.", 409, "ITEM_NAO_ATUALIZADO")
    return jsonify({"sucesso": True})


@api_treinos_bp.post("/execucoes/<int:sessao_id>/concluir")
@aluno_token_obrigatorio
def concluir_execucao(sessao_id):
    sessao = _sessao_do_aluno(sessao_id)
    if not sessao:
        return resposta_erro("Sessao nao encontrada.", 404, "SESSAO_NAO_ENCONTRADA")
    observacoes = execution_service.normalizar_observacao(request.get_json(silent=True) or {})
    ok, erro = database.concluir_sessao_treino(sessao_id, observacoes)
    if not ok:
        return resposta_erro(erro or "Nao foi possivel concluir.", 409, "SESSAO_NAO_CONCLUIDA")
    return jsonify({"sucesso": True})


@api_treinos_bp.post("/execucoes/<int:sessao_id>/cancelar")
@aluno_token_obrigatorio
def cancelar_execucao(sessao_id):
    sessao = _sessao_do_aluno(sessao_id)
    if not sessao:
        return resposta_erro("Sessao nao encontrada.", 404, "SESSAO_NAO_ENCONTRADA")
    observacoes = execution_service.normalizar_observacao(request.get_json(silent=True) or {})
    ok, erro = database.cancelar_sessao_treino(sessao_id, observacoes)
    if not ok:
        return resposta_erro(erro or "Nao foi possivel cancelar.", 409, "SESSAO_NAO_CANCELADA")
    return jsonify({"sucesso": True})
