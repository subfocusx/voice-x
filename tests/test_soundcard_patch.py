"""Тесты float32-фолбэка soundcard (без реального звукового железа).

Фолбэк (services.recorder.soundcard_patch._init_float_fallback) использует
только три «природных» точки: `mf._ffi` (построение WAVEFORMATEXTENSIBLE),
vtable устройства (`self._ptr[0][0].lpVtbl.*`) и `mf._com`/`mf._ole32`.
В тестах подставляем pure-Python заменители этих точек: реальный `ffi`
для построения формата (чистая память, никаких COM-вызовов), Python-ским
для vtable и ole32/com. Это стабильно работает под pytest/cov, где нативные
cffi-callback'и в vtable могут валиться access violation.
"""
from __future__ import annotations

import sys
import types

import pytest

from services.recorder import soundcard_patch
from services.recorder.audio_capture import CaptureSession, SourceUnavailableError

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="soundcard/COM только на Windows")


# ── pure-Python «устройство» с vtable, с фейками ffi/ole32/com ───────────────
class _DeviceShim:
    """"IAudioClient" на чистом Python: GetMixFormat отдаёт PCM, Initialize запоминает."""

    def __init__(self):
        self.mix_format_sent = 0xFFFE  # во что просим устройство
        self.init_calls = []
        self.freed = []
        self._ffi = None

    def _set_ffi(self, ffi):
        self._ffi = ffi

    def get_mix_format(self, out):
        p = self._ffi.new("WAVEFORMATEXTENSIBLE *")
        p[0].Format.wFormatTag = 1  # PCM — не EXTENSIBLE, оригинал завалится на assert
        out[0] = p
        return 0

    def initialize(self, sharemode, streamflags, bufferduration, fmt, guid):
        self.init_calls.append(
            {
                "sharemode": sharemode,
                "streamflags": streamflags,
                "bufferduration": bufferduration,
                "wFormatTag": fmt[0].Format.wFormatTag,
                "cbSize": fmt[0].Format.cbSize,
                "nChannels": fmt[0].Format.nChannels,
                "nSamplesPerSec": fmt[0].Format.nSamplesPerSec,
                "wBitsPerSample": fmt[0].Format.wBitsPerSample,
                "nBlockAlign": fmt[0].Format.nBlockAlign,
                "subformat_data1": fmt[0].SubFormat.Data1,
                "guid_null": guid == self._ffi.NULL,
            }
        )
        return 0


class _Vtable:
    def __init__(self, device: "DeviceShim"):
        self._device = device

    def GetMixFormat(self, client, out):
        return self._device.get_mix_format(out)

    def Initialize(self, client, sharemode, streamflags, bufferduration, period, fmt, guid):
        return self._device.initialize(sharemode, streamflags, bufferduration, fmt, guid)


class _Client:
    def __init__(self, device):
        self.lpVtbl = _Vtable(device)

    def __getitem__(self, _i):
        return self


class _Ptr:
    def __init__(self, device):
        self._dev = device

    def __getitem__(self, _i):
        return _Client(self._dev)


def _real_ffi():
    return pytest.importorskip("soundcard.mediafoundation")._ffi


def _fake_mf(device):
    ffi = _real_ffi()
    device._set_ffi(ffi)

    class _Com:
        @staticmethod
        def check_error(hr):
            if hr < 0:
                raise RuntimeError(f"HRESULT 0x{hr & 0xFFFFFFFF:08X}")

    class _Ole32:
        @staticmethod
        def CoTaskMemFree(p):
            device.freed.append(p)

    return types.SimpleNamespace(_ffi=ffi, _com=_Com(), _ole32=_Ole32())


def _fake_original(device, *, fail_with=None):
    def original(self, ptr, samplerate, channels, blocksize, isloopback, exclusive_mode=False):
        if fail_with is not None:
            raise fail_with
        raise AssertionError("wFormatTag != 0xFFFE")

    return original


class _FakeClientHost:
    """Эмуляция объекта _AudioClient: без channelmap, устройство доступно через _ptr."""

    def __init__(self, device):
        self._ptr = _Ptr(device)
        self.deviceperiod = (self._ptr,)


# ── сам фолбэк ───────────────────────────────────────────────────────────────
def test_build_float_ieee_shape():
    ffi = _real_ffi()
    fmt = soundcard_patch._build_float_ieee(ffi, 1, 48000)
    f = fmt[0].Format
    assert f.wFormatTag == 0xFFFE
    assert f.cbSize == 22
    assert f.nChannels == 1
    assert f.nSamplesPerSec == 48000
    assert f.wBitsPerSample == 32
    assert f.nAvgBytesPerSec == 48000 * 4
    assert fmt[0].Samples.wValidBitsPerSample == 32
    assert fmt[0].SubFormat.Data1 == 0x00000003  # KSDATAFORMAT_SUBTYPE_IEEE_FLOAT


