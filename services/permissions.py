"""Decoradores de autorizacao baseados em papel."""
from functools import wraps
from flask import jsonify, redirect, request, session, url_for


def usuario_logado():
    return bool(session.get("usuario_logado") and session.get("usuario_id"))


def papel_atual():
    return str(session.get("usuario_papel") or "").upper()


def login_obrigatorio(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not usuario_logado():
            if request.path.startswith("/api/"):
                return jsonify({"sucesso": False, "erro": "Autenticação necessária."}), 401
            return redirect(url_for("auth.pagina_login", proxima=request.path))
        return view(*args, **kwargs)
    return wrapper


def papel_requerido(*papeis):
    permitidos = {str(p).upper() for p in papeis}
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if not usuario_logado():
                if request.path.startswith("/api/"):
                    return jsonify({"sucesso": False, "erro": "Autenticação necessária."}), 401
                return redirect(url_for("auth.pagina_login", proxima=request.path))
            if papel_atual() not in permitidos:
                if request.path.startswith("/api/"):
                    return jsonify({"sucesso": False, "erro": "Você não tem permissão para esta ação."}), 403
                destino = "pagina_minha_area" if papel_atual() == "PROFESSOR" else ("aluno_app_inicio" if papel_atual() == "ALUNO" else "pagina_painel")
                return redirect(url_for(destino))
            return view(*args, **kwargs)
        return wrapper
    return decorator
