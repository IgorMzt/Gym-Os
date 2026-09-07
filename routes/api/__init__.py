"""Blueprints da API v1 do Gym OS."""

from .auth import api_auth_bp
from .aluno import api_aluno_bp
from .treinos import api_treinos_bp
from .historico import api_historico_bp
from .evolucao import api_evolucao_bp
from .financeiro import api_financeiro_bp
from .notificacoes import api_notificacoes_bp
from .experiencia import api_experiencia_bp

__all__ = [
    "api_auth_bp",
    "api_aluno_bp",
    "api_treinos_bp",
    "api_historico_bp",
    "api_evolucao_bp",
    "api_financeiro_bp",
    "api_notificacoes_bp",
    "api_experiencia_bp",
]
