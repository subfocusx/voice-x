"""AudioRecorder — служба локальной записи (services-слой, без GUI).

Полностью синхронный API: UI вызывает `start/stop/cancel` и сам опрашивает
`get_state()/get_levels()` в своём цикле (см. ui/recorder_panel.py). Захват идёт
в фоновом потоке; устройства и файлы закрываются корректно при любом исходе
(stop/cancel/ошибка). Записываем WAV (mono, int16, нативная частота) —
транскрайбер сам пересэмплирует в 16 кГц.

Состояние записи — `core.job.RecordingState`:
  IDLE → RECORDING → STOPPING → DONE | ERROR | CANCELLED
Транскрипция после DONE — отдельный процесс (Worker/transcriber), рекордер о
ней не знает.
"""
from __future__ import annotations

import threading
import time
import traceback
import wave
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from core.job import RecordingState
from core.logging_setup import get_logger
from core.paths import recordings_dir
from services import ffmpeg
from services.recorder import audio_capture

log = get_logger("recorder")

#: частота захвата (ffmpeg пересэмплирует в 16 кГц для ASR)
DEFAULT_SAMPLERATE = 48000


def _unwrap_device(dev):
    """AudioRecorder принимает высокоуровневые `CaptureDevice` (обёртка над
    soundcard). Низкоуровневому CaptureSession нужен сырой объект звуковой
    карты (с .recorder()) — достаём его из обёртки, а сырое устройство
    (например уже развёрнутое) пропускаем как есть."""
    if dev is None:
        return None
    inner = getattr(dev, "device", None)
    return inner if inner is not None else dev


class AudioRecorder:
    def __init__(self):
        self._state = RecordingState.IDLE
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._session: Optional[audio_capture.CaptureSession] = None
        self._stop_event = threading.Event()
        self._cancel_requested = False
        self._chunks: List[np.ndarray] = []
        self._levels = {audio_capture._MIC: 0.0, audio_capture._SYS: 0.0}
        self._source_kind = "mic"
        self.mic_device = None
        self.system_device = None
        self.samplerate = DEFAULT_SAMPLERATE
        self.save_mp3 = False
        self.error: Optional[str] = None
        self.last_path: Optional[Path] = None
        self.duration_sec: float = 0.0

    # ── состояние (thread-safe, читается из UI) ────────────────────────────
    def get_state(self) -> RecordingState:
        with self._lock:
            return self._state

    def get_levels(self) -> Dict[str, float]:
        with self._lock:
            return dict(self._levels)

    def is_busy(self) -> bool:
        return self.get_state() in (RecordingState.RECORDING, RecordingState.STOPPING)

    def is_recording(self) -> bool:
        return self.get_state() == RecordingState.RECORDING

    def _set_state(self, state: RecordingState) -> None:
        with self._lock:
            self._state = state
        log.info("recorder state -> %s", state.value)

    # ── управление ─────────────────────────────────────────────────────────
    def start(
        self,
        source_kind: str,
        *,
        mic_device=None,
        system_device=None,
        samplerate: int = DEFAULT_SAMPLERATE,
        save_mp3: bool = False,
    ) -> None:
        """Начать запись в фоновом потоке. Бросает, если уже идёт."""
        if self.is_busy():
            raise RuntimeError("запись уже идёт")
        # сброс от прошлой попытки
        self._source_kind = source_kind
        self.mic_device = mic_device
        self.system_device = system_device
        self.samplerate = samplerate
        self.save_mp3 = save_mp3
        self._chunks.clear()
        self.error = None
        self.last_path = None
        self.duration_sec = 0.0
        self._cancel_requested = False
        self._stop_event.clear()

        self._set_state(RecordingState.RECORDING)
        self._thread = threading.Thread(
            target=self._capture, daemon=True, name="voicex-recorder"
        )
        self._thread.start()

    def stop(self) -> None:
        """Остановить запись, сохранить WAV, перейти в DONE."""
        if self.get_state() != RecordingState.RECORDING:
            return
        self._cancel_requested = False
        self._set_state(RecordingState.STOPPING)
        self._stop_event.set()

    def cancel(self) -> None:
        """Отменить запись: без сохранения, перейти в CANCELLED."""
        if not self.is_busy():
            return
        self._cancel_requested = True
        self._set_state(RecordingState.STOPPING)
        self._stop_event.set()

    def wait(self, timeout: Optional[float] = None) -> bool:
        """Дождаться окончания захвата. True — поток завершён."""
        th = self._thread
        if th is None:
            return True
        th.join(timeout)
        return not th.is_alive()

    # ── фоновый поток ──────────────────────────────────────────────────────
    def _capture(self) -> None:
        session = audio_capture.CaptureSession(
            self._source_kind,
            mic_device=_unwrap_device(self.mic_device),
            system_device=_unwrap_device(self.system_device),
            samplerate=self.samplerate,
        )
        self._session = session
        start = time.monotonic()
        try:
            session.open()
            while not self._stop_event.is_set():
                mono, levels = session.read()
                self._chunks.append(np.ascontiguousarray(mono))
                with self._lock:
                    self._levels = levels
        except audio_capture.SourceUnavailableError as exc:
            log.error("recorder: %s", exc)
            self.error = str(exc)
            self._set_state(RecordingState.ERROR)
            return
        except Exception as exc:  # noqa: BLE001 — показать причину в UI
            log.error("recorder capture error:\n%s", traceback.format_exc())
            self.error = str(exc)
            self._set_state(RecordingState.ERROR)
            return
        finally:
            try:
                if session is not None:
                    session.close()
            except Exception:
                log.warning("recorder close failed")
            self._session = None

        self.duration_sec = time.monotonic() - start
        if self._cancel_requested:
            log.info("recorder: cancelled (no file)")
            self._set_state(RecordingState.CANCELLED)
            return

        try:
            path = self._write_wav()
        except Exception as exc:  # noqa: BLE001
            log.error("recorder write wav failed:\n%s", traceback.format_exc())
            self.error = str(exc)
            self._set_state(RecordingState.ERROR)
            return
        self.last_path = path
        if self.save_mp3:
            try:
                ffmpeg.wav_to_mp3(path)
            except Exception as exc:  # noqa: BLE001 — MP3 необязательный, не роняем
                log.warning("recorder: mp3 conversion failed: %s", exc)
        log.info("recorder: saved %s (%.2fs)", path, self.duration_sec)
        self._set_state(RecordingState.DONE)

    # ── файл ───────────────────────────────────────────────────────────────
    def _write_wav(self) -> Path:
        if not self._chunks:
            raise RuntimeError("нет записанных данных")
        mono = np.concatenate(self._chunks).astype(np.float32)
        ints = (np.clip(mono, -1.0, 1.0) * 32767.0).astype(np.int16)
        out_dir = recordings_dir()
        stem = "rec_" + time.strftime("%Y%m%d_%H%M%S")
        path = out_dir / f"{stem}.wav"
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)          # int16
            w.setframerate(self.samplerate)
            w.writeframes(ints.tobytes())
        return path
