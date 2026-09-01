"""Обёртка над ffmpeg/ffprobe: декодирование аудио в wav-16k-mono и длина файла.

Логика взята из проверенного пайплайна writher (test_gigaam.py + asr_engine.py):
декод через ffmpeg в pcm_s16le 16000/1, чтение через numpy.
Ошибки ffmpeg/ffprobe логируются в voicex.ffmpeg (см. core/logging_setup.py).
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
import wave
from pathlib import Path
from uuid import uuid4

import numpy as np

from core.logging_setup import get_logger

SAMPLE_RATE = 16000
log = get_logger("ffmpeg")

#: Расширения, которые берём на расшифровку (всё, что ffmpeg умеет декодировать).
ACCEPTED_EXTENSIONS = {
    ".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wma", ".amr",
    ".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".ts", ".m4v", ".3gp", ".wmv",
}


def is_supported(path: "str | Path") -> bool:
    """Проверяем расширение (регистронезависимо)."""
    return Path(path).suffix.lower() in ACCEPTED_EXTENSIONS


# ── поиск бинаря ────────────────────────────────────────────────────────────
def _find(name: str) -> str:
    """Найти ffmpeg/ffprobe: забандленный (frozen), WinGet-линки, потом PATH."""
    with_ext = name + (".exe" if os.name == "nt" else "")

    # 1) забандленный рядом с exe/распаковкой (приоритет в frozen-сборке)
    from core.paths import resource_dir
    bundled = resource_dir() / "bin" / with_ext
    if bundled.exists():
        return str(bundled)

    winlinks = Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Links"
    if (winlinks / with_ext).exists():
        return str(winlinks / with_ext)

    path_var = os.environ.get("PATH", "")
    for d in path_var.split(os.pathsep):
        if not d:
            continue
        cand = Path(d) / with_ext
        if cand.exists():
            return str(cand)

    return with_ext  # не нашли — вернём голое имя, ошибка проявится на запуске


_FFMPEG = _find("ffmpeg")
_FFPROBE = _find("ffprobe")


def ffmpeg_bin() -> str:
    return _FFMPEG


def ffprobe_bin() -> str:
    return _FFPROBE


def available() -> tuple[bool, str]:
    """ffmpeg/ffprobe на месте?"""
    if not Path(_FFMPEG).exists() or not Path(_FFPROBE).exists():
        log.warning("ffmpeg/ffprobe не найдены (fg=%s fp=%s)", _FFMPEG, _FFPROBE)
        return False, "ffmpeg/ffprobe не найдены на PATH"
    return True, ""


# ── probe: длительность ─────────────────────────────────────────────────────
def probe_duration(path: str | Path) -> float:
    """Длительность медиа в секундах через ffprobe."""
    r = subprocess.run(
        [
            _FFPROBE, "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        log.error("ffprobe failed on %s: %s", path, r.stderr.strip())
        raise RuntimeError(f"ffprobe failed: {r.stderr.strip()}")
    m = re.search(r"(\d+(?:\.\d*)?)", r.stdout.strip())
    return float(m.group(1)) if m else 0.0


# ── декод ───────────────────────────────────────────────────────────────────
def extract_audio_wav(src: Path, dst: Path) -> None:
    """Аудио/видео -> wav (16 бит, 16000 Гц, моно) через ffmpeg."""
    r = subprocess.run(
        [
            _FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(src), "-ar", str(SAMPLE_RATE), "-ac", "1",
            "-acodec", "pcm_s16le", str(dst),
        ],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        log.error("ffmpeg audio extraction failed for %s: %s", src, r.stderr.strip())
        raise RuntimeError(f"ffmpeg audio extraction failed: {r.stderr.strip()}")


def wav_to_waveform(wav_path: Path) -> np.ndarray:
    """wav pcm_s16le -> float32 [-1..1]."""
    with wave.open(str(wav_path), "rb") as wf:
        if wf.getframerate() != SAMPLE_RATE:
            # редкий случай — перекодируем в ожидаемую частоту
            log.error("wav %s: expected %s Hz, got %s",
                      wav_path, SAMPLE_RATE, wf.getframerate())
            raise RuntimeError(f"expected {SAMPLE_RATE} Hz, got {wf.getframerate()}")
        raw = wf.readframes(wf.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def load_waveform_16k(path: Path, workdir: Path | None = None) -> tuple[np.ndarray, float]:
    """Файл (аудио/видео) -> float32-волна 16kHz + длительность в секундах.

    Промежуточный wav создаётся во временной папке и удаляется.
    """
    tmp = (workdir or Path(tempfile.gettempdir())) / f"voicex_{uuid4().hex[:8]}.wav"
    try:
        extract_audio_wav(path, tmp)
        waveform = wav_to_waveform(tmp)
        log.info("decoded %s -> %.2fs (%d samples)", path,
                 len(waveform) / SAMPLE_RATE, len(waveform))
        return waveform, len(waveform) / SAMPLE_RATE
    finally:
        tmp.unlink(missing_ok=True)


def wav_to_mp3(wav_path: Path, *, bitrate: str = "192k") -> Path:
    """Конвертировать wav в mp3 (рядом, то же имя) через ffmpeg.

    Возвращает путь к созданному mp3; при ошибке бросает RuntimeError.
    """
    mp3_path = wav_path.with_suffix(".mp3")
    r = subprocess.run(
        [
            _FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(wav_path), "-codec:a", "libmp3lame", "-b:a", bitrate, str(mp3_path),
        ],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        log.error("ffmpeg mp3 conversion failed for %s: %s", wav_path, r.stderr.strip())
        raise RuntimeError(f"ffmpeg mp3 conversion failed: {r.stderr.strip()}")
    log.info("mp3 saved: %s", mp3_path)
    return mp3_path
