# Voice-X

**Voice-X** is a lightweight desktop speech-to-text workbench for Russian audio and video. It records microphone audio or accepts a dropped file, transcribes it **locally** (no cloud) with the [GigaAM v3](https://huggingface.co/istupakov/gigaam-v3) ONNX model, and writes the cleaned transcript to a `.txt` file.

Built with Python + `customtkinter`, it runs as a classic Windows desktop app with a system-tray presence.

> v0.1.0 — initial release.

---

## Features

- 🎙️ Record from your microphone, or drag-and-drop an audio/video file onto the window.
- 🔒 **Fully offline** transcription — nothing leaves your machine (GigaAM v3, ONNX int8, CPU only).
- 📄 Transcript is cleaned up and saved as a `.txt` next to the app data.
- 🧰 System tray: closing the window hides to the tray, a click restores it.
- 🌍 UI is in **Russian** (the ASR model is Russian-focused).

## Requirements

- Windows 10/11.
- Python **3.11+** when running from source.
- [ffmpeg](https://ffmpeg.org/) on `PATH` (used to decode audio/video; **not** bundled because it is large).

## Run from source

```bash
git clone https://github.com/subfocusx/voice-x.git
cd voice-x
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python app.py
```

By default the app looks for the GigaAM model in `./models` (or in the standard Hugging Face cache). Put the model files there if you want it to auto-detect:

```
models/
  config.json
  v3_e2e_ctc.int8.onnx
  vocab.json
```

## Build a standalone `.exe`

```bat
build.bat
```

This regenerates the icon (`build_icon.py`) and runs PyInstaller to produce `dist\Voice-X\Voice-X.exe` (onedir, windowed). Place the model in `./models` before building so it is bundled.

## Tests

```bash
.venv\Scripts\python -m pytest
```

## Technologies

- [customtkinter](https://customtkinter.tomschimansky.com/) — modern Tkinter UI
- [onnxruntime](https://onnxruntime.ai/) + [onnx-asr](https://github.com/istupakov/onnx-asr) — on-device ASR
- [SoundCard](https://github.com/bastibe/SoundCard) — WAV capture
- [pystray](https://github.com/moses-palmer/pystray) — system tray
- [PyInstaller](https://pyinstaller.org/) — packaging

## License

No license has been set yet — treat it as all rights reserved until one is added.
