"""Точка входа Voice-X: локальная расшифровка аудио/видео (GigaAM, офлайн).

Запуск:
    <venv>\\python.exe app.py
"""
from __future__ import annotations

import os
import sys

#: ссылка на ole32 (WinDLL), чтобы апартамент не выпускали до выхода из процесса
_COM_OLE32 = None


def _fix_console_encoding() -> None:
    """Windows-консоль по умолчанию cp1252 — переключаем на UTF-8."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def _init_main_thread_sta() -> None:
    """Держать главный поток в STA (single-threaded apartment).

    soundcard/comtypes при `import soundcard` (его тянет
    services.recorder.wasapi через череду импортов) инициализирует COM на
    главном потоке как MTA. Это ломает два не связанных между собой места:

      1) tkinter-диалог выбора файла сползает на «классический» (comdlg32)
         вместо современного Explorer-окна;
      2) tkinterdnd2 не может инициализировать OLE2
         (`unable to initialize OLE2`), т.е. перетаскивание файлов не
         работает.

    Обе проблемы лечатся одним и тем же: инициализировать COM на главном
    потоке как STA ДО первого обращения к soundcard (и вообще ДО построения
    Tk-окна). Тогда comtypes, встретив уже-инициализированный STA, молча
    получает RPC_E_CHANGED_MODE и не пересоздаёт апартамент, а Tk-диалог и
    tkdnd работают в штатном STA-режиме.

    Поток записи (voicex-recorder) — отдельный фоновый поток, у него свой
    апартамент; здесь важен только главный поток, где живут Tk-виджеты.
    Пропускаем (или не мешаем), если COM уже инициализирован кем-то ещё.
    """
    import ctypes

    global _COM_OLE32

    COINIT_APARTMENTTHREADED = 0x2  # STA, поддерживает OLE (drag&drop, диалоги)
    RPC_E_CHANGED_MODE = -2147417850
    try:
        ole32 = ctypes.WinDLL("ole32")
        hr = ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
    except Exception:  # noqa: BLE001 — никогда не роняем старт из-за COM
        return
    # S_OK=0 (первый), S_FALSE=1 (уже инициализирован) — всё хорошо.
    # RPC_E_CHANGED_MODE=(-2147417850) — поток уже был инициализирован как MTA
    # кем-то раньше; тогда ничего не меняем (шаг уже пропущен).
    if hr not in (0, 1, RPC_E_CHANGED_MODE):
        return
    # Держим ссылку, чтобы апартамент не «выпустили» до завершения процесса.
    _COM_OLE32 = ole32


def main() -> None:
    _fix_console_encoding()
    # СТА до import ui.main_window: иначе soundcard заведёт главный поток как
    # MTA, и сломает и файловый диалог (классика), и drag&drop (OLE2).
    _init_main_thread_sta()
    # логирование поднимаем до импорта GUI, чтобы падение при старте
    # (например, отсутствие модели / dnd) попало в лог.
    from core.logging_setup import setup_logging

    setup_logging(debug=bool(os.environ.get("VOICEX_DEBUG")))

    # транзитивно тянет CustomTkinter / tkinterdnd2; ошибки — с понятным текстом
    from ui.main_window import MainWindow

    app = MainWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
