"""Entrega controlada de arquivos privados locais por URL temporaria assinada."""

from flask import Blueprint, abort, make_response, send_file

from services import storage_service


media_bp = Blueprint("media", __name__)


@media_bp.get("/media/private/<path:token>")
def private_media(token: str):
    try:
        caminho, content_type, _ = storage_service.resolver_token_local(token)
    except FileNotFoundError:
        abort(404)
    except ValueError:
        abort(403)

    response = make_response(send_file(caminho, mimetype=content_type, conditional=True, max_age=0))
    response.headers["Cache-Control"] = "private, no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response
