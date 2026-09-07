"""Envio de notificacoes pelo Expo Push Service."""
import json
import urllib.error
import urllib.request

import database

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


def _token_valido(token: str) -> bool:
    return token.startswith("ExponentPushToken[") or token.startswith("ExpoPushToken[")


def enviar_para_aluno(pessoa_id: int, titulo: str, corpo: str, data=None):
    devices = database.listar_push_devices_pessoa(pessoa_id)
    mensagens = []
    for d in devices:
        token = d.get("expo_push_token") or ""
        if _token_valido(token):
            mensagens.append({"to": token, "sound": "default", "title": titulo, "body": corpo, "data": data or {}})
    if not mensagens:
        return {"enviadas": 0, "tickets": []}

    req = urllib.request.Request(
        EXPO_PUSH_URL,
        data=json.dumps(mensagens).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {"enviadas": 0, "erro": str(exc), "tickets": []}

    tickets = payload.get("data") if isinstance(payload, dict) else []
    if isinstance(tickets, dict):
        tickets = [tickets]
    # DeviceNotRegistered: desativa o token quando o erro vier imediatamente no ticket.
    for device, ticket in zip(devices, tickets or []):
        details = ticket.get("details") or {} if isinstance(ticket, dict) else {}
        if details.get("error") == "DeviceNotRegistered":
            database.desativar_push_token(device.get("expo_push_token"))
    return {"enviadas": len(mensagens), "tickets": tickets or []}
