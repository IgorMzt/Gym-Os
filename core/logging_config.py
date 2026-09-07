"""Logging consistente para terminal, cloud e diagnostico local."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from core.settings import Settings


_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_logging(settings: Settings, app_logger: logging.Logger) -> None:
    nivel = getattr(logging, settings.log_level, logging.INFO)
    formatter = logging.Formatter(_FORMAT)

    app_logger.setLevel(nivel)
    for handler in app_logger.handlers:
        handler.setLevel(nivel)
        if handler.formatter is None:
            handler.setFormatter(formatter)

    if not app_logger.handlers:
        stream = logging.StreamHandler()
        stream.setLevel(nivel)
        stream.setFormatter(formatter)
        app_logger.addHandler(stream)

    if settings.log_dir:
        diretorio = Path(settings.log_dir).expanduser().resolve()
        diretorio.mkdir(parents=True, exist_ok=True)
        destino = diretorio / "gym-os.log"
        if not any(isinstance(h, RotatingFileHandler) and getattr(h, "baseFilename", "") == str(destino) for h in app_logger.handlers):
            arquivo = RotatingFileHandler(destino, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8")
            arquivo.setLevel(nivel)
            arquivo.setFormatter(formatter)
            app_logger.addHandler(arquivo)
