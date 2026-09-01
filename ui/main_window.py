"""Главное окно Voice-X: собирает все компоненты и живёт по состоянию.

State machine (из задания): idle → file_chosen → running → done/error/cancelled.
UI только отражает состояние; обработка — в Worker (services.transcriber).
"""
from __future__ import annotations

import queue
import time
from pathlib import Path
from typing import Optional

import customtkinter as ctk

from core.job import Stage, STAGE_LABEL
from core.paths import output_dir
from core.settings import Settings
from services import ffmpeg
from ui.help import HelpIcon
from ui.progress import ProgressView
from ui.recorder_panel import RecorderPanel
from ui.result_view import ResultView
from ui.theme import (
    ACCENT, ACCENT_HOVER, SURFACE, SURFACE_2, SURFACE_HOVER, WINDOW_BG,
    TEXT, TEXT_DIM, TEXT_MUTE, SUCCESS, DANGER, font,
)
from ui.toast import Toast
from ui.upload_area import UploadArea
from ui.worker import Worker, EV_STAGE, EV_PROGRESS, EV_DONE

try:
    from ui.tray import TrayIcon
except Exception:  # noqa: BLE001 — pystray не установлен → работаем без трея
    TrayIcon = None

#: за что держит прогресс-бар на каждом этапе (0..1 общий путь)
_STAGE_BASE = {
    Stage.IDLE: 0.0,
    Stage.PROBE: 0.03,
    Stage.EXTRACT: 0.10,
    Stage.ASR: 0.15,
    Stage.CLEAN: 0.92,
}

#: в каком диапазоне общего бара живёт прогресс ASR (ASR_BASE..ASR_END)
_ASR_BASE, _ASR_END = _STAGE_BASE[Stage.ASR], 0.95


def _install_dnd_methods() -> None:
    """tkinterdnd2 монтирует методы DnD на tkinter.BaseWidget, но корень Tk/CTk
    (и `CTkCanvas`, единственный родитель во многих местах) наследует Misc, а
    не BaseWidget. Продублируем методы на tkinter.Misc, чтобы drop был принят
    и корнем, и любым канвасом окна. Внешних виджетов-контейнеров нет.
    """
    import tkinter as tk
    import tkinterdnd2
    if hasattr(tk.Misc, "drop_target_register"):
        return  # уже установлено
    prev = tk.BaseWidget.__dict__
    # класс-константы, на которые ссылается _dnd_bind
    for name in ("_subst_format_dnd", "_subst_format_str_dnd"):
        val = prev.get(name)
        if val is not None:
            setattr(tk.Misc, name, val)
    for name in (
        "dnd_bind", "_dnd_bind", "_substitute_dnd",
        "drag_source_register", "drag_source_unregister",
        "drop_target_register", "drop_target_unregister",
    ):
        fn = prev.get(name)
        if fn is not None:
            setattr(tk.Misc, name, fn)


def _enable_dnd(root: ctk.CTk) -> bool:
    """Включить drag&drop на корне (Tk-обёртка remainder).

    Возвращает True, если DnD успешно инициализирован. В средах без
    интерактивного десктопа (headless-сессия, песочница, RDP без рабочего
    стола) Windows OLE2 не может инициализироваться, и TkinterDnD.require
    бросает `unable to initialize OLE2`. Тогда приложение должно всё равно
    запуститься — просто без drag&drop (файл можно выбрать кнопкой, запись
    рекордером работает как обычно). Поэтому init обёрнут в try/except.
    """
    from tkinterdnd2 import TkinterDnD, DND_FILES
    try:
        TkinterDnD.require(root)
    except (RuntimeError, Exception) as exc:  # RuntimeError — tkdnd не загрузился
        print(f"[voice-x] drag&drop недоступен ({exc!r}) — работаем без него",
              flush=True)
        return False
    _install_dnd_methods()
    # Весь корень — drop-target: ловим даже там, где лежат дочерние виджеты.
    root.drop_target_register(DND_FILES)
    root.dnd_bind("<<Drop>>", root._on_drop_file)
    root.dnd_bind("<<DropEnter>>", root._on_drop_enter)
    root.dnd_bind("<<DropLeave>>", root._on_drop_leave)
    return True


