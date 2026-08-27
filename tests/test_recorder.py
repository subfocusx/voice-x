"""Хардвар-агностичные тесты рекордера Voice-X.

Не трогаем реальные устройства захвата (звук в CI/песочнице может быть
недоступен): проверяем перечисление/фильтрацию устройств на ручных данных,
конвертацию wav->mp3 на синтезированном файле и модель состояний.
"""
from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

import numpy as np
import pytest

from core.job import RecordingState, RECORDING_STATE_LABEL
from services.ffmpeg import available as ffmpeg_available
from services.ffmpeg import wav_to_mp3
from services.recorder import (
    KIND_MIC,
    KIND_SYSTEM,
    CaptureDevice,
    default_device,
    devices_of,
)
from services.recorder.wasapi import SOURCE_OPTIONS


# ── вспомогательный синтез wav ──────────────────────────────────────────────
def _write_sine_wav(path: Path, *, seconds: float = 1.0, rate: int = 48000,
                    freq: float = 440.0) -> Path:
    """Пишем моно 16-bit wav с синусом — без требований к реальному звуку."""
    n = int(seconds * rate)
    t = np.arange(n, dtype=np.float64) / rate
    samples = (0.5 * np.sin(2 * math.pi * freq * t))
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(pcm.tobytes())
    return path


# ── модель состояний ────────────────────────────────────────────────────────
def test_recording_state_enum_members():
    assert RecordingState.IDLE.value == "idle"
    assert RecordingState.RECORDING.value == "recording"
    assert RecordingState.STOPPING.value == "stopping"
    assert RecordingState.DONE.value == "done"
    assert RecordingState.ERROR.value == "error"
    assert RecordingState.CANCELLED.value == "cancelled"
    # все состояния — строковые enum
    for s in RecordingState:
        assert isinstance(s.value, str)


def test_recording_state_labels_cover_all_states():
    for s in RecordingState:
        assert s in RECORDING_STATE_LABEL
        assert isinstance(RECORDING_STATE_LABEL[s], str) and RECORDING_STATE_LABEL[s]


def test_source_options_contains_both():
    assert set(SOURCE_OPTIONS) == {KIND_MIC, KIND_SYSTEM, "both"}


# ── helpers устройств (без обращения к soundcard) ────────────────────────────
def _dummy_sources():
    # kind, name, device, is_default
    return [
        CaptureDevice(KIND_SYSTEM, "Система: Динамики (loopback)", "loop_1", True),
        CaptureDevice(KIND_SYSTEM, "Система: Монитор (loopback)", "loop_2", False),
        CaptureDevice(KIND_MIC, "Микрофон: Realtek", "mic_1", True),
        CaptureDevice(KIND_MIC, "Микрофон: Webcam", "mic_2", False),
    ]


def test_devices_of_filters_by_kind():
    srcs = _dummy_sources()
    sys_devs = devices_of(KIND_SYSTEM, srcs)
    mic_devs = devices_of(KIND_MIC, srcs)
    assert all(d.kind == KIND_SYSTEM for d in sys_devs)
    assert len(sys_devs) == 2
    assert all(d.kind == KIND_MIC for d in mic_devs)
    assert len(mic_devs) == 2


def test_default_device_prefers_is_default():
    srcs = _dummy_sources()
    d = default_device(KIND_SYSTEM, srcs)
    assert d is not None and d.is_default and d.name == "Система: Динамики (loopback)"
    d2 = default_device(KIND_MIC, srcs)
    assert d2 is not None and d2.is_default and d2.name == "Микрофон: Realtek"


def test_default_device_empty_returns_none():
    assert default_device(KIND_SYSTEM, []) is None
    # источник есть, но без нужного kind
    assert default_device(KIND_SYSTEM, _dummy_sources()) is not None
    only_mic = [CaptureDevice(KIND_MIC, "Микрофон: X", "m", True)]
    assert default_device(KIND_SYSTEM, only_mic) is None


def test_capture_device_repr_smoke():
    d = CaptureDevice(KIND_MIC, "Микрофон: X", "dev", True)
    assert "default=True" in repr(d)
    assert "mic" in repr(d)


def test_unwrap_device_pulls_raw_from_wrapper():
    """AudioRecorder принимает CaptureDevice-обёртки, но низкоуровневому
    CaptureSession нужен сырой soundcard-объект (с .recorder()) — проверяем,
    что развёртка не теряется (регрессия на границе recorder/capture)."""
    from services.recorder.recorder import _unwrap_device

    raw = object()
    d = CaptureDevice(KIND_MIC, "Микрофон: X", raw, True)
    assert _unwrap_device(d) is raw       # обёртка -> сырое устройство
    assert _unwrap_device(raw) is raw     # уже сырое — как есть
    assert _unwrap_device(None) is None


# ── wav -> mp3 (требует ffmpeg) ─────────────────────────────────────────────
def test_wav_to_mp3(owned_tmp_path):
    if not ffmpeg_available()[0]:
        pytest.skip("ffmpeg/ffprobe недоступны — пропускаем mp3-конвертацию")
    src = _write_sine_wav(owned_tmp_path / "tone.wav")
    mp3 = wav_to_mp3(src, bitrate="128k")
    assert mp3.exists()
    assert mp3.stat().st_size > 0
    assert mp3.suffix == ".mp3"
    assert mp3.name == "tone.mp3"
    # исходник не тронут
    assert src.exists()


def test_wav_to_mp3_fails_on_missing_input(owned_tmp_path):
    if not ffmpeg_available()[0]:
        pytest.skip("ffmpeg/ffprobe недоступны — пропускаем mp3-конвертацию")
    with pytest.raises(RuntimeError):
        wav_to_mp3(owned_tmp_path / "no_such.wav")
