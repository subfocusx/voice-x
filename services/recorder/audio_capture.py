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

#: человекочитаемые метки источника для сообщений об ошибке
_KIND_LABEL = {_MIC: "Микрофон", _SYS: "Системный звук"}


def _open_error_text(name: str, exc: Exception) -> str:
    """Понятное сообщение об ошибке открытия устройства."""
    return (
        f"Не удалось открыть «{name}» ({exc}). "
        "Проверьте устройство по умолчанию (Параметры → Звук → Ввод) "
        "или выберите другое устройство из списка."
    )


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
        name = getattr(device, "name", None) or _KIND_LABEL.get(kind, kind)
        try:
            rec = device.recorder(
                samplerate=self.samplerate,
                channels=self.channels,
                blocksize=self.blocksize,
            )
            rec.__enter__()  # держим поток открытым между вызовами read()
        except Exception as exc:  # noqa: BLE001 — показываем причину в UI
            log.error("open recorder failed kind=%s dev=%s: %s", kind, name, exc)
            raise SourceUnavailableError(_open_error_text(name, exc))
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
    def read(self) -> "Tuple[np.ndarray, np.ndarray, Dict[str, float]]":
        """Один блок: (mic float32, sys float32, levels {'mic','system'} — пиковые 0..1).

        Каналы микрофона и системного звука возвращаются РАЗДЕЛЬНО (не
        миксованные) — смешивание с усилением/лимитером делает AudioRecorder
        при записи (_write_wav). Когда соответствующего источника нет —
        канал заполняется нулями той же формы, что и наличный блок.
        """
        if not self._opened:
            raise RuntimeError("capture session not opened")
        levels = {_MIC: 0.0, _SYS: 0.0}
        parts: Dict[str, np.ndarray] = {}
        max_len = 0
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
            parts[kind] = mono
            max_len = max(max_len, mono.size)

        if not parts:
            zero = np.zeros(self.blocksize, dtype=np.float32)
            return zero, zero, levels

        mic = parts.get(_MIC)
        sys = parts.get(_SYS)
        if mic is None:
            mic = np.zeros(max_len, dtype=np.float32)
        if sys is None:
            sys = np.zeros(max_len, dtype=np.float32)
        # одинаковый размер для честного поканального суммирования
        n = min(mic.size, sys.size)
        return mic[:n], sys[:n], levels

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
