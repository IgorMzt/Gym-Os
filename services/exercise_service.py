"""Regras de negócio do banco de exercícios."""
from urllib.parse import urlparse

TIPOS = {
    "FORCA": "Força",
    "CARDIO": "Cardio",
    "MOBILIDADE": "Mobilidade",
    "ALONGAMENTO": "Alongamento",
    "OUTRO": "Outro",
}

DIFICULDADES = {
    "INICIANTE": "Iniciante",
    "INTERMEDIARIO": "Intermediário",
    "AVANCADO": "Avançado",
}


def _texto(valor, limite):
    valor = str(valor or "").strip()
    return valor[:limite] or None


def normalizar(dados, atual=None):
    nome = _texto(dados.get("nome"), 120)
    if not nome or len(nome) < 2:
        raise ValueError("Informe o nome do exercício.")

    grupo = _texto(dados.get("grupo_muscular"), 80)
    if not grupo:
        raise ValueError("Informe o grupo muscular.")

    tipo = str(dados.get("tipo") or "FORCA").strip().upper()
    if tipo not in TIPOS:
        raise ValueError("Tipo de exercício inválido.")

    dificuldade = str(dados.get("dificuldade") or "").strip().upper() or None
    if dificuldade and dificuldade not in DIFICULDADES:
        raise ValueError("Dificuldade inválida.")

    video_url = _texto(dados.get("video_url"), 500)
    if video_url:
        parsed = urlparse(video_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Informe uma URL de vídeo válida (http/https).")

    ativo_bruto = dados.get("ativo", True)
    ativo = ativo_bruto if isinstance(ativo_bruto, bool) else str(ativo_bruto).lower() in {"1","true","sim","yes","on"}

    return {
        "nome": nome,
        "grupo_muscular": grupo,
        "equipamento": _texto(dados.get("equipamento"), 100),
        "tipo": tipo,
        "dificuldade": dificuldade,
        "instrucoes": _texto(dados.get("instrucoes"), 4000),
        "observacoes": _texto(dados.get("observacoes"), 2000),
        "video_url": video_url,
        "imagem_path": (atual or {}).get("imagem_path"),
        "ativo": ativo,
    }
