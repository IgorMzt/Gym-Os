"""Cliente HTTP do Gym OS Agent V6.11, sem dependencia externa."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request


class AgentHttpError(RuntimeError):
    pass


def _request(server_url: str, path: str, *, token: str | None = None, method: str = "GET",
             payload=None, timeout: float = 8.0) -> dict:
    url = server_url.rstrip("/") + path
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json", "User-Agent": "GymOS-Agent/6.11"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resposta:
            corpo = resposta.read().decode("utf-8")
            return json.loads(corpo or "{}")
    except urllib.error.HTTPError as exc:
        detalhe = exc.read().decode("utf-8", errors="replace")
        raise AgentHttpError(f"HTTP {exc.code}: {detalhe}") from exc
    except urllib.error.URLError as exc:
        raise AgentHttpError(f"Backend indisponivel: {exc.reason}") from exc


def register(server_url: str, bootstrap_token: str, metadata: dict, timeout: float = 8.0) -> dict:
    return _request(server_url, "/api/v1/agent/register", token=bootstrap_token, method="POST", payload=metadata, timeout=timeout)


def heartbeat(server_url: str, token: str, metadata: dict, timeout: float = 8.0) -> dict:
    return _request(server_url, "/api/v1/agent/heartbeat", token=token, method="POST", payload=metadata, timeout=timeout)


def sync_access(server_url: str, token: str, timeout: float = 15.0) -> dict:
    return _request(server_url, "/api/v1/agent/sync/access", token=token, timeout=timeout)


def check_access(server_url: str, token: str, pessoa_id: int, timeout: float = 5.0) -> dict:
    return _request(server_url, "/api/v1/agent/access/check", token=token, method="POST", payload={"pessoa_id": int(pessoa_id)}, timeout=timeout)


def send_events(server_url: str, token: str, events: list[dict], timeout: float = 10.0) -> dict:
    return _request(server_url, "/api/v1/agent/events", token=token, method="POST", payload={"events": events}, timeout=timeout)


def get_commands(server_url: str, token: str, limit: int = 20, timeout: float = 8.0) -> dict:
    query = urllib.parse.urlencode({"limit": max(1, min(int(limit), 50))})
    return _request(server_url, f"/api/v1/agent/commands?{query}", token=token, timeout=timeout)


def ack_command(server_url: str, token: str, command_uuid: str, *, ok: bool, result=None, timeout: float = 8.0) -> dict:
    return _request(
        server_url, f"/api/v1/agent/commands/{urllib.parse.quote(command_uuid)}/ack",
        token=token, method="POST", payload={"ok": bool(ok), "result": result or {}}, timeout=timeout,
    )
