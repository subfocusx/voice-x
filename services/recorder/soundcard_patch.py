"""Runtime-патч soundcard для устройств с нестандартным mix-форматом.

soundcard 0.4.6 (mediafoundation-бэкенд) жёстко требует, чтобы mix-формат
устройства был WAVE_FORMAT_EXTENSIBLE (0xFFFE) с IEEE-float подформатом:

    _AudioClient.__init__ делает assert wFormatTag == 0xFFFE,
    затем assert cbSize == 22 и проверку SubFormat-подформата.

Некоторые устройства (Bluetooth/USB/виртуальные драйверы, Stereo-Mix-класса,
или сменившийся «формат по умолчанию» в Windows) отдают обычный WAVEFORMATEX
или расширяемый формат с другими полями — запись падает с AssertionError ещё
до открытия потока.

Патч перехватывает AssertionError из `_AudioClient.__init__` и сам достраивает
IEEE-float WAVEFORMATEXTENSIBLE (shared-режим: звуковой движок Windows сам
конвертирует/реэмплитрует в запрошенный формат), после чего вызывает
Initialize как в оригинале. Трасса чтения float32 у soundcard не меняется.
"""
from __future__ import annotations

import sys

from core.logging_setup import get_logger

log = get_logger("recorder.patch")

#: WAVE_FORMAT_EXTENSIBLE
_WAVE_FORMAT_EXTENSIBLE = 0xFFFE
#: KSDATAFORMAT_SUBTYPE_IEEE_FLOAT = {00000003-0000-0010-8000-00AA00389B71}
_KSDATAFORMAT_SUBTYPE_IEEE_FLOAT = (
    0x00000003, 0x0000, 0x0010, bytes((0x80, 0x00, 0xAA, 0x00, 0x38, 0x9B, 0x71, 0x00)),
)
#: streamflags из оригинала (autoconvert/resample/remix/nopersist)
_STREAMFLAGS = 0x00100000 | 0x80000000 | 0x08000000 | 0x00080000
_LOOPBACK_FLAG = 0x00020000
_AUDCLNT_SHAREMODE_SHARED = 0
_AUDCLNT_SHAREMODE_EXCLUSIVE = 1

#: каноничная маска каналов для моно/стерео
_CHANNEL_MASK = {1: 0x04, 2: 0x03}

_applied = False
#: ссылка на применённый враппер (для проверки идемпотентности в тестах)
_PATCHED_INIT = None


def _build_float_ieee(ffi, channels: int, samplerate: int):
    """IEEE-float WAVEFORMATEXTENSIBLE под запрошенный rate/каналы."""
    fmt = ffi.new("WAVEFORMATEXTENSIBLE *")
    f = fmt[0].Format
    f.wFormatTag = _WAVE_FORMAT_EXTENSIBLE
    f.nChannels = channels
    f.nSamplesPerSec = int(samplerate)
    f.nAvgBytesPerSec = int(samplerate) * channels * 4
    f.nBlockAlign = channels * 4
    f.wBitsPerSample = 32
    f.cbSize = 22
    fmt[0].Samples.wValidBitsPerSample = 32
    fmt[0].dwChannelMask = _CHANNEL_MASK.get(channels, (1 << channels) - 1)
    d1, d2, d3, d4 = _KSDATAFORMAT_SUBTYPE_IEEE_FLOAT
    fmt[0].SubFormat.Data1 = d1
    fmt[0].SubFormat.Data2 = d2
    fmt[0].SubFormat.Data3 = d3
    for i, b in enumerate(d4):
        fmt[0].SubFormat.Data4[i] = b
    return fmt


def _init_float_fallback(self, mf, samplerate, channels, blocksize, isloopback, exclusive_mode):
    """Завершить инициализацию `_AudioClient`, когда оригинал упал на assert."""
    ffi = mf._ffi
    ole32 = mf._ole32
    com = mf._com

    if not hasattr(self, "channelmap"):
        if isinstance(channels, int):
            self.channelmap = list(range(channels))
        else:
            self.channelmap = channels
    nch = len(set(self.channelmap))
    if blocksize is None:
        blocksize = self.deviceperiod[0] * samplerate

    ppMixFormat = ffi.new("WAVEFORMATEXTENSIBLE **")
    hr = self._ptr[0][0].lpVtbl.GetMixFormat(self._ptr[0], ppMixFormat)
    com.check_error(hr)

    fmt = _build_float_ieee(ffi, nch, int(samplerate))
    sharemode = _AUDCLNT_SHAREMODE_EXCLUSIVE if exclusive_mode else _AUDCLNT_SHAREMODE_SHARED
    streamflags = _STREAMFLAGS
    if isloopback:
        streamflags |= _LOOPBACK_FLAG
    bufferduration = int(blocksize / samplerate * 10_000_000)
    hr = self._ptr[0][0].lpVtbl.Initialize(
        self._ptr[0], sharemode, streamflags, bufferduration, 0, fmt, ffi.NULL
    )
    com.check_error(hr)
    ole32.CoTaskMemFree(ppMixFormat[0])

    self.samplerate = samplerate
    self._idle_start_time = None


def make_patched_init(mf, original_init):
    """Оригинальный `__init__` с фолбэком на AssertionError (для тестов)."""

    def patched(self, ptr, samplerate, channels, blocksize, isloopback, exclusive_mode=False):
        try:
            original_init(self, ptr, samplerate, channels, blocksize, isloopback, exclusive_mode)
        except AssertionError:
            log.warning(
                "soundcard: нестандартный mix-формат устройства — применяю float32-фолбэк"
            )
            _init_float_fallback(
                self, mf, samplerate, channels, blocksize, isloopback, exclusive_mode
            )

    return patched


def apply() -> None:
    """Применить патч к `soundcard.mediafoundation._AudioClient` (идемпотентно).

    Безопасно не на Windows и при отсутствии soundcard — приложение не падает.
    """
    global _applied, _PATCHED_INIT
    if _applied:
        return
    if sys.platform != "win32":
        _applied = True
        return
    try:
        import soundcard.mediafoundation as mf
    except Exception:
        log.warning("soundcard.mediafoundation недоступен — патч не применён")
        return

    original = mf._AudioClient.__init__
    if getattr(original, "__voicex_patched", False):
        _applied = True
        return
    _PATCHED_INIT = make_patched_init(mf, original)
    _PATCHED_INIT.__voicex_patched = True
    mf._AudioClient.__init__ = _PATCHED_INIT
    _applied = True
    log.info("soundcard patch applied (float32-fallback для нестандартных устройств)")