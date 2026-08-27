"""Юнит-тесты фабрики движков."""
from __future__ import annotations

import pytest

from services.engine import make_engine
from services.gigaam import GigaAMEngine
from services.whisper import WhisperEngine


def test_make_gigaam_alias():
    for name in ("giga", "gigaam", "giga-am", "GIGA"):
        assert isinstance(make_engine(name), GigaAMEngine)


def test_make_whisper():
    assert isinstance(make_engine("whisper"), WhisperEngine)


def test_make_unknown_raises():
    with pytest.raises(ValueError):
        make_engine("whisper-2")


def test_gigaam_sets_model_dir():
    e = make_engine("giga", model_dir="C:/models")
    assert e._model_dir is not None
