"""Entrada WSGI para servidores de producao."""

from app import create_app

app = create_app()
