"""Indice facial em memoria.

Os encodings deixam de ser desserializados do SQLite em toda verificacao. O indice
e recarregado apenas quando cadastro, recaptura ou remocao alteram a biometria.
"""
from threading import RLock

import database

_lock = RLock()
_pessoas = None
_amostras = None


def invalidate():
    global _pessoas, _amostras
    with _lock:
        _pessoas = None
        _amostras = None


def snapshot():
    global _pessoas, _amostras
    with _lock:
        if _pessoas is None or _amostras is None:
            _pessoas = database.listar_pessoas()
            _amostras = database.listar_amostras_faciais()
        # A leitura e somente de referencia; os chamadores nao devem mutar esses objetos.
        return _pessoas, _amostras


def warmup():
    snapshot()
