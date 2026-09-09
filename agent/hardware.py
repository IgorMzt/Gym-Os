"""Ponte local para os dispositivos fisicos da academia."""

from __future__ import annotations

import device_manager


def open_turnstile(catraca: dict) -> dict:
    """Aciona a catraca somente no computador local da academia."""
    return device_manager.acionar(catraca)


def test_turnstile(catraca: dict) -> dict:
    return open_turnstile(catraca)
