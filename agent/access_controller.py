"""Controlador online-first do acesso no computador da academia."""

from __future__ import annotations

from agent import client
from agent.access_engine import LocalAccessEngine


class AgentAccessController:
    """Reconhece localmente, consulta o cloud quando possivel e falha para cache offline."""

    def __init__(self, state, *, server_url: str, token_getter, request_timeout: float = 5.0,
                 offline_cache_max_minutes: int = 120):
        self.state = state
        self.server_url = server_url
        self.token_getter = token_getter
        self.request_timeout = float(request_timeout)
        self.engine = LocalAccessEngine(state, offline_cache_max_minutes=offline_cache_max_minutes)

    def authorize_encoding(self, encoding, *, catraca_id: int | None = None) -> dict:
        pessoa, _ = self.engine.match_encoding(encoding)
        online = None
        if pessoa is not None:
            try:
                token = self.token_getter()
                if token:
                    online = client.check_access(
                        self.server_url, token, int(pessoa["pessoa_id"]), timeout=self.request_timeout
                    )
            except Exception:
                online = None
        return self.engine.process_encoding(encoding, catraca_id=catraca_id, online_decision=online)
