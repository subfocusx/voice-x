"""Пути проекта: корень, выход, временная папка.

Никакой логики — только резолв путей относительно корня пакета.

В frozen-приложении (PyInstaller) `__file__` лежит во временной распаковке
(`_MEIPASS`), куда писать нельзя. Поэтому:
  * resource_dir()  — каталог забандленных ресурсов (модель, ffmpeg) — read-only;
  * data_dir()      — персистентный каталог настроек/записей/выхода
                      (%LOCALAPPDATA%\\Voice-X) — сюда можно писать.
В режиме исходников оба указывают на корень проекта (как и было).
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Корень проекта = voice-x\ (тот же уровень, что и пакет `core`).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

_data_dir_override: "Path | None" = None


def is_frozen() -> bool:
    """True, если запущено как запакованное приложение (PyInstaller)."""
    return bool(getattr(sys, "frozen", False))


def project_root() -> Path:
    """Корень пакета (исходники или распаковка). Read-only ресурсы."""
    return _PROJECT_ROOT


def resource_dir() -> Path:
    """Каталог с забандленными ресурсами (модель, ffmpeg, данные)."""
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        # onedir-фоллбэк: рядом с исполняемым файлом
        return Path(sys.executable).resolve().parent
    return _PROJECT_ROOT


def data_dir() -> Path:
    """Персистентный каталог, куда приложение ПИШЕТ (settings/output/recordings).

    Frozen — %LOCALAPPDATA%\\Voice-X (переживает переустановку/распаковку).
    Исходники — корень проекта (как раньше).
    """
    global _data_dir_override
    if _data_dir_override is not None:
        return _data_dir_override
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "Voice-X"
    base.mkdir(parents=True, exist_ok=True)
    _data_dir_override = base
    return base


def set_data_dir(path: "str | Path") -> None:
    """Опционально переопределить data_dir (для тестов)."""
    global _data_dir_override
    _data_dir_override = Path(path)


def output_dir() -> Path:
    r"""Папка для готовых расшифровок. По умолчанию — <data>\output."""
    d = data_dir() / "output"
    d.mkdir(parents=True, exist_ok=True)
    return d


def recordings_dir() -> Path:
    r"""Папка для локальных записей (WAV + итоговый .txt). <data>\recordings."""
    d = data_dir() / "recordings"
    d.mkdir(parents=True, exist_ok=True)
    return d


def tmp_dir() -> Path:
    """Папка под промежуточные wav. За пределами проекта, чистится ТЗ."""
    d = Path(tempfile.gettempdir()) / "voice-x"
    d.mkdir(parents=True, exist_ok=True)
    return d
