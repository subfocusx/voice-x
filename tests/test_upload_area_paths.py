"""Юнит-тесты разбора пути из события drag&drop (чистая функция)."""
from __future__ import annotations

from ui.upload_area import _first_dropped_path


def test_windows_braces():
    # Windows отдаёт {C:/path}
    assert _first_dropped_path("{C:/media/file.mp3}") == "C:/media/file.mp3"


def test_path_with_space_trims_at_first_space():
    # путь с пробелом в имени — DnD отдаёт {...}, внутри пробелы
    assert _first_dropped_path("{C:/media/my file.mp3}") == "C:/media/my"


def test_plain_path():
    assert _first_dropped_path("C:/a/b.mp4") == "C:/a/b.mp4"


def test_multiple_files_first_wins():
    assert _first_dropped_path("C:/a.mp3 C:/b.mp3") == "C:/a.mp3"


def test_empty_returns_none():
    assert _first_dropped_path("") is None
    assert _first_dropped_path("   ") is None
    assert _first_dropped_path("{}") is None
