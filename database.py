"""Camada de persistencia do controle de acesso da academia."""

import json
import sqlite3
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

import numpy as np

DB_PATH = Path(__file__).parent / "perfis.db"
SCHEMA_VERSION = 16

DEFAULT_PLANS = [
    ("Mensal", 11990, 30, "Acesso por 30 dias."),
    ("Trimestral", 29990, 90, "Acesso por 90 dias."),
    ("Semestral", 54990, 180, "Acesso por 180 dias."),
    ("Anual", 89990, 365, "Acesso por 365 dias."),
]

DEFAULT_SETTINGS = {
    "tema_padrao": "system",
    "tempo_resultado_ms": "2800",
    "limiar_reconhecimento": "0.50",
    "intervalo_log": "5",
    "intervalo_reconhecimento_ms": "850",
    "presenca_modo": "inteligente",
    "standby_sem_presenca_ms": "30000",
    "atraso_apos_presenca_ms": "700",
    "cooldown_proxima_pessoa_ms": "1000",
    "ausencia_rearmar_ms": "1200",
    "max_espera_saida_ms": "0",
    "sensibilidade_presenca": "media",
    "liveness_ativo": "1",
    "liveness_janela_segundos": "4",
    "som_ativo": "1",
    "quantidade_amostras": "5",
    "cadastro_redirect_ms": "3000",
    "cadastro_preparacao_captura_ms": "550",
    "cadastro_intervalo_captura_ms": "450",
    "erro_recuperacao_ms": "2500",
    "intervalo_detector_presenca_ms": "500",
    "intervalo_historico_ms": "5000",
    "catraca_padrao_id": "1",
    "dias_alerta_vencimento": "7",
    "janela_presenca_minutos": "120",
    "dashboard_atualizacao_ms": "10000",
    "tolerancia_financeira_dias": "5",
}


def conectar():
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def _adicionar_coluna(conn, tabela: str, coluna: str, definicao: str):
    colunas = {row[1] for row in conn.execute(f"PRAGMA table_info({tabela})")}
    if coluna not in colunas:
        conn.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {definicao}")


