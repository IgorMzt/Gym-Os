"""Cache leve das configuracoes operacionais, isolado por academia/unidade."""
from threading import RLock

import database

_lock = RLock()
_cache = {}


def _tenant_key():
    return (database.academia_atual_id(), database.unidade_atual_id())


def _carregar():
    key = _tenant_key()
    with _lock:
        if key not in _cache:
            _cache[key] = database.obter_configuracoes()
        return _cache[key]


def invalidate():
    key = _tenant_key()
    with _lock:
        _cache.pop(key, None)


def invalidate_all():
    with _lock:
        _cache.clear()


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
