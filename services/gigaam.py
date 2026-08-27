"""GigaAM v3 E2E CTC (int8) через onnx-asr — русскоязычное распознавание.

Повторяет проверенную логику распознавания:
частьями по 30 сек, load_model c quantization="int8" на CPU.
Логирование — через общий логгер voicex (см. core/logging_setup.py).
"""
from __future__ import annotations

import hashlib  # noqa: F401  (резерв, может пригодиться для кэша)
import os
import threading
import time
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from core.logging_setup import get_logger
from .engine import EngineInterface

CHUNK_SECONDS = 30  # максимум на один вызов recognize (обходим проблему длинного аудио)
log = get_logger("gigaam")


class GigaAMEngine(EngineInterface):
    name = "gigaam"

    def __init__(self, model_dir: str | None = None, sample_rate: int = 16000):
        self._model_dir = Path(model_dir) if model_dir else None
        self._sample_rate = sample_rate
        self._asr = None
        self._lock = threading.Lock()

    # ── модель ────────────────────────────────────────────────────────────
    def _resolve_model_dir(self) -> Path:
        if self._model_dir and Path(self._model_dir).exists():
            return self._model_dir
        # забандленная модель (frozen-сборка)
        from core.paths import resource_dir
        bundled = resource_dir() / "models"
        if bundled.exists():
            return bundled
        # HF-кэш (fallback при отсутствии локальной папки)
        return (
            Path.home()
            / ".cache" / "huggingface"
            / "models--istupakov--gigaam-v3-onnx-int8"
        )

    def load(self) -> None:
        if self._asr is not None:
            return
        with self._lock:
            if self._asr is not None:
                return
            from onnx_asr import load_model

            _register_cuda_dll_paths()
            log.info("loading model from %s", self._resolve_model_dir())
            self._asr = load_model(
                "gigaam-v3-e2e-ctc",
                path=str(self._resolve_model_dir()),
                quantization="int8",
                providers=["CPUExecutionProvider"],
            )
            log.info("model loaded")

    # ── распознавание ─────────────────────────────────────────────────────
    def transcribe(
        self,
        audio: np.ndarray,
        sample_rate: int,
        progress: Optional[Callable[[float], None]] = None,
        cancel: Optional[Callable[[], bool]] = None,
        paused: Optional[Callable[[], bool]] = None,
    ) -> str:
        self.load()
        duration = len(audio) / sample_rate

        if duration <= CHUNK_SECONDS:
            if progress:
                progress(1.0)
            return self._asr.recognize(audio, sample_rate=sample_rate)

        # — длинное аудио: чанками по 30 сек, с прогрессом и отменой/паузой
        chunk_size = int(CHUNK_SECONDS * sample_rate)
        texts: list[str] = []
        n = max(1, (len(audio) + chunk_size - 1) // chunk_size)

        for i in range(0, len(audio), chunk_size):
            if cancel and cancel():
                log.info("cancelled by user (chunk %s/%s)", i // chunk_size + 1, n)
                return " ".join(texts)
            while paused and paused():
                log.info("paused (chunk %s/%s)", i // chunk_size + 1, n)
                time.sleep(0.2)
                if cancel and cancel():
                    log.info("cancelled while paused (chunk %s/%s)",
                             i // chunk_size + 1, n)
                    return " ".join(texts)
            chunk = audio[i:i + chunk_size]
            piece = self._asr.recognize(chunk, sample_rate=sample_rate)
            texts.append(piece.strip())
            if progress:
                progress(min(1.0, (i + chunk_size) / len(audio)))

        return " ".join(t for t in texts if t)


# ── DLL-регистрация CUDA (Windows, скопировано из asr_engine.py) ────────────
def _register_cuda_dll_paths() -> None:
    import site
    import sys

    candidates: list[str] = []
    candidates += list(getattr(site, "getsitepackages", lambda: [])())
    candidates.append(Path(__file__).resolve().parent.parent)  # корень проекта
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(meipass)
    if getattr(sys, "frozen", False):
        candidates.append(os.path.dirname(sys.executable))

    seen: set[str] = set()
    for site_dir in candidates:
        if not site_dir:
            continue
        for pkg in ("cublas", "cuda_runtime", "cuda_nvrtc"):
            bin_dir = os.path.join(site_dir, "nvidia", pkg, "bin")
            if bin_dir not in seen:
                seen.add(bin_dir)
            if os.path.isdir(bin_dir):
                os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
                try:
                    os.add_dll_directory(bin_dir)
                except (OSError, AttributeError):
                    pass
