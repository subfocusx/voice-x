"""Устройства захвата (WASAPI) — перечисление и метки через soundcard.

soundcard 0.4.6 отдаёт `all_microphones(include_loopback=True)`: настоящие
микрофоны с `isloopback=False` плюс loopback-каждого устройства воспроизведения
с `isloopback=True`. Именно так и ловим «системный звук» (Google Meet/Zoom/браузер)
без внешних зависимостей вроде OBS.

Заметка на будущее: у объекта _Speaker в 0.4.6 НЕТ `.recorder()` — рабочий путь
только через `all_microphones(include_loopback=True)`.
"""
from __future__ import annotations

import ctypes
import threading
from typing import List, Optional

import soundcard as sc

KIND_MIC = "mic"
KIND_SYSTEM = "system"

#: человекочитаемые метки источников
KIND_LABEL = {
    KIND_MIC: "Микрофон",
    KIND_SYSTEM: "Системный звук",
}

#: выбор в UI: ключ -> описание источника
SOURCE_OPTIONS = {
    KIND_MIC: "Микрофон",
    KIND_SYSTEM: "Системный звук",
    "both": "Микрофон + система",
}

#: COM-инициализация на потоке (thread-local), чтобы не делать её многократно.
#: Главный поток держим STA ради Tk и drag&drop (см. app._init_main_thread_sta),
#: а любой поток, который трогает soundcard, переводим в MTA — без этого soundcard
#: на фоновом потоке видит 0 устройств.
_com_local = threading.local()
_COINIT_MTA = 0x0            # COINIT_MULTITHREADED
_RPC_E_CHANGED_MODE = -2147417850


def _ensure_com() -> None:
    """Гарантировать MTA-апартмент на текущем потоке (один раз на поток).

    Безопасно для уже инициализированного потока: если главный уже STA, вызов
    вернёт RPC_E_CHANGED_MODE и оставит апартмент как был (STA сохраняется).
    """
    if getattr(_com_local, "initialized", False):
        return
    try:
        ole32 = ctypes.WinDLL("ole32")
        hr = ole32.CoInitializeEx(None, _COINIT_MTA)
        # S_OK (0 / S_FALSE 1) — норм; RPC_E_CHANGED_MODE — уже есть апартмент
        # (например STA на главном), оставляем как есть.
        if hr not in (0, 1, _RPC_E_CHANGED_MODE):
            return
        _com_local.ole32 = ole32  # держим ссылку, чтобы апартмент жил
        _com_local.initialized = True
    except Exception:
        # COM может быть недоступен (например на не-Windows) — не мешаем работе
        _com_local.initialized = True


class CaptureDevice:
    """Одно устройство захвата: микрофон или loopback системного вывода."""

    __slots__ = ("kind", "name", "device", "is_default")

    def __init__(self, kind: str, name: str, device, is_default: bool = False):
        self.kind = kind
        self.name = name      # удобная метка для UI
        self.device = device  # soundcard Microphone (для открытия потока)
        self.is_default = is_default

    def __repr__(self) -> str:
        return f"<CaptureDevice {self.kind} {self.name!r} default={self.is_default}>"


def _default_ids():
    """id дефолтного микрофона и дефолтной колонки (для loopback)."""
    _ensure_com()
    try:
        mic = sc.default_microphone()
        mic_id = getattr(mic, "id", None)
    except Exception:
        mic_id = None
    try:
        spk = sc.default_speaker()
        spk_id = getattr(spk, "id", None)
    except Exception:
        spk_id = None
    return mic_id, spk_id


def list_sources() -> List[CaptureDevice]:
    """Все устройства захвата (mic + loopback системного вывода)."""
    _ensure_com()
    devices: List[CaptureDevice] = []
    mic_id, spk_id = _default_ids()
    try:
        mics = sc.all_microphones(include_loopback=True)
    except Exception:
        return devices
    for m in mics:
        is_lp = bool(getattr(m, "isloopback", False))
        kind = KIND_SYSTEM if is_lp else KIND_MIC
        dev_id = getattr(m, "id", None)
        default_id = spk_id if kind == KIND_SYSTEM else mic_id
        is_default = bool(dev_id is not None and dev_id == default_id)
        raw = getattr(m, "name", "") or ""
        devices.append(CaptureDevice(kind, _label(kind, raw), m, is_default))
    return devices


def _label(kind: str, raw_name: str) -> str:
    prefix = KIND_LABEL.get(kind, kind)
    return f"{prefix}: {raw_name}"


def devices_of(kind: str, sources: Optional[List[CaptureDevice]] = None) -> List[CaptureDevice]:
    """Устройства конкретного источника (mic/system)."""
    sources = sources if sources is not None else list_sources()
    return [d for d in sources if d.kind == kind]


def default_device(kind: str, sources: Optional[List[CaptureDevice]] = None) -> Optional[CaptureDevice]:
    """Дефолтное устройство для источника; None, если недоступно."""
    sources = sources if sources is not None else list_sources()
    sub = devices_of(kind, sources)
    if not sub:
        return None
    for d in sub:
        if d.is_default:
            return d
    return sub[0]
