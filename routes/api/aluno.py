"""Recursos do aluno expostos para o aplicativo mobile."""

from flask import Blueprint, g, jsonify, url_for

import database
from .common import aluno_token_obrigatorio, resposta_erro


api_aluno_bp = Blueprint("api_aluno", __name__, url_prefix="/api/v1/aluno")


@api_aluno_bp.get("/me")
@aluno_token_obrigatorio
def me():
    pessoa = database.obter_pessoa(g.aluno_id)
    if not pessoa:
        return resposta_erro("Aluno nao encontrado.", 404, "ALUNO_NAO_ENCONTRADO")

    return jsonify({
        "sucesso": True,
        "aluno": {
            "id": int(pessoa["id"]),
            "nome": pessoa.get("nome"),
            "cpf": pessoa.get("cpf"),
            "data_nascimento": pessoa.get("data_nascimento"),
            "sexo": pessoa.get("sexo"),
            "telefone": pessoa.get("telefone"),
            "email": pessoa.get("email"),
            "matricula": pessoa.get("matricula"),
            "plano": pessoa.get("plano"),
            "plano_id": pessoa.get("plano_id"),
            "data_inicio": pessoa.get("data_inicio"),
            "data_vencimento": pessoa.get("data_vencimento"),
            "status_financeiro": pessoa.get("status_financeiro"),
            "foto_url": url_for("static", filename=pessoa["foto_path"]) if pessoa.get("foto_path") else None,
        },
        "conta": {
            "login": g.aluno_acesso.get("login"),
            "ultimo_login": g.aluno_acesso.get("ultimo_login"),
        },
    })
