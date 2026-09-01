# Voice-X — локальная расшифровка + аудиозапись

Офлайн-десктоп-приложение на Python + CustomTkinter: локальная запись звука
(микрофон и/или системный выход) и распознавание речи на русской модели
**GigaAM v3** (ONNX, int8). Никакого облака — всё считает локально.

## Возможности

- **Локальный рекордер**: запись с микрофона, системного звука (Google Meet,
  Zoom, браузер) или обоих сразу; таймер + индикатор уровня; WAV на диск.
- **Авто-расшифровка**: после остановки записи запускается уже существующий
  конвейер распознавания — результат `*.txt`.
- **Drag&drop расшифровка** готовых аудио/видеофайлов (сохранена без изменений).
- Опционально сохранять MP3 рядом с WAV (галка «MP3» в панели записи).

## Запуск

Двойной клик `run.cmd` либо:

```powershell
<venv>\Scripts\python.exe app.py
```

Тестовый прогон пайплайна из консоли (без GUI):

```powershell
python -m services.cli "path/to/file.mp4" [--model-dir ...]
```

## Установка зависимостей

```powershell
<venv>\Scripts\python.exe -m pip install -r requirements.txt
```

- `soundcard>=0.4.6` — захват звука через WASAPI (микрофон + loopback).
- `ffmpeg`/`ffprobe` — декодирование и конвертация (на PATH или WinGet-линки).

## Архитектура

Voice-X разделён на слои; UI не знает об аудио-API, а расшифровка не знает о GUI.

```
core/      пути, настройки, модель Job / состояния записи, логирование
services/
  transcriber.py   пайплайн расшифровки (transcribe_file -> Job)
  ffmpeg.py        декод/конвертация (wav, mp3, 16k mono)
  recorder/        <-- НОВЫЙ ЛОКАЛЬНЫЙ РЕКОРДЕР
    __init__.py    публичное API
    wasapi.py      перечисление устройств (mic + loopback), метки
    audio_capture.py  абстракция потока захвата (open/read/close)
    recorder.py    AudioRecorder: start/stop/pause/resume/cancel/get_state/get_levels
ui/        main_window, worker (Worker/Queue), panel записи, результат
app.py     точка входа
```

### Рекордер как отдельная служба

`services/recorder` — автономный слой без привязки к GUI и к транскрайберу:

- `AudioRecorder` интерфейс: `start()`, `stop()`, `cancel()`, `get_state()`,
  `get_levels()`; не возвращает объекты UI.
- Фоновый поток (`voicex-recorder`) ведёт захват, пишет WAV в
  `core.paths.recordings_dir()` и по завершении переходит в
  `RecordingState.DONE` (или `ERROR`/`CANCELLED`).
- Остановка → сохранённый WAV → автоматически вызывается
  `services.transcriber.transcribe_file(...)` — та же цепочка, что и для
  перетащенного файла.

### Поток захвата (WASAPI, soundcard 0.4.6)

`soundcard.all_microphones(include_loopback=True)` возвращает настоящие
микрофоны (`isloopback=False`) и loopback каждого устройства воспроизведения
(`isloopback=True`). Именно так ловится «системный звук» без OBS и внешних
зависимостей.

> Заметка: у объекта `_Speaker` в soundcard 0.4.6 **нет** `.recorder()` —
> рабочий путь только через `all_microphones(include_loopback=True)`.

Запись ведётся на 48 кГц, моно. Для режима «Микрофон + система» два потока
(микрофон + loopback) работают одновременно и **усредняются** (мягкий микс без
клиппинга) — осознанный компромисс: объём может слегка просесть, зато один WAV
без дополнительной обработки.

### Поток расшифровки

После записи WAV 48 кГц проходит штатный путь: `ffmpeg` ресемплит в 16 кГц моно,
`GigaAM` распознаёт, при включённой очистке — LLM-очистка. Результат —
`{stem}_расшифровка.txt` рядом с исходником/в папке результата.

### Состояния

- **Рекордер** — своя машина: `IDLE → RECORDING → STOPPING → DONE | ERROR | CANCELLED`.
- **Расшифровка** — отдельная: `PROBE → EXTRACT → ASR → CLEAN → DONE | ERROR | CANCELLED`.

## Тесты

```powershell
<venv>\Scripts\python.exe -m pytest
```

`tests/test_recorder.py` — хардвар-агностичные проверки: модель состояний,
фильтрация/дефолт устройств (без обращения к реальному звуку), конвертация
wav→mp3 на синтезированном сигнале (пропускается, если ffmpeg недоступен).
