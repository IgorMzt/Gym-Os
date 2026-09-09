"""Orquestrador de sincronizacao, fila offline e comandos do agente V6.11."""

from __future__ import annotations

import os
import platform
import socket
import time
import uuid

from agent import client, hardware
from agent.state import AgentState


def machine_id() -> str:
    configured = (os.getenv("AGENT_MACHINE_ID") or "").strip()
    if configured:
        return configured[:160]
    return f"{socket.gethostname()}-{uuid.getnode():012x}"[:160]


def metadata(state: AgentState) -> dict:
    uid = (os.getenv("AGENT_UID") or os.getenv("AGENT_ID") or "academia-principal").strip()[:120]
    return {
        "agent_uid": uid,
        "agent_id": uid,
        "nome": (os.getenv("AGENT_NAME") or uid).strip()[:120],
        "machine_id": machine_id(),
        "hostname": socket.gethostname()[:160],
        "plataforma": platform.platform()[:80],
        "app_version": "6.11",
        "capabilities": {"face_recognition": True, "turnstile": True, "offline_queue": True},
        "queue_depth": state.queue_depth(),
        "cache_age_seconds": state.cache_age_seconds(),
    }


class AgentRuntime:
    def __init__(self, *, state: AgentState, server_url: str, bootstrap_token: str,
                 timeout: float = 8.0):
        self.state = state
        self.server_url = server_url.rstrip("/")
        self.bootstrap_token = bootstrap_token
        self.timeout = float(timeout)

    @property
    def token(self) -> str | None:
        return self.state.get_meta("agent_token")

    def ensure_registered(self) -> str:
        token = self.token
        if token:
            return token
        if not self.bootstrap_token:
            raise RuntimeError("AGENT_API_TOKEN obrigatorio para registrar um novo agente.")
        response = client.register(self.server_url, self.bootstrap_token, metadata(self.state), self.timeout)
        token = str(response.get("agent_token") or "").strip()
        if not response.get("sucesso") or not token:
            raise RuntimeError("Backend nao retornou token do agente.")
        self.state.set_meta("agent_token", token)
        self.state.set_meta("agent_db_id", response.get("agent", {}).get("id", ""))
        return token

    def heartbeat(self) -> dict:
        return client.heartbeat(self.server_url, self.ensure_registered(), metadata(self.state), self.timeout)

    def sync_access(self) -> dict:
        response = client.sync_access(self.server_url, self.ensure_registered(), max(self.timeout, 15.0))
        if not response.get("sucesso"):
            raise RuntimeError("Falha ao sincronizar cache de acesso.")
        return self.state.save_snapshot(response["snapshot"])

    def flush_events(self) -> dict:
        events = self.state.pending_events(50)
        if not events:
            return {"sent": 0}
        try:
            response = client.send_events(self.server_url, self.ensure_registered(), events, max(self.timeout, 10.0))
            if not response.get("sucesso"):
                raise RuntimeError("Servidor recusou lote de eventos.")
            # Eventos que o backend armazenou mas ainda nao conseguiu processar
            # permanecem na outbox. O reenvio e seguro por event_uuid.
            failed = {str(x) for x in (response.get("errors") or [])}
            sent_ids = [e["event_uuid"] for e in events if e["event_uuid"] not in failed]
            self.state.mark_events_sent(sent_ids)
            for event in events:
                if event["event_uuid"] in failed:
                    self.state.mark_event_error(event["event_uuid"], "backend_processing_error")
            return {"sent": len(sent_ids), "pending_retry": len(failed), "server": response}
        except Exception as exc:
            for event in events:
                self.state.mark_event_error(event["event_uuid"], str(exc))
            raise

    def _execute_command(self, command: dict) -> tuple[bool, dict]:
        tipo = str(command.get("type") or command.get("tipo") or "").upper()
        payload = command.get("payload") or {}
        if tipo == "PING":
            return True, {"pong": True, "time": time.time()}
        if tipo in {"SYNC_ACCESS", "REFRESH_CONFIG"}:
            return True, self.sync_access()
        if tipo == "TEST_TURNSTILE":
            catraca_id = payload.get("catraca_id")
            catraca = self.state.get_turnstile(int(catraca_id)) if catraca_id else self.state.get_turnstile()
            if not catraca:
                return False, {"error": "Catraca nao encontrada no cache local."}
            return True, hardware.test_turnstile(catraca)
        return False, {"error": f"Comando nao suportado: {tipo}"}

    def poll_commands(self) -> dict:
        response = client.get_commands(self.server_url, self.ensure_registered(), 20, self.timeout)
        commands = response.get("commands") or []
        processed = 0
        for command in commands:
            command_uuid = str(command.get("command_uuid") or "")
            tipo = str(command.get("type") or command.get("tipo") or "")
            if not command_uuid:
                continue
            seen = self.state.get_seen_command(command_uuid)
            if seen:
                # Se a execucao local terminou mas a rede caiu antes do ACK,
                # reenviamos o mesmo resultado sem executar o hardware de novo.
                ok = seen.get("status") == "ACKED"
                client.ack_command(
                    self.server_url, self.ensure_registered(), command_uuid,
                    ok=ok, result=seen.get("result") or {}, timeout=self.timeout,
                )
                processed += 1
                continue
            try:
                ok, result = self._execute_command(command)
            except Exception as exc:
                ok, result = False, {"error": str(exc)}
            self.state.remember_command(command_uuid, tipo, "ACKED" if ok else "FAILED", result)
            client.ack_command(self.server_url, self.ensure_registered(), command_uuid, ok=ok, result=result, timeout=self.timeout)
            processed += 1
        return {"processed": processed}

    def cycle(self, *, sync: bool = False) -> dict:
        result = {"heartbeat": self.heartbeat()}
        if sync:
            result["sync"] = self.sync_access()
        try:
            result["events"] = self.flush_events()
        except Exception as exc:
            result["events_error"] = str(exc)
        try:
            result["commands"] = self.poll_commands()
        except Exception as exc:
            result["commands_error"] = str(exc)
        return result
