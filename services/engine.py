"""Абстракция движка ASR: интерфейс + фабрика.

UI и оркестратор зависят только от EngineInterface, чтобы позже
подключить whisper, не трогая остальное.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Optional

import numpy as np

from core.logging_setup import get_logger

#: прогресс-колбэк: (завершённая_часть от 0..1 текущего вызова)
ProgressCallback = Callable[[float], None]
log = get_logger("engine")


class EngineInterface(ABC):
    """Движок: принимает float32-волну 16kHz, возвращает текст."""

    name: str = "engine"

    @abstractmethod
    def transcribe(
        self,
        audio: np.ndarray,
        sample_rate: int,
        progress: Optional[ProgressCallback] = None,
        cancel: Optional[Callable[[], bool]] = None,
    ) -> str:
        """Распознать. progress/cancel — опциональны, chunk-осознаны."""

    @abstractmethod
    def load(self) -> None:
        """Загрузить модель (лениво при первом transcribe тоже можно)."""


def make_engine(name: str, model_dir: str | None = None) -> EngineInterface:
    from .gigaam import GigaAMEngine
    from .whisper import WhisperEngine

    key = (name or "").lower()
    if key in ("giga", "gigaam", "giga-am"):
        log.info("make engine=%s model_dir=%s", "gigaam", model_dir)
        return GigaAMEngine(model_dir=model_dir)
    if key in ("whisper",):
        log.info("make engine=%s model_dir=%s", "whisper", model_dir)
        return WhisperEngine(model_dir=model_dir)
    raise ValueError(f"Неизвестный движок: {name!r}")
