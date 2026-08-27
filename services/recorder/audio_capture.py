"""Захват аудио: микрофон и/или системный loopback (soundcard/WASAPI).

`CaptureSession` открывает один или два потока (mic / system) и отдаёт моно-
блоки float32 в диапазоне примерно [-1, 1] плюс пиковые уровни по каждому
источнику. Это низкоуровневый слой: без потоков, без записи на диск —
только чтение из устройств.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np

from core.logging_setup import get_logger
from services.recorder import wasapi

log = get_logger("recorder.capture")


class SourceUnavailableError(RuntimeError):
    """Нет устройства нужного типа (микрофон или системный loopback)."""


#: имя источника в уровнях
_MIC = wasapi.KIND_MIC
_SYS = wasapi.KIND_SYSTEM


class CaptureSession:
    """Открывает потоки захвата и читает из них моно-блоки.

    source_kind: "mic" | "system" | "both". Передаваемые `mic_device` /
    `system_device` — объекты soundcard; если None, берётся дефолт.
    """

    def __init__(
        self,
        source_kind: str,
        *,
        mic_device=None,
        system_device=None,
        samplerate: int = 48000,
        channels: int = 1,
        blocksize: int = 1024,
    ):
        self.source_kind = source_kind
        self.mic_device = mic_device
        self.system_device = system_device
        self.samplerate = samplerate
        self.channels = channels
        self.blocksize = blocksize
        self._recs: List[Tuple[str, str, object]] = []  # (kind, name, recorder)
        self._opened = False

    # ── открытие ───────────────────────────────────────────────────────────
    def open(self) -> None:
        if self._opened:
            return
        # open() всегда выполняется на фоновом потоке (voicex-recorder).
        # Когда устройство передано явно, резолв идёт напрямую (без
        # list_sources/default_device) и COM на этом потоке не инициализирован —
        # из-за этого CoCreateInstance в soundcard падает с CO_E_NOTINITIALIZED
        # (0x800401F0). Гарантируем MTA-апартмент на текущем потоке.
        wasapi._ensure_com()
        mic = self._resolve_mic(self._needs_mic())
        system = self._resolve_system(self._needs_system())
        if self._needs_mic() and mic is None:
            raise SourceUnavailableError("Микрофон не найден — проверьте устройства записи")
        if self._needs_system() and system is None:
            raise SourceUnavailableError(
                "Системное устройство (loopback) не найдено. Нужен WASAPI-выход."
            )
        try:
            if mic is not None:
                self._open_recorder(_MIC, mic)
            if system is not None:
                self._open_recorder(_SYS, system)
        except Exception:
            self.close()
            raise
        self._opened = True
        log.info("capture open | kind=%s rate=%d ch=%d", self.source_kind,
                 self.samplerate, self.channels)

    def _needs_mic(self) -> bool:
        return self.source_kind in (_MIC, "both")

    def _needs_system(self) -> bool:
        return self.source_kind in (_SYS, "both")

    def _open_recorder(self, kind: str, device) -> None:
        name = getattr(device, "name", None) or kind
        rec = device.recorder(
            samplerate=self.samplerate,
            channels=self.channels,
            blocksize=self.blocksize,
        )
        rec.__enter__()  # держим поток открытым между вызовами read()
        self._recs.append((kind, name, rec))

    # ── резолв дефолтных устройств ─────────────────────────────────────────
    def _resolve_mic(self, needed: bool):
        if not needed:
            return None
        if self.mic_device is not None:
            return self.mic_device
        return wasapi.default_device(_MIC).device if wasapi.default_device(_MIC) else None

    def _resolve_system(self, needed: bool):
        if not needed:
            return None
        if self.system_device is not None:
            return self.system_device
        return wasapi.default_device(_SYS).device if wasapi.default_device(_SYS) else None

    # ── чтение ─────────────────────────────────────────────────────────────
    def read(self) -> Tuple[np.ndarray, Dict[str, float]]:
        """Один блок: (мono float32, levels {'mic','system'} — пиковые 0..1)."""
        if not self._opened:
            raise RuntimeError("capture session not opened")
        levels = {_MIC: 0.0, _SYS: 0.0}
        mono_parts: List[np.ndarray] = []
        for kind, _name, rec in self._recs:
            block = rec.record(numframes=self.blocksize)
            if block is None or block.size == 0:
                continue
            b = block.astype(np.float32)
            if b.ndim == 2 and b.shape[1] > 1:
                mono = b.mean(axis=1)
            else:
                mono = b.reshape(-1)
            peak = float(np.abs(mono).max()) if mono.size else 0.0
            levels[kind] = peak
            mono_parts.append(mono)

        if not mono_parts:
            return np.zeros(self.blocksize, dtype=np.float32), levels

        if len(mono_parts) == 1:
            mixed = mono_parts[0]
        else:
            # «оба»: мягкий микс (среднее) — не даёт клипа при наложении
            n = min(x.size for x in mono_parts)
            mixed = sum(x[:n] for x in mono_parts) / len(mono_parts)
        return mixed, levels

    # ── закрытие ───────────────────────────────────────────────────────────
    def close(self) -> None:
        for _kind, _name, rec in self._recs:
            try:
                rec.__exit__(None, None, None)
            except Exception:
                pass
        self._recs.clear()
        self._opened = False
        log.info("capture closed")
