"""Loop de conectividade do futuro agente local da academia."""

from __future__ import annotations

import os
import time

from dotenv import load_dotenv

from agent.client import heartbeat


def main() -> None:
    load_dotenv()
    server = (os.getenv("AGENT_SERVER_URL") or "http://127.0.0.1:5000").strip()
    token = (os.getenv("AGENT_API_TOKEN") or "").strip()
    agent_id = (os.getenv("AGENT_ID") or "academia-principal").strip()
    intervalo = max(10, int(os.getenv("AGENT_HEARTBEAT_SECONDS") or "30"))
    if not token:
        raise SystemExit("Defina AGENT_API_TOKEN antes de iniciar o agente.")

    print(f"Gym OS Agent 6.9 -> {server} ({agent_id})")
    while True:
        try:
            resposta = heartbeat(server, token, agent_id)
            print(f"heartbeat ok: server={resposta.get('server_version')}")
        except Exception as exc:
            print(f"heartbeat erro: {exc}")
        time.sleep(intervalo)


if __name__ == "__main__":
    main()
