"""Система логирования Voice-X.

Единый логгер `voicex.*`: пишет в <проект>/logs/voice-x.log (ротация по
размеру ~2 МБ, 3 бэкапа) и дублирует вывод в консоль. `setup_logging()`
вызывается один раз при старте приложения, далее — `get_logger("имя")`.

Пример:
    from core.logging_setup import setup_logging, get_logger
    setup_logging()
    log = get_logger("transcriber")
    log.info("файл %s принят", path)
"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from core.paths import data_dir

LOG_DIR_NAME = "logs"
LOG_FILE_NAME = "voice-x.log"
_MAX_BYTES = 2_000_000  # ~2 МБ до ротации
_BACKUP_COUNT = 3
_configured = False


def log_dir() -> Path:
    d = data_dir() / LOG_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def log_file() -> Path:
    return log_dir() / LOG_FILE_NAME


def setup_logging(debug: bool = False) -> None:
    """Инициализировать корневой логгер `voicex` один раз (идемпотентно)."""
    global _configured
    if _configured:
        return

    root = logging.getLogger("voicex")
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    root.propagate = False

    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")

    fh = RotatingFileHandler(
        log_file(), maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(sh)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Логгер вида `voicex.<name>`, например get_logger("gigaam")."""
    return logging.getLogger(f"voicex.{name}")
