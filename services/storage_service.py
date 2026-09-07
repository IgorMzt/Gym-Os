"""Abstracao minima de storage para preparar a migracao para object storage.

Na V6.9 o backend efetivo continua LOCAL. O contrato deste modulo permite
substituir a persistencia de uploads na V6.10/V6.11 sem espalhar caminhos de
disco pelas rotas.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_UPLOAD_DIR = BASE_DIR / "static" / "uploads"


def backend() -> str:
    return (os.getenv("STORAGE_BACKEND") or "local").strip().lower()


def _local_root() -> Path:
    configurado = (os.getenv("STORAGE_LOCAL_DIR") or "").strip()
    raiz = Path(configurado).expanduser().resolve() if configurado else DEFAULT_UPLOAD_DIR
    raiz.mkdir(parents=True, exist_ok=True)
    return raiz


def salvar_upload(conteudo: bytes, extensao: str = ".bin") -> str:
    if backend() != "local":
        raise RuntimeError("Object storage ainda nao foi ativado; use STORAGE_BACKEND=local na V6.9.")
    if not extensao.startswith("."):
        extensao = "." + extensao
    nome = f"{uuid.uuid4().hex}{extensao.lower()}"
    destino = _local_root() / nome
    destino.write_bytes(conteudo)
    return f"uploads/{nome}"


def remover_upload(caminho_relativo: str | None) -> None:
    if not caminho_relativo or backend() != "local":
        return
    nome = Path(str(caminho_relativo).replace("\\", "/")).name
    destino = _local_root() / nome
    try:
        destino.unlink(missing_ok=True)
    except OSError:
        pass


def healthcheck() -> dict:
    atual = backend()
    if atual != "local":
        return {"ok": False, "backend": atual, "detalhe": "backend ainda nao implementado"}
    try:
        raiz = _local_root()
        return {"ok": raiz.exists() and raiz.is_dir(), "backend": atual}
    except OSError as exc:
        return {"ok": False, "backend": atual, "detalhe": str(exc)}