def test_fallback_builds_float_format_and_initializes():
    device = _DeviceShim()
    mf = _fake_mf(device)
    host = _FakeClientHost(device)
    soundcard_patch._init_float_fallback(host, mf, 48000, 1, 1024, False, False)

    assert host.samplerate == 48000
    assert host.channelmap == [0]
    assert host._idle_start_time is None

    assert len(device.init_calls) == 1
    call = device.init_calls[0]
    assert call["sharemode"] == 0                                    # shared
    assert call["bufferduration"] == int(1024 / 48000 * 10_000_000)
    assert call["wFormatTag"] == 0xFFFE                              # EXTENSIBLE
    assert call["cbSize"] == 22
    assert call["nChannels"] == 1
    assert call["nSamplesPerSec"] == 48000
    assert call["wBitsPerSample"] == 32
    assert call["subformat_data1"] == 0x00000003                     # IEEE_FLOAT
    assert call["guid_null"] is True
    assert call["streamflags"] & 0x00020000 == 0                     # без loopback
    # mix-формат устройства освобождён
    assert len(device.freed) == 1


def test_fallback_sets_loopback_flag():
    device = _DeviceShim()
    mf = _fake_mf(device)
    host = _FakeClientHost(device)
    soundcard_patch._init_float_fallback(host, mf, 48000, 1, 1024, True, False)
    assert device.init_calls[0]["streamflags"] & 0x00020000 != 0


def test_fallback_stereo_channelmap_kept():
    device = _DeviceShim()
    mf = _fake_mf(device)
    host = _FakeClientHost(device)
    host.channelmap = [0, 1]
    soundcard_patch._init_float_fallback(host, mf, 48000, [0, 1], 1024, False, False)
    call = device.init_calls[0]
    assert call["nChannels"] == 2
    assert call["nBlockAlign"] == 8  # стерео


def test_fallback_raises_on_initialize_error():
    device = _DeviceShim()
    device.initialize = lambda *a: -1     # AUDCLNT_E_UNSUPPORTED_FORMAT
    mf = _fake_mf(device)
    host = _FakeClientHost(device)
    with pytest.raises(RuntimeError, match="HRESULT 0xFFFFFFFF"):
        soundcard_patch._init_float_fallback(host, mf, 48000, 1, 1024, False, False)


# ── обёртка make_patched_init ────────────────────────────────────────────────
def test_patched_init_falls_back_when_original_asserts():
    device = _DeviceShim()
    mf = _fake_mf(device)
    patched = soundcard_patch.make_patched_init(
        mf, _fake_original(device, fail_with=AssertionError("boom"))
    )
    # обычный (не патченный) путь: если AssertionError всплыл — тест сломан
    client = _fake_patched_client(patched, device)
    assert client.samplerate == 48000
    assert device.init_calls and device.init_calls[0]["wFormatTag"] == 0xFFFE


def _fake_patched_client(patched, device):
    host = _FakeClientHost(device)
    patched(host, host._ptr, 48000, 1, 1024, False)
    return host


def test_patched_init_reraises_non_assert_errors():
    device = _DeviceShim()
    mf = _fake_mf(device)
    patched = soundcard_patch.make_patched_init(
        mf, _fake_original(device, fail_with=ValueError("нет устройства"))
    )
    host = _FakeClientHost(device)
    with pytest.raises(ValueError, match="нет устройства"):
        patched(host, host._ptr, 48000, 1, 1024, False)


def test_apply_is_idempotent():
    mf = pytest.importorskip("soundcard.mediafoundation")
    soundcard_patch.apply()
    soundcard_patch.apply()
    assert soundcard_patch._PATCHED_INIT is not None
    assert mf._AudioClient.__init__ is soundcard_patch._PATCHED_INIT


# ── ошибка открытия с именем устройства ─────────────────────────────────────
class _BrokenDev:
    name = "Микрофон: Bluetooth-гарнитура"

    def recorder(self, **kwargs):
        raise AssertionError("wFormatTag != 0xFFFE")


def test_open_recorder_friendly_error():
    session = CaptureSession("mic", mic_device=_BrokenDev())
    with pytest.raises(SourceUnavailableError) as exc_info:
        session._open_recorder("mic", _BrokenDev())
    msg = str(exc_info.value)
    assert "Bluetooth-гарнитура" in msg
    assert "Параметры → Звук" in msg


def test_open_recorder_failure_name_fallback():
    """Устройство без .name — используем метку источника."""

    class NoNameDev:
        def recorder(self, **kwargs):
            raise RuntimeError("boom")

    session = CaptureSession("mic", mic_device=NoNameDev())
    with pytest.raises(SourceUnavailableError) as exc_info:
        session._open_recorder("mic", NoNameDev())
    assert "Микрофон" in str(exc_info.value)