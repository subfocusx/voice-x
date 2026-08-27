"""Юнит-тесты очистки (NoopCleaner = тождество)."""
from __future__ import annotations

from services.cleaner import NoopCleaner, get_cleaner


def test_singleton():
    assert get_cleaner() is get_cleaner()


def test_noop_identity():
    c = NoopCleaner()
    assert c.name() == "off"
    assert c.clean("Привет мир") == "Привет мир"
