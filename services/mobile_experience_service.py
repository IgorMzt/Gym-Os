"""Metricas e experiencia do aluno no aplicativo mobile."""

import re
from datetime import date, datetime, timedelta

import database


def _data(valor):
    if not valor:
        return None
    try:
        return datetime.fromisoformat(str(valor).replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(str(valor)[:10])
        except ValueError:
            return None


def _numero(valor):
    if valor in (None, ""):
        return 0.0
    texto = str(valor).replace(",", ".")
    m = re.search(r"-?\d+(?:\.\d+)?", texto)
    return float(m.group(0)) if m else 0.0


def _repeticoes(valor):
    nums = [float(x.replace(",", ".")) for x in re.findall(r"\d+(?:[.,]\d+)?", str(valor or ""))[:2]]
    if not nums:
        return 0.0
    return sum(nums) / len(nums)


def _volume_item(item):
    carga = _numero(item.get("carga_realizada"))
    series = float(item.get("series_realizadas") or 0)
    reps = _repeticoes(item.get("repeticoes_realizadas"))
    return round(carga * series * reps, 2)


def _itens_concluidos(pessoa_id: int):
    conn = database.conectar()
    try:
        return [dict(r) for r in conn.execute(
            """
            SELECT i.*,s.iniciado_em,s.finalizado_em,s.id sessao_id
            FROM treino_sessao_itens i
            JOIN treino_sessoes s ON s.id=i.sessao_id
            WHERE s.pessoa_id=? AND s.status='CONCLUIDO' AND i.concluido=1
            ORDER BY COALESCE(s.finalizado_em,s.iniciado_em),i.id
            """, (pessoa_id,)
        ).fetchall()]
    finally:
        conn.close()


def _recordes(pessoa_id: int):
    hoje = date.today()
    maxima = {}
    recentes = []
    total_recordes = 0
    for item in _itens_concluidos(pessoa_id):
        ex = int(item.get("exercicio_id") or 0)
        carga = _numero(item.get("carga_realizada"))
        quando = _data(item.get("finalizado_em") or item.get("iniciado_em"))
        anterior = maxima.get(ex, 0.0)
        if ex and carga > anterior:
            if anterior > 0:
                total_recordes += 1
                if quando and quando >= hoje - timedelta(days=30):
                    recentes.append({
                        "exercicio_id": ex,
                        "exercicio_nome": item.get("exercicio_nome"),
                        "carga_kg": round(carga, 2),
                        "data": quando.isoformat(),
                    })
            maxima[ex] = carga
    recentes.reverse()
    return total_recordes, recentes[:5]


def _streak(sessoes):
    dias = sorted({d for d in (_data(s.get("finalizado_em") or s.get("iniciado_em")) for s in sessoes) if d}, reverse=True)
    if not dias:
        return 0
    hoje = date.today()
    if dias[0] < hoje - timedelta(days=1):
        return 0
    streak = 1
    atual = dias[0]
    for d in dias[1:]:
        if d == atual - timedelta(days=1):
            streak += 1
            atual = d
        else:
            break
    return streak


def resumo_aluno(pessoa_id: int):
    preferencias = database.obter_preferencias_mobile(pessoa_id)
    sessoes = [s for s in database.listar_sessoes_treino([pessoa_id], 500) if s.get("status") == "CONCLUIDO"]
    hoje = date.today()
    inicio_semana = hoje - timedelta(days=hoje.weekday())
    semana = [s for s in sessoes if (_data(s.get("finalizado_em") or s.get("iniciado_em")) or date.min) >= inicio_semana]
    minutos = round(sum(int(s.get("duracao_segundos") or 0) for s in semana) / 60)
    exercicios = sum(int(s.get("exercicios_concluidos") or 0) for s in semana)

    semana_ids = {int(s["id"]) for s in semana}
    volume = 0.0
    for item in _itens_concluidos(pessoa_id):
        if int(item.get("sessao_id") or 0) in semana_ids:
            volume += _volume_item(item)

    meta = int(preferencias.get("meta_semanal") or 4)
    realizados = len(semana)
    progresso = min(100, round(realizados / meta * 100)) if meta else 0
    streak = _streak(sessoes)
    total_recordes, recordes_recentes = _recordes(pessoa_id)
    proximo = database.proximo_treino_aluno(pessoa_id)
    ficha = database.obter_ficha_ativa_aluno(pessoa_id)
    professor = database.obter_professor_ativo_do_aluno(pessoa_id)
    avaliacoes = database.listar_avaliacoes_fisicas(pessoa_id)
    em_andamento = database.obter_sessao_em_andamento_aluno(pessoa_id)

    total = len(sessoes)
    conquistas = [
        {"id":"primeiro_treino","titulo":"Primeiro passo","descricao":"Conclua seu primeiro treino.","desbloqueada":total >= 1},
        {"id":"cinco_treinos","titulo":"Pegando ritmo","descricao":"Conclua 5 treinos.","desbloqueada":total >= 5},
        {"id":"dez_treinos","titulo":"Consistência","descricao":"Conclua 10 treinos.","desbloqueada":total >= 10},
        {"id":"meta_semana","titulo":"Meta batida","descricao":"Complete sua meta semanal.","desbloqueada":realizados >= meta},
        {"id":"streak_3","titulo":"Em sequência","descricao":"Treine em 3 dias consecutivos.","desbloqueada":streak >= 3},
        {"id":"recorde","titulo":"Novo nível","descricao":"Supere uma carga anterior.","desbloqueada":total_recordes >= 1},
    ]

    return {
        "semana": {
            "realizados": realizados,
            "meta": meta,
            "progresso_percentual": progresso,
            "duracao_minutos": minutos,
            "exercicios": exercicios,
            "volume_kg": round(volume),
        },
        "streak_dias": streak,
        "total_treinos": total,
        "recordes_30_dias": recordes_recentes,
        "total_recordes": total_recordes,
        "conquistas": conquistas,
        "proximo_treino": proximo,
        "ficha": {"id": ficha.get("id"), "nome": ficha.get("nome"), "professor_nome": ficha.get("professor_nome")} if ficha else None,
        "professor": professor,
        "ultima_avaliacao": avaliacoes[0] if avaliacoes else None,
        "sessao_em_andamento": em_andamento,
        "recentes": sessoes[:3],
        "preferencias": preferencias,
    }


def resumo_sessao(pessoa_id: int, sessao_id: int):
    sessao = database.obter_sessao_treino(sessao_id)
    if not sessao or int(sessao.get("pessoa_id") or 0) != int(pessoa_id) or sessao.get("status") != "CONCLUIDO":
        return None
    volume = sum(_volume_item(i) for i in sessao.get("itens", []) if i.get("concluido"))
    return {
        "id": int(sessao["id"]),
        "treino_nome": sessao.get("treino_nome"),
        "ficha_nome": sessao.get("ficha_nome"),
        "duracao_segundos": int(sessao.get("duracao_segundos") or 0),
        "total_exercicios": int(sessao.get("total_exercicios") or 0),
        "exercicios_concluidos": int(sessao.get("exercicios_concluidos") or 0),
        "volume_kg": round(volume),
        "percepcao_esforco": sessao.get("percepcao_esforco"),
        "feedback_mobile": sessao.get("feedback_mobile"),
        "finalizado_em": sessao.get("finalizado_em"),
    }
