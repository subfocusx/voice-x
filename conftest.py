"""Корневой conftest для pytest: кладёт корень проекта на sys.path,
чтобы импорты core.* / services.* / ui.* работали из любого каталога.
"""
import os
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _make_temp_dir() -> Path:
    """Создаёт временный каталог, который остаётся доступным для записи/перечисления.

    Используем os.makedirs (а не tempfile.mkdtemp или tmp_path pytest):
    в этой среде каталоги, созданные через mkdtemp / pytest-базотемп, после
    заселения становятся нечитаемыми (WinError 5) из-за ACL-хука в песочнице.
    Самосозданный через os.makedirs каталог пишется/читается/удаляется нормально.
    """
    d = Path(__file__).resolve().parent / ".pytest_tmp" / f"tmp_{os.getpid()}_{id(object())}"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture
def owned_tmp_path() -> Path:
    """Временная папка с гарантированной записью/перечислением (замена tmp_path)."""
    d = _make_temp_dir()
    yield d
    shutil.rmtree(d, ignore_errors=True)