def _migrar_cobrancas_para_pessoa_opcional(conn):
    """Preserva cobrancas ao remover um aluno, desvinculando pessoa_id via SET NULL."""
    existe = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='cobrancas'"
    ).fetchone()
    if not existe:
        return

    colunas = {row[1]: row for row in conn.execute("PRAGMA table_info(cobrancas)")}
    fks = list(conn.execute("PRAGMA foreign_key_list(cobrancas)"))
    pessoa_notnull = bool(colunas.get("pessoa_id") and colunas["pessoa_id"][3])
    pessoa_fk = next((row for row in fks if row[3] == "pessoa_id"), None)
    on_delete = (pessoa_fk[6] if pessoa_fk else "").upper()
    if not pessoa_notnull and on_delete == "SET NULL":
        return

    # Esta migracao precisa ocorrer fora de uma transacao para que o PRAGMA seja efetivo.
    conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            CREATE TABLE cobrancas_nova (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pessoa_id INTEGER,
                plano_id INTEGER,
                gateway TEXT NOT NULL DEFAULT 'ASAAS',
                gateway_customer_id TEXT,
                gateway_payment_id TEXT UNIQUE,
                valor_centavos INTEGER NOT NULL,
                vencimento_original TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDENTE',
                pix_payload TEXT,
                pix_qr_base64 TEXT,
                data_pagamento TEXT,
                data_criacao TEXT DEFAULT CURRENT_TIMESTAMP,
                vencimento_antes TEXT,
                vencimento_apos TEXT,
                ultimo_evento TEXT,
                data_atualizacao TEXT,
                FOREIGN KEY (pessoa_id) REFERENCES pessoas(id) ON DELETE SET NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO cobrancas_nova (
                id,pessoa_id,plano_id,gateway,gateway_customer_id,gateway_payment_id,
                valor_centavos,vencimento_original,status,pix_payload,pix_qr_base64,
                data_pagamento,data_criacao,vencimento_antes,vencimento_apos,ultimo_evento,data_atualizacao
            )
            SELECT
                id,pessoa_id,plano_id,gateway,gateway_customer_id,gateway_payment_id,
                valor_centavos,vencimento_original,status,pix_payload,pix_qr_base64,
                data_pagamento,data_criacao,vencimento_antes,vencimento_apos,ultimo_evento,data_atualizacao
            FROM cobrancas
            """
        )
        conn.execute("DROP TABLE cobrancas")
        conn.execute("ALTER TABLE cobrancas_nova RENAME TO cobrancas")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")



def _migrar_tabela_pessoa_set_null(conn, tabela: str, create_sql: str, colunas_copy: list[str]):
    """Garante que pessoa_id seja opcional e ON DELETE SET NULL, preservando histórico."""
    existe = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tabela,)
    ).fetchone()
    if not existe:
        return

    info = {row[1]: row for row in conn.execute(f"PRAGMA table_info({tabela})")}
    fks = list(conn.execute(f"PRAGMA foreign_key_list({tabela})"))
    pessoa_info = info.get("pessoa_id")
    pessoa_fk = next(
        (row for row in fks if row[2] == "pessoas" and row[3] == "pessoa_id"),
        None,
    )
    pessoa_notnull = bool(pessoa_info and pessoa_info[3])
    on_delete = (pessoa_fk[6] if pessoa_fk else "").upper()

    if pessoa_info and not pessoa_notnull and on_delete == "SET NULL":
        return

    conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF")
    tabela_nova = f"{tabela}_nova_v8"
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(f"DROP TABLE IF EXISTS {tabela_nova}")
        conn.execute(create_sql.replace("{TABLE}", tabela_nova))
        cols_existentes = [c for c in colunas_copy if c in info]
        cols = ",".join(cols_existentes)
        if cols:
            conn.execute(
                f"INSERT INTO {tabela_nova} ({cols}) SELECT {cols} FROM {tabela}"
            )
        conn.execute(f"DROP TABLE {tabela}")
        conn.execute(f"ALTER TABLE {tabela_nova} RENAME TO {tabela}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def _migrar_historicos_para_pessoa_opcional(conn):
    _migrar_tabela_pessoa_set_null(
        conn,
        "logs_acesso",
        """
        CREATE TABLE {TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pessoa_id INTEGER,
            nome TEXT,
            cpf TEXT,
            matricula TEXT,
            status TEXT,
            motivo TEXT,
            data_hora TEXT DEFAULT CURRENT_TIMESTAMP,
            catraca_id INTEGER,
            catraca_nome TEXT,
            FOREIGN KEY (pessoa_id) REFERENCES pessoas(id) ON DELETE SET NULL
        )
        """,
        [
            "id", "pessoa_id", "nome", "cpf", "matricula", "status", "motivo",
            "data_hora", "catraca_id", "catraca_nome",
        ],
    )

    _migrar_tabela_pessoa_set_null(
        conn,
        "cobranca_eventos",
        """
        CREATE TABLE {TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cobranca_id INTEGER,
            pessoa_id INTEGER,
            event_id TEXT UNIQUE,
            gateway_payment_id TEXT,
            evento TEXT NOT NULL,
            status_resultante TEXT,
            detalhes TEXT,
            data_evento TEXT,
            data_recebimento TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (cobranca_id) REFERENCES cobrancas(id) ON DELETE SET NULL,
            FOREIGN KEY (pessoa_id) REFERENCES pessoas(id) ON DELETE SET NULL
        )
        """,
        [
            "id", "cobranca_id", "pessoa_id", "event_id", "gateway_payment_id",
            "evento", "status_resultante", "detalhes", "data_evento", "data_recebimento",
        ],
    )

def criar_tabelas():
    conn = conectar()
    try:
        _migrar_cobrancas_para_pessoa_opcional(conn)
        _migrar_historicos_para_pessoa_opcional(conn)
        # WAL melhora concorrencia entre leituras e gravacoes de varias catracas.
        conn.execute("PRAGMA journal_mode = WAL")
        # Repara referências históricas órfãs deixadas por exclusões de versões antigas.
        for tabela in ("logs_acesso", "cobrancas", "cobranca_eventos"):
            existe = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tabela,)).fetchone()
            if existe:
                colunas = {row[1] for row in conn.execute(f"PRAGMA table_info({tabela})")}
                if "pessoa_id" in colunas:
                    conn.execute(
                        f"UPDATE {tabela} SET pessoa_id=NULL WHERE pessoa_id IS NOT NULL "
                        "AND NOT EXISTS (SELECT 1 FROM pessoas p WHERE p.id=" + tabela + ".pessoa_id)"
                    )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pessoas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                encoding TEXT,
                liberado INTEGER DEFAULT 1,
                data_cadastro TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        for coluna, definicao in [
            ("cpf", "TEXT"),
            ("data_nascimento", "TEXT"),
            ("sexo", "TEXT"),
            ("telefone", "TEXT"),
            ("email", "TEXT"),
            ("matricula", "TEXT"),
            ("plano", "TEXT"),
            ("plano_id", "INTEGER"),
            ("data_inicio", "TEXT"),
            ("data_vencimento", "TEXT"),
            ("status_financeiro", "TEXT DEFAULT 'EM_DIA'"),
            ("observacoes", "TEXT"),
            ("foto_path", "TEXT"),
        ]:
            _adicionar_coluna(conn, "pessoas", coluna, definicao)

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS face_encodings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pessoa_id INTEGER NOT NULL,
                encoding TEXT NOT NULL,
                ordem INTEGER NOT NULL DEFAULT 1,
                data_cadastro TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (pessoa_id) REFERENCES pessoas(id) ON DELETE CASCADE,
                UNIQUE(pessoa_id, ordem)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS logs_acesso (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pessoa_id INTEGER,
                nome TEXT,
                cpf TEXT,
                matricula TEXT,
                status TEXT,
                motivo TEXT,
                data_hora TEXT DEFAULT CURRENT_TIMESTAMP,
                catraca_id INTEGER,
                catraca_nome TEXT,
                FOREIGN KEY (pessoa_id) REFERENCES pessoas(id) ON DELETE SET NULL
            )
            """
        )
        for coluna, definicao in [
            ("pessoa_id", "INTEGER"),
            ("cpf", "TEXT"),
            ("matricula", "TEXT"),
            ("motivo", "TEXT"),
            ("catraca_id", "INTEGER"),
            ("catraca_nome", "TEXT"),
        ]:
            _adicionar_coluna(conn, "logs_acesso", coluna, definicao)

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS planos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL UNIQUE,
                valor_centavos INTEGER NOT NULL DEFAULT 0,
                duracao_dias INTEGER NOT NULL,
                descricao TEXT,
                ativo INTEGER NOT NULL DEFAULT 1,
                data_cadastro TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS configuracoes (
                chave TEXT PRIMARY KEY,
                valor TEXT NOT NULL,
                data_atualizacao TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                login TEXT NOT NULL UNIQUE COLLATE NOCASE,
                nome TEXT NOT NULL,
                senha_hash TEXT NOT NULL,
                papel TEXT NOT NULL CHECK (papel IN ('ADMIN','RECEPCAO','PROFESSOR')),
                ativo INTEGER NOT NULL DEFAULT 1,
                origem TEXT NOT NULL DEFAULT 'LOCAL',
                ultimo_login TEXT,
                data_criacao TEXT DEFAULT CURRENT_TIMESTAMP,
                data_atualizacao TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_usuarios_papel_ativo ON usuarios(papel, ativo)")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS professores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER UNIQUE,
                nome TEXT NOT NULL,
                cpf TEXT UNIQUE,
                cref TEXT UNIQUE,
                telefone TEXT,
                email TEXT,
                especialidade TEXT,
                foto_path TEXT,
                observacoes TEXT,
                ativo INTEGER NOT NULL DEFAULT 1,
                data_criacao TEXT DEFAULT CURRENT_TIMESTAMP,
                data_atualizacao TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_professores_ativo_nome ON professores(ativo, nome)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS professor_alunos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                professor_id INTEGER NOT NULL,
                pessoa_id INTEGER NOT NULL,
                principal INTEGER NOT NULL DEFAULT 1,
                ativo INTEGER NOT NULL DEFAULT 1,
                data_vinculo TEXT DEFAULT CURRENT_TIMESTAMP,
                data_atualizacao TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (professor_id) REFERENCES professores(id) ON DELETE CASCADE,
                FOREIGN KEY (pessoa_id) REFERENCES pessoas(id) ON DELETE CASCADE,
                UNIQUE(professor_id, pessoa_id)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_professor_alunos_professor ON professor_alunos(professor_id, ativo)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_professor_alunos_pessoa ON professor_alunos(pessoa_id, ativo)")
        # Um aluno só pode ter um professor ativo.
        duplicados = conn.execute("""
            SELECT pessoa_id FROM professor_alunos WHERE ativo=1
            GROUP BY pessoa_id HAVING COUNT(*)>1
        """).fetchall()
        for dup in duplicados:
            manter = conn.execute("""
                SELECT id FROM professor_alunos
                WHERE pessoa_id=? AND ativo=1 ORDER BY id DESC LIMIT 1
            """,(dup["pessoa_id"],)).fetchone()
            if manter:
                conn.execute("""
                    UPDATE professor_alunos
                    SET ativo=0, data_atualizacao=CURRENT_TIMESTAMP
                    WHERE pessoa_id=? AND ativo=1 AND id<>?
                """,(dup["pessoa_id"],manter["id"]))
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_professor_alunos_um_ativo
            ON professor_alunos(pessoa_id) WHERE ativo=1
        """)

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS exercicios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL UNIQUE COLLATE NOCASE,
                grupo_muscular TEXT NOT NULL,
                equipamento TEXT,
                tipo TEXT NOT NULL DEFAULT 'FORCA'
                    CHECK (tipo IN ('FORCA','CARDIO','MOBILIDADE','ALONGAMENTO','OUTRO')),
                dificuldade TEXT
                    CHECK (dificuldade IS NULL OR dificuldade IN ('INICIANTE','INTERMEDIARIO','AVANCADO')),
                instrucoes TEXT,
                observacoes TEXT,
                imagem_path TEXT,
                video_url TEXT,
                ativo INTEGER NOT NULL DEFAULT 1,
                criado_por_usuario_id INTEGER,
                data_criacao TEXT DEFAULT CURRENT_TIMESTAMP,
                data_atualizacao TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (criado_por_usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_exercicios_grupo_ativo ON exercicios(grupo_muscular, ativo)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_exercicios_tipo_ativo ON exercicios(tipo, ativo)")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fichas_treino (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pessoa_id INTEGER NOT NULL,
                professor_id INTEGER,
                nome TEXT NOT NULL,
                objetivo TEXT,
                observacoes TEXT,
                ativo INTEGER NOT NULL DEFAULT 1,
                data_inicio TEXT,
                data_fim TEXT,
                criado_por_usuario_id INTEGER,
                data_criacao TEXT DEFAULT CURRENT_TIMESTAMP,
                data_atualizacao TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (pessoa_id) REFERENCES pessoas(id) ON DELETE CASCADE,
                FOREIGN KEY (professor_id) REFERENCES professores(id) ON DELETE SET NULL,
                FOREIGN KEY (criado_por_usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fichas_pessoa_ativo ON fichas_treino(pessoa_id, ativo)")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS treinos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ficha_id INTEGER NOT NULL,
                nome TEXT NOT NULL,
                ordem INTEGER NOT NULL DEFAULT 1,
                observacoes TEXT,
                FOREIGN KEY (ficha_id) REFERENCES fichas_treino(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_treinos_ficha_ordem ON treinos(ficha_id, ordem)")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS treino_exercicios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                treino_id INTEGER NOT NULL,
                exercicio_id INTEGER NOT NULL,
                ordem INTEGER NOT NULL DEFAULT 1,
                series INTEGER,
                repeticoes TEXT,
                carga TEXT,
                descanso_segundos INTEGER,
                observacoes TEXT,
                FOREIGN KEY (treino_id) REFERENCES treinos(id) ON DELETE CASCADE,
                FOREIGN KEY (exercicio_id) REFERENCES exercicios(id) ON DELETE RESTRICT
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_treino_exercicios_ordem ON treino_exercicios(treino_id, ordem)")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS treino_sessoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pessoa_id INTEGER NOT NULL,
                ficha_id INTEGER NOT NULL,
                treino_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'EM_ANDAMENTO'
                    CHECK (status IN ('EM_ANDAMENTO','CONCLUIDO','CANCELADO')),
                iniciado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                finalizado_em TEXT,
                duracao_segundos INTEGER,
                observacoes TEXT,
                iniciado_por_usuario_id INTEGER,
                origem TEXT NOT NULL DEFAULT 'PAINEL'
                    CHECK (origem IN ('PAINEL','ALUNO_APP')),
                FOREIGN KEY (pessoa_id) REFERENCES pessoas(id) ON DELETE CASCADE,
                FOREIGN KEY (ficha_id) REFERENCES fichas_treino(id) ON DELETE RESTRICT,
                FOREIGN KEY (treino_id) REFERENCES treinos(id) ON DELETE RESTRICT,
                FOREIGN KEY (iniciado_por_usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_treino_sessoes_pessoa_data ON treino_sessoes(pessoa_id, iniciado_em DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_treino_sessoes_status ON treino_sessoes(status, iniciado_em DESC)")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS treino_sessao_itens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sessao_id INTEGER NOT NULL,
                treino_exercicio_id INTEGER,
                exercicio_id INTEGER,
                ordem INTEGER NOT NULL,
                exercicio_nome TEXT NOT NULL,
                grupo_muscular TEXT,
                series_planejadas INTEGER,
                repeticoes_planejadas TEXT,
                carga_planejada TEXT,
                descanso_planejado INTEGER,
                observacoes_planejadas TEXT,
                concluido INTEGER NOT NULL DEFAULT 0,
                series_realizadas INTEGER,
                repeticoes_realizadas TEXT,
                carga_realizada TEXT,
                observacoes_execucao TEXT,
                concluido_em TEXT,
                FOREIGN KEY (sessao_id) REFERENCES treino_sessoes(id) ON DELETE CASCADE,
                FOREIGN KEY (treino_exercicio_id) REFERENCES treino_exercicios(id) ON DELETE SET NULL,
                FOREIGN KEY (exercicio_id) REFERENCES exercicios(id) ON DELETE SET NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_treino_sessao_itens_sessao_ordem ON treino_sessao_itens(sessao_id, ordem)")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS avaliacoes_fisicas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pessoa_id INTEGER NOT NULL,
                professor_id INTEGER,
                data_avaliacao TEXT NOT NULL,
                peso_kg REAL,
                altura_cm REAL,
                imc REAL,
                gordura_percentual REAL,
                massa_gorda_kg REAL,
                massa_magra_kg REAL,
                braco_cm REAL,
                antebraco_cm REAL,
                torax_cm REAL,
                cintura_cm REAL,
                abdomen_cm REAL,
                quadril_cm REAL,
                coxa_cm REAL,
                panturrilha_cm REAL,
                observacoes TEXT,
                foto_frontal_path TEXT,
                foto_lateral_path TEXT,
                foto_costas_path TEXT,
                criado_por_usuario_id INTEGER,
                data_criacao TEXT DEFAULT CURRENT_TIMESTAMP,
                data_atualizacao TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (pessoa_id) REFERENCES pessoas(id) ON DELETE CASCADE,
                FOREIGN KEY (professor_id) REFERENCES professores(id) ON DELETE SET NULL,
                FOREIGN KEY (criado_por_usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_avaliacoes_pessoa_data ON avaliacoes_fisicas(pessoa_id, data_avaliacao DESC, id DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_avaliacoes_professor_data ON avaliacoes_fisicas(professor_id, data_avaliacao DESC)")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS aluno_acessos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pessoa_id INTEGER NOT NULL UNIQUE,
                login TEXT NOT NULL UNIQUE COLLATE NOCASE,
                senha_hash TEXT NOT NULL,
                ativo INTEGER NOT NULL DEFAULT 1,
                ultimo_login TEXT,
                data_criacao TEXT DEFAULT CURRENT_TIMESTAMP,
                data_atualizacao TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (pessoa_id) REFERENCES pessoas(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_aluno_acessos_ativo ON aluno_acessos(ativo, pessoa_id)")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS logs_admin (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                acao TEXT NOT NULL,
                alvo TEXT,
                detalhes TEXT,
                ip TEXT,
                data_hora TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_meta (
                chave TEXT PRIMARY KEY,
                valor TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT OR REPLACE INTO schema_meta (chave, valor) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cobrancas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pessoa_id INTEGER,
                plano_id INTEGER,
                gateway TEXT NOT NULL DEFAULT 'ASAAS',
                gateway_customer_id TEXT,
                gateway_payment_id TEXT UNIQUE,
                valor_centavos INTEGER NOT NULL,
                vencimento_original TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDENTE',
                pix_payload TEXT,
                pix_qr_base64 TEXT,
                data_pagamento TEXT,
                data_criacao TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (pessoa_id) REFERENCES pessoas(id) ON DELETE SET NULL
            )
            """
        )
        for coluna, definicao in [
            ("vencimento_antes", "TEXT"),
            ("vencimento_apos", "TEXT"),
            ("ultimo_evento", "TEXT"),
            ("data_atualizacao", "TEXT"),
        ]:
            _adicionar_coluna(conn, "cobrancas", coluna, definicao)

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cobranca_eventos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cobranca_id INTEGER,
                pessoa_id INTEGER,
                event_id TEXT UNIQUE,
                gateway_payment_id TEXT,
                evento TEXT NOT NULL,
                status_resultante TEXT,
                detalhes TEXT,
                data_evento TEXT,
                data_recebimento TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (cobranca_id) REFERENCES cobrancas(id) ON DELETE SET NULL,
                FOREIGN KEY (pessoa_id) REFERENCES pessoas(id) ON DELETE SET NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS gateway_clientes (
                pessoa_id INTEGER PRIMARY KEY,
                gateway TEXT NOT NULL DEFAULT 'ASAAS',
                gateway_customer_id TEXT NOT NULL,
                data_criacao TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (pessoa_id) REFERENCES pessoas(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS webhook_eventos (
                event_id TEXT PRIMARY KEY,
                gateway TEXT NOT NULL,
                evento TEXT,
                data_recebimento TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        for coluna, definicao in [
            ("payment_id", "TEXT"),
            ("processado", "INTEGER NOT NULL DEFAULT 0"),
            ("erro", "TEXT"),
            ("data_processamento", "TEXT"),
        ]:
            _adicionar_coluna(conn, "webhook_eventos", coluna, definicao)

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS catracas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                local TEXT,
                modo TEXT NOT NULL DEFAULT 'SIMULADA',
                endpoint TEXT,
                ativa INTEGER NOT NULL DEFAULT 1,
                data_cadastro TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_pessoas_cpf ON pessoas(cpf) WHERE cpf IS NOT NULL")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_pessoas_matricula ON pessoas(matricula) WHERE matricula IS NOT NULL")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_data_hora ON logs_acesso(data_hora DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_pessoa ON logs_acesso(pessoa_id, data_hora DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_status ON logs_acesso(status, data_hora DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cobrancas_pessoa ON cobrancas(pessoa_id, id DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cobrancas_status ON cobrancas(status, vencimento_original)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cobranca_eventos_pessoa ON cobranca_eventos(pessoa_id, id DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_webhook_eventos_payment ON webhook_eventos(payment_id, data_recebimento DESC)")

        # Migra o encoding antigo para a tabela de amostras.
        antigos = conn.execute(
            "SELECT id, encoding FROM pessoas WHERE encoding IS NOT NULL AND TRIM(encoding) <> ''"
        ).fetchall()
        for pessoa in antigos:
            existe = conn.execute(
                "SELECT 1 FROM face_encodings WHERE pessoa_id = ? LIMIT 1", (pessoa[0],)
            ).fetchone()
            if not existe:
                conn.execute(
                    "INSERT INTO face_encodings (pessoa_id, encoding, ordem) VALUES (?, ?, 1)",
                    (pessoa[0], pessoa[1]),
                )

        sem_matricula = conn.execute(
            "SELECT id FROM pessoas WHERE matricula IS NULL OR TRIM(matricula) = '' ORDER BY id"
        ).fetchall()
        for pessoa in sem_matricula:
            conn.execute("UPDATE pessoas SET matricula = ? WHERE id = ?", (f"LEGACY-{pessoa[0]:05d}", pessoa[0]))

        # Vincula nomes de planos existentes quando houver correspondencia exata.
        for plano in conn.execute("SELECT id, nome FROM planos").fetchall():
            conn.execute(
                "UPDATE pessoas SET plano_id = ? WHERE plano = ? AND (plano_id IS NULL OR plano_id = '')",
                (plano[0], plano[1]),
            )

        # Vincula logs antigos somente quando existe exatamente um cadastro com o nome.
        conn.execute(
            """
            UPDATE logs_acesso
            SET pessoa_id = (SELECT MIN(p.id) FROM pessoas p WHERE p.nome = logs_acesso.nome),
                cpf = COALESCE(cpf, (SELECT MIN(p.cpf) FROM pessoas p WHERE p.nome = logs_acesso.nome)),
                matricula = COALESCE(matricula, (SELECT MIN(p.matricula) FROM pessoas p WHERE p.nome = logs_acesso.nome))
            WHERE pessoa_id IS NULL AND nome IS NOT NULL
              AND (SELECT COUNT(*) FROM pessoas p WHERE p.nome = logs_acesso.nome) = 1
            """
        )

        # Defaults de planos/configuracoes/catraca.
        for nome, valor, dias, descricao in DEFAULT_PLANS:
            conn.execute(
                "INSERT OR IGNORE INTO planos (nome, valor_centavos, duracao_dias, descricao, ativo) VALUES (?, ?, ?, ?, 1)",
                (nome, valor, dias, descricao),
            )
        # Agora que os planos padrao existem, conclui a associacao dos cadastros legados.
        conn.execute(
            """
            UPDATE pessoas
            SET plano_id = (SELECT p.id FROM planos p WHERE p.nome = pessoas.plano LIMIT 1)
            WHERE (plano_id IS NULL OR plano_id = '')
              AND plano IS NOT NULL
              AND EXISTS (SELECT 1 FROM planos p WHERE p.nome = pessoas.plano)
            """
        )
        for chave, valor in DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO configuracoes (chave, valor) VALUES (?, ?)", (chave, valor)
            )
        conn.execute(
            "INSERT OR IGNORE INTO catracas (id, nome, local, modo, ativa) VALUES (1, 'Catraca 01 - Entrada', 'Entrada principal', 'SIMULADA', 1)"
        )
        # Se a configuracao aponta para uma catraca inexistente, aponta para a primeira ativa.
        row = conn.execute("SELECT valor FROM configuracoes WHERE chave = 'catraca_padrao_id'").fetchone()
        if not row or not row[0] or not conn.execute("SELECT 1 FROM catracas WHERE id = ?", (row[0],)).fetchone():
            primeira = conn.execute("SELECT id FROM catracas WHERE ativa = 1 ORDER BY id LIMIT 1").fetchone()
            if primeira:
                conn.execute(
                    "INSERT INTO configuracoes (chave, valor) VALUES ('catraca_padrao_id', ?) "
                    "ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor, data_atualizacao=CURRENT_TIMESTAMP",
                    (str(primeira[0]),),
                )

        # Status financeiro para cadastros antigos.
        conn.execute("UPDATE pessoas SET status_financeiro = 'EM_DIA' WHERE status_financeiro IS NULL OR TRIM(status_financeiro) = ''")
        conn.commit()
    finally:
        conn.close()


def _encoding_para_json(encoding: np.ndarray) -> str:
    return json.dumps(np.asarray(encoding, dtype=float).tolist())


def _encoding_de_json(encoding_json: str) -> np.ndarray:
    return np.array(json.loads(encoding_json), dtype=float)


def adicionar_pessoa(dados, encodings=None, foto_path=None, liberado=True):
    if isinstance(dados, str):
        nome = dados.strip()
        if not nome:
            raise ValueError("Nome invalido.")
        encoding_unico = encodings
        encodings = [encoding_unico] if isinstance(encoding_unico, np.ndarray) else list(encoding_unico or [])
        dados = {
            "nome": nome, "cpf": None, "data_nascimento": None, "sexo": None,
            "telefone": None, "email": None, "matricula": gerar_proxima_matricula(),
            "plano": "Nao informado", "plano_id": None, "data_inicio": None,
            "data_vencimento": None, "status_financeiro": "EM_DIA",
            "observacoes": "Cadastro realizado pelo modo de terminal", "liberado": liberado,
        }
    else:
        encodings = list(encodings or [])
    if not encodings:
        raise ValueError("Ao menos uma amostra facial e necessaria.")

    conn = conectar()
    try:
        primeiro_encoding = _encoding_para_json(encodings[0])
        cur = conn.execute(
            """
            INSERT INTO pessoas (
                nome, encoding, liberado, cpf, data_nascimento, sexo, telefone, email,
                matricula, plano, plano_id, data_inicio, data_vencimento,
                status_financeiro, observacoes, foto_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dados["nome"], primeiro_encoding, int(bool(dados.get("liberado", True))),
                dados.get("cpf"), dados.get("data_nascimento"), dados.get("sexo"),
                dados.get("telefone"), dados.get("email"), dados["matricula"],
                dados.get("plano"), dados.get("plano_id"), dados.get("data_inicio"),
                dados.get("data_vencimento"), dados.get("status_financeiro", "EM_DIA"),
                dados.get("observacoes"), foto_path,
            ),
        )
        pessoa_id = int(cur.lastrowid)
        conn.executemany(
            "INSERT INTO face_encodings (pessoa_id, encoding, ordem) VALUES (?, ?, ?)",
            [(pessoa_id, _encoding_para_json(enc), ordem) for ordem, enc in enumerate(encodings, 1)],
        )
        conn.commit()
        return pessoa_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def atualizar_pessoa(pessoa_id: int, dados: dict):
    conn = conectar()
    try:
        conn.execute(
            """
            UPDATE pessoas SET nome=?, cpf=?, data_nascimento=?, sexo=?, telefone=?, email=?,
                matricula=?, plano=?, plano_id=?, data_inicio=?, data_vencimento=?,
                status_financeiro=?, observacoes=?, liberado=? WHERE id=?
            """,
            (
                dados["nome"], dados["cpf"], dados.get("data_nascimento") or None,
                dados.get("sexo") or None, dados.get("telefone") or None,
                dados.get("email") or None, dados["matricula"], dados.get("plano"),
                dados.get("plano_id"), dados.get("data_inicio") or None,
                dados.get("data_vencimento") or None, dados.get("status_financeiro", "EM_DIA"),
                dados.get("observacoes") or None, int(bool(dados.get("liberado", True))), pessoa_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def atualizar_amostras_e_foto(pessoa_id: int, encodings: Iterable[np.ndarray] | None = None, foto_path: str | None = None):
    conn = conectar()
    try:
        if foto_path is not None:
            conn.execute("UPDATE pessoas SET foto_path = ? WHERE id = ?", (foto_path, pessoa_id))
        if encodings is not None:
            encodings = list(encodings)
            conn.execute("DELETE FROM face_encodings WHERE pessoa_id = ?", (pessoa_id,))
            conn.executemany(
                "INSERT INTO face_encodings (pessoa_id, encoding, ordem) VALUES (?, ?, ?)",
                [(pessoa_id, _encoding_para_json(enc), ordem) for ordem, enc in enumerate(encodings, 1)],
            )
            if encodings:
                conn.execute("UPDATE pessoas SET encoding = ? WHERE id = ?", (_encoding_para_json(encodings[0]), pessoa_id))
        conn.commit()
    finally:
        conn.close()


def _row_pessoa(row):
    if row is None:
        return None
    return {
        "id": row["id"], "nome": row["nome"],
        "encoding": _encoding_de_json(row["encoding"]) if row["encoding"] else None,
        "liberado": bool(row["liberado"]), "data_cadastro": row["data_cadastro"],
        "cpf": row["cpf"], "data_nascimento": row["data_nascimento"], "sexo": row["sexo"],
        "telefone": row["telefone"], "email": row["email"], "matricula": row["matricula"],
        "plano": row["plano"], "plano_id": row["plano_id"], "data_inicio": row["data_inicio"],
        "data_vencimento": row["data_vencimento"], "status_financeiro": row["status_financeiro"],
        "observacoes": row["observacoes"], "foto_path": row["foto_path"],
    }


def listar_pessoas():
    conn = conectar()
    try:
        rows = conn.execute(
            """
            SELECT id,nome,encoding,liberado,data_cadastro,cpf,data_nascimento,sexo,telefone,email,
                   matricula,plano,plano_id,data_inicio,data_vencimento,status_financeiro,observacoes,foto_path
            FROM pessoas ORDER BY nome COLLATE NOCASE
            """
        ).fetchall()
        return [_row_pessoa(row) for row in rows]
    finally:
        conn.close()


def listar_pessoas_com_ultimo_acesso():
    conn = conectar()
    try:
        rows = conn.execute(
            """
            SELECT p.id,p.nome,p.cpf,p.matricula,p.plano,p.plano_id,p.data_vencimento,p.status_financeiro,
                   p.liberado,p.foto_path,
                   (SELECT l.data_hora FROM logs_acesso l WHERE l.pessoa_id=p.id ORDER BY l.id DESC LIMIT 1) AS ultimo_acesso
            FROM pessoas p ORDER BY p.nome COLLATE NOCASE
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def obter_pessoa(pessoa_id: int):
    conn = conectar()
    try:
        row = conn.execute(
            """
            SELECT id,nome,encoding,liberado,data_cadastro,cpf,data_nascimento,sexo,telefone,email,
                   matricula,plano,plano_id,data_inicio,data_vencimento,status_financeiro,observacoes,foto_path
            FROM pessoas WHERE id=?
            """, (pessoa_id,)
        ).fetchone()
        return _row_pessoa(row) if row else None
    finally:
        conn.close()


def listar_amostras_faciais():
    conn = conectar()
    try:
        rows = conn.execute("SELECT pessoa_id,encoding FROM face_encodings ORDER BY pessoa_id,ordem").fetchall()
        por_pessoa: dict[int, list[np.ndarray]] = {}
        for row in rows:
            por_pessoa.setdefault(int(row["pessoa_id"]), []).append(_encoding_de_json(row["encoding"]))
        return por_pessoa
    finally:
        conn.close()


def atualizar_liberacao(pessoa_id: int, liberado: bool) -> bool:
    conn = conectar()
    try:
        cur = conn.execute("UPDATE pessoas SET liberado=? WHERE id=?", (int(liberado), pessoa_id))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def remover_pessoa(pessoa_id: int) -> bool:
    """Remove o cadastro sem apagar históricos financeiros/de acesso."""
    conn = conectar()
    try:
        conn.execute("BEGIN IMMEDIATE")

        # Históricos são preservados e apenas perdem o vínculo com o cadastro removido.
        for tabela in ("logs_acesso", "cobrancas", "cobranca_eventos"):
            existe = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tabela,)
            ).fetchone()
            if existe:
                colunas = {row[1] for row in conn.execute(f"PRAGMA table_info({tabela})")}
                if "pessoa_id" in colunas:
                    conn.execute(
                        f"UPDATE {tabela} SET pessoa_id=NULL WHERE pessoa_id=?",
                        (pessoa_id,),
                    )

        # Dados dependentes sem utilidade sem o aluno podem ser apagados.
        for tabela in ("face_encodings", "gateway_clientes"):
            existe = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tabela,)
            ).fetchone()
            if existe:
                conn.execute(f"DELETE FROM {tabela} WHERE pessoa_id=?", (pessoa_id,))

        cur = conn.execute("DELETE FROM pessoas WHERE id=?", (pessoa_id,))
        conn.commit()
        return cur.rowcount > 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def listar_planos(ativos_apenas=False):
    conn = conectar()
    try:
        sql = "SELECT id,nome,valor_centavos,duracao_dias,descricao,ativo,data_cadastro FROM planos"
        if ativos_apenas:
            sql += " WHERE ativo=1"
        sql += " ORDER BY duracao_dias"
        return [dict(row) for row in conn.execute(sql).fetchall()]
    finally:
        conn.close()


def obter_plano(plano_id: int):
    conn = conectar()
    try:
        row = conn.execute("SELECT id,nome,valor_centavos,duracao_dias,descricao,ativo,data_cadastro FROM planos WHERE id=?", (plano_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def obter_plano_por_nome(nome: str):
    conn = conectar()
    try:
        row = conn.execute("SELECT id,nome,valor_centavos,duracao_dias,descricao,ativo FROM planos WHERE nome=?", (nome,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def salvar_plano(dados: dict, plano_id: int | None = None):
    conn = conectar()
    try:
        if plano_id:
            conn.execute(
                "UPDATE planos SET nome=?,valor_centavos=?,duracao_dias=?,descricao=?,ativo=? WHERE id=?",
                (dados["nome"], dados["valor_centavos"], dados["duracao_dias"], dados.get("descricao"), int(bool(dados.get("ativo", True))), plano_id),
            )
        else:
            cur = conn.execute(
                "INSERT INTO planos (nome,valor_centavos,duracao_dias,descricao,ativo) VALUES (?,?,?,?,?)",
                (dados["nome"], dados["valor_centavos"], dados["duracao_dias"], dados.get("descricao"), int(bool(dados.get("ativo", True)))),
            )
            plano_id = int(cur.lastrowid)
        conn.commit()
        return plano_id
    finally:
        conn.close()


def atualizar_status_plano(pessoa_id: int, status: str):
    status = status if status in {"EM_DIA", "PENDENTE", "VENCIDO"} else "EM_DIA"
    conn = conectar()
    try:
        conn.execute("UPDATE pessoas SET status_financeiro=? WHERE id=?", (status, pessoa_id))
        conn.commit()
    finally:
        conn.close()


def status_financeiro_efetivo(pessoa: dict) -> str:
    vencimento = pessoa.get("data_vencimento")
    tolerancia = int(obter_configuracao("tolerancia_financeira_dias", "5") or 5)
    if vencimento:
        try:
            if date.fromisoformat(vencimento) + timedelta(days=max(0, tolerancia)) < date.today():
                return "VENCIDO"
        except ValueError:
            return "VENCIDO"
    return pessoa.get("status_financeiro") or "EM_DIA"


def acesso_permitido(pessoa: dict) -> tuple[bool, str]:
    if not pessoa.get("liberado", False):
        return False, "Acesso bloqueado manualmente"
    status_financeiro = status_financeiro_efetivo(pessoa)
    if status_financeiro == "PENDENTE":
        vencimento = pessoa.get("data_vencimento")
        tolerancia = max(0, int(obter_configuracao("tolerancia_financeira_dias", "5") or 5))
        if vencimento:
            try:
                limite = date.fromisoformat(vencimento) + timedelta(days=tolerancia)
                if date.today() <= limite:
                    restantes = max(0, (limite - date.today()).days)
                    return True, f"Pagamento pendente dentro da tolerancia ({restantes} dia(s))"
            except ValueError:
                pass
        return False, "Pagamento pendente"
    if status_financeiro == "VENCIDO":
        return False, "Plano vencido"
    if not pessoa.get("data_vencimento"):
        return False, "Plano sem vencimento"
    return True, "Plano ativo e mensalidade em dia"


def renovar_plano(pessoa_id: int, plano_id: int | None = None):
    pessoa = obter_pessoa(pessoa_id)
    if not pessoa:
        raise ValueError("Aluno nao encontrado.")
    plano = obter_plano(plano_id) if plano_id else None
    if not plano:
        plano = obter_plano(pessoa.get("plano_id")) if pessoa.get("plano_id") else obter_plano_por_nome(pessoa.get("plano") or "")
    if not plano or not plano.get("ativo"):
        raise ValueError("Plano ativo nao encontrado.")
    hoje = date.today()
    try:
        venc = date.fromisoformat(pessoa.get("data_vencimento")) if pessoa.get("data_vencimento") else hoje
    except ValueError:
        venc = hoje
    # A renovação sempre parte do vencimento atual.
    base = venc
    novo_vencimento = base + timedelta(days=int(plano["duracao_dias"]))
    conn = conectar()
    try:
        conn.execute(
            "UPDATE pessoas SET plano=?, plano_id=?, data_vencimento=?, status_financeiro='EM_DIA' WHERE id=?",
            (plano["nome"], plano["id"], novo_vencimento.isoformat(), pessoa_id),
        )
        conn.commit()
    finally:
        conn.close()
    return novo_vencimento.isoformat()


def registrar_log(pessoa_id, nome, status, motivo, cpf=None, matricula=None, janela_segundos=5, catraca_id=None, catraca_nome=None) -> bool:
    conn = conectar()
    try:
        if pessoa_id is not None:
            repetido = conn.execute(
                """
                SELECT 1 FROM logs_acesso WHERE pessoa_id=? AND status=?
                  AND COALESCE(catraca_id,0)=COALESCE(?,0)
                  AND data_hora >= datetime('now', ?) ORDER BY id DESC LIMIT 1
                """, (pessoa_id, status, catraca_id, f"-{janela_segundos} seconds")
            ).fetchone()
        else:
            repetido = conn.execute(
                """
                SELECT 1 FROM logs_acesso WHERE pessoa_id IS NULL AND nome=? AND status=?
                  AND COALESCE(catraca_id,0)=COALESCE(?,0)
                  AND data_hora >= datetime('now', ?) ORDER BY id DESC LIMIT 1
                """, (nome, status, catraca_id, f"-{janela_segundos} seconds")
            ).fetchone()
        if repetido:
            return False
        conn.execute(
            "INSERT INTO logs_acesso (pessoa_id,nome,cpf,matricula,status,motivo,catraca_id,catraca_nome) VALUES (?,?,?,?,?,?,?,?)",
            (pessoa_id, nome, cpf, matricula, status, motivo, catraca_id, catraca_nome),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def listar_logs(limite=50, filtros=None):
    filtros = filtros or {}
    conn = conectar()
    try:
        where, params = [], []
        if filtros.get("data_inicio"):
            where.append("date(data_hora) >= date(?)"); params.append(filtros["data_inicio"])
        if filtros.get("data_fim"):
            where.append("date(data_hora) <= date(?)"); params.append(filtros["data_fim"])
        if filtros.get("status"):
            where.append("status=?"); params.append(filtros["status"])
        if filtros.get("termo"):
            termo = f"%{filtros['termo']}%"
            where.append("(nome LIKE ? OR cpf LIKE ? OR matricula LIKE ?)"); params.extend([termo, termo, termo])
        if filtros.get("catraca_id"):
            where.append("catraca_id=?"); params.append(int(filtros["catraca_id"]))
        sql = "SELECT id,pessoa_id,nome,cpf,matricula,status,motivo,data_hora,catraca_id,catraca_nome FROM logs_acesso"
        if where: sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY id DESC LIMIT ?"; params.append(int(limite))
        return [dict(row) for row in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()



def listar_logs_pessoa(pessoa_id: int, limite=20):
    conn = conectar()
    try:
        rows = conn.execute(
            """
            SELECT id,pessoa_id,nome,cpf,matricula,status,motivo,data_hora,catraca_id,catraca_nome
            FROM logs_acesso
            WHERE pessoa_id=?
            ORDER BY id DESC
            LIMIT ?
            """,
            (int(pessoa_id), int(limite)),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

def listar_logs_publicos(limite=8):
    conn = conectar()
    try:
        rows = conn.execute("SELECT nome,status,motivo,data_hora FROM logs_acesso ORDER BY id DESC LIMIT ?", (limite,)).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def contar_pessoas():
    pessoas = listar_pessoas(); total = len(pessoas)
    liberados = sum(1 for pessoa in pessoas if acesso_permitido(pessoa)[0])
    return total, liberados, total - liberados


def dashboard():
    hoje = date.today().isoformat()
    pessoas = listar_pessoas()
    total = len(pessoas)
    ativos = sum(1 for p in pessoas if acesso_permitido(p)[0])
    bloqueados = total - ativos
    conn = conectar()
    try:
        row = conn.execute(
            "SELECT COUNT(*) total, SUM(CASE WHEN status='LIBERADO' THEN 1 ELSE 0 END) liberados, "
            "SUM(CASE WHEN status='BLOQUEADO' THEN 1 ELSE 0 END) bloqueados, SUM(CASE WHEN status='NEGADO' THEN 1 ELSE 0 END) negados "
            "FROM logs_acesso WHERE date(data_hora)=date(?)", (hoje,)
        ).fetchone()
        acessos_hoje = int(row["total"] or 0)
        liberados_hoje = int(row["liberados"] or 0)
        bloqueados_hoje = int(row["bloqueados"] or 0)
        negados_hoje = int(row["negados"] or 0)
        horarios = [0] * 24
        for r in conn.execute("SELECT CAST(strftime('%H', data_hora) AS INTEGER) h, COUNT(*) n FROM logs_acesso WHERE datetime(data_hora) >= datetime('now','-24 hours') GROUP BY h").fetchall():
            horarios[int(r["h"])] = int(r["n"])
        vencendo = conn.execute(
            "SELECT id,nome,matricula,plano,data_vencimento FROM pessoas WHERE data_vencimento IS NOT NULL AND date(data_vencimento) BETWEEN date(?) AND date(?, '+7 day') ORDER BY date(data_vencimento),nome",
            (hoje, hoje),
        ).fetchall()
        ultimos = conn.execute("SELECT nome,status,motivo,data_hora,catraca_nome FROM logs_acesso ORDER BY id DESC LIMIT 10").fetchall()
        alunos_acessos = conn.execute(
            """
            SELECT p.id,p.nome,p.matricula,p.plano,p.data_vencimento,p.liberado,
                   (SELECT l.data_hora FROM logs_acesso l WHERE l.pessoa_id=p.id ORDER BY l.id DESC LIMIT 1) AS ultimo_acesso
            FROM pessoas p
            ORDER BY CASE WHEN ultimo_acesso IS NULL THEN 1 ELSE 0 END, ultimo_acesso DESC, p.nome COLLATE NOCASE
            LIMIT 8
            """
        ).fetchall()
        pico = max(horarios, default=0) or 1
        horarios_chart = [
            {"hora": h, "rotulo": f"{h:02d}h", "quantidade": n, "percentual": round((n / pico) * 100, 1)}
            for h, n in enumerate(horarios)
        ]
        return {
            "total": total, "ativos": ativos, "bloqueados": bloqueados,
            "acessos_hoje": acessos_hoje, "liberados_hoje": liberados_hoje,
            "bloqueados_hoje": bloqueados_hoje, "negados_hoje": negados_hoje,
            "horarios": horarios, "horarios_chart": horarios_chart, "vencendo": [dict(r) for r in vencendo],
            "ultimos": [dict(r) for r in ultimos], "alunos_acessos": [dict(r) for r in alunos_acessos],
        }
    finally:
        conn.close()


def cpf_existe(cpf, ignorar_id=None):
    conn = conectar()
    try:
        if ignorar_id is None:
            row = conn.execute("SELECT 1 FROM pessoas WHERE cpf=? LIMIT 1", (cpf,)).fetchone()
        else:
            row = conn.execute("SELECT 1 FROM pessoas WHERE cpf=? AND id<>? LIMIT 1", (cpf, ignorar_id)).fetchone()
        return row is not None
    finally:
        conn.close()


def matricula_existe(matricula, ignorar_id=None):
    conn = conectar()
    try:
        if ignorar_id is None:
            row = conn.execute("SELECT 1 FROM pessoas WHERE matricula=? LIMIT 1", (matricula,)).fetchone()
        else:
            row = conn.execute("SELECT 1 FROM pessoas WHERE matricula=? AND id<>? LIMIT 1", (matricula, ignorar_id)).fetchone()
        return row is not None
    finally:
        conn.close()


def gerar_proxima_matricula():
    """Gera matrícula não sequencial de 6 caracteres para novos alunos."""
    import secrets, string
    alfabeto = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    for _ in range(100):
        candidata = "".join(secrets.choice(alfabeto) for _ in range(6))
        if not matricula_existe(candidata):
            return candidata
    raise RuntimeError("Não foi possível gerar uma matrícula única.")


def obter_pessoa_por_primeiro_acesso(cpf: str, matricula: str, data_nascimento: str):
    conn = conectar()
    try:
        row = conn.execute(
            """SELECT * FROM pessoas
               WHERE cpf=? AND UPPER(TRIM(matricula))=UPPER(TRIM(?))
                 AND data_nascimento=? LIMIT 1""",
            (cpf, matricula, data_nascimento),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def obter_acesso_aluno_por_cpf(cpf: str):
    conn = conectar()
    try:
        row = conn.execute(
            """SELECT aa.*,p.nome,p.matricula,p.foto_path,p.cpf
               FROM aluno_acessos aa JOIN pessoas p ON p.id=aa.pessoa_id
               WHERE p.cpf=? LIMIT 1""", (cpf,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def buscar_alunos_global(termo: str, limite=8):
    q = (termo or "").strip()
    if len(q) < 2:
        return []
    like = f"%{q}%"
    conn = conectar()
    try:
        return [dict(r) for r in conn.execute(
            """SELECT id,nome,cpf,matricula,plano,data_vencimento,foto_path
               FROM pessoas
               WHERE nome LIKE ? COLLATE NOCASE OR cpf LIKE ? OR matricula LIKE ? COLLATE NOCASE
               ORDER BY CASE WHEN matricula=? COLLATE NOCASE THEN 0 ELSE 1 END,nome COLLATE NOCASE
               LIMIT ?""", (like,like,like,q,int(limite))
        ).fetchall()]
    finally:
        conn.close()


def listar_catracas(apenas_ativas=False):
    conn = conectar()
    try:
        sql = "SELECT id,nome,local,modo,endpoint,ativa,data_cadastro FROM catracas"
        if apenas_ativas: sql += " WHERE ativa=1"
        sql += " ORDER BY id"
        return [dict(r) for r in conn.execute(sql).fetchall()]
    finally:
        conn.close()


def obter_catraca(catraca_id: int):
    conn = conectar()
    try:
        row = conn.execute("SELECT id,nome,local,modo,endpoint,ativa,data_cadastro FROM catracas WHERE id=?", (catraca_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def salvar_catraca(dados: dict, catraca_id=None):
    conn = conectar()
    try:
        if catraca_id:
            conn.execute("UPDATE catracas SET nome=?,local=?,modo=?,endpoint=?,ativa=? WHERE id=?", (dados["nome"],dados.get("local"),dados.get("modo","SIMULADA"),dados.get("endpoint"),int(bool(dados.get("ativa",True))),catraca_id))
        else:
            cur = conn.execute(
                "INSERT INTO catracas (nome,local,modo,endpoint,ativa) VALUES (?,?,?,?,?)",
                (dados["nome"], dados.get("local"), dados.get("modo", "SIMULADA"), dados.get("endpoint"), int(bool(dados.get("ativa", True)))),
            )
            catraca_id = cur.lastrowid
        conn.commit(); return int(catraca_id)
    finally:
        conn.close()


def obter_configuracoes():
    conn=conectar()
    try: return {r["chave"]: r["valor"] for r in conn.execute("SELECT chave,valor FROM configuracoes").fetchall()}
    finally: conn.close()


def obter_configuracao(chave, padrao=None):
    conn=conectar()
    try:
        row=conn.execute("SELECT valor FROM configuracoes WHERE chave=?", (chave,)).fetchone()
        return row[0] if row else padrao
    finally: conn.close()


def salvar_configuracoes(dados: dict):
    conn=conectar()
    try:
        for chave, valor in dados.items():
            conn.execute("INSERT INTO configuracoes (chave,valor,data_atualizacao) VALUES (?,?,CURRENT_TIMESTAMP) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor,data_atualizacao=CURRENT_TIMESTAMP", (chave,str(valor)))
        conn.commit()
    finally: conn.close()


criar_tabelas()


def registrar_log_admin(acao: str, alvo=None, detalhes=None, ip=None):
    conn = conectar()
    try:
        conn.execute(
            "INSERT INTO logs_admin (acao, alvo, detalhes, ip) VALUES (?, ?, ?, ?)",
            (str(acao)[:80], str(alvo)[:160] if alvo else None,
             str(detalhes)[:1000] if detalhes else None, str(ip)[:80] if ip else None),
        )
        conn.commit()
    finally:
        conn.close()


def listar_logs_admin(limite=100):
    conn = conectar()
    try:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM logs_admin ORDER BY id DESC LIMIT ?", (max(1, min(int(limite), 500)),)
        ).fetchall()]
    finally:
        conn.close()


def verificar_integridade():
    conn = conectar()
    try:
        quick = conn.execute("PRAGMA quick_check").fetchone()[0]
        fk = [dict(r) for r in conn.execute("PRAGMA foreign_key_check").fetchall()]
        versao = conn.execute(
            "SELECT valor FROM schema_meta WHERE chave='schema_version'"
        ).fetchone()
        return {
            "ok": quick == "ok" and not fk,
            "quick_check": quick,
            "foreign_keys": len(fk),
            "schema_version": versao[0] if versao else "1",
            "tamanho_bytes": DB_PATH.stat().st_size if DB_PATH.exists() else 0,
        }
    finally:
        conn.close()


def criar_backup(destino):
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    origem = conectar()
    copia = sqlite3.connect(destino)
    try:
        origem.backup(copia)
        copia.commit()
    finally:
        copia.close()
        origem.close()
    return destino


def restaurar_backup(origem):
    origem = Path(origem)
    teste = sqlite3.connect(origem)
    try:
        check = teste.execute("PRAGMA quick_check").fetchone()[0]
        tabelas = {r[0] for r in teste.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        obrigatorias = {"pessoas", "logs_acesso", "configuracoes"}
        if check != "ok" or not obrigatorias.issubset(tabelas):
            raise ValueError("O arquivo não é um backup válido deste sistema.")
    finally:
        teste.close()

    # SQLite backup API evita copiar um banco parcialmente aberto.
    fonte = sqlite3.connect(origem)
    destino = conectar()
    try:
        fonte.backup(destino)
        destino.commit()
    finally:
        destino.close()
        fonte.close()
    criar_tabelas()


def obter_gateway_cliente(pessoa_id):
    conn = conectar()
    try:
        r = conn.execute(
            "SELECT gateway_customer_id FROM gateway_clientes WHERE pessoa_id=? AND gateway='ASAAS'",
            (pessoa_id,),
        ).fetchone()
        return r[0] if r else None
    finally:
        conn.close()


def salvar_gateway_cliente(pessoa_id, customer_id):
    conn = conectar()
    try:
        conn.execute(
            """
            INSERT INTO gateway_clientes(pessoa_id,gateway,gateway_customer_id)
            VALUES(?,'ASAAS',?)
            ON CONFLICT(pessoa_id) DO UPDATE SET gateway_customer_id=excluded.gateway_customer_id
            """,
            (pessoa_id, customer_id),
        )
        conn.commit()
    finally:
        conn.close()


def criar_cobranca_local(pessoa_id, plano_id, payment_id, customer_id, valor_centavos, vencimento, pix_payload, pix_qr_base64):
    conn = conectar()
    try:
        cur = conn.execute(
            """
            INSERT INTO cobrancas(
                pessoa_id,plano_id,gateway,gateway_payment_id,gateway_customer_id,
                valor_centavos,vencimento_original,status,pix_payload,pix_qr_base64,
                ultimo_evento,data_atualizacao
            ) VALUES(?,?,'ASAAS',?,?,?,?, 'PENDENTE',?,?, 'PAYMENT_CREATED', CURRENT_TIMESTAMP)
            """,
            (pessoa_id, plano_id, payment_id, customer_id, valor_centavos, vencimento, pix_payload, pix_qr_base64),
        )
        conn.execute("UPDATE pessoas SET status_financeiro='PENDENTE' WHERE id=?", (pessoa_id,))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def listar_cobrancas_pessoa(pessoa_id, limite=20):
    conn = conectar()
    try:
        return [
            dict(r) for r in conn.execute(
                "SELECT * FROM cobrancas WHERE pessoa_id=? ORDER BY id DESC LIMIT ?",
                (pessoa_id, limite),
            ).fetchall()
        ]
    finally:
        conn.close()


def obter_cobranca_gateway(payment_id):
    conn = conectar()
    try:
        r = conn.execute("SELECT * FROM cobrancas WHERE gateway_payment_id=?", (payment_id,)).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def obter_cobranca_aberta(pessoa_id, vencimento=None):
    conn = conectar()
    try:
        sql = "SELECT * FROM cobrancas WHERE pessoa_id=? AND status IN ('PENDENTE','VENCIDO')"
        args = [pessoa_id]
        if vencimento:
            sql += " AND vencimento_original=?"
            args.append(vencimento)
        sql += " ORDER BY id DESC LIMIT 1"
        r = conn.execute(sql, tuple(args)).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def registrar_evento_webhook(event_id, evento, payment_id=None):
    """Reserva um evento para processamento idempotente.

    Eventos já concluídos retornam False. Eventos previamente recebidos mas que
    falharam continuam elegíveis para retry, evitando perder webhook após 500.
    """
    conn = conectar()
    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO webhook_eventos(event_id,gateway,evento,payment_id,processado)
            VALUES(?,'ASAAS',?,?,0)
            """,
            (event_id, evento, payment_id),
        )
        conn.execute(
            "UPDATE webhook_eventos SET evento=?, payment_id=COALESCE(?,payment_id) WHERE event_id=?",
            (evento, payment_id, event_id),
        )
        row = conn.execute("SELECT processado FROM webhook_eventos WHERE event_id=?", (event_id,)).fetchone()
        conn.commit()
        return bool(row is not None and not int(row[0] or 0))
    finally:
        conn.close()


def concluir_evento_webhook(event_id):
    conn = conectar()
    try:
        conn.execute(
            "UPDATE webhook_eventos SET processado=1, erro=NULL, data_processamento=CURRENT_TIMESTAMP WHERE event_id=?",
            (event_id,),
        )
        conn.commit()
    finally:
        conn.close()


def falhar_evento_webhook(event_id, erro):
    conn = conectar()
    try:
        conn.execute(
            "UPDATE webhook_eventos SET processado=0, erro=? WHERE event_id=?",
            (str(erro)[:1000], event_id),
        )
        conn.commit()
    finally:
        conn.close()


def _registrar_evento_financeiro(cobranca, event_id, evento, status_resultante=None, detalhes=None, data_evento=None):
    conn = conectar()
    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO cobranca_eventos(
                cobranca_id,pessoa_id,event_id,gateway_payment_id,evento,status_resultante,detalhes,data_evento
            ) VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                cobranca.get("id") if cobranca else None,
                cobranca.get("pessoa_id") if cobranca else None,
                event_id,
                cobranca.get("gateway_payment_id") if cobranca else None,
                evento,
                status_resultante,
                detalhes,
                data_evento,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def listar_eventos_financeiros_pessoa(pessoa_id, limite=40):
    conn = conectar()
    try:
        return [
            dict(r) for r in conn.execute(
                """
                SELECT * FROM cobranca_eventos
                WHERE pessoa_id=? ORDER BY id DESC LIMIT ?
                """,
                (pessoa_id, limite),
            ).fetchall()
        ]
    finally:
        conn.close()


def confirmar_cobranca(payment_id, data_pagamento=None, event_id=None, evento="PAYMENT_RECEIVED"):
    cobranca = obter_cobranca_gateway(payment_id)
    if not cobranca:
        return None
    if cobranca["status"] == "PAGO":
        if event_id:
            _registrar_evento_financeiro(cobranca, event_id, evento, "PAGO", "Pagamento já processado.", data_pagamento)
        return cobranca

    pessoa = obter_pessoa(cobranca["pessoa_id"])
    vencimento_antes = pessoa.get("data_vencimento") if pessoa else None
    novo = renovar_plano(cobranca["pessoa_id"], cobranca["plano_id"])
    conn = conectar()
    try:
        conn.execute(
            """
            UPDATE cobrancas
            SET status='PAGO', data_pagamento=?, vencimento_antes=?, vencimento_apos=?,
                ultimo_evento=?, data_atualizacao=CURRENT_TIMESTAMP
            WHERE gateway_payment_id=?
            """,
            (data_pagamento or datetime.now().isoformat(timespec='seconds'), vencimento_antes, novo, evento, payment_id),
        )
        conn.execute("UPDATE pessoas SET status_financeiro='EM_DIA' WHERE id=?", (cobranca["pessoa_id"],))
        conn.commit()
    finally:
        conn.close()
    cobranca = obter_cobranca_gateway(payment_id)
    if event_id:
        _registrar_evento_financeiro(cobranca, event_id, evento, "PAGO", f"Plano renovado até {novo}.", data_pagamento)
    cobranca["novo_vencimento"] = novo
    return cobranca


def marcar_cobranca_vencida(payment_id, event_id=None, data_evento=None):
    cobranca = obter_cobranca_gateway(payment_id)
    if not cobranca:
        return None
    if cobranca["status"] not in {"PAGO", "ESTORNADO", "CANCELADO"}:
        conn = conectar()
        try:
            conn.execute(
                "UPDATE cobrancas SET status='VENCIDO', ultimo_evento='PAYMENT_OVERDUE', data_atualizacao=CURRENT_TIMESTAMP WHERE gateway_payment_id=?",
                (payment_id,),
            )
            # Mantém PENDENTE no cadastro: o bloqueio só ocorre após a tolerância local.
            conn.execute("UPDATE pessoas SET status_financeiro='PENDENTE' WHERE id=?", (cobranca["pessoa_id"],))
            conn.commit()
        finally:
            conn.close()
    cobranca = obter_cobranca_gateway(payment_id)
    if event_id:
        _registrar_evento_financeiro(cobranca, event_id, "PAYMENT_OVERDUE", cobranca["status"], "Cobrança vencida no gateway; tolerância local continua válida.", data_evento)
    return cobranca


def cancelar_cobranca(payment_id, event_id=None, data_evento=None):
    cobranca = obter_cobranca_gateway(payment_id)
    if not cobranca:
        return None
    if cobranca["status"] != "PAGO":
        conn = conectar()
        try:
            conn.execute(
                "UPDATE cobrancas SET status='CANCELADO', ultimo_evento='PAYMENT_DELETED', data_atualizacao=CURRENT_TIMESTAMP WHERE gateway_payment_id=?",
                (payment_id,),
            )
            outra = conn.execute(
                "SELECT 1 FROM cobrancas WHERE pessoa_id=? AND gateway_payment_id<>? AND status IN ('PENDENTE','VENCIDO') LIMIT 1",
                (cobranca["pessoa_id"], payment_id),
            ).fetchone()
            if not outra:
                conn.execute("UPDATE pessoas SET status_financeiro='EM_DIA' WHERE id=?", (cobranca["pessoa_id"],))
            conn.commit()
        finally:
            conn.close()
    cobranca = obter_cobranca_gateway(payment_id)
    if event_id:
        _registrar_evento_financeiro(cobranca, event_id, "PAYMENT_DELETED", cobranca["status"], "Cobrança removida/cancelada no gateway.", data_evento)
    return cobranca


def estornar_cobranca(payment_id, event_id=None, data_evento=None):
    cobranca = obter_cobranca_gateway(payment_id)
    if not cobranca:
        return None
    rollback = False
    if cobranca["status"] == "PAGO":
        pessoa = obter_pessoa(cobranca["pessoa_id"])
        if pessoa and cobranca.get("vencimento_apos") and pessoa.get("data_vencimento") == cobranca.get("vencimento_apos"):
            conn = conectar()
            try:
                conn.execute(
                    "UPDATE pessoas SET data_vencimento=?, status_financeiro='PENDENTE' WHERE id=?",
                    (cobranca.get("vencimento_antes"), cobranca["pessoa_id"]),
                )
                conn.commit()
                rollback = True
            finally:
                conn.close()
    conn = conectar()
    try:
        conn.execute(
            "UPDATE cobrancas SET status='ESTORNADO', ultimo_evento='PAYMENT_REFUNDED', data_atualizacao=CURRENT_TIMESTAMP WHERE gateway_payment_id=?",
            (payment_id,),
        )
        conn.commit()
    finally:
        conn.close()
    cobranca = obter_cobranca_gateway(payment_id)
    detalhe = "Estorno confirmado; vencimento revertido com segurança." if rollback else "Estorno confirmado; vencimento não revertido porque houve alteração posterior ou não havia renovação registrada."
    if event_id:
        _registrar_evento_financeiro(cobranca, event_id, "PAYMENT_REFUNDED", "ESTORNADO", detalhe, data_evento)
    return cobranca


def registrar_evento_cobranca_sem_acao(payment_id, event_id, evento, data_evento=None):
    cobranca = obter_cobranca_gateway(payment_id) if payment_id else None
    if cobranca:
        conn = conectar()
        try:
            conn.execute(
                "UPDATE cobrancas SET ultimo_evento=?, data_atualizacao=CURRENT_TIMESTAMP WHERE gateway_payment_id=?",
                (evento, payment_id),
            )
            conn.commit()
        finally:
            conn.close()
        cobranca = obter_cobranca_gateway(payment_id)
    _registrar_evento_financeiro(cobranca, event_id, evento, cobranca.get("status") if cobranca else None, "Evento recebido sem mudança de estado local.", data_evento)
    return cobranca



# ---------- Usuários e autenticação ----------

def garantir_usuario_bootstrap(login: str, nome: str, senha_hash: str):
    conn = conectar()
    try:
        existente = conn.execute("SELECT * FROM usuarios WHERE origem='ENV' ORDER BY id LIMIT 1").fetchone()
        if existente:
            conn.execute(
                "UPDATE usuarios SET login=?, nome=?, senha_hash=?, papel='ADMIN', ativo=1, data_atualizacao=CURRENT_TIMESTAMP WHERE id=?",
                (login, nome, senha_hash, existente["id"]),
            )
            uid = existente["id"]
        else:
            por_login = conn.execute("SELECT * FROM usuarios WHERE login=? COLLATE NOCASE", (login,)).fetchone()
            if por_login:
                # Nao sobrescreve uma conta local existente; apenas garante que haja um admin ativo.
                uid = por_login["id"]
            else:
                cur = conn.execute(
                    "INSERT INTO usuarios (login,nome,senha_hash,papel,ativo,origem) VALUES (?,?,?,'ADMIN',1,'ENV')",
                    (login, nome, senha_hash),
                )
                uid = cur.lastrowid
        conn.commit()
        return uid
    finally:
        conn.close()

def obter_usuario_por_login(login: str):
    conn = conectar()
    try:
        row = conn.execute("SELECT * FROM usuarios WHERE login=? COLLATE NOCASE LIMIT 1", (login,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def obter_usuario(usuario_id: int):
    conn = conectar()
    try:
        row = conn.execute("SELECT * FROM usuarios WHERE id=?", (usuario_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def listar_usuarios():
    conn = conectar()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM usuarios ORDER BY ativo DESC, nome COLLATE NOCASE, id").fetchall()]
    finally:
        conn.close()

def criar_usuario(login: str, nome: str, senha_hash: str, papel: str, ativo: bool = True):
    conn = conectar()
    try:
        cur = conn.execute(
            "INSERT INTO usuarios (login,nome,senha_hash,papel,ativo,origem) VALUES (?,?,?,?,?,'LOCAL')",
            (login, nome, senha_hash, papel, 1 if ativo else 0),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()

def atualizar_usuario(usuario_id: int, login: str, nome: str, papel: str, ativo: bool):
    conn = conectar()
    try:
        cur = conn.execute(
            "UPDATE usuarios SET login=?, nome=?, papel=?, ativo=?, data_atualizacao=CURRENT_TIMESTAMP WHERE id=? AND origem<>'ENV'",
            (login, nome, papel, 1 if ativo else 0, usuario_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()

def atualizar_senha_usuario(usuario_id: int, senha_hash: str):
    conn = conectar()
    try:
        cur = conn.execute(
            "UPDATE usuarios SET senha_hash=?, data_atualizacao=CURRENT_TIMESTAMP WHERE id=? AND origem<>'ENV'",
            (senha_hash, usuario_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()

def atualizar_ultimo_login(usuario_id: int):
    conn = conectar()
    try:
        conn.execute("UPDATE usuarios SET ultimo_login=CURRENT_TIMESTAMP WHERE id=?", (usuario_id,))
        conn.commit()
    finally:
        conn.close()

def contar_admins_ativos(excluir_id=None):
    conn = conectar()
    try:
        if excluir_id is None:
            row = conn.execute("SELECT COUNT(*) FROM usuarios WHERE papel='ADMIN' AND ativo=1").fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) FROM usuarios WHERE papel='ADMIN' AND ativo=1 AND id<>?", (excluir_id,)).fetchone()
        return int(row[0])
    finally:
        conn.close()


# ---------- Professores e vínculos ----------

def listar_professores():
    conn = conectar()
    try:
        rows = conn.execute(
            """
            SELECT pr.*,
                   u.login AS usuario_login,
                   u.ativo AS usuario_ativo,
                   (SELECT COUNT(*) FROM professor_alunos pa
                    WHERE pa.professor_id=pr.id AND pa.ativo=1) AS total_alunos
            FROM professores pr
            LEFT JOIN usuarios u ON u.id=pr.usuario_id
            ORDER BY pr.ativo DESC, pr.nome COLLATE NOCASE, pr.id
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def obter_professor(professor_id: int):
    conn = conectar()
    try:
        row = conn.execute(
            """
            SELECT pr.*, u.login AS usuario_login, u.ativo AS usuario_ativo
            FROM professores pr
            LEFT JOIN usuarios u ON u.id=pr.usuario_id
            WHERE pr.id=?
            """, (professor_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def obter_professor_por_usuario(usuario_id: int):
    conn = conectar()
    try:
        row = conn.execute(
            """
            SELECT pr.*, u.login AS usuario_login, u.ativo AS usuario_ativo
            FROM professores pr
            JOIN usuarios u ON u.id=pr.usuario_id
            WHERE pr.usuario_id=? LIMIT 1
            """, (usuario_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def criar_professor(dados: dict):
    conn = conectar()
    try:
        cur = conn.execute(
            """
            INSERT INTO professores
                (usuario_id,nome,cpf,cref,telefone,email,especialidade,foto_path,observacoes,ativo)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                dados.get("usuario_id"), dados["nome"], dados.get("cpf"), dados.get("cref"),
                dados.get("telefone"), dados.get("email"), dados.get("especialidade"),
                dados.get("foto_path"), dados.get("observacoes"), 1 if dados.get("ativo", True) else 0,
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def atualizar_professor(professor_id: int, dados: dict):
    conn = conectar()
    try:
        cur = conn.execute(
            """
            UPDATE professores SET
                usuario_id=?, nome=?, cpf=?, cref=?, telefone=?, email=?, especialidade=?,
                foto_path=?, observacoes=?, ativo=?, data_atualizacao=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (
                dados.get("usuario_id"), dados["nome"], dados.get("cpf"), dados.get("cref"),
                dados.get("telefone"), dados.get("email"), dados.get("especialidade"),
                dados.get("foto_path"), dados.get("observacoes"), 1 if dados.get("ativo", True) else 0,
                professor_id,
            ),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def usuario_professor_disponivel(usuario_id: int, ignorar_professor_id=None):
    conn = conectar()
    try:
        usuario = conn.execute(
            "SELECT id,papel,ativo FROM usuarios WHERE id=?", (usuario_id,)
        ).fetchone()
        if not usuario or usuario["papel"] != "PROFESSOR":
            return False
        sql = "SELECT id FROM professores WHERE usuario_id=?"
        params = [usuario_id]
        if ignorar_professor_id is not None:
            sql += " AND id<>?"
            params.append(ignorar_professor_id)
        return conn.execute(sql, params).fetchone() is None
    finally:
        conn.close()


def listar_usuarios_professor():
    conn = conectar()
    try:
        return [dict(r) for r in conn.execute(
            """
            SELECT u.id,u.nome,u.login,u.ativo,
                   pr.id AS professor_id
            FROM usuarios u
            LEFT JOIN professores pr ON pr.usuario_id=u.id
            WHERE u.papel='PROFESSOR'
            ORDER BY u.ativo DESC,u.nome COLLATE NOCASE
            """
        ).fetchall()]
    finally:
        conn.close()


def vincular_aluno_professor(professor_id: int, pessoa_id: int):
    conn = conectar()
    try:
        if not conn.execute("SELECT 1 FROM professores WHERE id=? AND ativo=1", (professor_id,)).fetchone():
            raise ValueError("Professor não encontrado ou inativo.")
        if not conn.execute("SELECT 1 FROM pessoas WHERE id=?", (pessoa_id,)).fetchone():
            raise ValueError("Aluno não encontrado.")
        conn.execute(
            """
            INSERT INTO professor_alunos (professor_id,pessoa_id,principal,ativo)
            VALUES (?,?,1,1)
            ON CONFLICT(professor_id,pessoa_id) DO UPDATE SET
                ativo=1, data_atualizacao=CURRENT_TIMESTAMP
            """, (professor_id,pessoa_id)
        )
        conn.commit()
        return True
    finally:
        conn.close()


def desvincular_aluno_professor(professor_id: int, pessoa_id: int):
    conn = conectar()
    try:
        cur = conn.execute(
            "UPDATE professor_alunos SET ativo=0,data_atualizacao=CURRENT_TIMESTAMP WHERE professor_id=? AND pessoa_id=?",
            (professor_id,pessoa_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def listar_alunos_professor(professor_id: int, somente_ativos=True):
    conn = conectar()
    try:
        filtro = "AND pa.ativo=1" if somente_ativos else ""
        rows = conn.execute(
            f"""
            SELECT p.id,p.nome,p.cpf,p.matricula,p.telefone,p.email,p.foto_path,p.liberado,
                   p.data_inicio,p.data_vencimento,p.plano,p.observacoes,
                   pa.principal,pa.data_vinculo,
                   (SELECT l.data_hora FROM logs_acesso l WHERE l.pessoa_id=p.id ORDER BY l.id DESC LIMIT 1) AS ultimo_acesso
            FROM professor_alunos pa
            JOIN pessoas p ON p.id=pa.pessoa_id
            WHERE pa.professor_id=? {filtro}
            ORDER BY p.nome COLLATE NOCASE
            """, (professor_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def professor_tem_aluno(professor_id: int, pessoa_id: int):
    conn = conectar()
    try:
        return conn.execute(
            "SELECT 1 FROM professor_alunos WHERE professor_id=? AND pessoa_id=? AND ativo=1",
            (professor_id,pessoa_id),
        ).fetchone() is not None
    finally:
        conn.close()


def listar_professores_aluno(pessoa_id: int):
    conn = conectar()
    try:
        return [dict(r) for r in conn.execute(
            """
            SELECT pr.id,pr.nome,pr.cref,pr.especialidade,pr.foto_path,pa.principal,pa.data_vinculo
            FROM professor_alunos pa
            JOIN professores pr ON pr.id=pa.professor_id
            WHERE pa.pessoa_id=? AND pa.ativo=1 AND pr.ativo=1
            ORDER BY pa.principal DESC,pr.nome COLLATE NOCASE
            """, (pessoa_id,)
        ).fetchall()]
    finally:
        conn.close()


# ---------- Banco de exercícios ----------

def listar_exercicios():
    conn = conectar()
    try:
        rows = conn.execute(
            """
            SELECT e.*,
                   u.nome AS criado_por_nome,
                   u.login AS criado_por_login
            FROM exercicios e
            LEFT JOIN usuarios u ON u.id=e.criado_por_usuario_id
            ORDER BY e.ativo DESC, e.grupo_muscular COLLATE NOCASE, e.nome COLLATE NOCASE
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def obter_exercicio(exercicio_id: int):
    conn = conectar()
    try:
        row = conn.execute(
            """
            SELECT e.*,
                   u.nome AS criado_por_nome,
                   u.login AS criado_por_login
            FROM exercicios e
            LEFT JOIN usuarios u ON u.id=e.criado_por_usuario_id
            WHERE e.id=?
            """,
            (exercicio_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def criar_exercicio(dados: dict, usuario_id=None):
    conn = conectar()
    try:
        cur = conn.execute(
            """
            INSERT INTO exercicios
                (nome,grupo_muscular,equipamento,tipo,dificuldade,instrucoes,
                 observacoes,imagem_path,video_url,ativo,criado_por_usuario_id)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                dados["nome"], dados["grupo_muscular"], dados.get("equipamento"),
                dados.get("tipo") or "FORCA", dados.get("dificuldade"),
                dados.get("instrucoes"), dados.get("observacoes"),
                dados.get("imagem_path"), dados.get("video_url"),
                1 if dados.get("ativo", True) else 0, usuario_id,
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def atualizar_exercicio(exercicio_id: int, dados: dict):
    conn = conectar()
    try:
        cur = conn.execute(
            """
            UPDATE exercicios SET
                nome=?, grupo_muscular=?, equipamento=?, tipo=?, dificuldade=?,
                instrucoes=?, observacoes=?, imagem_path=?, video_url=?, ativo=?,
                data_atualizacao=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (
                dados["nome"], dados["grupo_muscular"], dados.get("equipamento"),
                dados.get("tipo") or "FORCA", dados.get("dificuldade"),
                dados.get("instrucoes"), dados.get("observacoes"),
                dados.get("imagem_path"), dados.get("video_url"),
                1 if dados.get("ativo", True) else 0, exercicio_id,
            ),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def estatisticas_exercicios():
    conn = conectar()
    try:
        row = conn.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN ativo=1 THEN 1 ELSE 0 END) AS ativos,
                   COUNT(DISTINCT CASE WHEN ativo=1 THEN grupo_muscular END) AS grupos,
                   COUNT(DISTINCT CASE WHEN ativo=1 AND equipamento IS NOT NULL AND TRIM(equipamento)<>'' THEN equipamento END) AS equipamentos
            FROM exercicios
            """
        ).fetchone()
        return {
            "total": int(row["total"] or 0),
            "ativos": int(row["ativos"] or 0),
            "grupos": int(row["grupos"] or 0),
            "equipamentos": int(row["equipamentos"] or 0),
        }
    finally:
        conn.close()


# ---------- Fichas de treino ----------

def listar_fichas_treino(pessoa_id=None):
    conn = conectar()
    try:
        sql = """
            SELECT f.*, p.nome AS aluno_nome, pr.nome AS professor_nome
            FROM fichas_treino f
            JOIN pessoas p ON p.id=f.pessoa_id
            LEFT JOIN professores pr ON pr.id=f.professor_id
        """
        params = []
        if pessoa_id is not None:
            sql += " WHERE f.pessoa_id=?"
            params.append(pessoa_id)
        sql += " ORDER BY f.ativo DESC, f.data_criacao DESC, f.id DESC"
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def obter_ficha_treino(ficha_id: int):
    conn = conectar()
    try:
        ficha = conn.execute(
            """
            SELECT f.*, p.nome AS aluno_nome, pr.nome AS professor_nome
            FROM fichas_treino f
            JOIN pessoas p ON p.id=f.pessoa_id
            LEFT JOIN professores pr ON pr.id=f.professor_id
            WHERE f.id=?
            """, (ficha_id,)
        ).fetchone()
        if not ficha:
            return None
        resultado = dict(ficha)
        treinos = []
        for tr in conn.execute(
            "SELECT * FROM treinos WHERE ficha_id=? ORDER BY ordem,id", (ficha_id,)
        ).fetchall():
            treino = dict(tr)
            treino["exercicios"] = [dict(r) for r in conn.execute(
                """
                SELECT te.*, e.nome AS exercicio_nome, e.grupo_muscular,
                       e.equipamento, e.tipo, e.imagem_path
                FROM treino_exercicios te
                JOIN exercicios e ON e.id=te.exercicio_id
                WHERE te.treino_id=?
                ORDER BY te.ordem,te.id
                """, (tr["id"],)
            ).fetchall()]
            treinos.append(treino)
        resultado["treinos"] = treinos
        return resultado
    finally:
        conn.close()


def criar_ficha_treino(dados: dict, usuario_id=None):
    conn = conectar()
    try:
        conn.execute("BEGIN IMMEDIATE")
        if dados.get("ativo"):
            conn.execute(
                "UPDATE fichas_treino SET ativo=0,data_atualizacao=CURRENT_TIMESTAMP WHERE pessoa_id=?",
                (dados["pessoa_id"],)
            )
        cur = conn.execute(
            """
            INSERT INTO fichas_treino
              (pessoa_id,professor_id,nome,objetivo,observacoes,ativo,data_inicio,data_fim,criado_por_usuario_id)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                dados["pessoa_id"], dados.get("professor_id"), dados["nome"],
                dados.get("objetivo"), dados.get("observacoes"),
                1 if dados.get("ativo", True) else 0,
                dados.get("data_inicio"), dados.get("data_fim"), usuario_id,
            )
        )
        ficha_id = cur.lastrowid
        for t_ordem, treino in enumerate(dados.get("treinos") or [], 1):
            tcur = conn.execute(
                "INSERT INTO treinos(ficha_id,nome,ordem,observacoes) VALUES(?,?,?,?)",
                (ficha_id, treino["nome"], t_ordem, treino.get("observacoes"))
            )
            treino_id = tcur.lastrowid
            for e_ordem, item in enumerate(treino.get("exercicios") or [], 1):
                conn.execute(
                    """
                    INSERT INTO treino_exercicios
                      (treino_id,exercicio_id,ordem,series,repeticoes,carga,descanso_segundos,observacoes)
                    VALUES(?,?,?,?,?,?,?,?)
                    """,
                    (
                        treino_id, item["exercicio_id"], e_ordem, item.get("series"),
                        item.get("repeticoes"), item.get("carga"),
                        item.get("descanso_segundos"), item.get("observacoes"),
                    )
                )
        conn.commit()
        return ficha_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def atualizar_ficha_treino(ficha_id: int, dados: dict):
    conn = conectar()
    try:
        conn.execute("BEGIN IMMEDIATE")
        atual = conn.execute("SELECT pessoa_id FROM fichas_treino WHERE id=?", (ficha_id,)).fetchone()
        if not atual:
            conn.rollback()
            return False
        if dados.get("ativo"):
            conn.execute(
                "UPDATE fichas_treino SET ativo=0,data_atualizacao=CURRENT_TIMESTAMP WHERE pessoa_id=? AND id<>?",
                (dados["pessoa_id"], ficha_id)
            )
        conn.execute(
            """
            UPDATE fichas_treino SET pessoa_id=?,professor_id=?,nome=?,objetivo=?,observacoes=?,
              ativo=?,data_inicio=?,data_fim=?,data_atualizacao=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (
                dados["pessoa_id"], dados.get("professor_id"), dados["nome"],
                dados.get("objetivo"), dados.get("observacoes"),
                1 if dados.get("ativo", True) else 0,
                dados.get("data_inicio"), dados.get("data_fim"), ficha_id,
            )
        )
        conn.execute("DELETE FROM treinos WHERE ficha_id=?", (ficha_id,))
        for t_ordem, treino in enumerate(dados.get("treinos") or [], 1):
            tcur = conn.execute(
                "INSERT INTO treinos(ficha_id,nome,ordem,observacoes) VALUES(?,?,?,?)",
                (ficha_id, treino["nome"], t_ordem, treino.get("observacoes"))
            )
            treino_id = tcur.lastrowid
            for e_ordem, item in enumerate(treino.get("exercicios") or [], 1):
                conn.execute(
                    """
                    INSERT INTO treino_exercicios
                      (treino_id,exercicio_id,ordem,series,repeticoes,carga,descanso_segundos,observacoes)
                    VALUES(?,?,?,?,?,?,?,?)
                    """,
                    (
                        treino_id, item["exercicio_id"], e_ordem, item.get("series"),
                        item.get("repeticoes"), item.get("carga"),
                        item.get("descanso_segundos"), item.get("observacoes"),
                    )
                )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def estatisticas_fichas_treino():
    conn = conectar()
    try:
        row = conn.execute(
            """
            SELECT COUNT(*) total,
                   SUM(CASE WHEN ativo=1 THEN 1 ELSE 0 END) ativas,
                   COUNT(DISTINCT CASE WHEN ativo=1 THEN pessoa_id END) alunos_com_ficha
            FROM fichas_treino
            """
        ).fetchone()
        total_alunos = conn.execute("SELECT COUNT(*) FROM pessoas").fetchone()[0]
        return {
            "total": int(row["total"] or 0),
            "ativas": int(row["ativas"] or 0),
            "alunos_com_ficha": int(row["alunos_com_ficha"] or 0),
            "alunos_sem_ficha": max(0, int(total_alunos or 0) - int(row["alunos_com_ficha"] or 0)),
        }
    finally:
        conn.close()


# ---------- Autogestão professor ↔ aluno ----------
def obter_professor_ativo_do_aluno(pessoa_id: int):
    conn=conectar()
    try:
        r=conn.execute("""SELECT pa.id vinculo_id,pa.professor_id,pa.pessoa_id,pa.data_vinculo,
                         p.nome professor_nome FROM professor_alunos pa
                         JOIN professores p ON p.id=pa.professor_id
                         WHERE pa.pessoa_id=? AND pa.ativo=1 ORDER BY pa.id DESC LIMIT 1""",(pessoa_id,)).fetchone()
        return dict(r) if r else None
    finally: conn.close()

def listar_alunos_disponiveis():
    conn=conectar()
    try:
        return [dict(r) for r in conn.execute("""SELECT p.* FROM pessoas p
            WHERE NOT EXISTS(SELECT 1 FROM professor_alunos pa WHERE pa.pessoa_id=p.id AND pa.ativo=1)
            ORDER BY p.nome COLLATE NOCASE""").fetchall()]
    finally: conn.close()

def assumir_aluno_professor(professor_id:int,pessoa_id:int):
    conn=conectar()
    try:
        conn.execute("BEGIN IMMEDIATE")
        if not conn.execute("SELECT id FROM pessoas WHERE id=?",(pessoa_id,)).fetchone():
            conn.rollback(); return False,"Aluno não encontrado."
        if not conn.execute("SELECT id FROM professores WHERE id=? AND ativo=1",(professor_id,)).fetchone():
            conn.rollback(); return False,"Professor não encontrado ou inativo."
        atual=conn.execute("SELECT professor_id FROM professor_alunos WHERE pessoa_id=? AND ativo=1",(pessoa_id,)).fetchone()
        if atual:
            conn.rollback()
            return False,("Este aluno já está com você." if int(atual["professor_id"])==int(professor_id) else "Este aluno já possui um professor responsável.")
        conn.execute("""
            INSERT INTO professor_alunos(professor_id,pessoa_id,principal,ativo,data_vinculo,data_atualizacao)
            VALUES(?,?,1,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)
            ON CONFLICT(professor_id,pessoa_id) DO UPDATE SET
                principal=1, ativo=1,
                data_vinculo=CURRENT_TIMESTAMP,
                data_atualizacao=CURRENT_TIMESTAMP
        """,(professor_id,pessoa_id))
        conn.commit(); return True,None
    except sqlite3.IntegrityError:
        conn.rollback(); return False,"Este aluno acabou de ser assumido por outro professor."
    finally: conn.close()

def liberar_aluno_professor(professor_id:int,pessoa_id:int):
    conn=conectar()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur=conn.execute("""UPDATE professor_alunos SET ativo=0,data_atualizacao=CURRENT_TIMESTAMP
                            WHERE professor_id=? AND pessoa_id=? AND ativo=1""",(professor_id,pessoa_id))
        conn.commit()
        return (True,None) if cur.rowcount else (False,"Este aluno não está vinculado a você.")
    except Exception:
        conn.rollback(); raise
    finally: conn.close()

def contar_fichas_pendentes_professor(professor_id:int):
    conn=conectar()
    try:
        r=conn.execute("""SELECT COUNT(*) total FROM professor_alunos pa
          WHERE pa.professor_id=? AND pa.ativo=1 AND NOT EXISTS(
          SELECT 1 FROM fichas_treino f WHERE f.pessoa_id=pa.pessoa_id AND f.ativo=1)""",(professor_id,)).fetchone()
        return int(r["total"] or 0)
    finally: conn.close()


# ---------- Execução e histórico de treinos ----------

def listar_treinos_disponiveis_para_execucao(pessoa_ids=None):
    conn = conectar()
    try:
        sql = """
            SELECT t.id AS treino_id, t.nome AS treino_nome, t.ordem,
                   f.id AS ficha_id, f.nome AS ficha_nome, f.pessoa_id,
                   p.nome AS aluno_nome, pr.nome AS professor_nome,
                   (SELECT COUNT(*) FROM treino_exercicios te WHERE te.treino_id=t.id) AS total_exercicios
            FROM treinos t
            JOIN fichas_treino f ON f.id=t.ficha_id AND f.ativo=1
            JOIN pessoas p ON p.id=f.pessoa_id
            LEFT JOIN professores pr ON pr.id=f.professor_id
        """
        params = []
        if pessoa_ids is not None:
            pessoa_ids = list(pessoa_ids)
            if not pessoa_ids:
                return []
            marks = ",".join("?" for _ in pessoa_ids)
            sql += f" WHERE f.pessoa_id IN ({marks})"
            params.extend(pessoa_ids)
        sql += " ORDER BY p.nome COLLATE NOCASE, f.id DESC, t.ordem, t.id"
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def criar_sessao_treino(pessoa_id: int, treino_id: int, usuario_id=None, origem="PAINEL"):
    conn = conectar()
    try:
        conn.execute("BEGIN IMMEDIATE")
        treino = conn.execute(
            """
            SELECT t.id treino_id,t.ficha_id,t.nome treino_nome,f.pessoa_id,f.ativo
            FROM treinos t JOIN fichas_treino f ON f.id=t.ficha_id
            WHERE t.id=?
            """, (treino_id,)
        ).fetchone()
        if not treino:
            conn.rollback()
            return None, "Treino não encontrado."
        if int(treino["pessoa_id"]) != int(pessoa_id):
            conn.rollback()
            return None, "Este treino não pertence ao aluno informado."
        if not treino["ativo"]:
            conn.rollback()
            return None, "A ficha deste treino não está ativa."

        em_andamento = conn.execute(
            """
            SELECT id FROM treino_sessoes
            WHERE pessoa_id=? AND status='EM_ANDAMENTO'
            ORDER BY id DESC LIMIT 1
            """, (pessoa_id,)
        ).fetchone()
        if em_andamento:
            conn.rollback()
            return int(em_andamento["id"]), "JA_EXISTE"

        itens = conn.execute(
            """
            SELECT te.*,e.nome exercicio_nome,e.grupo_muscular
            FROM treino_exercicios te
            JOIN exercicios e ON e.id=te.exercicio_id
            WHERE te.treino_id=?
            ORDER BY te.ordem,te.id
            """, (treino_id,)
        ).fetchall()
        if not itens:
            conn.rollback()
            return None, "Este treino não possui exercícios."

        cur = conn.execute(
            """
            INSERT INTO treino_sessoes
                (pessoa_id,ficha_id,treino_id,status,iniciado_por_usuario_id,origem)
            VALUES(?,?,?,'EM_ANDAMENTO',?,?)
            """, (pessoa_id, treino["ficha_id"], treino_id, usuario_id, origem)
        )
        sessao_id = cur.lastrowid
        for item in itens:
            conn.execute(
                """
                INSERT INTO treino_sessao_itens
                    (sessao_id,treino_exercicio_id,exercicio_id,ordem,exercicio_nome,
                     grupo_muscular,series_planejadas,repeticoes_planejadas,carga_planejada,
                     descanso_planejado,observacoes_planejadas)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    sessao_id,item["id"],item["exercicio_id"],item["ordem"],item["exercicio_nome"],
                    item["grupo_muscular"],item["series"],item["repeticoes"],item["carga"],
                    item["descanso_segundos"],item["observacoes"],
                )
            )
        conn.commit()
        return sessao_id, None
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def obter_sessao_treino(sessao_id: int):
    conn = conectar()
    try:
        row = conn.execute(
            """
            SELECT s.*,p.nome aluno_nome,f.nome ficha_nome,t.nome treino_nome,
                   u.nome iniciado_por_nome
            FROM treino_sessoes s
            JOIN pessoas p ON p.id=s.pessoa_id
            JOIN fichas_treino f ON f.id=s.ficha_id
            JOIN treinos t ON t.id=s.treino_id
            LEFT JOIN usuarios u ON u.id=s.iniciado_por_usuario_id
            WHERE s.id=?
            """, (sessao_id,)
        ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["itens"] = [dict(r) for r in conn.execute(
            """
            SELECT * FROM treino_sessao_itens
            WHERE sessao_id=? ORDER BY ordem,id
            """, (sessao_id,)
        ).fetchall()]
        total = len(result["itens"])
        concluidos = sum(1 for i in result["itens"] if i["concluido"])
        result["total_exercicios"] = total
        result["exercicios_concluidos"] = concluidos
        result["progresso_percentual"] = round((concluidos / total) * 100) if total else 0
        return result
    finally:
        conn.close()


def atualizar_item_sessao(item_id: int, dados: dict):
    conn = conectar()
    try:
        item = conn.execute(
            """
            SELECT i.*,s.status FROM treino_sessao_itens i
            JOIN treino_sessoes s ON s.id=i.sessao_id
            WHERE i.id=?
            """, (item_id,)
        ).fetchone()
        if not item:
            return False, "Item não encontrado.", None
        if item["status"] != "EM_ANDAMENTO":
            return False, "Este treino já foi finalizado.", item["sessao_id"]

        concluido = 1 if dados.get("concluido") else 0
        conn.execute(
            """
            UPDATE treino_sessao_itens SET
                concluido=?,
                series_realizadas=?,
                repeticoes_realizadas=?,
                carga_realizada=?,
                observacoes_execucao=?,
                concluido_em=CASE WHEN ?=1 THEN COALESCE(concluido_em,CURRENT_TIMESTAMP) ELSE NULL END
            WHERE id=?
            """,
            (
                concluido,dados.get("series_realizadas"),dados.get("repeticoes_realizadas"),
                dados.get("carga_realizada"),dados.get("observacoes_execucao"),
                concluido,item_id,
            )
        )
        conn.commit()
        return True, None, item["sessao_id"]
    finally:
        conn.close()


def concluir_sessao_treino(sessao_id: int, observacoes=None):
    conn = conectar()
    try:
        conn.execute("BEGIN IMMEDIATE")
        sessao = conn.execute("SELECT * FROM treino_sessoes WHERE id=?", (sessao_id,)).fetchone()
        if not sessao:
            conn.rollback()
            return False, "Sessão não encontrada."
        if sessao["status"] != "EM_ANDAMENTO":
            conn.rollback()
            return False, "Esta sessão já foi finalizada."
        pendentes = conn.execute(
            "SELECT COUNT(*) FROM treino_sessao_itens WHERE sessao_id=? AND concluido=0",
            (sessao_id,)
        ).fetchone()[0]
        if pendentes:
            conn.rollback()
            return False, f"Ainda há {pendentes} exercício(s) pendente(s)."
        conn.execute(
            """
            UPDATE treino_sessoes SET
                status='CONCLUIDO',
                finalizado_em=CURRENT_TIMESTAMP,
                duracao_segundos=MAX(0,CAST((julianday(CURRENT_TIMESTAMP)-julianday(iniciado_em))*86400 AS INTEGER)),
                observacoes=?
            WHERE id=?
            """, (observacoes, sessao_id)
        )
        conn.commit()
        return True, None
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def cancelar_sessao_treino(sessao_id: int, observacoes=None):
    conn = conectar()
    try:
        cur = conn.execute(
            """
            UPDATE treino_sessoes SET
                status='CANCELADO',
                finalizado_em=CURRENT_TIMESTAMP,
                duracao_segundos=MAX(0,CAST((julianday(CURRENT_TIMESTAMP)-julianday(iniciado_em))*86400 AS INTEGER)),
                observacoes=?
            WHERE id=? AND status='EM_ANDAMENTO'
            """, (observacoes, sessao_id)
        )
        conn.commit()
        return (True, None) if cur.rowcount else (False, "Sessão não encontrada ou já finalizada.")
    finally:
        conn.close()


def listar_sessoes_treino(pessoa_ids=None, limite=100):
    conn = conectar()
    try:
        sql = """
            SELECT s.*,p.nome aluno_nome,f.nome ficha_nome,t.nome treino_nome,
                   (SELECT COUNT(*) FROM treino_sessao_itens i WHERE i.sessao_id=s.id) total_exercicios,
                   (SELECT COUNT(*) FROM treino_sessao_itens i WHERE i.sessao_id=s.id AND i.concluido=1) exercicios_concluidos
            FROM treino_sessoes s
            JOIN pessoas p ON p.id=s.pessoa_id
            JOIN fichas_treino f ON f.id=s.ficha_id
            JOIN treinos t ON t.id=s.treino_id
        """
        params = []
        if pessoa_ids is not None:
            pessoa_ids = list(pessoa_ids)
            if not pessoa_ids:
                return []
            marks = ",".join("?" for _ in pessoa_ids)
            sql += f" WHERE s.pessoa_id IN ({marks})"
            params += pessoa_ids
        sql += " ORDER BY CASE WHEN s.status='EM_ANDAMENTO' THEN 0 ELSE 1 END, s.iniciado_em DESC LIMIT ?"
        params.append(int(limite))
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def estatisticas_execucoes(pessoa_ids=None):
    conn = conectar()
    try:
        where = ""
        params = []
        if pessoa_ids is not None:
            pessoa_ids = list(pessoa_ids)
            if not pessoa_ids:
                return {"em_andamento":0,"concluidos":0,"ultimos_30_dias":0,"duracao_media_min":0}
            marks = ",".join("?" for _ in pessoa_ids)
            where = f" WHERE pessoa_id IN ({marks})"
            params += pessoa_ids
        row = conn.execute(
            f"""
            SELECT
                SUM(CASE WHEN status='EM_ANDAMENTO' THEN 1 ELSE 0 END) em_andamento,
                SUM(CASE WHEN status='CONCLUIDO' THEN 1 ELSE 0 END) concluidos,
                SUM(CASE WHEN status='CONCLUIDO' AND datetime(iniciado_em)>=datetime('now','-30 days') THEN 1 ELSE 0 END) ultimos_30_dias,
                AVG(CASE WHEN status='CONCLUIDO' THEN duracao_segundos END) duracao_media
            FROM treino_sessoes{where}
            """, params
        ).fetchone()
        return {
            "em_andamento": int(row["em_andamento"] or 0),
            "concluidos": int(row["concluidos"] or 0),
            "ultimos_30_dias": int(row["ultimos_30_dias"] or 0),
            "duracao_media_min": round(float(row["duracao_media"] or 0)/60),
        }
    finally:
        conn.close()


def evolucao_carga_exercicio(pessoa_id: int, exercicio_id: int, limite=20):
    conn = conectar()
    try:
        return [dict(r) for r in conn.execute(
            """
            SELECT s.iniciado_em,i.carga_realizada,i.repeticoes_realizadas,i.series_realizadas
            FROM treino_sessao_itens i
            JOIN treino_sessoes s ON s.id=i.sessao_id
            WHERE s.pessoa_id=? AND i.exercicio_id=? AND s.status='CONCLUIDO' AND i.concluido=1
            ORDER BY s.iniciado_em DESC LIMIT ?
            """, (pessoa_id,exercicio_id,int(limite))
        ).fetchall()]
    finally:
        conn.close()


# ---------- Avaliação física e evolução ----------

def listar_avaliacoes_fisicas(pessoa_id: int):
    conn = conectar()
    try:
        return [dict(r) for r in conn.execute(
            """
            SELECT a.*,p.nome AS aluno_nome,pr.nome AS professor_nome
            FROM avaliacoes_fisicas a
            JOIN pessoas p ON p.id=a.pessoa_id
            LEFT JOIN professores pr ON pr.id=a.professor_id
            WHERE a.pessoa_id=?
            ORDER BY a.data_avaliacao DESC,a.id DESC
            """, (pessoa_id,)
        ).fetchall()]
    finally:
        conn.close()


def obter_avaliacao_fisica(avaliacao_id: int):
    conn = conectar()
    try:
        row = conn.execute(
            """
            SELECT a.*,p.nome AS aluno_nome,pr.nome AS professor_nome
            FROM avaliacoes_fisicas a
            JOIN pessoas p ON p.id=a.pessoa_id
            LEFT JOIN professores pr ON pr.id=a.professor_id
            WHERE a.id=?
            """, (avaliacao_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def criar_avaliacao_fisica(dados: dict, usuario_id=None):
    conn = conectar()
    try:
        cur = conn.execute(
            """
            INSERT INTO avaliacoes_fisicas(
                pessoa_id,professor_id,data_avaliacao,peso_kg,altura_cm,imc,
                gordura_percentual,massa_gorda_kg,massa_magra_kg,braco_cm,
                antebraco_cm,torax_cm,cintura_cm,abdomen_cm,quadril_cm,coxa_cm,
                panturrilha_cm,observacoes,foto_frontal_path,foto_lateral_path,
                foto_costas_path,criado_por_usuario_id
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                dados["pessoa_id"],dados.get("professor_id"),dados["data_avaliacao"],
                dados.get("peso_kg"),dados.get("altura_cm"),dados.get("imc"),
                dados.get("gordura_percentual"),dados.get("massa_gorda_kg"),dados.get("massa_magra_kg"),
                dados.get("braco_cm"),dados.get("antebraco_cm"),dados.get("torax_cm"),
                dados.get("cintura_cm"),dados.get("abdomen_cm"),dados.get("quadril_cm"),
                dados.get("coxa_cm"),dados.get("panturrilha_cm"),dados.get("observacoes"),
                dados.get("foto_frontal_path"),dados.get("foto_lateral_path"),dados.get("foto_costas_path"),
                usuario_id,
            )
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def atualizar_avaliacao_fisica(avaliacao_id: int, dados: dict):
    conn = conectar()
    try:
        cur = conn.execute(
            """
            UPDATE avaliacoes_fisicas SET
                data_avaliacao=?,peso_kg=?,altura_cm=?,imc=?,gordura_percentual=?,
                massa_gorda_kg=?,massa_magra_kg=?,braco_cm=?,antebraco_cm=?,torax_cm=?,
                cintura_cm=?,abdomen_cm=?,quadril_cm=?,coxa_cm=?,panturrilha_cm=?,
                observacoes=?,foto_frontal_path=?,foto_lateral_path=?,foto_costas_path=?,
                data_atualizacao=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (
                dados["data_avaliacao"],dados.get("peso_kg"),dados.get("altura_cm"),dados.get("imc"),
                dados.get("gordura_percentual"),dados.get("massa_gorda_kg"),dados.get("massa_magra_kg"),
                dados.get("braco_cm"),dados.get("antebraco_cm"),dados.get("torax_cm"),
                dados.get("cintura_cm"),dados.get("abdomen_cm"),dados.get("quadril_cm"),
                dados.get("coxa_cm"),dados.get("panturrilha_cm"),dados.get("observacoes"),
                dados.get("foto_frontal_path"),dados.get("foto_lateral_path"),dados.get("foto_costas_path"),
                avaliacao_id,
            )
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def resumo_avaliacoes_alunos(pessoa_ids=None):
    conn = conectar()
    try:
        sql = """
            SELECT p.id,p.nome,p.matricula,p.foto_path,
                   (SELECT a.data_avaliacao FROM avaliacoes_fisicas a WHERE a.pessoa_id=p.id ORDER BY a.data_avaliacao DESC,a.id DESC LIMIT 1) ultima_avaliacao,
                   (SELECT a.peso_kg FROM avaliacoes_fisicas a WHERE a.pessoa_id=p.id ORDER BY a.data_avaliacao DESC,a.id DESC LIMIT 1) ultimo_peso,
                   (SELECT a.gordura_percentual FROM avaliacoes_fisicas a WHERE a.pessoa_id=p.id ORDER BY a.data_avaliacao DESC,a.id DESC LIMIT 1) ultima_gordura,
                   (SELECT COUNT(*) FROM avaliacoes_fisicas a WHERE a.pessoa_id=p.id) total_avaliacoes
            FROM pessoas p
        """
        params = []
        if pessoa_ids is not None:
            pessoa_ids = list(pessoa_ids)
            if not pessoa_ids:
                return []
            marks = ",".join("?" for _ in pessoa_ids)
            sql += f" WHERE p.id IN ({marks})"
            params += pessoa_ids
        sql += " ORDER BY p.nome COLLATE NOCASE"
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def estatisticas_avaliacoes(pessoa_ids=None):
    conn = conectar()
    try:
        where = ""
        params = []
        if pessoa_ids is not None:
            pessoa_ids = list(pessoa_ids)
            if not pessoa_ids:
                return {"avaliacoes":0,"alunos_avaliados":0,"ultimos_30_dias":0,"alunos_sem_avaliacao":0}
            marks = ",".join("?" for _ in pessoa_ids)
            where = f" WHERE pessoa_id IN ({marks})"
            params += pessoa_ids
        row = conn.execute(
            f"""
            SELECT COUNT(*) avaliacoes,
                   COUNT(DISTINCT pessoa_id) alunos_avaliados,
                   SUM(CASE WHEN date(data_avaliacao)>=date('now','-30 days') THEN 1 ELSE 0 END) ultimos_30_dias
            FROM avaliacoes_fisicas{where}
            """, params
        ).fetchone()
        if pessoa_ids is None:
            total_alunos = conn.execute("SELECT COUNT(*) FROM pessoas").fetchone()[0]
        else:
            total_alunos = len(pessoa_ids)
        avaliados = int(row["alunos_avaliados"] or 0)
        return {
            "avaliacoes": int(row["avaliacoes"] or 0),
            "alunos_avaliados": avaliados,
            "ultimos_30_dias": int(row["ultimos_30_dias"] or 0),
            "alunos_sem_avaliacao": max(0, int(total_alunos) - avaliados),
        }
    finally:
        conn.close()


# ---------- App/PWA do aluno ----------

def obter_acesso_aluno_por_login(login: str):
    conn = conectar()
    try:
        row = conn.execute(
            """
            SELECT aa.*,p.nome,p.matricula,p.foto_path
            FROM aluno_acessos aa
            JOIN pessoas p ON p.id=aa.pessoa_id
            WHERE aa.login=? COLLATE NOCASE
            LIMIT 1
            """, ((login or "").strip(),)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def obter_acesso_aluno_por_pessoa(pessoa_id: int):
    conn = conectar()
    try:
        row = conn.execute(
            """
            SELECT aa.*,p.nome,p.matricula
            FROM aluno_acessos aa
            JOIN pessoas p ON p.id=aa.pessoa_id
            WHERE aa.pessoa_id=?
            """, (pessoa_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def salvar_acesso_aluno(pessoa_id: int, login: str, senha_hash=None, ativo=True):
    login = (login or "").strip()
    if not login:
        raise ValueError("Informe um login.")
    conn = conectar()
    try:
        pessoa = conn.execute("SELECT id FROM pessoas WHERE id=?", (pessoa_id,)).fetchone()
        if not pessoa:
            raise ValueError("Aluno não encontrado.")
        conflito_equipe = conn.execute(
            "SELECT id FROM usuarios WHERE login=? COLLATE NOCASE LIMIT 1", (login,)
        ).fetchone()
        if conflito_equipe:
            raise ValueError("Este login já pertence a uma conta da equipe.")
        conflito_aluno = conn.execute(
            "SELECT pessoa_id FROM aluno_acessos WHERE login=? COLLATE NOCASE AND pessoa_id<>? LIMIT 1",
            (login, pessoa_id)
        ).fetchone()
        if conflito_aluno:
            raise ValueError("Este login já pertence a outro aluno.")

        atual = conn.execute(
            "SELECT id,senha_hash FROM aluno_acessos WHERE pessoa_id=?", (pessoa_id,)
        ).fetchone()
        if atual:
            if senha_hash:
                conn.execute(
                    """
                    UPDATE aluno_acessos
                    SET login=?,senha_hash=?,ativo=?,data_atualizacao=CURRENT_TIMESTAMP
                    WHERE pessoa_id=?
                    """, (login, senha_hash, 1 if ativo else 0, pessoa_id)
                )
            else:
                conn.execute(
                    """
                    UPDATE aluno_acessos
                    SET login=?,ativo=?,data_atualizacao=CURRENT_TIMESTAMP
                    WHERE pessoa_id=?
                    """, (login, 1 if ativo else 0, pessoa_id)
                )
            acesso_id = atual["id"]
        else:
            if not senha_hash:
                raise ValueError("Defina uma senha para criar o acesso.")
            cur = conn.execute(
                """
                INSERT INTO aluno_acessos(pessoa_id,login,senha_hash,ativo)
                VALUES(?,?,?,?)
                """, (pessoa_id, login, senha_hash, 1 if ativo else 0)
            )
            acesso_id = cur.lastrowid
        conn.commit()
        return acesso_id
    finally:
        conn.close()


def atualizar_ultimo_login_aluno(acesso_id: int):
    conn = conectar()
    try:
        conn.execute(
            "UPDATE aluno_acessos SET ultimo_login=CURRENT_TIMESTAMP WHERE id=?",
            (acesso_id,)
        )
        conn.commit()
    finally:
        conn.close()


def obter_ficha_ativa_aluno(pessoa_id: int):
    conn = conectar()
    try:
        row = conn.execute(
            """
            SELECT id FROM fichas_treino
            WHERE pessoa_id=? AND ativo=1
            ORDER BY data_criacao DESC,id DESC LIMIT 1
            """, (pessoa_id,)
        ).fetchone()
    finally:
        conn.close()
    return obter_ficha_treino(row["id"]) if row else None


def obter_sessao_em_andamento_aluno(pessoa_id: int):
    conn = conectar()
    try:
        row = conn.execute(
            """
            SELECT id FROM treino_sessoes
            WHERE pessoa_id=? AND status='EM_ANDAMENTO'
            ORDER BY id DESC LIMIT 1
            """, (pessoa_id,)
        ).fetchone()
    finally:
        conn.close()
    return obter_sessao_treino(row["id"]) if row else None


def listar_ultimas_cargas_aluno(pessoa_id: int, limite=8):
    conn = conectar()
    try:
        return [dict(r) for r in conn.execute(
            """
            SELECT i.exercicio_id,i.exercicio_nome,i.carga_realizada,
                   i.repeticoes_realizadas,i.series_realizadas,s.iniciado_em
            FROM treino_sessao_itens i
            JOIN treino_sessoes s ON s.id=i.sessao_id
            WHERE s.pessoa_id=? AND s.status='CONCLUIDO' AND i.concluido=1
              AND COALESCE(i.carga_realizada,'')<>''
            ORDER BY s.iniciado_em DESC,i.id DESC LIMIT ?
            """, (pessoa_id,int(limite))
        ).fetchall()]
    finally:
        conn.close()


# ---------- Recursos de autosserviço e evolução ----------

def proximo_treino_aluno(pessoa_id: int):
    ficha = obter_ficha_ativa_aluno(pessoa_id)
    if not ficha or not ficha.get("treinos"):
        return None
    treinos = ficha["treinos"]
    conn = conectar()
    try:
        ultimo = conn.execute(
            """SELECT treino_id FROM treino_sessoes
               WHERE pessoa_id=? AND ficha_id=? AND status='CONCLUIDO'
               ORDER BY COALESCE(finalizado_em,iniciado_em) DESC,id DESC LIMIT 1""",
            (pessoa_id,ficha["id"])
        ).fetchone()
    finally:
        conn.close()
    if not ultimo:
        return treinos[0]
    ids=[int(x["id"]) for x in treinos]
    try: idx=ids.index(int(ultimo["treino_id"]))
    except ValueError: return treinos[0]
    return treinos[(idx+1)%len(treinos)]


def ultima_execucao_exercicio(pessoa_id: int, exercicio_id: int):
    conn=conectar()
    try:
        row=conn.execute(
            """SELECT i.carga_realizada,i.repeticoes_realizadas,i.series_realizadas,s.iniciado_em
               FROM treino_sessao_itens i JOIN treino_sessoes s ON s.id=i.sessao_id
               WHERE s.pessoa_id=? AND i.exercicio_id=? AND s.status='CONCLUIDO' AND i.concluido=1
               ORDER BY COALESCE(s.finalizado_em,s.iniciado_em) DESC,i.id DESC LIMIT 1""",
            (pessoa_id,exercicio_id)
        ).fetchone()
        return dict(row) if row else None
    finally: conn.close()


def historico_exercicio_aluno(pessoa_id:int, exercicio_id:int, limite=30):
    conn=conectar()
    try:
        return [dict(r) for r in conn.execute(
            """SELECT i.exercicio_nome,i.carga_realizada,i.repeticoes_realizadas,i.series_realizadas,
                      s.iniciado_em,s.finalizado_em
               FROM treino_sessao_itens i JOIN treino_sessoes s ON s.id=i.sessao_id
               WHERE s.pessoa_id=? AND i.exercicio_id=? AND s.status='CONCLUIDO' AND i.concluido=1
               ORDER BY COALESCE(s.finalizado_em,s.iniciado_em) DESC,i.id DESC LIMIT ?""",
            (pessoa_id,exercicio_id,int(limite))
        ).fetchall()]
    finally: conn.close()


def duplicar_ficha_treino(ficha_id:int, pessoa_id:int, professor_id=None, usuario_id=None):
    original=obter_ficha_treino(ficha_id)
    if not original: raise ValueError("Ficha não encontrada.")
    dados={
        "pessoa_id":int(pessoa_id),"professor_id":professor_id or original.get("professor_id"),
        "nome":f"{original['nome']} · cópia","objetivo":original.get("objetivo"),
        "observacoes":original.get("observacoes"),"ativo":True,
        "data_inicio":None,"data_fim":None,
        "treinos":[{"nome":tr["nome"],"observacoes":tr.get("observacoes"),
                    "exercicios":[{"exercicio_id":e["exercicio_id"],"series":e.get("series"),
                                  "repeticoes":e.get("repeticoes"),"carga":e.get("carga"),
                                  "descanso_segundos":e.get("descanso_segundos"),
                                  "observacoes":e.get("observacoes")} for e in tr.get("exercicios",[])]}
                   for tr in original.get("treinos",[])]
    }
    return criar_ficha_treino(dados,usuario_id)


def metricas_professor(professor_id:int):
    conn=conectar()
    try:
        total=int(conn.execute("SELECT COUNT(*) FROM professor_alunos WHERE professor_id=? AND ativo=1",(professor_id,)).fetchone()[0])
        sem_ficha=int(conn.execute("""SELECT COUNT(*) FROM professor_alunos pa WHERE pa.professor_id=? AND pa.ativo=1
            AND NOT EXISTS(SELECT 1 FROM fichas_treino f WHERE f.pessoa_id=pa.pessoa_id AND f.ativo=1)""",(professor_id,)).fetchone()[0])
        sem_avaliacao=int(conn.execute("""SELECT COUNT(*) FROM professor_alunos pa WHERE pa.professor_id=? AND pa.ativo=1
            AND NOT EXISTS(SELECT 1 FROM avaliacoes_fisicas a WHERE a.pessoa_id=pa.pessoa_id
            AND date(a.data_avaliacao)>=date('now','localtime','-60 day'))""",(professor_id,)).fetchone()[0])
        treinando=int(conn.execute("""SELECT COUNT(DISTINCT s.pessoa_id) FROM treino_sessoes s
            JOIN professor_alunos pa ON pa.pessoa_id=s.pessoa_id AND pa.professor_id=? AND pa.ativo=1
            WHERE s.status='EM_ANDAMENTO'""",(professor_id,)).fetchone()[0])
        return {"total":total,"sem_ficha":sem_ficha,"sem_avaliacao_60":sem_avaliacao,"treinando":treinando}
    finally: conn.close()
