"""Всплывающее уведомление (toast) поверх окна.

Появляется в правом верхнем углу и само исчезает через несколько секунд.
Только показ; никакой логики приложения.
"""
from __future__ import annotations

import customtkinter as ctk

from ui.theme import SUCCESS, DANGER, WARNING, TEXT, BORDER, font

_KIND_COLOR = {
    "success": SUCCESS,
    "error": DANGER,
    "warning": WARNING,
}


class Toast:
    """Менеджер одиночного toast-уведомления."""

    def __init__(self, master: ctk.CTk, duration_ms: int = 2800) -> None:
        self.master = master
        self.duration_ms = duration_ms
        self._frame: ctk.CTkFrame | None = None

    def show(self, message: str, kind: str = "success") -> None:
        """Показать уведомление, заменив предыдущее (если висит)."""
        self.hide()
        color = _KIND_COLOR.get(kind, SUCCESS)
        frame = ctk.CTkFrame(self.master, fg_color=color, corner_radius=12)
        label = ctk.CTkLabel(
            frame, text=f"  {message}", font=font(13, "bold"), text_color=TEXT,
        )
        label.pack(padx=16, pady=10)
        # правый верхний угол, поверх grid-содержимого
        frame.place(relx=0.98, rely=0.03, anchor="ne")
        self._frame = frame
        self.master.after(self.duration_ms, self.hide)

    def hide(self) -> None:
        if self._frame is not None:
            self._frame.destroy()
            self._frame = None
