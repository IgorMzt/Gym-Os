"""Validação e cálculos de avaliação física."""
from datetime import date

MEDIDAS = ("braco_cm","antebraco_cm","torax_cm","cintura_cm","abdomen_cm","quadril_cm","coxa_cm","panturrilha_cm")

def _float(v, minimo=None, maximo=None):
    if v in (None, ""):
        return None
    try:
        n = float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        raise ValueError("Há um valor numérico inválido na avaliação.")
    if minimo is not None and n < minimo:
        raise ValueError("Há um valor abaixo do mínimo permitido.")
    if maximo is not None and n > maximo:
        raise ValueError("Há um valor acima do máximo permitido.")
    return round(n, 2)

def _txt(v, limite):
    s = str(v or "").strip()
    return s[:limite] or None

def normalizar(payload, pessoa_id, professor_id=None, fotos=None):
    data_av = _txt(payload.get("data_avaliacao"), 10) or date.today().isoformat()
    try:
        date.fromisoformat(data_av)
    except ValueError:
        raise ValueError("Data da avaliação inválida.")

    peso = _float(payload.get("peso_kg"), 20, 400)
    altura = _float(payload.get("altura_cm"), 80, 250)
    gordura = _float(payload.get("gordura_percentual"), 1, 70)

    imc = None
    if peso is not None and altura is not None:
        imc = round(peso / ((altura / 100) ** 2), 2)

    massa_gorda = massa_magra = None
    if peso is not None and gordura is not None:
        massa_gorda = round(peso * gordura / 100, 2)
        massa_magra = round(peso - massa_gorda, 2)

    dados = {
        "pessoa_id": int(pessoa_id),
        "professor_id": professor_id,
        "data_avaliacao": data_av,
        "peso_kg": peso,
        "altura_cm": altura,
        "imc": imc,
        "gordura_percentual": gordura,
        "massa_gorda_kg": massa_gorda,
        "massa_magra_kg": massa_magra,
        "observacoes": _txt(payload.get("observacoes"), 3000),
    }
    for campo in MEDIDAS:
        dados[campo] = _float(payload.get(campo), 10, 250)

    fotos = fotos or {}
    dados.update({
        "foto_frontal_path": fotos.get("foto_frontal_path"),
        "foto_lateral_path": fotos.get("foto_lateral_path"),
        "foto_costas_path": fotos.get("foto_costas_path"),
    })
    return dados

def comparacao(avaliacoes):
    if not avaliacoes:
        return {}
    atual = avaliacoes[0]
    anterior = avaliacoes[1] if len(avaliacoes) > 1 else None
    campos = ["peso_kg","gordura_percentual","massa_magra_kg","cintura_cm","braco_cm","coxa_cm"]
    saida = {}
    for campo in campos:
        a = atual.get(campo)
        b = anterior.get(campo) if anterior else None
        saida[campo] = {
            "atual": a,
            "anterior": b,
            "delta": round(a-b, 2) if a is not None and b is not None else None,
        }
    return saida
