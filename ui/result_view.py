"""Результат расшифровки: тайминг-сводка, текст + Копировать/Сохранить/Открыть.

Простое отображение текста. Сохранение .txt в output_dir/выбранную папку.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import customtkinter as ctk

from ui.theme import (
    SURFACE, SURFACE_2, ACCENT, ACCENT_HOVER, SUCCESS, DANGER,
    TEXT, TEXT_DIM, TEXT_MUTE, font,
)


class ResultView(ctk.CTkFrame):
    def __init__(self, master, default_output_dir: Optional[Path], *args, **kwargs):
        super().__init__(master, fg_color=SURFACE, corner_radius=14, **kwargs)
        self._output_dir = Path(default_output_dir) if default_output_dir else None

        # кнопки
        act_style = dict(corner_radius=10, text_color=TEXT)
        self._copy_btn = ctk.CTkButton(self, text="Копировать", width=104,
                                       fg_color=SURFACE_2, hover_color=ACCENT_HOVER,
                                       command=self._copy, **act_style)
        self._copy_btn.grid(row=0, column=0, padx=(12, 4), pady=10, sticky="w")

        self._save_btn = ctk.CTkButton(self, text="Сохранить .txt", width=120,
                                       fg_color=SURFACE_2, hover_color=ACCENT_HOVER,
                                       command=self._save, **act_style)
        self._save_btn.grid(row=0, column=1, padx=4, pady=10)

        self._open_btn = ctk.CTkButton(self, text="Открыть", width=88,
                                       fg_color=SURFACE_2, hover_color=ACCENT_HOVER,
                                       command=self._open_folder, **act_style)
        self._open_btn.grid(row=0, column=2, padx=4, pady=10, sticky="w")

        # сводка таймингов (Разбор · Извлечение · Распознавание + длительность)
        self._summary_label = ctk.CTkLabel(
            self, text="", text_color=TEXT_DIM, anchor="w", font=font(12),
        )
        self._summary_label.grid(row=1, column=0, columnspan=3,
                                 padx=14, pady=(0, 6), sticky="ew")

        self._path_label = ctk.CTkLabel(
            self, text="", text_color=TEXT_MUTE, anchor="e", font=font(12),
        )
        self._path_label.grid(row=1, column=3, padx=14, pady=(0, 6), sticky="e")

        # текст
        self._textbox = ctk.CTkTextbox(self, wrap="word", height=200,
                                       fg_color=SURFACE_2, text_color=TEXT,
                                       border_width=0, corner_radius=10,
                                       font=font(13))
        self._textbox.grid(row=2, column=0, columnspan=4,
                           padx=12, pady=(0, 12), sticky="nsew")
        self.grid_columnconfigure(3, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._saved_path: Optional[Path] = None
        self._input_stem = "transcript"

    # ── публичный API ──────────────────────────────────────────────────
    def show(self, text: str, input_stem: str = "transcript",
             summary: str = "") -> None:
        self._input_stem = input_stem
        self._saved_path = None
        self._summary_label.configure(text=summary)
        self._path_label.configure(text="")
        self._textbox.configure(state="normal")
        self._textbox.delete("1.0", "end")
        self._textbox.insert("1.0", text)
        self._textbox.configure(state="disabled")

    def clear(self) -> None:
        self._saved_path = None
        self._summary_label.configure(text="")
        self._path_label.configure(text="")
        self._textbox.configure(state="normal")
        self._textbox.delete("1.0", "end")
        self._textbox.configure(state="disabled")

    def get_text(self) -> str:
        return self._textbox.get("1.0", "end-1c")

    # ── действия ───────────────────────────────────────────────────────
    def _copy(self) -> None:
        txt = self.get_text()
        if not txt:
            return
        self.clipboard_clear()
        self.clipboard_append(txt)
        self._flash("Скопировано")

    def _save(self, auto: bool = False) -> Optional[Path]:
        txt = self.get_text()
        if not txt:
            return None
        default_dir = self._output_dir or Path.home()
        default_name = f"{self._input_stem}_расшифровка.txt"

        if auto and default_dir.exists():
            target = default_dir / default_name
        else:
            from tkinter import filedialog
            target = filedialog.asksaveasfilename(
                title="Сохранить расшифровку",
                initialdir=str(default_dir),
                initialfile=default_name,
                defaultextension=".txt",
                filetypes=[("Текстовый файл", "*.txt")],
            )
            if not target:
                return None
            target = Path(target)

        try:
            target.write_text(txt, encoding="utf-8")
            self._saved_path = target
            self._path_label.configure(text=str(target))
            self._flash("Сохранено")
        except OSError as exc:
            self._flash(f"Ошибка: {exc}", error=True)
        return target

    def _open_folder(self) -> None:
        path = self._saved_path or self._output_dir
        if not path:
            return
        os.startfile(str(path))  # type: ignore[attr-defined]  # Windows-only

    # ── помощь ─────────────────────────────────────────────────────────
    def _flash(self, msg: str, error: bool = False) -> None:
        self._path_label.configure(
            text=msg, text_color=DANGER if error else SUCCESS,
        )
        self.after(2500, lambda: self._path_label.configure(
            text=str(self._saved_path or ""), text_color=TEXT_MUTE))
