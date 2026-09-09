import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import numpy as np
from flask import Flask

import database
from agent.access_engine import LocalAccessEngine
from agent.state import AgentState
from core.settings import Settings
from routes.api.agent import api_agent_bp
from services import agent_service


class AgentV611Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path = database.DB_PATH
        self.old_backend = database.DATABASE_BACKEND
        database.DATABASE_BACKEND = "sqlite"
        database.DB_PATH = Path(self.tmp.name) / "gym.db"
        database.criar_tabelas()

    def tearDown(self):
        database.DB_PATH = self.old_path
        database.DATABASE_BACKEND = self.old_backend
        self.tmp.cleanup()

    def _settings(self):
        with patch.dict("os.environ", {
            "APP_ENV": "testing",
            "APP_ROLE": "cloud",
            "DATABASE_BACKEND": "sqlite",
            "STORAGE_BACKEND": "local",
            "ENABLE_LOCAL_HARDWARE": "0",
            "AGENT_API_TOKEN": "bootstrap-seguro-v611",
        }, clear=False):
            return Settings.from_env()

    def _register(self, uid="pc-01"):
        agente, token = agent_service.registrar_ou_rotacionar_agente({
            "agent_uid": uid,
            "nome": "Entrada principal",
            "hostname": "gym-pc",
            "machine_id": "machine-123",
            "capabilities": {"turnstile": True},
        }, "127.0.0.1")
        return agente, token

    def test_schema_21_cria_tabelas_do_agente(self):
        self.assertEqual(database.SCHEMA_VERSION, 21)
        conn = database.conectar()
        try:
            tabelas = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            self.assertTrue({"agentes_locais", "agente_comandos", "agente_eventos"}.issubset(tabelas))
            versao = conn.execute("SELECT valor FROM schema_meta WHERE chave='schema_version'").fetchone()[0]
            self.assertEqual(versao, "21")
        finally:
            conn.close()

    def test_token_individual_e_armazenado_apenas_como_hash(self):
        agente, token = self._register()
        self.assertGreaterEqual(len(token), 48)
        autenticado = agent_service.autenticar_agente(token)
        self.assertEqual(autenticado["id"], agente["id"])
        conn = database.conectar()
        try:
            row = conn.execute("SELECT token_hash FROM agentes_locais WHERE id=?", (agente["id"],)).fetchone()
            self.assertNotEqual(row[0], token)
            self.assertEqual(row[0], agent_service.token_hash(token))
        finally:
            conn.close()

    def test_comando_cloud_agente_tem_ciclo_completo(self):
        agente, _ = self._register()
        comando = database.criar_comando_agente(agente["id"], "PING", {"x": 1})
        self.assertEqual(database.contar_comandos_pendentes_agente(agente["id"]), 1)
        pendentes = database.buscar_comandos_agente(agente["id"], 20)
        self.assertEqual(pendentes[0]["type"], "PING")
        self.assertTrue(database.confirmar_comando_agente(
            agente["id"], comando["command_uuid"], ok=True, result={"pong": True}
        ))
        salvo = database.listar_comandos_agente(agente["id"], 1)[0]
        self.assertEqual(salvo["status"], "ACKED")

    def test_eventos_sao_idempotentes(self):
        agente, _ = self._register()
        evento = {"event_uuid": "evt-1", "type": "AGENT_TEST", "payload": {"ok": True}}
        a = agent_service.processar_eventos(agente, [evento])
        b = agent_service.processar_eventos(agente, [evento])
        self.assertEqual(a["accepted"], 1)
        self.assertEqual(b["duplicates"], 1)
        self.assertEqual(len(database.listar_eventos_agente(agente["id"])), 1)

    def test_estado_local_persiste_snapshot_e_outbox(self):
        state = AgentState(Path(self.tmp.name) / "agent-state.db")
        snapshot = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "sync_version": "abc",
            "config": {"limiar_reconhecimento": "0.50"},
            "catracas": [{"id": 1, "nome": "C1", "modo": "SIMULADA", "ativa": True}],
            "pessoas": [{
                "id": 10, "nome": "Aluno", "liberado": True, "status_financeiro": "EM_DIA",
                "data_vencimento": (date.today() + timedelta(days=10)).isoformat(),
                "encodings": [np.zeros(128).tolist()],
            }],
        }
        state.save_snapshot(snapshot)
        self.assertEqual(len(state.list_people_with_encodings()), 1)
        self.assertEqual(state.get_turnstile(1)["nome"], "C1")
        event_uuid = state.queue_event("TEST", {"a": 1})
        self.assertEqual(state.queue_depth(), 1)
        state.mark_events_sent([event_uuid])
        self.assertEqual(state.queue_depth(), 0)

    def test_acesso_offline_libera_com_cache_fresco_e_catraca_simulada(self):
        state = AgentState(Path(self.tmp.name) / "offline.db")
        state.save_snapshot({
            "generated_at": datetime.now(timezone.utc).isoformat(), "sync_version": "v1",
            "config": {"limiar_reconhecimento": "0.50", "tolerancia_financeira_dias": "5"},
            "catracas": [{"id": 1, "nome": "C1", "modo": "SIMULADA", "ativa": True}],
            "pessoas": [{
                "id": 1, "nome": "Aluno", "liberado": True, "status_financeiro": "EM_DIA",
                "data_vencimento": (date.today() + timedelta(days=5)).isoformat(),
                "encodings": [np.zeros(128).tolist()],
            }],
        })
        result = LocalAccessEngine(state, offline_cache_max_minutes=120).process_encoding(np.zeros(128), catraca_id=1)
        self.assertEqual(result["status"], "LIBERADO")
        self.assertEqual(result["decision_source"], "CACHE_OFFLINE")
        self.assertEqual(state.queue_depth(), 1)

    def test_cache_offline_expirado_falha_fechado(self):
        state = AgentState(Path(self.tmp.name) / "stale.db")
        velho = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        state.save_snapshot({
            "generated_at": velho, "sync_version": "v1",
            "config": {"limiar_reconhecimento": "0.50"},
            "catracas": [{"id": 1, "nome": "C1", "modo": "SIMULADA", "ativa": True}],
            "pessoas": [{
                "id": 1, "nome": "Aluno", "liberado": True, "status_financeiro": "EM_DIA",
                "data_vencimento": (date.today() + timedelta(days=5)).isoformat(),
                "encodings": [np.zeros(128).tolist()],
            }],
        })
        result = LocalAccessEngine(state, offline_cache_max_minutes=30).process_encoding(np.zeros(128), catraca_id=1)
        self.assertEqual(result["status"], "BLOQUEADO")
        self.assertIn("Cache local expirado", result["reason"])

    def test_api_registro_heartbeat_sync_e_comandos(self):
        app = Flask(__name__)
        app.config["GYM_SETTINGS"] = self._settings()
        app.register_blueprint(api_agent_bp)
        client = app.test_client()
        self.assertEqual(client.post("/api/v1/agent/register", json={"agent_uid": "pc-api"}).status_code, 401)
        reg = client.post(
            "/api/v1/agent/register", json={"agent_uid": "pc-api", "nome": "PC API"},
            headers={"Authorization": "Bearer bootstrap-seguro-v611"},
        )
        self.assertEqual(reg.status_code, 201, reg.get_data(as_text=True))
        token = reg.get_json()["agent_token"]
        headers = {"Authorization": f"Bearer {token}"}
        hb = client.post("/api/v1/agent/heartbeat", json={"queue_depth": 0}, headers=headers)
        self.assertEqual(hb.status_code, 200, hb.get_data(as_text=True))
        sync = client.get("/api/v1/agent/sync/access", headers=headers)
        self.assertEqual(sync.status_code, 200, sync.get_data(as_text=True))
        agente = database.listar_agentes()[0]
        database.criar_comando_agente(agente["id"], "PING", {})
        commands = client.get("/api/v1/agent/commands", headers=headers)
        self.assertEqual(commands.status_code, 200)
        self.assertEqual(commands.get_json()["commands"][0]["type"], "PING")


if __name__ == "__main__":
    unittest.main()
