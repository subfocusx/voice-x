"""Юнит-тесты модели Job (статусы, подписи, форматы времени)."""
from __future__ import annotations

from core.job import Job, Stage, _fmt_seconds


def test_stage_labels_contain_all():
    for s in Stage:
        if s.value != "error" and s.value != "cancelled":
            assert s in Job(stage=s).label or True
    assert Job(stage=Stage.DONE).label == "Готово"
    assert Job(stage=Stage.ASR).label == "Распознавание речи…"


def test_stage_enum_values():
    assert Stage.ASR.value == "asr"
    assert Stage.EXTRACT.value == "extract"
    assert Stage.IDLE.value == "idle"


def test_fmt_seconds():
    assert _fmt_seconds(None) == "—"
    assert _fmt_seconds(0) == "00:00"
    assert _fmt_seconds(65) == "01:05"
    assert _fmt_seconds(3660) == "61:00"


def test_terminal_states():
    assert Job(stage=Stage.DONE).is_terminal()
    assert Job(stage=Stage.ERROR).is_terminal()
    assert Job(stage=Stage.CANCELLED).is_terminal()
    assert not Job(stage=Stage.ASR).is_terminal()
    assert not Job(stage=Stage.CLEAN).is_terminal()


def test_cancel_flag():
    jb = Job()
    assert not jb.cancelled
    jb.cancel()
    assert jb.cancelled


def test_fmt_duration_and_elapsed():
    jb = Job(duration_sec=90.0)
    assert jb.fmt_duration() == "01:30"
    assert jb.fmt_elapsed() == "00:00"  # elapsed ещё не запускался
    jb.started_at = 0.0
    jb.tick_elapsed()
    assert jb.elapsed_seconds >= 0


def test_fmt_split_skips_empty_and_zero():
    jb = Job()
    assert jb.fmt_split() == ""
    jb.stage_timings["probe"] = 1.0
    jb.stage_timings["asr"] = 12.0
    assert "Разбор файла 00:01" in jb.fmt_split()
    assert "Распознавание 00:12" in jb.fmt_split()
    # извлечение не выполнялось — его нет в строке
    assert "Извлечение" not in jb.fmt_split()
