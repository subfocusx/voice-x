"""Whisper — заглушка на будущее.

MVP работает только на GigaAM. Файл-стаб, чтобы интерфейс движка уже
имел второго кандидата без правки остального кода.
"""
from __future__ import annotations

from typing import Callable, Optional

import numpy as np

from .engine import EngineInterface


class WhisperEngine(EngineInterface):
    name = "whisper"

    def __init__(self, model_dir: str | None = None):
        self._model_dir = model_dir

    def load(self) -> None:
        raise NotImplementedError(
            "Whisper ещё не подключен. Используй движок 'gigaam'."
        )

    def transcribe(
        self,
        audio: np.ndarray,
        sample_rate: int,
        progress: Optional[Callable[[float], None]] = None,
        cancel: Optional[Callable[[], bool]] = None,
    ) -> str:
        self.load()
        return ""