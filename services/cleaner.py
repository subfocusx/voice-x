"""Очистка расшифровки (LLM) — интерфейс и выключенный дефолт.

Первая версия: очистка отключена (raw расшифровка). Чтобы включить —
реализуйте CleanerInterface (например, через локальный OpenAI-совместимый
endpoint) и пропишите его в get_cleaner().
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class CleanerInterface(ABC):
    """Превращает «сырой» вывод ASR в аккуратный текст."""

    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def clean(self, raw_text: str) -> str:
        ...


class NoopCleaner(CleanerInterface):
    """Ничего не делает — возвращает текст как есть."""

    def name(self) -> str:
        return "off"

    def clean(self, raw_text: str) -> str:
        return raw_text


_CLEANER: CleanerInterface | None = None


def get_cleaner() -> CleanerInterface:
    """Фабрика очистителя. По умолчанию — выключен (raw)."""
    global _CLEANER
    if _CLEANER is None:
        _CLEANER = NoopCleaner()
    return _CLEANER