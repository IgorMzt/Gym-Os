"""Camada unica de acionamento da catraca.

O navegador nunca abre o equipamento diretamente. A politica de acesso decide no
backend e somente entao esta camada recebe o comando. Modos HTTP/SERIAL ficam
explicitamente bloqueados ate existir um adaptador seguro e testado.
"""
from datetime import datetime, timezone


class DeviceError(RuntimeError):
    pass


def acionar(catraca):
    if not catraca or not catraca.get("ativa"):
        raise DeviceError("Catraca nao encontrada ou inativa.")

    modo = str(catraca.get("modo") or "SIMULADA").upper()
    if modo == "SIMULADA":
        return {
            "sucesso": True,
            "modo": "SIMULADA",
            "catraca_id": catraca.get("id"),
            "acionado_em": datetime.now(timezone.utc).isoformat(),
            "mensagem": "Comando de abertura simulado.",
        }

    if modo in {"HTTP", "SERIAL", "HARDWARE"}:
        raise DeviceError(f"Adaptador {modo} ainda nao configurado.")

    raise DeviceError("Modo de catraca invalido.")
