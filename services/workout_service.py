"""Validação e regras das fichas de treino."""

def _txt(v, limite):
    v = str(v or "").strip()
    return v[:limite] or None

def _int(v, minimo=None, maximo=None, obrigatorio=False):
    if v in (None, ""):
        if obrigatorio:
            raise ValueError("Campo numérico obrigatório.")
        return None
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise ValueError("Há um valor numérico inválido na ficha.")
    if minimo is not None and n < minimo:
        raise ValueError("Há um valor abaixo do mínimo permitido na ficha.")
    if maximo is not None and n > maximo:
        raise ValueError("Há um valor acima do máximo permitido na ficha.")
    return n

def normalizar(payload):
    pessoa_id = _int(payload.get("pessoa_id"), 1, obrigatorio=True)
    nome = _txt(payload.get("nome"), 120)
    if not nome:
        raise ValueError("Informe o nome da ficha.")

    professor_id = _int(payload.get("professor_id"), 1)
    ativo_raw = payload.get("ativo", True)
    ativo = ativo_raw if isinstance(ativo_raw, bool) else str(ativo_raw).lower() in {"1","true","on","sim","yes"}

    treinos_saida = []
    treinos = payload.get("treinos") or []
    if not isinstance(treinos, list) or not treinos:
        raise ValueError("Adicione pelo menos um treino à ficha.")

    for idx, treino in enumerate(treinos, 1):
        nome_treino = _txt(treino.get("nome"), 80)
        if not nome_treino:
            raise ValueError(f"Informe o nome do treino {idx}.")
        itens = treino.get("exercicios") or []
        if not itens:
            raise ValueError(f"O treino {nome_treino} precisa ter pelo menos um exercício.")
        itens_saida = []
        vistos = set()
        for item in itens:
            exercicio_id = _int(item.get("exercicio_id"), 1, obrigatorio=True)
            if exercicio_id in vistos:
                raise ValueError(f"Há exercício duplicado no treino {nome_treino}.")
            vistos.add(exercicio_id)
            itens_saida.append({
                "exercicio_id": exercicio_id,
                "series": _int(item.get("series"), 1, 99),
                "repeticoes": _txt(item.get("repeticoes"), 40),
                "carga": _txt(item.get("carga"), 40),
                "descanso_segundos": _int(item.get("descanso_segundos"), 0, 3600),
                "observacoes": _txt(item.get("observacoes"), 1000),
            })
        treinos_saida.append({
            "nome": nome_treino,
            "observacoes": _txt(treino.get("observacoes"), 1000),
            "exercicios": itens_saida,
        })

    return {
        "pessoa_id": pessoa_id,
        "professor_id": professor_id,
        "nome": nome,
        "objetivo": _txt(payload.get("objetivo"), 500),
        "observacoes": _txt(payload.get("observacoes"), 2000),
        "ativo": ativo,
        "data_inicio": _txt(payload.get("data_inicio"), 10),
        "data_fim": _txt(payload.get("data_fim"), 10),
        "treinos": treinos_saida,
    }
