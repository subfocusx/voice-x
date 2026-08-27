"""Оркестратор: файл -> готовый текст.

Пайплайн (тот же, что в промте «логика обработки»):
  probe → ffmpeg(wav16k) → engine.transcribe → (clean) → transcript.

`transcribe_file` — сервисный слой без GUI. Работает в текущем потоке,
прогресс отдаёт через callback. UI запускает его в фоне (см. ui/worker.py).
Здесь же замеряем время каждого этапа (stage_timings) для разбивки по таймингам.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Optional

from core.job import Job, Stage
from core.logging_setup import get_logger
from services import ffmpeg
from services.cleaner import get_cleaner
from services.engine import make_engine

log = get_logger("transcriber")


class _StageTimer:
    """Секундомер одного этапа: создай перед этапом, забери время после."""

    __slots__ = ("_t",)

    def __init__(self) -> None:
        self._t = time.monotonic()

    def mark(self) -> float:
        return time.monotonic() - self._t


def transcribe_file(
    input_path: Path | str,
    *,
    engine_name: str = "gigaam",
    model_dir: Optional[str] = None,
    clean_enabled: bool = False,
    on_stage: Optional[Callable[[Stage], None]] = None,
    on_progress: Optional[Callable[[float], None]] = None,
    cancel: Optional[Callable[[], bool]] = None,
    paused: Optional[Callable[[], bool]] = None,
) -> Job:
    """Выполнить расшифровку и вернуть заполненный Job."""
    job = Job(input_path=Path(input_path), clean_enabled=clean_enabled)
    job.started()
    log.info("start %s | engine=%s model=%s clean=%s",
             job.input_path, engine_name, model_dir, clean_enabled)
    try:
        # — probe: длительность
        _emit_stage(on_stage, Stage.PROBE)
        t = _StageTimer()
        job.duration_sec = ffmpeg.probe_duration(job.input_path)
        job.stage_timings[Stage.PROBE.value] = t.mark()

        _emit_stage(on_stage, Stage.EXTRACT)
        if _is_cancelled(cancel):
            return _cancelled(job)
        t = _StageTimer()
        audio, _ = ffmpeg.load_waveform_16k(job.input_path)
        job.stage_timings[Stage.EXTRACT.value] = t.mark()

        _emit_stage(on_stage, Stage.ASR)
        engine = make_engine(engine_name, model_dir=model_dir)
        t = _StageTimer()
        raw = engine.transcribe(
            audio,
            sample_rate=ffmpeg.SAMPLE_RATE,
            progress=on_progress,
            cancel=cancel,
            paused=paused,
        )
        job.stage_timings[Stage.ASR.value] = t.mark()
        if _is_cancelled(cancel):
            return _cancelled(job)

        _emit_stage(on_stage, Stage.CLEAN)
        final_text = raw
        if clean_enabled:
            t = _StageTimer()
            final_text = get_cleaner().clean(raw)
            job.stage_timings[Stage.CLEAN.value] = t.mark()

        job.transcript = final_text
        job.progress = 1.0
        job.stage = Stage.DONE
        log.info("done %s | dur=%s split=[%s]",
                 job.input_path, job.fmt_duration(), job.fmt_split())
        return job

    except Exception as exc:  # noqa: BLE001 — UI покажет текст ошибки
        log.exception("transcribe failed %s: %s", job.input_path, exc)
        job.error = str(exc)
        job.stage = Stage.ERROR
        return job
    finally:
        job.tick_elapsed()


def _cancelled(job: Job) -> Job:
    job.stage = Stage.CANCELLED
    log.info("cancelled %s", job.input_path)
    return job


def _emit_stage(cb: Optional[Callable[[Stage], None]], stage: Stage) -> None:
    if cb:
        cb(stage)


def _is_cancelled(cancel: Optional[Callable[[], bool]]) -> bool:
    return bool(cancel and cancel())
