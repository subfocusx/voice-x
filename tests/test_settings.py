"""Юнит-тесты настроек (фоллбэки, сохранение/чтение, resolve_model_dir)."""
from __future__ import annotations

import json

from core.settings import Settings


def test_load_missing_file_returns_defaults(owned_tmp_path):
    s = Settings.load(path=owned_tmp_path / "nope.json")
    assert s.engine == "gigaam"
    assert s.clean_enabled is False
    assert s.model_dir == ""


def test_save_roundtrip(owned_tmp_path):
    p = owned_tmp_path / "s.json"
    s = Settings(engine="gigaam", clean_enabled=True, model_dir="C:/m", output_dir="C:/o")
    s.save(path=p)
    s2 = Settings.load(path=p)
    assert s2.clean_enabled is True
    assert s2.model_dir == "C:/m"
    assert s2.output_dir == "C:/o"


def test_load_bad_json_defaults(owned_tmp_path):
    p = owned_tmp_path / "bad.json"
    p.write_text("{ некорректный json", encoding="utf-8")
    s = Settings.load(path=p)
    assert s.engine == "gigaam"


def test_resolve_model_dir_prefers_explicit(owned_tmp_path):
    existing = owned_tmp_path / "models"
    existing.mkdir()
    s = Settings(model_dir=str(existing))
    assert s.resolve_model_dir() == existing
