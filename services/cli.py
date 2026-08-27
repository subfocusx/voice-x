"""Консольный вход для smoke-теста пайплайна (без GUI).

Пример:
  python -m services.cli "path/to/file.mp4" [--model E:\\...\\models]

Печатает этапы и распознанный текст. Нужен для проверки вертикального
среза до того, как собран интерфейс.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from core.job import Stage  # noqa: E402
from core.logging_setup import setup_logging  # noqa: E402
from services import ffmpeg  # noqa: E402
from services.transcriber import transcribe_file  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Тестовый прогон пайплайна GigaAM")
    ap.add_argument("file", help="аудио/видео файл")
    ap.add_argument("--model", default=None, help="папка с int8-моделью GigaAM")
    ap.add_argument("--model-dir", default=None, help="alias для --model")
    args = ap.parse_args()

    setup_logging(debug=True)

    model_dir = args.model or args.model_dir
    if not Path(args.file).exists():
        print(f"Файл не найден: {args.file}")
        return 2

    ok, why = ffmpeg.available()
    if not ok:
        print(f"ffmpeg недоступен: {why}")
        return 3

    t0 = time.monotonic()
    job = transcribe_file(
        args.file, model_dir=model_dir, clean_enabled=False,
    )
    dur = time.monotonic() - t0

    print(f"\nЭтап:    {job.stage.value}")
    print(f"Длина:   {job.fmt_duration()}")
    print(f"Время:   {dur:.1f}s")
    if job.stage == Stage.DONE:
        print(f"Разбивка: {job.fmt_split()}")
    if job.error:
        print(f"Ошибка:  {job.error}")
        return 1
    print("\n=== РАСПОЗНАНО ===")
    print(job.transcript or "(пусто)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
