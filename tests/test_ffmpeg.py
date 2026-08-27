"""Юнит-тесты поддержки расширений (ffmpeg.is_supported)."""
from __future__ import annotations

import pytest

from services import ffmpeg


@pytest.mark.parametrize("ext,expected", [
    (".mp3", True),
    (".MP3", True),
    (".wav", True),
    (".m4a", True),
    (".mp4", True),
    (".mkv", True),
    (".flac", True),
    (".txt", False),
    (".docx", False),
    (".py", False),
    ("", False),
])
def test_is_supported(ext, expected):
    assert ffmpeg.is_supported("file" + ext) is expected


def test_sample_rate():
    assert ffmpeg.SAMPLE_RATE == 16000
