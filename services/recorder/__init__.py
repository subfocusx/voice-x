"""Локальный аудиорекордер Voice-X.

Пакет `services/recorder` — служба захвата звука с микрофона и/или
системного аудио (WASAPI-loopback). Никакой привязки к GUI: UI сам
опрашивает состояние через `AudioRecorder.get_state()/get_levels()`, а фоновый
поток записи не трогает виджеты.
"""
from services.recorder.audio_capture import CaptureSession, SourceUnavailableError
from services.recorder.recorder import AudioRecorder
from services.recorder.wasapi import (
    KIND_MIC, KIND_SYSTEM, CaptureDevice, default_device, devices_of,
    list_sources,
)

__all__ = [
    "AudioRecorder",
    "CaptureSession",
    "SourceUnavailableError",
    "CaptureDevice",
    "list_sources",
    "devices_of",
    "default_device",
    "KIND_MIC",
    "KIND_SYSTEM",
]