def _first_dropped_path(data: str) -> Optional[str]:
    """Один элемент из data события DnD после tk.splitlist."""
    if not data:
        return None
    data = data.strip().strip("{}")
    return data if data else None


class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        self._dnd_enabled = _enable_dnd(self)

        self.settings = Settings.load()
        self.worker = Worker()

        self.title("Voice-X · локальная расшифровка")
        self.geometry("700x600")
        self.minsize(560, 500)
        ctk.set_appearance_mode("dark")
        self.configure(fg_color=WINDOW_BG)

        self._file: Optional[Path] = None
        self._running = False
        self._rec_busy = False
        self._started_mono: float = 0.0

        self._toast = Toast(self)
        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # трей: X сворачивает в трей, «Выход» — закрывает по-настоящему
        self._tray_q: "queue.Queue[str]" = queue.Queue()
        self._tray: Optional["TrayIcon"] = None
        if TrayIcon is not None:
            try:
                self._tray = TrayIcon(
                    on_show=self._tray_enqueue_show,
                    on_quit=self._tray_enqueue_quit,
                )
                self._tray.start()
            except Exception as exc:  # noqa: BLE001
                print(f"[voice-x] трей недоступен ({exc!r}) — окно закрывается "
                      f"напрямую", flush=True)
                self._tray = None
        if self._tray is not None:
            self.after(200, self._tray_poll)

    # ── построение ───────────────────────────────────────────────────────
    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        # Ряд кнопки «Распознать» НЕ растягивается: только область результата
        # (row 5) поглощает свободное место.
        self.grid_rowconfigure(2, weight=0)

        # шапка: заголовок + «?»-иконка справа
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, padx=20, pady=(16, 6), sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        title = ctk.CTkLabel(
            header, text="Voice-X — расшифровка аудио / видео",
            text_color=TEXT, font=font(18, "bold"), anchor="w",
        )
        title.grid(row=0, column=0, sticky="w")
        self.help_icon = HelpIcon(header)
        self.help_icon.grid(row=0, column=1, sticky="e")

        # 1) верхняя карточка: загрузка + движок — единая компактная строка.
        #    Обе группы в одной строке, чтобы окно не требовалось растягивать.
        top_bar = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=14)
        top_bar.grid(row=1, column=0, padx=16, pady=0, sticky="ew")
        top_bar.grid_columnconfigure(1, weight=1)   # файл тянется
        top_bar.grid_columnconfigure(3, weight=0)   # движок фиксированный

        # 1a) загрузка файла — компактно: иконка «📁» + подпись + «✕»
        self.upload = UploadArea(
            top_bar,
            on_file_selected=self._on_file_selected,
            on_file_cleared=self._on_file_cleared,
        )
        self.upload.grid(row=0, column=1, padx=(8, 4), pady=8, sticky="ew")

        # 1b) движок + папка модели — справа, иконки вместо длинных кнопок
        self._models_list: list[dict] = []
        self.engine_menu = ctk.CTkOptionMenu(
            top_bar, values=["GigaAM v3 (int8)"], width=150,
            fg_color=SURFACE_2, button_color=SURFACE_2, button_hover_color=SURFACE_HOVER,
            text_color=TEXT, font=font(12),
            dropdown_fg_color=SURFACE_2, dropdown_hover_color=SURFACE_HOVER,
            command=self._on_engine_change,
        )
        self.engine_menu.grid(row=0, column=2, padx=(4, 4), pady=8, sticky="e")
        self._refresh_model_list()

        self.model_dir_btn = ctk.CTkButton(
            top_bar, text="📂", width=40, height=40, command=self._pick_model_dir,
            fg_color=SURFACE_2, hover_color=SURFACE_HOVER, text_color=TEXT,
            corner_radius=10, font=font(14),
        )
        self.model_dir_btn.grid(row=0, column=3, padx=(4, 8), pady=8, sticky="e")

        # куда резолвится модель (краткий статус, обновляется в _update_model_path)
        self.model_path_label = ctk.CTkLabel(
            top_bar, text="", anchor="e", font=font(11),
        )
        self.model_path_label.grid(row=0, column=4, padx=(0, 14), pady=8, sticky="e")

        # 2) кнопка «Распознать»
        self.recognize_btn = ctk.CTkButton(
            self, text="Распознать ▶", height=42, command=self._start_run,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=TEXT,
            corner_radius=12, font=font(14, "bold"),
            state="disabled",
        )
        self.recognize_btn.grid(row=2, column=0, padx=16, pady=(12, 4), sticky="ew")

        # 3) рекордер (микрофон / системный звук)
        self.recorder_panel = RecorderPanel(
            self,
            on_transcribe=self._transcribe_recorded,
            on_busy_changed=self._on_recorder_busy,
            on_toast=lambda msg, kind="info": self._toast.show(msg, kind=kind),
            save_mp3=self.settings.save_mp3,
            on_save_mp3=self._on_save_mp3,
            mic_gain=self.settings.mic_gain,
            system_gain=self.settings.system_gain,
            limiter=self.settings.rec_limiter,
        )
        self.recorder_panel.grid(row=4, column=0, padx=16, pady=(8, 0), sticky="ew")

        # 3) прогресс
        self.progress = ProgressView(
            self, on_cancel=self._cancel_run, on_pause_toggle=self._toggle_pause,
        )
        self.progress.grid(row=3, column=0, padx=16, pady=(6, 0), sticky="ew")

        # 5) результат (растягивается)
        self.result = ResultView(self, default_output_dir=output_dir())
        self.result.grid(row=5, column=0, padx=16, pady=(10, 14), sticky="nsew")
        self.grid_rowconfigure(5, weight=1)

        self._set_running(False)
        self._check_model_hint()

    def _set_running(self, running: bool) -> None:
        """Синхронить UI под состояние выполнения."""
        self._running = running
        state = ("disabled" if running
                 else ("normal" if self._file is not None else "disabled"))
        self.recognize_btn.configure(state=state)
        self.upload._browse_btn.configure(state="disabled" if running else "normal")
        self.model_dir_btn.configure(state="disabled" if running else "normal")
        self.recorder_panel.set_running(running)

    def _check_model_hint(self) -> None:
        """Ненавязчиво показать состояние модели в строке прогресса."""
        model_dir = self.settings.resolve_model_dir()
        if model_dir and Path(model_dir).exists():
            self.progress.set_stage("Модель найдена. Выберите файл…", enabled_cancel=False)
        else:
            self.progress.set_stage(
                "Внимание: папка модели не найдена. Укажите её кнопкой «Папка модели»",
                enabled_cancel=False,
            )
        self._update_model_path()

    def _update_model_path(self) -> None:
        """Краткий статус модели в верхней карточке (✓/⚠)."""
        model_dir = self.settings.resolve_model_dir()
        if model_dir and Path(model_dir).exists():
            self.model_path_label.configure(text="✓ модель", text_color=SUCCESS)
        else:
            self.model_path_label.configure(text="⚠ модель не найдена",
                                            text_color=DANGER)

    def _pick_model_dir(self) -> None:
        """Выбор папки с моделью вручную (кнопка «Папка модели…»)."""
        from tkinter import filedialog

        initial = str(self.settings.resolve_model_dir()
                      or self.settings.model_dir
                      or Path.home())
        path = filedialog.askdirectory(title="Папка с моделью GigaAM (int8)",
                                       initialdir=initial)
        if not path:
            return
        self.settings.model_dir = path
        self.settings.save()
        self._check_model_hint()
        self._toast.show("Папка модели выбрана")

    # ── события файла ────────────────────────────────────────────────────
    def _on_file_selected(self, path: str) -> None:
        p = Path(path)
        if not p.exists() or not ffmpeg.is_supported(str(p)):
            self.upload.set_file(None)
            self.result._flash("Формат не поддерживается", error=True)
            return
        self._file = p
        self.result.clear()
        self.progress.set_progress(0.0)
        self.progress.set_stage("Файл готов. Нажмите «Распознать»", enabled_cancel=False)
        self.recognize_btn.configure(state="normal")

    def _on_file_cleared(self) -> None:
        """Сброс: файл удалён из загрузки → вернуть окно в исходное состояние."""
        self._file = None
        self.recognize_btn.configure(state="disabled")
        # если выполняется транскрипция, прервать её
        if self._running and self.worker.is_running():
            self.worker.cancel()
        self.progress.set_progress(0.0)
        self.progress.set_stage("Выберите или перетащите файл…", enabled_cancel=False)
        self.result.clear()

    def _on_engine_change(self, _choice: str) -> None:
        # выбор в выпадающем списке = выбор папки модели; движок всегда GigaAM
        for entry in self._models_list:
            if entry["label"] == _choice:
                self.settings.model_dir = str(entry["path"])
                self.settings.save()
                self._check_model_hint()
                self._toast.show(f"Модель: {entry['label']}")
                return

    def _refresh_model_list(self) -> None:
        """Заполнить выпадающий список папками-моделями из корня моделей."""
        from services.gigaam import discover_models
        root = self.settings.models_root or ""
        self._models_list = discover_models(root) if root else []
        if self._models_list:
            self.engine_menu.configure(
                values=[e["label"] for e in self._models_list])
            # показать текущую выбранную модель (по model_dir), иначе первую
            cur = Path(self.settings.model_dir).resolve()
            current_label = next(
                (e["label"] for e in self._models_list
                 if Path(str(e["path"])).resolve() == cur),
                self._models_list[0]["label"],
            )
            self.engine_menu.set(current_label)
        else:
            self.engine_menu.configure(
                values=["GigaAM v3 (int8) (папка не найдена)"])
            self.engine_menu.set("GigaAM v3 (int8) (папка не найдена)")

    # ── drag & drop (на корневом окне — ловим всюду) ─────────────────────
    def _on_drop_file(self, event) -> str:
        data = getattr(event, "data", "") or ""
        if not data:
            return ""
        # splitlist корректно разбирает `{путь с пробелами}` в один элемент
        items = self.tk.splitlist(data)
        if not items:
            return ""
        path = _first_dropped_path(str(items[0]))
        if path:
            self._on_file_selected(path)
            return "COPY"
        return ""

    def _on_drop_enter(self, event) -> str:
        self.upload.highlight(True)
        return "COPY"

    def _on_drop_leave(self, event) -> str:
        self.upload.highlight(False)
        return ""

    # ── запуск / отмена ──────────────────────────────────────────────────
    def _start_run(self) -> None:
        if self._running or self._rec_busy or self._file is None:
            return
        self._run_job(self._file)

    def _transcribe_recorded(self, path: Path, _stem: str) -> None:
        """Коллбек от RecorderPanel: после успешного stop транскрибируем запись."""
        if self._running:
            return
        self._run_job(Path(path))

    def _run_job(self, input_path: Path) -> None:
        model_dir = self.settings.resolve_model_dir()
        if not model_dir or not Path(model_dir).exists():
            self.result.show(
                "Модель GigaAM не найдена.\n\n"
                "Укажите папку с моделью (v3_e2e_ctc.int8.onnx + vocab) "
                "кнопкой «Папка модели» или в поле model_dir файла settings.json "
                "рядом с приложением.\n\n"
                f"Искали в: {[str(c) for c in self._model_dirs()]}",
                input_stem=input_path.stem,
            )
            return

        self._set_running(True)
        self.upload.set_file(str(input_path))
        self.result.clear()
        self.progress.set_progress(_STAGE_BASE[Stage.PROBE])
        self.progress.set_time(0)
        self._started_mono = time.monotonic()

        self.worker.start(
            input_path,
            engine_name=self.settings.engine or "gigaam",
            model_dir=str(model_dir),
            clean_enabled=self.settings.clean_enabled,
        )
        self._poll()

    def _on_recorder_busy(self, busy: bool) -> None:
        """Запись идёт — файловые контролы блокируются."""
        self._rec_busy = busy
        if busy:
            self.recognize_btn.configure(state="disabled")
            self.upload._browse_btn.configure(state="disabled")
            self.model_dir_btn.configure(state="disabled")
        else:
            self._set_running(self._running)

    def _on_save_mp3(self, value: bool) -> None:
        self.settings.save_mp3 = bool(value)
        self.settings.save()

    def _poll(self) -> None:
        """Вычитываем события воркера из главного потока."""
        for kind, val in self.worker.drain():
            if kind == EV_STAGE:
                self._on_stage(val)
            elif kind == EV_PROGRESS:
                self._on_progress(val)
            elif kind == EV_DONE:
                self._on_done(val)
        if self._running:
            self.progress.set_time(time.monotonic() - self._started_mono)
            self.after(200, self._poll)

    def _cancel_run(self) -> None:
        if self.worker.is_running():
            self.progress.set_stage("Остановка…", enabled_cancel=False)
            self.worker.cancel()

    def _toggle_pause(self) -> None:
        if not self.worker.is_running():
            return
        if self.worker.is_paused:
            self.worker.resume()
            self.progress.set_paused(False)
            self.progress.set_stage("Продолжаем…")
        else:
            self.worker.pause()
            self.progress.set_paused(True)
            self.progress.set_stage("Пауза — нажмите «Продолжить»")

    # ── колбеки из воркера ───────────────────────────────────────────────
    def _on_stage(self, stage: Stage) -> None:
        label = STAGE_LABEL.get(stage, stage.value)
        can_cancel = stage in (Stage.PROBE, Stage.EXTRACT, Stage.ASR, Stage.CLEAN)
        self.progress.set_stage(label, enabled_cancel=can_cancel)
        base = _STAGE_BASE.get(stage, 0.0)
        self.progress.set_progress(base)

    def _on_progress(self, frac: float) -> None:
        overall = _ASR_BASE + (max(0.0, min(1.0, frac)) * (_ASR_END - _ASR_BASE))
        self.progress.set_progress(overall)

    def _on_done(self, job) -> None:
        self._set_running(False)
        self.progress.set_enabled(False)
        did_cancel = job.stage == Stage.CANCELLED

        if did_cancel:
            self.progress.set_stage("Отменено", enabled_cancel=False)
            self.progress.set_progress(0.0)
            self._toast.show("Отменено", kind="warning")
        elif job.stage == Stage.ERROR:
            self.progress.set_stage("Ошибка", enabled_cancel=False)
            self.result.show(f"Ошибка:\n{job.error or 'неизвестная'}\n\n"
                             f"Файл: {job.input_path}", input_stem=job.input_path.stem)
            self._toast.show("Ошибка", kind="error")
        elif job.stage == Stage.DONE:
            self.progress.set_stage("Готово", enabled_cancel=False)
            self.progress.set_progress(1.0)
            self.progress.set_time(job.elapsed_seconds)
            self.result.show(job.transcript, input_stem=job.input_path.stem,
                             summary=self._timing_summary(job))
            self._toast.show("Готово ✓")

    # ── вспомогательное ──────────────────────────────────────────────────
    def _timing_summary(self, job) -> str:
        """Строка-сводка таймингов: длительность · разбивка · время обработки."""
        parts = []
        if job.duration_sec:
            parts.append(f"Длительность {job.fmt_duration()}")
        split = job.fmt_split()
        if split:
            parts.append(split)
        if job.elapsed_seconds:
            parts.append(f"Обработка {job.fmt_elapsed()}")
        return "   ·   ".join(parts)

    def _model_dirs(self):
        # for the error message
        from core.settings import _MODEL_CANDIDATES
        return [str(c) for c in _MODEL_CANDIDATES]

    # ── трей ───────────────────────────────────────────────────────────────
    # Клики по иконке у часов приходят в потоке pystray, поэтому мы не трогаем
    # Tk напрямую: кладём действие в очередь, а разбирает её цикл ниже в
    # главном потоке (после(...)), как и события воркера.
    def _tray_enqueue_show(self) -> None:
        self._tray_q.put("show")

    def _tray_enqueue_quit(self) -> None:
        self._tray_q.put("quit")

    def _tray_poll(self) -> None:
        while True:
            try:
                action = self._tray_q.get_nowait()
            except queue.Empty:
                break
            if action == "show":
                self._show_from_tray()
            elif action == "quit":
                self._quit_app()
        if self._tray is not None and self.winfo_exists():
            self.after(200, self._tray_poll)

    def _show_from_tray(self) -> None:
        self.deiconify()
        self.lift()
        self.focus_force()

    def _quit_app(self) -> None:
        if self._tray is not None:
            self._tray.stop()
        if self.recorder_panel.is_recording():
            self.recorder_panel.cancel()
        if self._running:
            self.worker.cancel()
        self.destroy()

    def _on_close(self) -> None:
        # Кнопка «✕»: сворачиваем окно в трей (работа продолжается в фоне).
        # Полностью закрыть приложение можно «Выход» в меню трея.
        if self._tray is not None:
            self.withdraw()
            return
        self._quit_app()
