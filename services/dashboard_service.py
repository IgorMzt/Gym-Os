"""Serviço do dashboard executivo.

Este módulo usa somente dados reais já existentes no produto.
"Presença estimada" não representa saída física: considera alunos com um
acesso LIBERADO recente dentro da janela configurada.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import database


def _config_int(chave: str, padrao: int, minimo: int, maximo: int) -> int:
    try:
        valor = int(database.obter_configuracao(chave, str(padrao)))
    except (TypeError, ValueError):
        valor = padrao
    return max(minimo, min(maximo, valor))


def _status_financeiro(pessoa: dict) -> str:
    return database.status_financeiro_efetivo(pessoa)


def _foto_web(path):
    if not path:
        return None
    valor = str(path).replace("\\", "/")
    marcador = "static/"
    if marcador in valor:
        return "/" + valor.split(marcador, 1)[1].join(["static/", ""]) if False else "/" + marcador + valor.split(marcador, 1)[1]
    if valor.startswith("/static/"):
        return valor
    return None


def _alertas(pessoas: list[dict], dias_alerta: int) -> list[dict]:
    hoje = date.today()
    itens = []

    for pessoa in pessoas:
        vencimento = pessoa.get("data_vencimento")
        venc = None
        if vencimento:
            try:
                venc = date.fromisoformat(vencimento)
            except ValueError:
                venc = None

        financeiro = _status_financeiro(pessoa)
        if financeiro == "PENDENTE":
            itens.append({
                "tipo": "financeiro",
                "nivel": "atencao",
                "titulo": "Pagamento pendente",
                "texto": pessoa.get("nome") or "Aluno",
                "pessoa_id": pessoa["id"],
            })
        elif financeiro == "VENCIDO":
            itens.append({
                "tipo": "vencido",
                "nivel": "critico",
                "titulo": "Plano vencido",
                "texto": pessoa.get("nome") or "Aluno",
                "pessoa_id": pessoa["id"],
            })
        elif venc:
            dias = (venc - hoje).days
            if 0 <= dias <= dias_alerta:
                itens.append({
                    "tipo": "vencendo",
                    "nivel": "atencao",
                    "titulo": "Plano vencendo",
                    "texto": f"{pessoa.get('nome') or 'Aluno'} · {dias} dia(s)",
                    "pessoa_id": pessoa["id"],
                })

        if not pessoa.get("liberado", True):
            itens.append({
                "tipo": "bloqueio",
                "nivel": "critico",
                "titulo": "Aluno bloqueado",
                "texto": pessoa.get("nome") or "Aluno",
                "pessoa_id": pessoa["id"],
            })

        nascimento = pessoa.get("data_nascimento")
        if nascimento:
            try:
                nasc = date.fromisoformat(nascimento)
                if (nasc.month, nasc.day) == (hoje.month, hoje.day):
                    itens.append({
                        "tipo": "aniversario",
                        "nivel": "positivo",
                        "titulo": "Aniversariante hoje",
                        "texto": pessoa.get("nome") or "Aluno",
                        "pessoa_id": pessoa["id"],
                    })
            except ValueError:
                pass

    prioridade = {"critico": 0, "atencao": 1, "positivo": 2}
    itens.sort(key=lambda x: (prioridade.get(x["nivel"], 9), x["titulo"], x["texto"]))
    return itens[:12]


def obter_dashboard() -> dict:
    agora = datetime.now()
    hoje = date.today()
    inicio_hoje = hoje.isoformat()
    dias_alerta = _config_int("dias_alerta_vencimento", 7, 1, 60)
    janela_presenca = _config_int("janela_presenca_minutos", 120, 15, 720)
    atualizacao_ms = _config_int("dashboard_atualizacao_ms", 10000, 3000, 60000)
    limite_presenca = agora - timedelta(minutes=janela_presenca)

    pessoas = database.listar_pessoas()
    total = len(pessoas)
    ativos = sum(1 for p in pessoas if database.acesso_permitido(p)[0])
    bloqueados_manuais = sum(1 for p in pessoas if not p.get("liberado", True))
    inadimplentes = sum(1 for p in pessoas if _status_financeiro(p) in {"PENDENTE", "VENCIDO"})
    vencendo = 0
    cadastrados_hoje = 0

    for p in pessoas:
        if str(p.get("data_cadastro") or "").startswith(inicio_hoje):
            cadastrados_hoje += 1
        venc = p.get("data_vencimento")
        if venc and _status_financeiro(p) == "EM_DIA":
            try:
                dias = (date.fromisoformat(venc) - hoje).days
                if 0 <= dias <= dias_alerta:
                    vencendo += 1
            except ValueError:
                pass

    conn = database.conectar()
    try:
        inicio_dia = datetime.combine(hoje, datetime.min.time()).strftime("%Y-%m-%d %H:%M:%S")
        fim_dia = datetime.combine(hoje + timedelta(days=1), datetime.min.time()).strftime("%Y-%m-%d %H:%M:%S")
        resumo_logs = conn.execute(
            """
            SELECT COUNT(*) total,
                   SUM(CASE WHEN status='LIBERADO' THEN 1 ELSE 0 END) liberados,
                   SUM(CASE WHEN status='BLOQUEADO' THEN 1 ELSE 0 END) bloqueados,
                   SUM(CASE WHEN status='NEGADO' THEN 1 ELSE 0 END) negados
            FROM logs_acesso
            WHERE data_hora>=? AND data_hora<?
            """,
            (inicio_dia, fim_dia),
        ).fetchone()

        entradas_hoje = int(resumo_logs["liberados"] or 0)
        tentativas_hoje = int(resumo_logs["total"] or 0)
        recusas_hoje = int((resumo_logs["bloqueados"] or 0) + (resumo_logs["negados"] or 0))

        hora_limite = limite_presenca.strftime("%Y-%m-%d %H:%M:%S")
        recentes = conn.execute(
            """
            SELECT l.pessoa_id, l.nome, l.matricula, l.data_hora, l.catraca_nome,
                   p.plano, p.foto_path, l.id AS ultimo_id
            FROM logs_acesso l
            LEFT JOIN pessoas p ON p.id=l.pessoa_id
            WHERE l.status='LIBERADO'
              AND l.pessoa_id IS NOT NULL
              AND l.data_hora >= ?
              AND l.id = (
                  SELECT MAX(l2.id) FROM logs_acesso l2
                  WHERE l2.pessoa_id=l.pessoa_id AND l2.status='LIBERADO'
                    AND l2.data_hora >= ?
              )
            ORDER BY l.data_hora DESC
            LIMIT 12
            """,
            (hora_limite, hora_limite),
        ).fetchall()

        presenca = []
        for r in recentes:
            item = dict(r)
            item["foto_url"] = _foto_web(item.get("foto_path"))
            presenca.append(item)

        ultimos = [
            dict(r) for r in conn.execute(
                """
                SELECT id,pessoa_id,nome,status,motivo,data_hora,catraca_nome
                FROM logs_acesso
                ORDER BY id DESC LIMIT 12
                """
            ).fetchall()
        ]

        horas = {h: 0 for h in range(24)}
        for r in conn.execute(
            """
            SELECT CAST(SUBSTR(data_hora,12,2) AS INTEGER) hora, COUNT(*) qtd
            FROM logs_acesso
            WHERE status='LIBERADO' AND data_hora>=? AND data_hora<?
            GROUP BY hora
            """,
            (inicio_dia, fim_dia),
        ).fetchall():
            horas[int(r["hora"])] = int(r["qtd"])

        pico_valor = max(horas.values()) if horas else 0
        pico_hora = max(horas, key=horas.get) if pico_valor else None
        chart = [
            {"hora": h, "rotulo": f"{h:02d}h", "quantidade": horas[h]}
            for h in range(24)
        ]

        limite_ultima_hora = (agora - timedelta(minutes=60)).strftime("%Y-%m-%d %H:%M:%S")
        ultima_hora = int(conn.execute(
            """
            SELECT COUNT(*) FROM logs_acesso
            WHERE status='LIBERADO' AND data_hora >= ?
            """,
            (limite_ultima_hora,),
        ).fetchone()[0] or 0)

        catracas = [dict(r) for r in conn.execute(
            """
            SELECT c.id,c.nome,c.local,c.modo,c.ativa,
                   (SELECT MAX(l.data_hora) FROM logs_acesso l WHERE l.catraca_id=c.id) AS ultimo_evento
            FROM catracas c ORDER BY c.id
            """
        ).fetchall()]

        inicio_mes = hoje.replace(day=1).isoformat()
        if hoje.month == 12:
            fim_mes = date(hoje.year + 1, 1, 1).isoformat()
        else:
            fim_mes = date(hoje.year, hoje.month + 1, 1).isoformat()
        financeiro_row = conn.execute(
            """
            SELECT
              COALESCE(SUM(CASE WHEN status='PAGO' AND data_pagamento>=? AND data_pagamento<? THEN valor_centavos ELSE 0 END),0) receita_hoje,
              COALESCE(SUM(CASE WHEN status='PAGO' AND data_pagamento>=? AND data_pagamento<? THEN valor_centavos ELSE 0 END),0) receita_mes,
              COALESCE(SUM(CASE WHEN status IN ('PENDENTE','VENCIDO') THEN valor_centavos ELSE 0 END),0) a_receber,
              SUM(CASE WHEN status='VENCIDO' THEN 1 ELSE 0 END) cobrancas_vencidas,
              SUM(CASE WHEN status='PAGO' AND data_pagamento>=? AND data_pagamento<? THEN 1 ELSE 0 END) pagamentos_mes
            FROM cobrancas
            """,
            (inicio_dia, fim_dia, inicio_mes, fim_mes, inicio_mes, fim_mes),
        ).fetchone()
        pagamentos_recentes = [dict(r) for r in conn.execute(
            """
            SELECT c.pessoa_id,p.nome,c.valor_centavos,c.data_pagamento,c.gateway_payment_id
            FROM cobrancas c LEFT JOIN pessoas p ON p.id=c.pessoa_id
            WHERE c.status='PAGO'
            ORDER BY COALESCE(c.data_pagamento,c.data_atualizacao,c.data_criacao) DESC LIMIT 6
            """
        ).fetchall()]
        financeiro = {
            "receita_hoje_centavos": int(financeiro_row["receita_hoje"] or 0),
            "receita_mes_centavos": int(financeiro_row["receita_mes"] or 0),
            "a_receber_centavos": int(financeiro_row["a_receber"] or 0),
            "cobrancas_vencidas": int(financeiro_row["cobrancas_vencidas"] or 0),
            "pagamentos_mes": int(financeiro_row["pagamentos_mes"] or 0),
            "pagamentos_recentes": pagamentos_recentes,
        }
    finally:
        conn.close()

    return {
        "gerado_em": agora.isoformat(timespec="seconds"),
        "atualizacao_ms": atualizacao_ms,
        "janela_presenca_minutos": janela_presenca,
        "kpis": {
            "alunos_ativos": ativos,
            "presenca_estimada": len(presenca),
            "entradas_hoje": entradas_hoje,
            "ultima_hora": ultima_hora,
            "vencendo": vencendo,
            "inadimplentes": inadimplentes,
            "bloqueados": bloqueados_manuais,
            "novos_hoje": cadastrados_hoje,
            "tentativas_hoje": tentativas_hoje,
            "recusas_hoje": recusas_hoje,
            "total_alunos": total,
        },
        "pico": {
            "hora": f"{pico_hora:02d}h" if pico_hora is not None else "—",
            "quantidade": pico_valor,
        },
        "chart": chart,
        "presenca": presenca,
        "feed": ultimos,
        "alertas": _alertas(pessoas, dias_alerta),
        "catracas": catracas,
        "financeiro_disponivel": True,
        "financeiro": financeiro,
    }
