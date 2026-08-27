"""Область загрузки (компактная): перетащи файл или выбери через диалог.

Один ряд: иконка-кнопка «Выбрать файл» + короткая подпись файла + крестик
сброса. Длинных плейсхолдеров и широких кнопок больше нет — загрузка и
движок умещаются в одну строку верхней карточки.

Drag&drop handled полностью в `main_window._enable_dnd` (регистрируется на
корневом окне), здесь только публичный API загрузки.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

import customtkinter as ctk

from services import ffmpeg
from ui.theme import (
    SURFACE_HOVER, BORDER, TEXT, TEXT_MUTE, ACCENT, ACCENT_HOVER, font,
)


#: одиночный файл из data события DnD (Windows отдаёт `{C:/path}`)
def _first_dropped_path(data: str) -> Optional[str]:
    if not data:
        return None
    data = data.strip().strip("{}")
    if not data:
        return None
    # может прийти несколько через пробел/перенос — берём первый
    head = data.split(" ")[0].strip("{}")
    return head if head else None


class UploadArea(ctk.CTkFrame):
    """Компактная загрузка: иконка выбора + подпись + сброс, одним рядом."""

    def __init__(
        self,
        master,
        on_file_selected: Callable[[str], None],
        on_file_cleared: Optional[Callable[[], None]] = None,
        *args,
        **kwargs,
    ):
        kwargs.setdefault("fg_color", "transparent")
        kwargs.setdefault("corner_radius", 0)
        super().__init__(master, *args, **kwargs)

        self._on_file_selected = on_file_selected
        self._on_file_cleared = on_file_cleared
        self._current_path: Optional[Path] = None

        self.grid_columnconfigure(1, weight=1)

        # иконка выбора файла (вместо длинной кнопки «Выбрать файл…»)
        self._browse_btn = ctk.CTkButton(
            self, text="📁", command=self._browse, width=44, height=40,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, corner_radius=10,
            text_color=TEXT, font=font(16),
        )
        self._browse_btn.grid(row=0, column=0, padx=(6, 8), pady=8, sticky="w")

        # подпись: «Перетащите сюда» → «📄 имя · папка»
        self._file_label = ctk.CTkLabel(
            self, text="Перетащите сюда файл", text_color=TEXT_MUTE,
            anchor="w", font=font(13),
        )
        self._file_label.grid(row=0, column=1, pady=8, sticky="ew")

        # сброс (появляется только когда файл выбран)
        self._clear_btn = ctk.CTkButton(
            self, text="✕", command=self._clear, width=40, height=40,
            fg_color="transparent", border_width=1, text_color=TEXT,
            hover_color=SURFACE_HOVER, border_color=BORDER, corner_radius=10,
        )
        self._clear_btn.grid(row=0, column=2, padx=(6, 6), pady=8, sticky="e")
        self._clear_btn.grid_remove()

    # ── публичный API ─────────────────────────────────────────────────────
    def set_file(self, path: str | Path | None) -> None:
        """Показать выбранный файл (внешний вызов)."""
        if path:
            p = Path(path)
            self._current_path = p
            self._file_label.configure(
                text=f"📄 {p.name}  ·  {p.parent.name}", text_color=TEXT)
            self._clear_btn.grid()
        else:
            self._current_path = None
            self._file_label.configure(text="Перетащите сюда файл",
                                       text_color=TEXT_MUTE)
            self._clear_btn.grid_remove()

    def clear(self) -> None:
        self.set_file(None)
        if self._on_file_cleared:
            self._on_file_cleared()

    def highlight(self, on: bool) -> None:
        """Подсветка при перетаскивании."""
        self.configure(border_width=3 if on else 0,
                       border_color=ACCENT if on else "transparent")

    # ── внутреннее ────────────────────────────────────────────────────────
    def _clear(self) -> None:
        self.clear()

    def _browse(self) -> None:
        from ui import native_file_dialog

        exts = " ".join(sorted(ffmpeg.ACCEPTED_EXTENSIONS, key=str.lower))
        types = [("Медиа-файлы", exts), ("Все файлы", "*.*")]
        # Нативный IFileOpenDialog (всегда современный диалог Explorer:
        # адресная строка, поиск, вставка пути). При внутренней ошибке сам
        # откатывается на tkinter.filedialog.
        path = native_file_dialog.askopenfilename(
            title="Выберите аудио/видео",
            filetypes=types,
            parent=self,
        )
        if path:
            self.set_file(path)
            self._on_file_selected(path)
