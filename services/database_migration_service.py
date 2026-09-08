"""Migracao controlada do banco legado SQLite para PostgreSQL (V6.10)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import database


TABLE_ORDER = [
    "planos",
    "configuracoes",
    "pessoas",
    "usuarios",
    "professores",
    "professor_alunos",
    "face_encodings",
    "exercicios",
    "fichas_treino",
    "treinos",
    "treino_exercicios",
    "treino_sessoes",
    "treino_sessao_itens",
    "avaliacoes_fisicas",
    "aluno_acessos",
    "mobile_refresh_tokens",
    "mobile_push_devices",
    "mobile_aluno_preferencias",
    "cobrancas",
    "cobranca_eventos",
    "gateway_clientes",
    "webhook_eventos",
    "catracas",
    "logs_acesso",
    "logs_admin",
    "schema_meta",
]

PRIMARY_KEYS = {
    "planos": ["id"],
    "configuracoes": ["chave"],
    "pessoas": ["id"],
    "usuarios": ["id"],
    "professores": ["id"],
    "professor_alunos": ["id"],
    "face_encodings": ["id"],
    "exercicios": ["id"],
    "fichas_treino": ["id"],
    "treinos": ["id"],
    "treino_exercicios": ["id"],
    "treino_sessoes": ["id"],
    "treino_sessao_itens": ["id"],
    "avaliacoes_fisicas": ["id"],
    "aluno_acessos": ["id"],
    "mobile_refresh_tokens": ["id"],
    "mobile_push_devices": ["id"],
    "mobile_aluno_preferencias": ["pessoa_id"],
    "cobrancas": ["id"],
    "cobranca_eventos": ["id"],
    "gateway_clientes": ["pessoa_id"],
    "webhook_eventos": ["event_id"],
    "catracas": ["id"],
    "logs_acesso": ["id"],
    "logs_admin": ["id"],
    "schema_meta": ["chave"],
}

BUSINESS_TABLES = [
    "pessoas", "usuarios", "professores", "logs_acesso", "cobrancas",
    "fichas_treino", "treino_sessoes", "avaliacoes_fisicas", "aluno_acessos",
]


def _sqlite_tables(conn) -> set[str]:
    return {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        if not str(row[0]).startswith("sqlite_")
    }


def _sqlite_columns(conn, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def _postgres_columns(conn, table: str) -> list[str]:
    rows = conn.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=?
        ORDER BY ordinal_position
        """,
        (table,),
    ).fetchall()
    return [str(row[0]) for row in rows]


def _target_has_business_data(conn) -> dict[str, int]:
    result: dict[str, int] = {}
    for table in BUSINESS_TABLES:
        row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        qtd = int(row[0] or 0)
        if qtd:
            result[table] = qtd
    return result


def _upsert_sql(table: str, columns: list[str]) -> str:
    pk = [col for col in PRIMARY_KEYS[table] if col in columns]
    quoted_cols = ",".join(f'"{c}"' for c in columns)
    placeholders = ",".join("?" for _ in columns)
    sql = f'INSERT INTO "{table}" ({quoted_cols}) VALUES ({placeholders})'
    if not pk:
        return sql + " ON CONFLICT DO NOTHING"
    conflict = ",".join(f'"{c}"' for c in pk)
    updates = [c for c in columns if c not in pk]
    if not updates:
        return sql + f" ON CONFLICT ({conflict}) DO NOTHING"
    set_sql = ",".join(f'"{c}"=EXCLUDED."{c}"' for c in updates)
    return sql + f" ON CONFLICT ({conflict}) DO UPDATE SET {set_sql}"


