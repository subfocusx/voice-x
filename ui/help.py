"""Справка по приложению: текст и «?»-иконка с тултипом при наведении.

Простой тултип на tk.Toplevel (поверх окна), привязан к Enter/Leave/Click
виджета. Никакой логики приложения — только текст и показ.
"""
from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from ui.theme import SURFACE, BORDER, TEXT, TEXT_DIM, SURFACE_2, font

#: текст справки (показывается при наведении на «?»)
HELP_TEXT = (
    "Voice-X — локальная расшифровка аудио/видео\n"
    "Модель GigaAM v3 (int8), офлайн, без отправки в облако\n\n"
    "1. Перетащите файл или нажмите «Выбрать файл»\n"
    "2. Укажите движок / папку модели (если нужно)\n"
    "3. Нажмите «Распознать» и дождитесь «Готово»\n"
    "4. Скопируйте текст, сохраните в .txt или откройте папку\n\n"
    "Поддерживаются: mp3, wav, m4a, ogg, mp4, mkv и др.\n"
    "Если папка модели не найдена — укажите её кнопкой «Папка модели»."
)


class ToolTip:
    """Всплывающая подсказка рядом с виджетом по наведению."""

    def __init__(self, widget, text: str, delay: int = 450) -> None:
        self.widget = widget
        self.text = text
        self.delay = delay
        self._tip: tk.Toplevel | None = None
        self._after: str | None = None
        widget.bind("<Enter>", self._schedule)
        widget.bind("<Leave>", self._hide)
        widget.bind("<ButtonPress>", self._hide)

    def _schedule(self, _event=None) -> None:
        self._cancel()
        self._after = self.widget.after(self.delay, self._show)

    def _cancel(self) -> None:
        if self._after is not None:
            self.widget.after_cancel(self._after)
            self._after = None

    def _show(self) -> None:
        self._after = None
        if self._tip is not None:
            return
        w = self.widget
        x, y = w.winfo_rootx(), w.winfo_rooty()
        cx, cy = w.winfo_width(), w.winfo_height()

        top = tk.Toplevel(w)
        top.wm_overrideredirect(True)
        top.wm_geometry(f"+{x + 6}+{y + cy + 6}")
        top.attributes("-topmost", True)

        label = tk.Label(
            top, text=self.text, justify="left", anchor="w",
            bg=SURFACE, fg=TEXT, relief="solid", borderwidth=1,
            highlightbackground=BORDER, highlightthickness=0,
            padx=10, pady=8, font=("Segoe UI", 10),
        )
        label.pack()
        self._tip = top

    def _hide(self, _event=None) -> None:
        self._cancel()
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None


class HelpIcon(ctk.CTkButton):
    """Маленькая круглая кнопка «?» с тултипом при наведении."""

    def __init__(self, master, tooltip: str = HELP_TEXT, **kwargs) -> None:
        super().__init__(
            master, text="?", width=26, height=26, corner_radius=13,
            fg_color="transparent", hover_color=SURFACE_2,
            text_color=TEXT_DIM, font=font(13, "bold"), **kwargs,
        )
        ToolTip(self, tooltip)
