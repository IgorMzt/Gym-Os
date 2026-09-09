"""Estado persistente e cache offline do Gym OS Agent."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentState:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def connect(self):
        conn = sqlite3.connect(self.path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _init_schema(self):
        conn = self.connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    chave TEXT PRIMARY KEY,
                    valor TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS access_people (
                    pessoa_id INTEGER PRIMARY KEY,
                    nome TEXT NOT NULL,
                    cpf TEXT,
                    matricula TEXT,
                    plano TEXT,
                    plano_id INTEGER,
                    data_vencimento TEXT,
                    status_financeiro TEXT,
                    liberado INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS access_face_encodings (
                    pessoa_id INTEGER NOT NULL,
                    ordem INTEGER NOT NULL,
                    encoding_json TEXT NOT NULL,
                    PRIMARY KEY (pessoa_id, ordem),
                    FOREIGN KEY (pessoa_id) REFERENCES access_people(pessoa_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS cached_catracas (
                    id INTEGER PRIMARY KEY,
                    nome TEXT,
                    local TEXT,
                    modo TEXT,
                    endpoint TEXT,
                    ativa INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS outbox (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_uuid TEXT NOT NULL UNIQUE,
                    tipo TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS commands_seen (
                    command_uuid TEXT PRIMARY KEY,
                    tipo TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_json TEXT,
                    processed_at TEXT NOT NULL
                );
                """
            )
            conn.commit()
        finally:
            conn.close()

    def get_meta(self, key: str, default=None):
        conn = self.connect()
        try:
            row = conn.execute("SELECT valor FROM meta WHERE chave=?", (key,)).fetchone()
            return row[0] if row else default
        finally:
            conn.close()

    def set_meta(self, key: str, value) -> None:
        conn = self.connect()
        try:
            conn.execute(
                "INSERT INTO meta(chave,valor) VALUES(?,?) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor",
                (key, str(value)),
            )
            conn.commit()
        finally:
            conn.close()

    def save_snapshot(self, snapshot: dict) -> dict:
        pessoas = snapshot.get("pessoas") or []
        catracas = snapshot.get("catracas") or []
        config = snapshot.get("config") or {}
        now = _utc_now()
        conn = self.connect()
        try:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("DELETE FROM access_face_encodings")
            conn.execute("DELETE FROM access_people")
            conn.execute("DELETE FROM cached_catracas")
            for pessoa in pessoas:
                conn.execute(
                    """
                    INSERT INTO access_people(
                        pessoa_id,nome,cpf,matricula,plano,plano_id,data_vencimento,
                        status_financeiro,liberado,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        int(pessoa["id"]), str(pessoa.get("nome") or "Aluno"), pessoa.get("cpf"),
                        pessoa.get("matricula"), pessoa.get("plano"), pessoa.get("plano_id"),
                        pessoa.get("data_vencimento"), pessoa.get("status_financeiro"),
                        1 if pessoa.get("liberado") else 0, now,
                    ),
                )
                for ordem, encoding in enumerate(pessoa.get("encodings") or [], 1):
                    conn.execute(
                        "INSERT INTO access_face_encodings(pessoa_id,ordem,encoding_json) VALUES(?,?,?)",
                        (int(pessoa["id"]), ordem, json.dumps(encoding, separators=(",", ":"))),
                    )
            for catraca in catracas:
                conn.execute(
                    "INSERT INTO cached_catracas(id,nome,local,modo,endpoint,ativa) VALUES(?,?,?,?,?,?)",
                    (
                        int(catraca["id"]), catraca.get("nome"), catraca.get("local"),
                        catraca.get("modo") or "SIMULADA", catraca.get("endpoint"),
                        1 if catraca.get("ativa", True) else 0,
                    ),
                )
            metas = {
                "last_access_sync_at": snapshot.get("generated_at") or now,
                "sync_version": snapshot.get("sync_version") or "",
                "access_config": json.dumps(config, ensure_ascii=False, separators=(",", ":")),
            }
            for k, v in metas.items():
                conn.execute(
                    "INSERT INTO meta(chave,valor) VALUES(?,?) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor",
                    (k, str(v)),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return {"pessoas": len(pessoas), "catracas": len(catracas), "sync_version": snapshot.get("sync_version")}

    def get_access_config(self) -> dict:
        raw = self.get_meta("access_config", "{}")
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def list_people_with_encodings(self) -> list[dict]:
        conn = self.connect()
        try:
            pessoas = {int(r["pessoa_id"]): dict(r) for r in conn.execute("SELECT * FROM access_people").fetchall()}
            for pessoa in pessoas.values():
                pessoa["liberado"] = bool(pessoa["liberado"])
                pessoa["encodings"] = []
            for row in conn.execute("SELECT pessoa_id,ordem,encoding_json FROM access_face_encodings ORDER BY pessoa_id,ordem"):
                pessoa = pessoas.get(int(row["pessoa_id"]))
                if pessoa is not None:
                    pessoa["encodings"].append(json.loads(row["encoding_json"]))
            return list(pessoas.values())
        finally:
            conn.close()

    def get_person(self, pessoa_id: int) -> dict | None:
        conn = self.connect()
        try:
            row = conn.execute("SELECT * FROM access_people WHERE pessoa_id=?", (int(pessoa_id),)).fetchone()
            if not row:
                return None
            data = dict(row)
            data["liberado"] = bool(data["liberado"])
            return data
        finally:
            conn.close()

    def get_turnstile(self, catraca_id: int | None = None) -> dict | None:
        conn = self.connect()
        try:
            if catraca_id is not None:
                row = conn.execute("SELECT * FROM cached_catracas WHERE id=? AND ativa=1", (int(catraca_id),)).fetchone()
            else:
                row = conn.execute("SELECT * FROM cached_catracas WHERE ativa=1 ORDER BY id LIMIT 1").fetchone()
            if not row:
                return None
            data = dict(row)
            data["ativa"] = bool(data["ativa"])
            return data
        finally:
            conn.close()

    def queue_event(self, tipo: str, payload: dict, occurred_at: str | None = None) -> str:
        event_uuid = str(uuid.uuid4())
        now = occurred_at or _utc_now()
        conn = self.connect()
        try:
            conn.execute(
                "INSERT INTO outbox(event_uuid,tipo,payload_json,occurred_at,created_at) VALUES(?,?,?,?,?)",
                (event_uuid, str(tipo).upper()[:80], json.dumps(payload, ensure_ascii=False), now, _utc_now()),
            )
            conn.commit()
        finally:
            conn.close()
        return event_uuid

    def pending_events(self, limit: int = 50) -> list[dict]:
        conn = self.connect()
        try:
            rows = conn.execute("SELECT * FROM outbox ORDER BY id LIMIT ?", (max(1, min(int(limit), 100)),)).fetchall()
            return [
                {
                    "event_uuid": r["event_uuid"], "type": r["tipo"],
                    "payload": json.loads(r["payload_json"]), "occurred_at": r["occurred_at"],
                }
                for r in rows
            ]
        finally:
            conn.close()

    def mark_events_sent(self, event_uuids: list[str]) -> None:
        if not event_uuids:
            return
        conn = self.connect()
        try:
            conn.executemany("DELETE FROM outbox WHERE event_uuid=?", [(e,) for e in event_uuids])
            conn.commit()
        finally:
            conn.close()

    def mark_event_error(self, event_uuid: str, error: str) -> None:
        conn = self.connect()
        try:
            conn.execute(
                "UPDATE outbox SET attempts=attempts+1,last_error=? WHERE event_uuid=?",
                (str(error)[:500], event_uuid),
            )
            conn.commit()
        finally:
            conn.close()

    def queue_depth(self) -> int:
        conn = self.connect()
        try:
            return int(conn.execute("SELECT COUNT(*) FROM outbox").fetchone()[0])
        finally:
            conn.close()

    def remember_command(self, command_uuid: str, tipo: str, status: str, result: dict | None = None) -> None:
        conn = self.connect()
        try:
            conn.execute(
                """
                INSERT INTO commands_seen(command_uuid,tipo,status,result_json,processed_at) VALUES(?,?,?,?,?)
                ON CONFLICT(command_uuid) DO UPDATE SET status=excluded.status,result_json=excluded.result_json,processed_at=excluded.processed_at
                """,
                (command_uuid, tipo, status, json.dumps(result or {}, ensure_ascii=False), _utc_now()),
            )
            conn.commit()
        finally:
            conn.close()

    def get_seen_command(self, command_uuid: str) -> dict | None:
        conn = self.connect()
        try:
            row = conn.execute("SELECT * FROM commands_seen WHERE command_uuid=?", (command_uuid,)).fetchone()
            if not row:
                return None
            data = dict(row)
            try:
                data["result"] = json.loads(data.get("result_json") or "{}")
            except Exception:
                data["result"] = {}
            return data
        finally:
            conn.close()

    def command_seen(self, command_uuid: str) -> bool:
        return self.get_seen_command(command_uuid) is not None

    def cache_age_seconds(self) -> int | None:
        raw = self.get_meta("last_access_sync_at")
        if not raw:
            return None
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return max(0, int((datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds()))
        except Exception:
            return None
