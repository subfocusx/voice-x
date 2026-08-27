"""Блок прогресса: подпись этапа, прогресс-бар с процентами внутри, иконки паузы/стопа.

Только отображение состояния из Job. Логика в worker / services.

Верхний ряд: слева подпись этапа, справа таймер + две иконки (пауза, стоп) без текста.
Под ним бар (толще), процент вписан внутрь бара.
"""
from __future__ import annotations

import customtkinter as ctk

from ui.theme import (
    SURFACE, SURFACE_2, SURFACE_HOVER, ACCENT,
    TEXT, TEXT_DIM, TEXT_MUTE, font,
)


class ProgressView(ctk.CTkFrame):
    def __init__(self, master, on_cancel, on_pause_toggle=None, *args, **kwargs):
        super().__init__(master, fg_color=SURFACE, corner_radius=14, *args, **kwargs)
        self._on_cancel = on_cancel
        self._on_pause_toggle = on_pause_toggle
        self._paused = False

        # верхний ряд: этап слева, таймер + иконки пауза/стоп справа
        self._stage_label = ctk.CTkLabel(
            self, text="Готов к работе", text_color=TEXT_DIM, anchor="w",
            font=font(13),
        )
        self._stage_label.grid(row=0, column=0, sticky="w", padx=(14, 6), pady=(12, 4))
        self.grid_columnconfigure(0, weight=1)  # этап тянется → иконки прижаты вправо

        self._time_label = ctk.CTkLabel(
            self, text="", text_color=TEXT_MUTE, width=56, font=font(12), anchor="e",
        )
        self._time_label.grid(row=0, column=1, padx=(0, 10), pady=(12, 4), sticky="e")

        self._pause_btn = ctk.CTkButton(
            self, text="⏸", width=36, height=32, fg_color=SURFACE_2,
            hover_color=SURFACE_HOVER, text_color=TEXT, corner_radius=8,
            font=font(14), command=self._pause_clicked,
        )
        self._pause_btn.grid(row=0, column=2, padx=(0, 6), pady=(12, 4), sticky="e")

        self._cancel_btn = ctk.CTkButton(
            self, text="■", width=36, height=32, fg_color=SURFACE_2,
            hover_color=SURFACE_HOVER, text_color=TEXT, corner_radius=8,
            font=font(14), command=self._cancel_clicked,
        )
        self._cancel_btn.grid(row=0, column=3, padx=14, pady=(12, 4), sticky="e")

        # бар (толще) с процентами внутри
        self._bar_box = ctk.CTkFrame(self, fg_color="transparent")
        self._bar_box.grid(row=1, column=0, columnspan=4, padx=14, pady=(2, 12), sticky="ew")

        self._bar = ctk.CTkProgressBar(
            self._bar_box, height=22, corner_radius=11,
            fg_color=SURFACE_2, progress_color=ACCENT,
        )
        self._bar.grid(row=0, column=0, sticky="ew")
        self._bar.set(0.0)

        # проценты поверх бара (по центру)
        self._pct_label = ctk.CTkLabel(
            self._bar_box, text="0%", text_color=TEXT, font=font(12, "bold"), anchor="center",
        )
        self._pct_label.place(relx=0.5, rely=0.5, anchor="center")

        self.set_enabled(False)

    # ── состояние ─────────────────────────────────────────────────────────
    def set_stage(self, label: str, enabled_cancel: bool = True) -> None:
        self._stage_label.configure(text=label)
        self.set_enabled(enabled_cancel)

    def set_progress(self, frac: float) -> None:
        frac = max(0.0, min(1.0, frac))
        self._bar.set(frac)
        self._pct_label.configure(text=f"{int(round(frac * 100))}%")

    def set_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self._cancel_btn.configure(state=state)
        self._pause_btn.configure(state=state)
        if not enabled:
            self._set_paused(False)

    def set_paused(self, paused: bool) -> None:
        self._set_paused(paused)

    def _set_paused(self, paused: bool) -> None:
        self._paused = paused
        self._pause_btn.configure(text="▶" if paused else "⏸")

    # ── таймер ────────────────────────────────────────────────────────────
    def set_time(self, seconds: float) -> None:
        """Показать прошедшее время как MM:SS."""
        m, s = divmod(int(max(0, seconds)), 60)
        self._time_label.configure(text=f"{m:02d}:{s:02d}")

    def _cancel_clicked(self) -> None:
        if self._on_cancel:
            self._on_cancel()

    def _pause_clicked(self) -> None:
        if self._on_pause_toggle:
            self._on_pause_toggle()