def inspect_sqlite_source(source: str | Path) -> dict:
    path = Path(source).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Banco SQLite nao encontrado: {path}")
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        quick = conn.execute("PRAGMA quick_check").fetchone()[0]
        if quick != "ok":
            raise ValueError(f"SQLite falhou no PRAGMA quick_check: {quick}")
        fk_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk_violations:
            raise ValueError(f"SQLite possui {len(fk_violations)} violacao(oes) de chave estrangeira.")
        tables = _sqlite_tables(conn)
        required = {"pessoas", "configuracoes", "logs_acesso"}
        if not required.issubset(tables):
            raise ValueError("Arquivo SQLite nao possui as tabelas obrigatorias do Gym OS.")
        counts = {}
        for table in TABLE_ORDER:
            if table in tables:
                counts[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] or 0)
        version = None
        if "schema_meta" in tables:
            row = conn.execute("SELECT valor FROM schema_meta WHERE chave='schema_version'").fetchone()
            version = row[0] if row else None
        return {
            "source": str(path),
            "quick_check": quick,
            "foreign_key_violations": 0,
            "schema_version": version,
            "tables": len(tables),
            "rows": counts,
            "total_rows": sum(counts.values()),
        }
    finally:
        conn.close()


def migrate_sqlite_to_postgresql(source: str | Path, *, allow_existing: bool = False,
                                 dry_run: bool = False) -> dict:
    if not database.is_postgresql():
        raise RuntimeError(
            "A migracao exige DATABASE_BACKEND=postgresql e DATABASE_URL apontando para o banco de destino."
        )

    report = inspect_sqlite_source(source)
    if dry_run:
        report.update({"dry_run": True, "target": "postgresql"})
        return report

    database.criar_tabelas()
    source_path = Path(source).expanduser().resolve()
    src = sqlite3.connect(f"file:{source_path.as_posix()}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    dst = database.conectar()
    copied: dict[str, int] = {}
    try:
        existing = _target_has_business_data(dst)
        if existing and not allow_existing:
            detalhe = ", ".join(f"{k}={v}" for k, v in existing.items())
            raise RuntimeError(
                "PostgreSQL de destino ja contem dados de negocio. Use um banco vazio ou repita com "
                f"--allow-existing se souber o que esta fazendo. Encontrado: {detalhe}"
            )

        # criar_tabelas() adiciona apenas seeds operacionais. Em um destino novo,
        # removemos esses seeds antes da copia para preservar exatamente os IDs
        # do SQLite e evitar conflito de UNIQUE(nome) em planos/catracas.
        if not existing and not allow_existing:
            for table in ("configuracoes", "planos", "catracas", "database_migrations", "schema_meta"):
                dst.execute(f"DELETE FROM {table}")

        source_tables = _sqlite_tables(src)
        for table in TABLE_ORDER:
            if table not in source_tables:
                continue
            source_columns = _sqlite_columns(src, table)
            target_columns = set(_postgres_columns(dst, table))
            columns = [c for c in source_columns if c in target_columns]
            if not columns:
                continue
            select_cols = ",".join(f'"{c}"' for c in columns)
            rows = src.execute(f'SELECT {select_cols} FROM "{table}"').fetchall()
            if not rows:
                copied[table] = 0
                continue
            values = [tuple(row[c] for c in columns) for row in rows]
            dst.executemany(_upsert_sql(table, columns), values)
            copied[table] = len(values)

        # A fonte pode estar em schema 19; o destino V6.10 sempre termina em 20.
        dst.execute(
            "INSERT INTO schema_meta(chave,valor) VALUES('schema_version',?) "
            "ON CONFLICT(chave) DO UPDATE SET valor=EXCLUDED.valor",
            (str(database.SCHEMA_VERSION),),
        )
        detalhe = json.dumps({"source_schema": report.get("schema_version"), "rows": copied}, ensure_ascii=False)
        dst.execute(
            "INSERT INTO database_migrations(migration_key,origem,detalhes) VALUES(?,?,?) "
            "ON CONFLICT(migration_key) DO UPDATE SET detalhes=EXCLUDED.detalhes",
            ("sqlite-to-postgresql-v6.10", str(source_path), detalhe),
        )
        database._sincronizar_sequences_postgresql(dst)
        dst.commit()
    except Exception:
        dst.rollback()
        raise
    finally:
        dst.close()
        src.close()

    return {
        "ok": True,
        "source": str(source_path),
        "source_schema": report.get("schema_version"),
        "target_schema": database.SCHEMA_VERSION,
        "target": "postgresql",
        "copied": copied,
        "total_copied": sum(copied.values()),
    }
