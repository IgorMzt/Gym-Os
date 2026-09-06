"""Cache leve das configuracoes operacionais.

Evita abrir uma conexao SQLite para cada parametro consultado durante uma leitura
facial. O cache e invalidado sempre que as configuracoes sao alteradas pelo painel.
"""
from threading import RLock

import database

_lock = RLock()
_cache = None


def _carregar():
    global _cache
    with _lock:
        if _cache is None:
            _cache = database.obter_configuracoes()
        return _cache


def invalidate():
    global _cache
    with _lock:
        _cache = None


def get(chave, padrao=None):
    return _carregar().get(chave, padrao)


def get_int(chave, padrao):
    try:
        return int(float(get(chave, str(padrao))))
    except (TypeError, ValueError):
        return padrao


def get_float(chave, padrao):
    try:
        return float(get(chave, str(padrao)))
    except (TypeError, ValueError):
        return padrao


def get_bool(chave, padrao=True):
    valor = get(chave, "1" if padrao else "0")
    return str(valor).strip().lower() in {"1", "true", "sim", "on", "yes"}
