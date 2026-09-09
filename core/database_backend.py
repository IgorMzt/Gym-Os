"""Adaptadores de banco do Gym OS para SQLite e PostgreSQL.

A camada publica de persistencia continua em ``database.py``. Este modulo cuida
somente da conexao/driver, mantendo a API ``conn.execute(...).fetch*`` usada
historicamente pelo projeto.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Iterable


IDENTITY_TABLES = {
    "pessoas", "face_encodings", "logs_acesso", "planos", "usuarios",
    "professores", "professor_alunos", "exercicios", "fichas_treino",
    "treinos", "treino_exercicios", "treino_sessoes", "treino_sessao_itens",
    "avaliacoes_fisicas", "aluno_acessos", "mobile_refresh_tokens",
    "mobile_push_devices", "agentes_locais", "agente_comandos", "agente_eventos",
    "logs_admin", "cobrancas", "cobranca_eventos", "catracas", "database_migrations",
}


class HybridRow(dict):
    """Linha com acesso por nome e por indice, como ``sqlite3.Row``."""

    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


@dataclass
class RuntimeDatabaseConfig:
    backend: str = "sqlite"
    sqlite_path: Path | None = None
    database_url: str = ""
    pool_min: int = 1
    pool_max: int = 8
    pool_timeout: int = 10
    timezone: str = "America/Sao_Paulo"


_config = RuntimeDatabaseConfig()
_pool = None
_pool_lock = RLock()


def configure(*, backend: str, sqlite_path: Path | None = None, database_url: str = "",
              pool_min: int = 1, pool_max: int = 8, pool_timeout: int = 10,
              timezone: str = "America/Sao_Paulo") -> None:
    global _config, _pool
    backend = str(backend or "sqlite").strip().lower()
    with _pool_lock:
        if _pool is not None:
            try:
                _pool.close()
            except Exception:
                pass
            _pool = None
        _config = RuntimeDatabaseConfig(
            backend=backend,
            sqlite_path=Path(sqlite_path) if sqlite_path is not None else None,
            database_url=str(database_url or "").strip(),
            pool_min=max(1, int(pool_min)),
            pool_max=max(1, int(pool_max)),
            pool_timeout=max(1, int(pool_timeout)),
            timezone=str(timezone or "America/Sao_Paulo"),
        )


def backend_name() -> str:
    return _config.backend


def is_postgresql() -> bool:
    return _config.backend == "postgresql"


def _load_psycopg():
    try:
        import psycopg  # type: ignore
        from psycopg_pool import ConnectionPool  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "PostgreSQL configurado, mas psycopg/psycopg_pool nao estao instalados. "
            "Execute: python -m pip install -r requirements.txt"
        ) from exc
    return psycopg, ConnectionPool


def integrity_error_types():
    try:
        psycopg, _ = _load_psycopg()
        return (sqlite3.IntegrityError, psycopg.IntegrityError)
    except RuntimeError:
        return (sqlite3.IntegrityError,)


def _hybrid_row_factory(cursor):
    descricao = cursor.description or ()
    nomes = [col.name for col in descricao]

    def make_row(values):
        if not nomes:
            return tuple(values)
        return HybridRow(zip(nomes, values))

    return make_row


def _postgres_pool():
    global _pool
    if not _config.database_url:
        raise RuntimeError("DATABASE_URL obrigatoria quando DATABASE_BACKEND=postgresql.")
    with _pool_lock:
        if _pool is None:
            psycopg, ConnectionPool = _load_psycopg()
            _pool = ConnectionPool(
                conninfo=_config.database_url,
                min_size=_config.pool_min,
                max_size=_config.pool_max,
                timeout=float(_config.pool_timeout),
                kwargs={"row_factory": _hybrid_row_factory},
                open=True,
            )
        return _pool


def _replace_qmarks(sql: str) -> str:
    """Converte placeholders qmark para psycopg sem alterar '?' dentro de strings."""
    out: list[str] = []
    in_single = False
    in_double = False
    i = 0
    while i < len(sql):
        ch = sql[i]
        if ch == "'" and not in_double:
            # SQL escapa aspas simples duplicando-as.
            if in_single and i + 1 < len(sql) and sql[i + 1] == "'":
                out.extend([ch, sql[i + 1]])
                i += 2
                continue
            in_single = not in_single
            out.append(ch)
        elif ch == '"' and not in_single:
            in_double = not in_double
            out.append(ch)
        elif ch == "?" and not in_single and not in_double:
            out.append("%s")
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def translate_postgresql_sql(sql: str) -> str:
    """Traduz o subconjunto legado de SQL SQLite usado pelo Gym OS."""
    original = str(sql)
    texto = original
    texto = re.sub(r"\s+COLLATE\s+NOCASE\b", "", texto, flags=re.I)
    texto = re.sub(r"\bBEGIN\s+IMMEDIATE\b", "BEGIN", texto, flags=re.I)
    # O schema PostgreSQL mantem timestamps como TEXT nesta versao para
    # preservar compatibilidade com o legado. Normaliza CURRENT_TIMESTAMP em DML.
    if not re.match(r"^\s*(CREATE|ALTER)\b", texto, flags=re.I):
        texto = re.sub(
            r"\bCURRENT_TIMESTAMP\b",
            "to_char(CURRENT_TIMESTAMP, 'YYYY-MM-DD HH24:MI:SS')",
            texto,
            flags=re.I,
        )

    # INSERT OR IGNORE -> INSERT ... ON CONFLICT DO NOTHING.
    if re.search(r"^\s*INSERT\s+OR\s+IGNORE\s+INTO\b", texto, flags=re.I):
        texto = re.sub(r"^\s*INSERT\s+OR\s+IGNORE\s+INTO\b", "INSERT INTO", texto, count=1, flags=re.I)
        if not re.search(r"\bON\s+CONFLICT\b", texto, flags=re.I):
            texto = texto.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"

    # O unico REPLACE historico e schema_meta.
    if re.search(r"^\s*INSERT\s+OR\s+REPLACE\s+INTO\s+schema_meta\b", texto, flags=re.I):
        texto = re.sub(r"^\s*INSERT\s+OR\s+REPLACE\s+INTO\b", "INSERT INTO", texto, count=1, flags=re.I)
        texto = texto.rstrip().rstrip(";") + " ON CONFLICT (chave) DO UPDATE SET valor=EXCLUDED.valor"

    return _replace_qmarks(texto)


def _insert_table(sql: str) -> str | None:
    m = re.match(r"^\s*INSERT\s+(?:OR\s+\w+\s+)?INTO\s+[\"']?([A-Za-z_][A-Za-z0-9_]*)", sql, re.I)
    return m.group(1).lower() if m else None


class PostgresCursor:
    def __init__(self, cursor, lastrowid=None, prefetched=None):
        self._cursor = cursor
        self.lastrowid = lastrowid
        self._prefetched = list(prefetched or [])

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def fetchone(self):
        if self._prefetched:
            return self._prefetched.pop(0)
        return self._cursor.fetchone()

    def fetchall(self):
        if self._prefetched:
            itens = self._prefetched[:]
            self._prefetched.clear()
            itens.extend(self._cursor.fetchall())
            return itens
        return self._cursor.fetchall()

    def __iter__(self):
        while self._prefetched:
            yield self._prefetched.pop(0)
        yield from self._cursor


class PostgresConnection:
    def __init__(self, pool):
        self._pool = pool
        self._conn = pool.getconn(timeout=float(_config.pool_timeout))
        # Mantem CURRENT_TIMESTAMP alinhado ao ambiente operacional sem deixar
        # uma transacao aberta antes do primeiro comando da aplicacao.
        self._conn.execute("SELECT set_config('TimeZone', %s, false)", (_config.timezone,))
        self._conn.commit()

    def execute(self, sql: str, params: Iterable[Any] | None = None):
        params = tuple(params or ())
        translated = translate_postgresql_sql(sql)
        table = _insert_table(translated)
        wants_identity = bool(table in IDENTITY_TABLES and not re.search(r"\bRETURNING\b", translated, re.I))
        if wants_identity:
            translated = translated.rstrip().rstrip(";") + " RETURNING id"
        cursor = self._conn.execute(translated, params)
        lastrowid = None
        prefetched = []
        if wants_identity:
            row = cursor.fetchone()
            if row is not None:
                prefetched.append(row)
                try:
                    lastrowid = int(row[0])
                except (TypeError, ValueError, KeyError, IndexError):
                    lastrowid = None
        return PostgresCursor(cursor, lastrowid=lastrowid, prefetched=prefetched)

    def executemany(self, sql: str, seq_of_params):
        translated = translate_postgresql_sql(sql)
        cursor = self._conn.cursor()
        cursor.executemany(translated, seq_of_params)
        return PostgresCursor(cursor)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        if self._conn is not None:
            conn, self._conn = self._conn, None
            # SELECTs tambem abrem transacao no psycopg. Devolver uma conexao
            # INTRANS faz o pool emitir warning e executar rollback por conta
            # propria. Limpamos explicitamente antes de devolve-la.
            try:
                if int(conn.info.transaction_status) != 0:
                    conn.rollback()
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
            self._pool.putconn(conn)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type:
            self.rollback()
        else:
            self.commit()
        self.close()


def connect():
    if _config.backend == "sqlite":
        if _config.sqlite_path is None:
            raise RuntimeError("Caminho SQLite nao configurado.")
        conn = sqlite3.connect(_config.sqlite_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn
    if _config.backend == "postgresql":
        return PostgresConnection(_postgres_pool())
    raise RuntimeError(f"Backend de banco nao suportado: {_config.backend}")


def close_pool() -> None:
    global _pool
    with _pool_lock:
        if _pool is not None:
            try:
                _pool.close()
            finally:
                _pool = None
