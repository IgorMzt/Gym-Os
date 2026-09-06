"""Regras da execução de treinos."""

def _txt(v, limite):
    s = str(v or "").strip()
    return s[:limite] or None

def _int(v, minimo=None, maximo=None):
    if v in (None, ""):
        return None
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise ValueError("Valor numérico inválido.")
    if minimo is not None and n < minimo:
        raise ValueError("Valor abaixo do mínimo permitido.")
    if maximo is not None and n > maximo:
        raise ValueError("Valor acima do máximo permitido.")
    return n

def normalizar_item(payload):
    concluido = payload.get("concluido", False)
    if not isinstance(concluido, bool):
        concluido = str(concluido).lower() in {"1","true","sim","on","yes"}
    return {
        "concluido": concluido,
        "series_realizadas": _int(payload.get("series_realizadas"), 0, 99),
        "repeticoes_realizadas": _txt(payload.get("repeticoes_realizadas"), 80),
        "carga_realizada": _txt(payload.get("carga_realizada"), 80),
        "observacoes_execucao": _txt(payload.get("observacoes_execucao"), 1000),
    }

def normalizar_observacao(payload):
    return _txt(payload.get("observacoes"), 2000)
