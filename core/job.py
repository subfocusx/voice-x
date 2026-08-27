"""Модель задачи расшифровки: статус, стейт, тайминги.

UI только читает эти поля; обработка живёт в services/job_runner.py.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Optional


class Stage(str, Enum):
    IDLE = "idle"          # ничего
    PROBE = "probe"        # читаем файл, узнаём длительность
    EXTRACT = "extract"    # ffmpeg -> wav 16k mono
    ASR = "asr"            # распознавание (GigaAM)
    CLEAN = "clean"        # LLM-очистка (если включена)
    DONE = "done"
    ERROR = "error"
    CANCELLED = "cancelled"


class RecordingState(str, Enum):
    """Состояние локальной записи (рекордер — отдельная от расшифровки машина)."""
    IDLE = "idle"            # ничего не записываем
    RECORDING = "recording"  # идёт захват с микро/системы
    STOPPING = "stopping"    # остановка, финализируем WAV
    DONE = "done"            # звук сохранён, можно транскрибировать
    ERROR = "error"          # устройство/захват упали
    CANCELLED = "cancelled"


#: подписи состояний записи (для статусной строки UI)
RECORDING_STATE_LABEL = {
    RecordingState.IDLE: "Готов к записи",
    RecordingState.RECORDING: "Идёт запись…",
    RecordingState.STOPPING: "Остановка…",
    RecordingState.DONE: "Запись сохранена",
    RecordingState.ERROR: "Ошибка записи",
    RecordingState.CANCELLED: "Запись отменена",
}


#: человекочитаемые подписи этапов (порядок важен — это виз. путь)
STAGE_LABEL = {
    Stage.IDLE: "Готов к загрузке",
    Stage.PROBE: "Получение информации о файле…",
    Stage.EXTRACT: "Извлечение аудио…",
    Stage.ASR: "Распознавание речи…",
    Stage.CLEAN: "Очистка текста…",
    Stage.DONE: "Готово",
}

#: порядок показа разбивки по этапам в UI (короткие подписи)
STAGE_ORDER = (
    Stage.PROBE,
    Stage.EXTRACT,
    Stage.ASR,
    Stage.CLEAN,
)
STAGE_SHORT = {
    Stage.PROBE: "Разбор файла",
    Stage.EXTRACT: "Извлечение",
    Stage.ASR: "Распознавание",
    Stage.CLEAN: "Очистка",
}


@dataclass
class Job:
    """Вся информация о текущей задаче распознавания."""

    input_path: Optional[Path] = None
    output_path: Optional[Path] = None      # конечный .txt (если сохранён)
    stage: Stage = Stage.IDLE
    progress: float = 0.0                  # 0..1 агрегированный
    stage_progress: float = 0.0            # 0..1 внутри текущего этапа
    transcript: str = ""                   # итоговый текст
    clean_enabled: bool = True
    duration_sec: Optional[float] = None   # длительность исходника
    error: Optional[str] = None
    elapsed_seconds: float = 0.0
    started_at: Optional[float] = None
    stage_timings: dict[str, float] = field(default_factory=dict)  # этап -> сек
    _cancelled: bool = field(default=False, repr=False)

    # ── управление ────────────────────────────────────────────────────
    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def cancel(self) -> None:
        self._cancelled = True

    def is_terminal(self) -> bool:
        return self.stage in (Stage.DONE, Stage.CANCELLED, Stage.ERROR)

    # ── помощь для UI ───────────────────────────────────────────────────
    @property
    def label(self) -> str:
        return STAGE_LABEL.get(self.stage, self.stage.value)

    def started(self) -> None:
        self.started_at = time.monotonic()

    def tick_elapsed(self) -> None:
        if self.started_at is not None:
            self.elapsed_seconds = time.monotonic() - self.started_at

    def fmt_duration(self) -> str:
        """'MM:SS' для длительности исходника."""
        return _fmt_seconds(self.duration_sec)

    def fmt_elapsed(self) -> str:
        """'MM:SS' для времени обработки."""
        return _fmt_seconds(self.elapsed_seconds)

    def fmt_split(self) -> str:
        """'Разбор 00:01 · Извлечение 00:03 · Распознавание 00:12' по факту."""
        parts = [
            f"{STAGE_SHORT.get(st, st.value)} {_fmt_seconds(self.stage_timings.get(st.value))}"
            for st in STAGE_ORDER
            if st.value in self.stage_timings and self.stage_timings[st.value] > 0
        ]
        return " · ".join(parts)


def _fmt_seconds(sec: Optional[float]) -> str:
    if sec is None:
        return "—"
    sec = int(round(max(0, sec)))
    return f"{sec // 60:02d}:{sec % 60:02d}"
