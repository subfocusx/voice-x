"""Панель записи Voice-X: источник, устройства, таймер, уровни.

Граничная роль: показать состояние `AudioRecorder` и сгенерировать события
«запись»/«стоп»/«отмена». Сам захват — в services/recorder; панель НЕ трогает
звуковой API напрямую. Обратная связь — через опрос `get_state()/get_levels()`
из GUI-цикла (after), без обращений к виджетам из фонового потока.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import customtkinter as ctk

from core.job import RecordingState
from services.recorder import (
    KIND_MIC, KIND_SYSTEM, AudioRecorder, devices_of, list_sources,
)
from ui.theme import (
    ACCENT, ACCENT_HOVER, DANGER, SURFACE, SURFACE_2, SURFACE_HOVER,
    SUCCESS, TEXT, TEXT_DIM, TEXT_MUTE, font,
)

#: чувствительность индикатора уровня (линейная до 1.0)
_LEVEL_GAIN = 2.0

#: текст кнопки по состоянию
_BTN_TEXT = {
    "record": "⏺ Начать запись",
    "stop": "⏹ Остановить",
    "busy": "Стоп…",
}


class RecorderPanel(ctk.CTkFrame):
    """Один блок: управление записью. `on_transcribe` зовётся после успешного
    stop с путём к WAV; `on_busy_changed` — при входе/выходе из записи."""

    def __init__(self, master, *, on_transcribe, on_busy_changed=None, on_toast=None,
                 save_mp3: bool = False, on_save_mp3=None,
                 mic_gain: float = 1.0, system_gain: float = 1.0, limiter: bool = True):
        super().__init__(master, fg_color=SURFACE, corner_radius=14)
        self.on_transcribe = on_transcribe
        self.on_busy_changed = on_busy_changed
        self.on_toast = on_toast
        self._save_mp3 = bool(save_mp3)
        self._on_save_mp3 = on_save_mp3
        self._mic_gain = float(mic_gain)
        self._system_gain = float(system_gain)
        self._limiter = bool(limiter)

        self.recorder = AudioRecorder()
        self._sources = list_sources()
        self._mic_devices = devices_of(KIND_MIC, self._sources)
        self._sys_devices = devices_of(KIND_SYSTEM, self._sources)

        self._polling = False
        self._last_state = RecordingState.IDLE
        self._done_handled = False
        self._rec_started: float = 0.0

        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(2, weight=0)
        self.grid_columnconfigure(3, weight=0)

        self._build()

    # ── построение ─────────────────────────────────────────────────────────
    def _build(self) -> None:
        self._advanced_expanded = False
        self._source_btn, self._adv_toggle = self._build_source_row()
        self._rec_btn, self._timer_lbl, self._status_lbl = self._build_controls()
        self._mic_bar, self._sys_bar = self._build_advanced()
        self._populate_device_menus()
        self._reset_idle_ui()

    def _build_source_row(self):
        ctk.CTkLabel(self, text="Источник", text_color=TEXT_DIM,
                     font=font(12)).grid(row=0, column=0, padx=(14, 6), pady=(12, 4), sticky="w")
        source_btn = ctk.CTkOptionMenu(
            self, values=list(_SOURCE_TEXT.values()), width=170,
            fg_color=SURFACE_2, button_color=SURFACE_2, button_hover_color=SURFACE_HOVER,
            text_color=TEXT, font=font(12),
            dropdown_fg_color=SURFACE_2, dropdown_hover_color=SURFACE_HOVER,
            command=self._on_source_change,
        )
        source_btn.grid(row=0, column=1, padx=14, pady=(12, 4), sticky="w")
        source_btn.set(_SOURCE_TEXT[KIND_MIC])

        # опция «Сохранять MP3»
        self._mp3_check = ctk.CTkCheckBox(
            self, text="сохранить MP3", command=self._on_mp3_toggle,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            border_color=SURFACE_HOVER, checkmark_color=TEXT,
            text_color=TEXT_DIM, font=font(11),
        )
        self._mp3_check.grid(row=0, column=2, padx=(8, 4), pady=(12, 4), sticky="e")
        self._mp3_check.select() if self._save_mp3 else self._mp3_check.deselect()

        # переключатель раскрытия расширенных настроек (устройства и уровни)
        adv_toggle = ctk.CTkButton(
            self, text="▸ устройства и уровни", width=156, height=28,
            command=self._toggle_advanced,
            fg_color=SURFACE_2, hover_color=SURFACE_HOVER, text_color=TEXT_DIM,
            corner_radius=8, font=font(11),
        )
        adv_toggle.grid(row=0, column=3, padx=(6, 14), pady=(12, 4), sticky="e")
        return source_btn, adv_toggle

    def _device_row(self, parent, row: int, label: str) -> ctk.CTkOptionMenu:
        ctk.CTkLabel(parent, text=label, text_color=TEXT_DIM,
                     font=font(12)).grid(row=row, column=0, padx=(14, 6), pady=3, sticky="w")
        menu = ctk.CTkOptionMenu(
            parent, values=[], width=330,
            fg_color=SURFACE_2, button_color=SURFACE_2, button_hover_color=SURFACE_HOVER,
            text_color=TEXT, font=font(12),
            dropdown_fg_color=SURFACE_2, dropdown_hover_color=SURFACE_HOVER,
        )
        menu.grid(row=row, column=1, columnspan=3, padx=14, pady=3, sticky="ew")
        return menu

    def _build_controls(self):
        rec_btn = self._rec_btn = ctk.CTkButton(
            self, text=_BTN_TEXT["record"], height=38, command=self._toggle_record,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=TEXT,
            corner_radius=12, font=font(14, "bold"),
        )
        rec_btn.grid(row=1, column=0, columnspan=4, padx=14, pady=(10, 2), sticky="ew")

        timer_lbl = ctk.CTkLabel(self, text="00:00", text_color=TEXT,
                                 font=font(22, "bold"), anchor="w")
        timer_lbl.grid(row=2, column=0, padx=(14, 0), pady=(2, 0), sticky="w")
        status_lbl = ctk.CTkLabel(self, text="", text_color=TEXT_MUTE,
                                  font=font(12), anchor="e")
        status_lbl.grid(row=2, column=1, columnspan=3, padx=14, pady=(2, 0), sticky="e")
        return rec_btn, timer_lbl, status_lbl

    def _build_advanced(self):
        """Сворачиваемый блок: выбор устройств + уровни + баланс микса."""
        self._adv_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._adv_frame.grid_columnconfigure(1, weight=1)
        self._mic_btn = self._device_row(self._adv_frame, 0, "Микрофон")
        self._sys_btn = self._device_row(self._adv_frame, 1, "Система")
        mic_bar, _ = self._level_row(self._adv_frame, 2, "Ур. микрофона")
        sys_bar, _ = self._level_row(self._adv_frame, 3, "Ур. системы")
        self._mic_gain_slider = self._gain_row(self._adv_frame, 4, "Громкость микрофона")
        self._sys_gain_slider = self._gain_row(self._adv_frame, 5, "Громкость системы")
        self._mic_gain_slider.set(self._mic_gain)
        self._sys_gain_slider.set(self._system_gain)
        self._adv_frame.grid(row=3, column=0, columnspan=4, sticky="ew")
        self._apply_advanced_visibility()
        return mic_bar, sys_bar

    def _toggle_advanced(self) -> None:
        self._advanced_expanded = not self._advanced_expanded
        self._apply_advanced_visibility()

    def _apply_advanced_visibility(self) -> None:
        if self._advanced_expanded:
            self._adv_frame.grid()
            self._adv_toggle.configure(text="▾ скрыть настройки")
        else:
            self._adv_frame.grid_remove()
            self._adv_toggle.configure(text="▸ устройства и уровни")

    def _level_row(self, parent, row: int, label: str):
        ctk.CTkLabel(parent, text=label, text_color=TEXT_MUTE,
                     font=font(11)).grid(row=row, column=0, padx=(14, 6), pady=2, sticky="w")
        bar = ctk.CTkProgressBar(
            parent, height=8, progress_color=ACCENT,
            fg_color=SURFACE_2, corner_radius=4,
        )
        bar.grid(row=row, column=1, columnspan=3, padx=14, pady=2, sticky="ew")
        bar.set(0.0)
        return bar, None

    def _gain_row(self, parent, row: int, label: str):
        ctk.CTkLabel(parent, text=label, text_color=TEXT_MUTE,
                     font=font(11)).grid(row=row, column=0, padx=(14, 6), pady=2, sticky="w")
        slider = ctk.CTkSlider(
            parent, from_=0.0, to=2.0, number_of_steps=40, width=240,
            fg_color=SURFACE_2, progress_color=ACCENT, button_color=ACCENT,
            button_hover_color=ACCENT_HOVER,
        )
        slider.grid(row=row, column=1, columnspan=3, padx=14, pady=2, sticky="ew")
        return slider

    # ── данные устройств ───────────────────────────────────────────────────
    def _populate_device_menus(self) -> None:
        self._mic_options = {d.name: d for d in self._mic_devices}
        self._sys_options = {d.name: d for d in self._sys_devices}
        self._mic_btn.configure(values=list(self._mic_options))
        self._sys_btn.configure(values=list(self._sys_options))
        if self._mic_devices:
            self._mic_btn.set(self._mic_devices[0].name)
        if self._sys_devices:
            self._sys_btn.set(self._sys_devices[0].name)
        self._apply_source_rules()

    def _on_source_change(self, _choice: str) -> None:
        self._apply_source_rules()

    def _on_mp3_toggle(self) -> None:
        self._save_mp3 = bool(self._mp3_check.get())
        if self._on_save_mp3:
            self._on_save_mp3(self._save_mp3)

    def _apply_source_rules(self) -> None:
        kind = self._selected_source_kind()
        use_mic = kind in (KIND_MIC, "both")
        use_sys = kind in (KIND_SYSTEM, "both")
        self._mic_btn.configure(state="normal" if use_mic and self._mic_devices else "disabled")
        self._sys_btn.configure(state="normal" if use_sys and self._sys_devices else "disabled")

    # ── чтение выбранного источника ────────────────────────────────────────
    def _selected_source_kind(self) -> str:
        text = self._source_btn.get().strip()
        for kind, t in _SOURCE_TEXT.items():
            if t == text:
                return kind
        return KIND_MIC

    # ── действия ───────────────────────────────────────────────────────────
    def _toggle_record(self) -> None:
        state = self.recorder.get_state()
        if state == RecordingState.RECORDING:
            self._do_stop()
        elif state in (RecordingState.IDLE, RecordingState.DONE,
                       RecordingState.ERROR, RecordingState.CANCELLED):
            self._do_start()
        # STOPPING — кнопка disabled, ничего не делаем

    def _do_start(self) -> None:
        kind = self._selected_source_kind()
        mic_dev = self._resolve_device(self._mic_btn, self._mic_devices)
        sys_dev = self._resolve_device(self._sys_btn, self._sys_devices)
        if kind in (KIND_MIC, "both") and mic_dev is None:
            self._status_lbl.configure(text="Нет микрофона", text_color=DANGER)
            return
        if kind in (KIND_SYSTEM, "both") and sys_dev is None:
            self._status_lbl.configure(text="Нет системного устройства", text_color=DANGER)
            return
        try:
            self.recorder.start(
                kind, mic_device=mic_dev, system_device=sys_dev,
                save_mp3=self._save_mp3,
                mic_gain=float(self._mic_gain_slider.get()),
                system_gain=float(self._sys_gain_slider.get()),
                limiter=self._limiter,
            )
        except RuntimeError as exc:
            self._status_lbl.configure(text=str(exc), text_color=DANGER)
            return
        self._rec_started = time.monotonic()
        self._done_handled = False
        self._last_state = self.recorder.get_state()
        self._set_recording_ui(busy=True)
        self._start_polling()
        self._notify_busy(True)

    def _do_stop(self) -> None:
        self.recorder.stop()
        self._last_state = self.recorder.get_state()
        self._rec_btn.configure(state="disabled", text=_BTN_TEXT["busy"])
        self._status_lbl.configure(text="Остановка…", text_color=TEXT_DIM)

    def _resolve_device(self, menu, devices):
        name = menu.get().strip()
        if not name:
            return None
        return next((d for d in devices if d.name == name), None)

    # ── опрос состояния (GUI-цикл) ─────────────────────────────────────────
    def _start_polling(self) -> None:
        if self._polling:
            return
        self._polling = True
        self.after(100, self._poll)

    def _poll(self) -> None:
        if not self._polling:
            return
        state = self.recorder.get_state()
        levels = self.recorder.get_levels()
        self._update_levels(levels)

        if state == RecordingState.RECORDING:
            self._timer_lbl.configure(text=self._fmt_elapsed(time.monotonic() - self._rec_started))
            self._status_lbl.configure(
                text="Запись…" if self._selected_source_kind() != "both" else "Запись (микрофон + система)",
                text_color=SUCCESS)
        elif state == RecordingState.STOPPING:
            self._status_lbl.configure(text="Сохранение…", text_color=TEXT_DIM)
        elif state == RecordingState.DONE:
            self._handle_done()
        elif state == RecordingState.ERROR:
            self._handle_error()
        elif state == RecordingState.CANCELLED:
            self._handle_cancelled()

        self.after(100, self._poll)

    def _handle_done(self) -> None:
        path = self.recorder.last_path
        self._timer_lbl.configure(text=self._fmt_elapsed(self.recorder.duration_sec))
        self._status_lbl.configure(text="Готово", text_color=SUCCESS)
        self._set_idle_ui()
        self._stop_polling()
        self._notify_busy(False)
        self._rec_btn.configure(state="normal")
        if not self._done_handled and path is not None and path.exists():
            self._done_handled = True
            # автозапуск расшифровки
            self.on_transcribe(Path(path), path.stem)

    def _handle_error(self) -> None:
        self._timer_lbl.configure(text="--:--")
        self._status_lbl.configure(text=self.recorder.error or "Ошибка записи", text_color=DANGER)
        self._set_idle_ui()
        self._stop_polling()
        self._notify_busy(False)
        self._rec_btn.configure(state="normal")
        if self.on_toast:
            self.on_toast("Ошибка записи", kind="error")

    def _handle_cancelled(self) -> None:
        self._timer_lbl.configure(text="00:00")
        self._status_lbl.configure(text="Отменено", text_color=TEXT_MUTE)
        self._set_idle_ui()
        self._stop_polling()
        self._notify_busy(False)
        self._rec_btn.configure(state="normal")
        if self.on_toast:
            self.on_toast("Запись отменена", kind="warning")

    # ── UI-состояния ───────────────────────────────────────────────────────
    def _set_recording_ui(self, busy: bool) -> None:
        self._source_btn.configure(state="disabled" if busy else "normal")
        self._rec_btn.configure(state="normal", text=_BTN_TEXT["stop"],
                                fg_color=DANGER)
        self._timer_lbl.configure(text="00:00")
        self._status_lbl.configure(text="Запись…", text_color=SUCCESS)

    def _set_idle_ui(self) -> None:
        self._rec_btn.configure(state="normal", text=_BTN_TEXT["record"],
                                fg_color=ACCENT, hover_color=ACCENT_HOVER)
        self._apply_source_rules()

    def _reset_idle_ui(self) -> None:
        self._rec_btn.configure(state="normal", text=_BTN_TEXT["record"],
                                fg_color=ACCENT, hover_color=ACCENT_HOVER)
        self._timer_lbl.configure(text="00:00")
        self._status_lbl.configure(text="", text_color=TEXT_MUTE)
        self._apply_source_rules()

    def _update_levels(self, levels) -> None:
        mic = min(1.0, levels.get(KIND_MIC, 0.0) * _LEVEL_GAIN)
        sys = min(1.0, levels.get(KIND_SYSTEM, 0.0) * _LEVEL_GAIN)
        self._mic_bar.set(mic)
        self._sys_bar.set(sys)

    # ── внешним (MainWindow) ───────────────────────────────────────────────
    def set_running(self, running: bool) -> None:
        """Транскрипция идёт (файл/запись) — заблокировать управление записью."""
        self._source_btn.configure(state="disabled" if running else "normal")
        self._mic_btn.configure(state="disabled" if running else self._mic_btn.cget("state"))
        self._sys_btn.configure(state="disabled" if running else self._sys_btn.cget("state"))
        self._rec_btn.configure(state="disabled" if running else "normal")
        self._apply_source_rules()

    def is_recording(self) -> bool:
        return self.recorder.is_recording() or self.recorder.is_busy()

    def cancel(self) -> None:
        if self.recorder.is_busy():
            self.recorder.cancel()

    # ── хелперы ────────────────────────────────────────────────────────────
    def _fmt_elapsed(self, sec: float) -> str:
        sec = max(0, int(sec))
        return f"{sec // 60:02d}:{sec % 60:02d}"

    def _notify_busy(self, busy: bool) -> None:
        if self.on_busy_changed:
            self.on_busy_changed(busy)

    def _stop_polling(self) -> None:
        self._polling = False


#: соответствие ключ→текст для меню источника
_SOURCE_TEXT = {
    KIND_MIC: "Микрофон",
    KIND_SYSTEM: "Системный звук",
    "both": "Микрофон + система",
}
