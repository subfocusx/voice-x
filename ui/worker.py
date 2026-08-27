"""Фоновый исполнитель расшифровки (thread-safe).

tkinter нельзя трогать из не-GUI потока, а вызывать `widget.after` из
другого потока можно не всегда. Поэтому Worker кладёт события в
`queue.Queue`, а главный поток сам вычитывает их через `drain()` внутри
своего цикла `after` (см. MainWindow._poll). Так гарантированно без гонок.

Логика обработки — в services/transcriber.py; здесь только потоки и очередь.
"""
from __future__ import annotations

import queue
import threading
from pathlib import Path
from typing import Callable, Optional

from core.job import Job, Stage
from services.transcriber import transcribe_file

#: события, которые Worker отдаёт UI-потоку
EV_STAGE, EV_PROGRESS, EV_DONE = "stage", "progress", "done"


class Worker:
    def __init__(self):
        self._queue: "queue.Queue[tuple[str, object]]" = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._cancelled = False
        self._paused = threading.Event()

    # ── управление ────────────────────────────────────────────────────────
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def cancel(self) -> None:
        self._cancelled = True

    def pause(self) -> None:
        self._paused.set()

    def resume(self) -> None:
        self._paused.clear()

    @property
    def is_paused(self) -> bool:
        return self._paused.is_set()

    # ── чтение событий (только из UI-потока) ──────────────────────────────
    def drain(self) -> "list[tuple[str, object]]":
        """Забрать все накопленные события, не блокируя."""
        events: "list[tuple[str, object]]" = []
        while True:
            try:
                events.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return events

    # ── запуск ─────────────────────────────────────────────────────────────
    def start(
        self,
        input_path: str | Path,
        *,
        engine_name: str,
        model_dir: Optional[str],
        clean_enabled: bool,
    ) -> None:
        """Запустить расшифровку. События — в очередь, отдаёт poll()."""
        self._cancelled = False
        self._paused.clear()
        args = {
            "engine_name": engine_name,
            "model_dir": model_dir,
            "clean_enabled": clean_enabled,
        }

        def target() -> None:
            try:
                job = transcribe_file(
                    input_path,
                    on_stage=lambda s: self._queue.put((EV_STAGE, s)),
                    on_progress=lambda p: self._queue.put((EV_PROGRESS, p)),
                    cancel=lambda: self._cancelled,
                    paused=lambda: self._paused.is_set(),
                    **args,
                )
            except Exception as exc:  # noqa: BLE001 — страховка от падения потока
                job = Job(
                    input_path=Path(input_path),
                    stage=Stage.ERROR,
                    error=str(exc),
                )
            self._queue.put((EV_DONE, job))

        self._thread = threading.Thread(target=target, daemon=True)
        self._thread.start()