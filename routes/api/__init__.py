"""Blueprints da API v1 do Gym OS."""

from .auth import api_auth_bp
from .aluno import api_aluno_bp
from .treinos import api_treinos_bp

__all__ = ["api_auth_bp", "api_aluno_bp", "api_treinos_bp"]
