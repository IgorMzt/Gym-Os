"""Executavel do Gym OS Local Agent V6.11."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv

from agent.runtime import AgentRuntime
from agent.state import AgentState


def _build_runtime():
    load_dotenv()
    server = (os.getenv("AGENT_SERVER_URL") or "http://127.0.0.1:5000").strip()
    bootstrap = (os.getenv("AGENT_API_TOKEN") or "").strip()
    state_path = (os.getenv("AGENT_STATE_PATH") or str(Path(__file__).with_name("agent_state.db"))).strip()
    timeout = max(2.0, float(os.getenv("AGENT_REQUEST_TIMEOUT") or "8"))
    state = AgentState(state_path)
    return state, AgentRuntime(state=state, server_url=server, bootstrap_token=bootstrap, timeout=timeout)


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m agent.main")
    parser.add_argument("--once", action="store_true", help="Executa um ciclo e encerra.")
    parser.add_argument("--diagnose", action="store_true", help="Mostra estado local sem alterar o cache.")
    parser.add_argument("--sync", action="store_true", help="Forca sincronizacao de acesso no primeiro ciclo.")
    args = parser.parse_args()

    state, runtime = _build_runtime()
    if args.diagnose:
        print(json.dumps({
            "ok": True,
            "version": "6.11",
            "registered": bool(state.get_meta("agent_token")),
            "queue_depth": state.queue_depth(),
            "cache_age_seconds": state.cache_age_seconds(),
            "sync_version": state.get_meta("sync_version"),
            "state_path": str(state.path),
        }, indent=2, ensure_ascii=False))
        return

    heartbeat_seconds = max(10, int(os.getenv("AGENT_HEARTBEAT_SECONDS") or "30"))
    sync_seconds = max(60, int(os.getenv("AGENT_SYNC_SECONDS") or "300"))
    backoff = 2
    last_sync = 0.0
    print(f"Gym OS Agent 6.11 -> {runtime.server_url}")
    while True:
        now = time.monotonic()
        force_sync = args.sync or last_sync == 0.0 or now - last_sync >= sync_seconds
        try:
            result = runtime.cycle(sync=force_sync)
            if force_sync and "sync" in result:
                last_sync = now
            print(json.dumps({"ok": True, "queue": state.queue_depth(), "sync": force_sync}, ensure_ascii=False))
            backoff = 2
            if args.once:
                return
            time.sleep(heartbeat_seconds)
        except KeyboardInterrupt:
            return
        except Exception as exc:
            print(f"agent offline/retry: {exc}")
            if args.once:
                raise
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)


if __name__ == "__main__":
    main()
