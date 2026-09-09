"""Servicos do Gym OS Local Agent (V6.11).

O backend central nunca recebe imagens da camera nesta camada. O agente local
sincroniza somente os dados minimos necessarios para reconhecimento/autorizacao,
reporta eventos idempotentes e recebe comandos operacionais.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone

import database


def token_hash(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def emitir_token_agente() -> str:
    return secrets.token_urlsafe(48)


def registrar_ou_rotacionar_agente(dados: dict, ip: str | None = None) -> tuple[dict, str]:
    agent_uid = str(dados.get("agent_uid") or dados.get("agent_id") or "").strip()[:120]
    if not agent_uid:
        raise ValueError("agent_uid obrigatorio.")
    nome = str(dados.get("nome") or agent_uid).strip()[:120]
    machine_id = str(dados.get("machine_id") or "").strip()[:160] or None
    hostname = str(dados.get("hostname") or "").strip()[:160] or None
    plataforma = str(dados.get("plataforma") or "").strip()[:80] or None
    app_version = str(dados.get("app_version") or "").strip()[:40] or None
    capacidades = dados.get("capabilities") or {}
    if not isinstance(capacidades, dict):
        capacidades = {}

    token = emitir_token_agente()
    agente = database.registrar_agente(
        agent_uid=agent_uid,
        nome=nome,
        token_hash=token_hash(token),
        machine_id=machine_id,
        hostname=hostname,
        plataforma=plataforma,
        app_version=app_version,
        capabilities=capacidades,
        ip=ip,
    )
    return agente, token


def autenticar_agente(token: str) -> dict | None:
    token = str(token or "").strip()
    if not token:
        return None
    return database.obter_agente_por_token_hash(token_hash(token))


def heartbeat(agente: dict, dados: dict, ip: str | None = None) -> dict:
    atualizado = database.atualizar_heartbeat_agente(
        int(agente["id"]),
        hostname=str(dados.get("hostname") or "").strip()[:160] or None,
        machine_id=str(dados.get("machine_id") or "").strip()[:160] or None,
        plataforma=str(dados.get("plataforma") or "").strip()[:80] or None,
        app_version=str(dados.get("app_version") or "").strip()[:40] or None,
        capabilities=dados.get("capabilities") if isinstance(dados.get("capabilities"), dict) else None,
        ip=ip,
        queue_depth=dados.get("queue_depth"),
        cache_age_seconds=dados.get("cache_age_seconds"),
    )
    return atualizado or agente


def access_snapshot() -> dict:
    pessoas = database.listar_pessoas()
    amostras = database.listar_amostras_faciais()
    payload_pessoas = []
    for pessoa in pessoas:
        item = {
            "id": int(pessoa["id"]),
            "nome": pessoa.get("nome"),
            "cpf": pessoa.get("cpf"),
            "matricula": pessoa.get("matricula"),
            "plano": pessoa.get("plano"),
            "plano_id": pessoa.get("plano_id"),
            "data_vencimento": pessoa.get("data_vencimento"),
            "status_financeiro": database.status_financeiro_efetivo(pessoa),
            "liberado": bool(pessoa.get("liberado")),
            "encodings": [enc.tolist() for enc in amostras.get(int(pessoa["id"]), [])],
        }
        if not item["encodings"] and pessoa.get("encoding") is not None:
            item["encodings"] = [pessoa["encoding"].tolist()]
        payload_pessoas.append(item)

    cfg = database.obter_configuracoes()
    config_keys = {
        "tolerancia_financeira_dias", "limiar_reconhecimento", "liveness_ativo",
        "liveness_janela_segundos", "intervalo_log", "catraca_padrao_id",
    }
    configuracao = {k: cfg.get(k) for k in config_keys if k in cfg}
    catracas = [
        {k: c.get(k) for k in ("id", "nome", "local", "modo", "endpoint", "ativa")}
        for c in database.listar_catracas(apenas_ativas=True)
    ]
    base = {"pessoas": payload_pessoas, "config": configuracao, "catracas": catracas}
    digest = hashlib.sha256(
        json.dumps(base, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return {
        "sync_version": digest,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **base,
    }


def decisao_acesso_online(pessoa_id: int) -> dict:
    pessoa = database.obter_pessoa(int(pessoa_id))
    if not pessoa:
        return {"allowed": False, "reason": "Aluno nao encontrado.", "pessoa": None}
    permitido, motivo = database.acesso_permitido(pessoa)
    return {
        "allowed": bool(permitido),
        "reason": motivo,
        "pessoa": {
            "id": int(pessoa["id"]),
            "nome": pessoa.get("nome"),
            "cpf": pessoa.get("cpf"),
            "matricula": pessoa.get("matricula"),
            "plano": pessoa.get("plano"),
            "data_vencimento": pessoa.get("data_vencimento"),
            "status_financeiro": database.status_financeiro_efetivo(pessoa),
        },
    }


def processar_eventos(agente: dict, eventos: list[dict]) -> dict:
    aceitos = 0
    duplicados = 0
    erros = []
    for bruto in eventos[:100]:
        if not isinstance(bruto, dict):
            erros.append("evento_invalido")
            continue
        event_uuid = str(bruto.get("event_uuid") or "").strip()[:80]
        tipo = str(bruto.get("type") or bruto.get("tipo") or "").strip().upper()[:80]
        payload = bruto.get("payload") or {}
        ocorrido_em = str(bruto.get("occurred_at") or "").strip()[:80] or None
        if not event_uuid or not tipo or not isinstance(payload, dict):
            erros.append(event_uuid or "evento_sem_id")
            continue
        criado = database.registrar_evento_agente(
            int(agente["id"]), event_uuid, tipo, payload, ocorrido_em
        )
        if not criado:
            duplicados += 1
            existente = database.obter_evento_agente(event_uuid)
            # Um evento armazenado cujo processamento falhou pode ser
            # reenviado pelo agente. Nao duplicamos o registro, apenas
            # repetimos a etapa de processamento pendente.
            if existente and int(existente.get("processed") or 0) == 0:
                if tipo == "ACCESS_DECISION":
                    try:
                        database.registrar_log_evento_agente(payload, ocorrido_em)
                        database.marcar_evento_agente_processado(event_uuid)
                    except Exception as exc:
                        database.marcar_evento_agente_processado(event_uuid, str(exc))
                        erros.append(event_uuid)
                else:
                    database.marcar_evento_agente_processado(event_uuid)
            continue
        aceitos += 1
        if tipo == "ACCESS_DECISION":
            try:
                database.registrar_log_evento_agente(payload, ocorrido_em)
                database.marcar_evento_agente_processado(event_uuid)
            except Exception as exc:
                database.marcar_evento_agente_processado(event_uuid, str(exc))
                erros.append(event_uuid)
        else:
            database.marcar_evento_agente_processado(event_uuid)
    return {"accepted": aceitos, "duplicates": duplicados, "errors": erros}
