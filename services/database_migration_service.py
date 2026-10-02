"""Migracao controlada do banco legado SQLite para PostgreSQL (V6.14)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import database


TABLE_ORDER = [
    "academias",
    "unidades",
    "planos",
    "configuracoes",
    "pessoas",
    "usuarios",
    "professores",
    "professor_alunos",
    "face_encodings",
    "biometric_profiles",
    "storage_objects",
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
    "agentes_locais",
    "agente_comandos",
    "agente_eventos",
    "cobrancas",
    "cobranca_eventos",
    "gateway_clientes",
    "webhook_eventos",
    "catracas",
    "logs_acesso",
    "logs_admin",
    "saas_planos",
    "saas_recursos",
    "saas_plano_recursos",
    "saas_assinaturas",
    "saas_cupons",
    "saas_site_conteudo",
    "academia_branding",
    "saas_checkouts",
    "saas_auditoria",
    "schema_meta",
]

PRIMARY_KEYS = {
    "academias": ["id"],
    "unidades": ["id"],
    "planos": ["id"],
    "configuracoes": ["chave"],
    "pessoas": ["id"],
    "usuarios": ["id"],
    "professores": ["id"],
    "professor_alunos": ["id"],
    "face_encodings": ["id"],
    "biometric_profiles": ["pessoa_id"],
    "storage_objects": ["id"],
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
    "agentes_locais": ["id"],
    "agente_comandos": ["id"],
    "agente_eventos": ["id"],
    "cobrancas": ["id"],
    "cobranca_eventos": ["id"],
    "gateway_clientes": ["pessoa_id"],
    "webhook_eventos": ["event_id"],
    "catracas": ["id"],
    "logs_acesso": ["id"],
    "logs_admin": ["id"],
    "saas_planos": ["id"],
    "saas_recursos": ["codigo"],
    "saas_plano_recursos": ["plano_id", "recurso_codigo"],
    "saas_assinaturas": ["id"],
    "saas_cupons": ["id"],
    "saas_site_conteudo": ["chave"],
    "academia_branding": ["academia_id"],
    "saas_checkouts": ["id"],
    "saas_auditoria": ["id"],
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
            for table in (
                "configuracoes", "planos", "catracas", "saas_plano_recursos", "saas_assinaturas",
                "saas_cupons", "saas_checkouts", "saas_auditoria", "academia_branding",
                "saas_site_conteudo", "saas_recursos", "saas_planos", "database_migrations", "schema_meta"
            ):
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

        # Fontes anteriores a V6.13 nao possuem contexto de academia/unidade.
        # Todo dado legado pertence a Academia Principal / Unidade Principal.
        for table in ("pessoas","usuarios","professores","catracas","agentes_locais","logs_acesso","logs_admin","storage_objects"):
            dst.execute(f"UPDATE {table} SET academia_id=1 WHERE academia_id IS NULL")
            dst.execute(f"UPDATE {table} SET unidade_id=1 WHERE unidade_id IS NULL")
        for table in ("planos","exercicios"):
            dst.execute(f"UPDATE {table} SET academia_id=1 WHERE academia_id IS NULL")

        # Fontes V6.11 ou anteriores nao possuem biometric_profiles. Como o schema
        # do destino e criado antes da copia, o backfill inicial ainda nao encontra
        # pessoas. Refazemos o preenchimento depois que pessoas/encodings chegaram.
        dst.execute(
            """
            INSERT INTO biometric_profiles(pessoa_id,version,sample_count,source_reference,status)
            SELECT p.id,1,COUNT(f.id),p.foto_path,CASE WHEN COUNT(f.id)>0 THEN 'ACTIVE' ELSE 'EMPTY' END
            FROM pessoas p LEFT JOIN face_encodings f ON f.pessoa_id=p.id
            GROUP BY p.id,p.foto_path
            ON CONFLICT(pessoa_id) DO NOTHING
            """
        )

        # Garante seeds SaaS quando a origem e anterior a V6.14; em fontes V6.14
        # os INSERT ... ON CONFLICT preservam os dados copiados.
        database._criar_schema_saas_v614(dst)

        # A fonte pode estar em schema anterior; o destino sempre termina no schema atual.
        dst.execute(
            "INSERT INTO schema_meta(chave,valor) VALUES('schema_version',?) "
            "ON CONFLICT(chave) DO UPDATE SET valor=EXCLUDED.valor",
            (str(database.SCHEMA_VERSION),),
        )
        detalhe = json.dumps({"source_schema": report.get("schema_version"), "rows": copied}, ensure_ascii=False)
        dst.execute(
            "INSERT INTO database_migrations(migration_key,origem,detalhes) VALUES(?,?,?) "
            "ON CONFLICT(migration_key) DO UPDATE SET detalhes=EXCLUDED.detalhes",
            ("sqlite-to-postgresql-v6.14", str(source_path), detalhe),
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
