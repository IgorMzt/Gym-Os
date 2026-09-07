"""Cliente HTTP minimalista do agente local, sem dependencia externa."""

from __future__ import annotations

import json
import urllib.error
import urllib.request


def heartbeat(server_url: str, token: str, agent_id: str, timeout: float = 5.0) -> dict:
    url = server_url.rstrip("/") + "/api/v1/agent/heartbeat"
    corpo = json.dumps({"agent_id": agent_id}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=corpo,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "GymOS-Agent/6.9",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resposta:
            return json.loads(resposta.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detalhe = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Heartbeat recusado ({exc.code}): {detalhe}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Backend indisponivel: {exc.reason}") from exc
