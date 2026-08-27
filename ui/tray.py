"""Системный трей для Voice-X (pystray + Pillow).

Иконка у часов со строкой состояния; по клику на "Показать окно" —
вернуть главное окно, "Выход" — закрыть приложение. Меню и клики
приходят в потоке pystray, поэтому наружу отдаются простые колбэки,
а MainWindow маршалит их в поток Tk через свою очередь (см. _tray_q).
"""
from __future__ import annotations

import threading
from typing import Callable, Optional

import pystray
from PIL import Image, ImageDraw

from ui.theme import ACCENT


def build_icon_image(size: int = 64) -> Image.Image:
    """Нарисовать иконку микрофона (акцентный круг + белый микрофон)."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # фон — скруглённый квадрат акцентного цвета
    d.rounded_rectangle([2, 2, size - 2, size - 2], radius=size // 5, fill=ACCENT)

    cx = size // 2
    w = size // 5
    top = size // 4
    bot = size // 2 + size // 12
    # корпус микрофона
    d.rounded_rectangle([cx - w, top, cx + w, bot], radius=w // 2, fill="white")
    # ножка
    d.line([cx, bot, cx, bot + size // 6], fill="white", width=max(2, size // 14))
    # дуга подставки
    d.arc([cx - w, top, cx + w, bot + size // 12], start=0, end=180,
          fill="white", width=max(2, size // 14))
    return img


class TrayIcon:
    """Иконка у часов. Показ окна / Выход — через меню."""

    MENU_SHOW = "Показать окно"
    MENU_QUIT = "Выход"

    def __init__(self, on_show: Callable[[], None], on_quit: Callable[[], None]):
        self._on_show = on_show
        self._on_quit = on_quit
        self._icon = pystray.Icon(
            "voice-x",
            build_icon_image(64),
            "Voice-X",
            menu=pystray.Menu(
                pystray.MenuItem(self.MENU_SHOW, self._show, default=True),
                pystray.MenuItem(self.MENU_QUIT, self._quit),
            ),
        )
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Запустить трей в фоновом потоке (mainloop остаётся в Tk)."""
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._icon.run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        try:
            self._icon.stop()
        except Exception:  # noqa: BLE001 — иконка могла быть уже остановлена
            pass

    # ── колбэки (выполняются в потоке pystray) ──────────────────────────
    def _show(self, icon, item) -> None:
        self._on_show()

    def _quit(self, icon, item) -> None:
        self._on_quit()
