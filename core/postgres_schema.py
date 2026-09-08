"""DDL PostgreSQL da V6.10.

Os campos de data/hora continuam TEXT nesta etapa para preservar a API e o
formato historico do SQLite durante a migracao. A normalizacao para tipos DATE /
TIMESTAMPTZ pode ser feita em uma migracao futura sem misturar essa mudanca com
a troca de engine.
"""

TS_DEFAULT = "DEFAULT (to_char(CURRENT_TIMESTAMP, 'YYYY-MM-DD HH24:MI:SS'))"


def _ts(name: str, *, not_null: bool = False) -> str:
    nn = " NOT NULL" if not_null else ""
    return f"{name} TEXT{nn} {TS_DEFAULT}"


POSTGRES_SCHEMA_STATEMENTS = [
    f"""
    CREATE TABLE IF NOT EXISTS pessoas (
        id BIGSERIAL PRIMARY KEY,
        nome TEXT NOT NULL,
        encoding TEXT,
        liberado INTEGER DEFAULT 1,
        data_cadastro TEXT {TS_DEFAULT},
        cpf TEXT,
        data_nascimento TEXT,
        sexo TEXT,
        telefone TEXT,
        email TEXT,
        matricula TEXT,
        plano TEXT,
        data_inicio TEXT,
        data_vencimento TEXT,
        observacoes TEXT,
        foto_path TEXT,
        plano_id BIGINT,
        status_financeiro TEXT DEFAULT 'EM_DIA'
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS face_encodings (
        id BIGSERIAL PRIMARY KEY,
        pessoa_id BIGINT NOT NULL REFERENCES pessoas(id) ON DELETE CASCADE,
        encoding TEXT NOT NULL,
        ordem INTEGER NOT NULL DEFAULT 1,
        data_cadastro TEXT {TS_DEFAULT},
        UNIQUE(pessoa_id, ordem)
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS logs_acesso (
        id BIGSERIAL PRIMARY KEY,
        pessoa_id BIGINT REFERENCES pessoas(id) ON DELETE SET NULL,
        nome TEXT,
        cpf TEXT,
        matricula TEXT,
        status TEXT,
        motivo TEXT,
        data_hora TEXT {TS_DEFAULT},
        catraca_id BIGINT,
        catraca_nome TEXT
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS planos (
        id BIGSERIAL PRIMARY KEY,
        nome TEXT NOT NULL UNIQUE,
        valor_centavos INTEGER NOT NULL DEFAULT 0,
        duracao_dias INTEGER NOT NULL,
        descricao TEXT,
        ativo INTEGER NOT NULL DEFAULT 1,
        data_cadastro TEXT {TS_DEFAULT}
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS configuracoes (
        chave TEXT PRIMARY KEY,
        valor TEXT NOT NULL,
        data_atualizacao TEXT {TS_DEFAULT}
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS usuarios (
        id BIGSERIAL PRIMARY KEY,
        login TEXT NOT NULL,
        nome TEXT NOT NULL,
        senha_hash TEXT NOT NULL,
        papel TEXT NOT NULL CHECK (papel IN ('ADMIN','RECEPCAO','PROFESSOR')),
        ativo INTEGER NOT NULL DEFAULT 1,
        origem TEXT NOT NULL DEFAULT 'LOCAL',
        ultimo_login TEXT,
        data_criacao TEXT {TS_DEFAULT},
        data_atualizacao TEXT {TS_DEFAULT}
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS professores (
        id BIGSERIAL PRIMARY KEY,
        usuario_id BIGINT UNIQUE REFERENCES usuarios(id) ON DELETE SET NULL,
        nome TEXT NOT NULL,
        cpf TEXT UNIQUE,
        cref TEXT UNIQUE,
        telefone TEXT,
        email TEXT,
        especialidade TEXT,
        foto_path TEXT,
        observacoes TEXT,
        ativo INTEGER NOT NULL DEFAULT 1,
        data_criacao TEXT {TS_DEFAULT},
        data_atualizacao TEXT {TS_DEFAULT}
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS professor_alunos (
        id BIGSERIAL PRIMARY KEY,
        professor_id BIGINT NOT NULL REFERENCES professores(id) ON DELETE CASCADE,
        pessoa_id BIGINT NOT NULL REFERENCES pessoas(id) ON DELETE CASCADE,
        principal INTEGER NOT NULL DEFAULT 1,
        ativo INTEGER NOT NULL DEFAULT 1,
        data_vinculo TEXT {TS_DEFAULT},
        data_atualizacao TEXT {TS_DEFAULT},
        UNIQUE(professor_id, pessoa_id)
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS exercicios (
        id BIGSERIAL PRIMARY KEY,
        nome TEXT NOT NULL,
        grupo_muscular TEXT NOT NULL,
        equipamento TEXT,
        tipo TEXT NOT NULL DEFAULT 'FORCA' CHECK (tipo IN ('FORCA','CARDIO','MOBILIDADE','ALONGAMENTO','OUTRO')),
        dificuldade TEXT CHECK (dificuldade IS NULL OR dificuldade IN ('INICIANTE','INTERMEDIARIO','AVANCADO')),
        instrucoes TEXT,
        observacoes TEXT,
        imagem_path TEXT,
        video_url TEXT,
        ativo INTEGER NOT NULL DEFAULT 1,
        criado_por_usuario_id BIGINT REFERENCES usuarios(id) ON DELETE SET NULL,
        data_criacao TEXT {TS_DEFAULT},
        data_atualizacao TEXT {TS_DEFAULT}
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS fichas_treino (
        id BIGSERIAL PRIMARY KEY,
        pessoa_id BIGINT NOT NULL REFERENCES pessoas(id) ON DELETE CASCADE,
        professor_id BIGINT REFERENCES professores(id) ON DELETE SET NULL,
        nome TEXT NOT NULL,
        objetivo TEXT,
        observacoes TEXT,
        ativo INTEGER NOT NULL DEFAULT 1,
        data_inicio TEXT,
        data_fim TEXT,
        criado_por_usuario_id BIGINT REFERENCES usuarios(id) ON DELETE SET NULL,
        data_criacao TEXT {TS_DEFAULT},
        data_atualizacao TEXT {TS_DEFAULT}
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS treinos (
        id BIGSERIAL PRIMARY KEY,
        ficha_id BIGINT NOT NULL REFERENCES fichas_treino(id) ON DELETE CASCADE,
        nome TEXT NOT NULL,
        ordem INTEGER NOT NULL DEFAULT 1,
        observacoes TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS treino_exercicios (
        id BIGSERIAL PRIMARY KEY,
        treino_id BIGINT NOT NULL REFERENCES treinos(id) ON DELETE CASCADE,
        exercicio_id BIGINT NOT NULL REFERENCES exercicios(id) ON DELETE RESTRICT,
        ordem INTEGER NOT NULL DEFAULT 1,
        series INTEGER,
        repeticoes TEXT,
        carga TEXT,
        descanso_segundos INTEGER,
        observacoes TEXT
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS treino_sessoes (
        id BIGSERIAL PRIMARY KEY,
        pessoa_id BIGINT NOT NULL REFERENCES pessoas(id) ON DELETE CASCADE,
        ficha_id BIGINT NOT NULL REFERENCES fichas_treino(id) ON DELETE RESTRICT,
        treino_id BIGINT NOT NULL REFERENCES treinos(id) ON DELETE RESTRICT,
        status TEXT NOT NULL DEFAULT 'EM_ANDAMENTO' CHECK (status IN ('EM_ANDAMENTO','CONCLUIDO','CANCELADO')),
        iniciado_em TEXT NOT NULL {TS_DEFAULT},
        finalizado_em TEXT,
        duracao_segundos INTEGER,
        observacoes TEXT,
        iniciado_por_usuario_id BIGINT REFERENCES usuarios(id) ON DELETE SET NULL,
        origem TEXT NOT NULL DEFAULT 'PAINEL' CHECK (origem IN ('PAINEL','ALUNO_APP')),
        percepcao_esforco INTEGER,
        feedback_mobile TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS treino_sessao_itens (
        id BIGSERIAL PRIMARY KEY,
        sessao_id BIGINT NOT NULL REFERENCES treino_sessoes(id) ON DELETE CASCADE,
        treino_exercicio_id BIGINT REFERENCES treino_exercicios(id) ON DELETE SET NULL,
        exercicio_id BIGINT REFERENCES exercicios(id) ON DELETE SET NULL,
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
        concluido_em TEXT
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS avaliacoes_fisicas (
        id BIGSERIAL PRIMARY KEY,
        pessoa_id BIGINT NOT NULL REFERENCES pessoas(id) ON DELETE CASCADE,
        professor_id BIGINT REFERENCES professores(id) ON DELETE SET NULL,
        data_avaliacao TEXT NOT NULL,
        peso_kg DOUBLE PRECISION,
        altura_cm DOUBLE PRECISION,
        imc DOUBLE PRECISION,
        gordura_percentual DOUBLE PRECISION,
        massa_gorda_kg DOUBLE PRECISION,
        massa_magra_kg DOUBLE PRECISION,
        braco_cm DOUBLE PRECISION,
        antebraco_cm DOUBLE PRECISION,
        torax_cm DOUBLE PRECISION,
        cintura_cm DOUBLE PRECISION,
        abdomen_cm DOUBLE PRECISION,
        quadril_cm DOUBLE PRECISION,
        coxa_cm DOUBLE PRECISION,
        panturrilha_cm DOUBLE PRECISION,
        observacoes TEXT,
        foto_frontal_path TEXT,
        foto_lateral_path TEXT,
        foto_costas_path TEXT,
        criado_por_usuario_id BIGINT REFERENCES usuarios(id) ON DELETE SET NULL,
        data_criacao TEXT {TS_DEFAULT},
        data_atualizacao TEXT {TS_DEFAULT}
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS aluno_acessos (
        id BIGSERIAL PRIMARY KEY,
        pessoa_id BIGINT NOT NULL UNIQUE REFERENCES pessoas(id) ON DELETE CASCADE,
        login TEXT NOT NULL,
        senha_hash TEXT NOT NULL,
        ativo INTEGER NOT NULL DEFAULT 1,
        ultimo_login TEXT,
        data_criacao TEXT {TS_DEFAULT},
        data_atualizacao TEXT {TS_DEFAULT}
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS mobile_refresh_tokens (
        id BIGSERIAL PRIMARY KEY,
        aluno_acesso_id BIGINT NOT NULL REFERENCES aluno_acessos(id) ON DELETE CASCADE,
        pessoa_id BIGINT NOT NULL REFERENCES pessoas(id) ON DELETE CASCADE,
        token_hash TEXT NOT NULL UNIQUE,
        expires_at TEXT NOT NULL,
        revoked_at TEXT,
        replaced_by_hash TEXT,
        last_used_at TEXT,
        ip TEXT,
        user_agent TEXT,
        created_at TEXT {TS_DEFAULT}
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS mobile_push_devices (
        id BIGSERIAL PRIMARY KEY,
        pessoa_id BIGINT NOT NULL REFERENCES pessoas(id) ON DELETE CASCADE,
        expo_push_token TEXT NOT NULL UNIQUE,
        plataforma TEXT,
        device_name TEXT,
        app_version TEXT,
        ativo INTEGER NOT NULL DEFAULT 1,
        last_seen_at TEXT {TS_DEFAULT},
        created_at TEXT {TS_DEFAULT},
        updated_at TEXT {TS_DEFAULT}
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS mobile_aluno_preferencias (
        pessoa_id BIGINT PRIMARY KEY REFERENCES pessoas(id) ON DELETE CASCADE,
        meta_semanal INTEGER NOT NULL DEFAULT 4 CHECK (meta_semanal BETWEEN 1 AND 14),
        lembrete_treino_ativo INTEGER NOT NULL DEFAULT 0,
        lembrete_treino_hora TEXT NOT NULL DEFAULT '19:00',
        atualizado_em TEXT {TS_DEFAULT}
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS logs_admin (
        id BIGSERIAL PRIMARY KEY,
        acao TEXT NOT NULL,
        alvo TEXT,
        detalhes TEXT,
        ip TEXT,
        data_hora TEXT {TS_DEFAULT}
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS schema_meta (
        chave TEXT PRIMARY KEY,
        valor TEXT NOT NULL
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS cobrancas (
        id BIGSERIAL PRIMARY KEY,
        pessoa_id BIGINT REFERENCES pessoas(id) ON DELETE SET NULL,
        plano_id BIGINT,
        gateway TEXT NOT NULL DEFAULT 'ASAAS',
        gateway_customer_id TEXT,
        gateway_payment_id TEXT UNIQUE,
        valor_centavos INTEGER NOT NULL,
        vencimento_original TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'PENDENTE',
        pix_payload TEXT,
        pix_qr_base64 TEXT,
        data_pagamento TEXT,
        data_criacao TEXT {TS_DEFAULT},
        vencimento_antes TEXT,
        vencimento_apos TEXT,
        ultimo_evento TEXT,
        data_atualizacao TEXT
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS cobranca_eventos (
        id BIGSERIAL PRIMARY KEY,
        cobranca_id BIGINT REFERENCES cobrancas(id) ON DELETE SET NULL,
        pessoa_id BIGINT REFERENCES pessoas(id) ON DELETE SET NULL,
        event_id TEXT UNIQUE,
        gateway_payment_id TEXT,
        evento TEXT NOT NULL,
        status_resultante TEXT,
        detalhes TEXT,
        data_evento TEXT,
        data_recebimento TEXT {TS_DEFAULT}
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS gateway_clientes (
        pessoa_id BIGINT PRIMARY KEY REFERENCES pessoas(id) ON DELETE CASCADE,
        gateway TEXT NOT NULL DEFAULT 'ASAAS',
        gateway_customer_id TEXT NOT NULL,
        data_criacao TEXT {TS_DEFAULT}
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS webhook_eventos (
        event_id TEXT PRIMARY KEY,
        gateway TEXT NOT NULL,
        evento TEXT,
        data_recebimento TEXT {TS_DEFAULT},
        payment_id TEXT,
        processado INTEGER NOT NULL DEFAULT 0,
        erro TEXT,
        data_processamento TEXT
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS catracas (
        id BIGSERIAL PRIMARY KEY,
        nome TEXT NOT NULL,
        local TEXT,
        modo TEXT NOT NULL DEFAULT 'SIMULADA',
        endpoint TEXT,
        ativa INTEGER NOT NULL DEFAULT 1,
        data_cadastro TEXT {TS_DEFAULT}
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS database_migrations (
        id BIGSERIAL PRIMARY KEY,
        migration_key TEXT NOT NULL UNIQUE,
        origem TEXT,
        detalhes TEXT,
        executado_em TEXT {TS_DEFAULT}
    )
    """,
    # Evolucao segura caso um banco PostgreSQL de teste tenha sido criado durante a V6.10.
    "ALTER TABLE treino_sessoes ADD COLUMN IF NOT EXISTS percepcao_esforco INTEGER",
    "ALTER TABLE treino_sessoes ADD COLUMN IF NOT EXISTS feedback_mobile TEXT",
    "ALTER TABLE webhook_eventos ADD COLUMN IF NOT EXISTS payment_id TEXT",
    "ALTER TABLE webhook_eventos ADD COLUMN IF NOT EXISTS processado INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE webhook_eventos ADD COLUMN IF NOT EXISTS erro TEXT",
    "ALTER TABLE webhook_eventos ADD COLUMN IF NOT EXISTS data_processamento TEXT",
    "ALTER TABLE cobrancas ADD COLUMN IF NOT EXISTS vencimento_antes TEXT",
    "ALTER TABLE cobrancas ADD COLUMN IF NOT EXISTS vencimento_apos TEXT",
    "ALTER TABLE cobrancas ADD COLUMN IF NOT EXISTS ultimo_evento TEXT",
    "ALTER TABLE cobrancas ADD COLUMN IF NOT EXISTS data_atualizacao TEXT",
    # Indices historicos.
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_pessoas_cpf ON pessoas(cpf) WHERE cpf IS NOT NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_pessoas_matricula ON pessoas(matricula) WHERE matricula IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_logs_data_hora ON logs_acesso(data_hora DESC)",
    "CREATE INDEX IF NOT EXISTS idx_logs_pessoa ON logs_acesso(pessoa_id, data_hora DESC)",
    "CREATE INDEX IF NOT EXISTS idx_logs_status ON logs_acesso(status, data_hora DESC)",
    "CREATE INDEX IF NOT EXISTS idx_cobrancas_pessoa ON cobrancas(pessoa_id, id DESC)",
    "CREATE INDEX IF NOT EXISTS idx_cobrancas_status ON cobrancas(status, vencimento_original)",
    "CREATE INDEX IF NOT EXISTS idx_cobranca_eventos_pessoa ON cobranca_eventos(pessoa_id, id DESC)",
    "CREATE INDEX IF NOT EXISTS idx_webhook_eventos_payment ON webhook_eventos(payment_id, data_recebimento DESC)",
    "CREATE INDEX IF NOT EXISTS idx_usuarios_papel_ativo ON usuarios(papel, ativo)",
    "CREATE INDEX IF NOT EXISTS idx_professores_ativo_nome ON professores(ativo, nome)",
    "CREATE INDEX IF NOT EXISTS idx_professor_alunos_professor ON professor_alunos(professor_id, ativo)",
    "CREATE INDEX IF NOT EXISTS idx_professor_alunos_pessoa ON professor_alunos(pessoa_id, ativo)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_professor_alunos_um_ativo ON professor_alunos(pessoa_id) WHERE ativo=1",
    "CREATE INDEX IF NOT EXISTS idx_exercicios_grupo_ativo ON exercicios(grupo_muscular, ativo)",
    "CREATE INDEX IF NOT EXISTS idx_exercicios_tipo_ativo ON exercicios(tipo, ativo)",
    "CREATE INDEX IF NOT EXISTS idx_fichas_pessoa_ativo ON fichas_treino(pessoa_id, ativo)",
    "CREATE INDEX IF NOT EXISTS idx_treinos_ficha_ordem ON treinos(ficha_id, ordem)",
    "CREATE INDEX IF NOT EXISTS idx_treino_exercicios_ordem ON treino_exercicios(treino_id, ordem)",
    "CREATE INDEX IF NOT EXISTS idx_treino_sessoes_pessoa_data ON treino_sessoes(pessoa_id, iniciado_em DESC)",
    "CREATE INDEX IF NOT EXISTS idx_treino_sessoes_status ON treino_sessoes(status, iniciado_em DESC)",
    "CREATE INDEX IF NOT EXISTS idx_treino_sessao_itens_sessao_ordem ON treino_sessao_itens(sessao_id, ordem)",
    "CREATE INDEX IF NOT EXISTS idx_avaliacoes_pessoa_data ON avaliacoes_fisicas(pessoa_id, data_avaliacao DESC, id DESC)",
    "CREATE INDEX IF NOT EXISTS idx_avaliacoes_professor_data ON avaliacoes_fisicas(professor_id, data_avaliacao DESC)",
    "CREATE INDEX IF NOT EXISTS idx_aluno_acessos_ativo ON aluno_acessos(ativo, pessoa_id)",
    "CREATE INDEX IF NOT EXISTS idx_mobile_refresh_ativo ON mobile_refresh_tokens(aluno_acesso_id, revoked_at, expires_at)",
    "CREATE INDEX IF NOT EXISTS idx_mobile_push_pessoa_ativo ON mobile_push_devices(pessoa_id, ativo)",
    # Equivalentes case-insensitive do COLLATE NOCASE do SQLite.
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_usuarios_login_lower ON usuarios(LOWER(login))",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_aluno_acessos_login_lower ON aluno_acessos(LOWER(login))",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_exercicios_nome_lower ON exercicios(LOWER(nome))",
]
