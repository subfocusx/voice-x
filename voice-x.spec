# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Voice-X: onedir, windowed, with system tray and ASR model.

Builds a self-contained folder dist/Voice-X:
    Voice-X.exe          - launches without a console
    _internal/models/    - the GigaAM ONNX int8 model (approx. 214 MB)
    _internal/...        - Python runtime + bundled dependency packages

ffmpeg is NOT bundled (a full build is ~217 MB) - the app locates it via the
WinGet Links folder / PATH (see services/ffmpeg._find).

Before building, place the GigaAM model into ./models (config.json +
v3_e2e_ctc.int8.onnx + vocab). The spec silently skips it if the folder is
absent.

Run from the project root:
    python -m PyInstaller voice-x.spec --noconfirm --clean
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

ROOT = Path(__file__).resolve().parent
MODELS = ROOT / "models"  # drop the GigaAM int8 model here before building

datas = []
binaries = []
hiddenimports = ["darkdetect", "ui.native_file_dialog"]

# GigaAM model (config.json + v3_e2e_ctc.int8.onnx + vocab) -> _internal/models
if MODELS.exists():
    datas += [(str(MODELS), "models")]

# packages that ship data/binaries (customtkinter themes, tkdnd, onnx_asr configs)
for pkg in ("customtkinter", "tkinterdnd2", "onnx_asr"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    [str(ROOT / "app.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["torch", "torchaudio", "librosa", "matplotlib", "pandas",
              "sklearn", "scipy", "IPython"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Voice-X",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(ROOT / "voice-x.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Voice-X",
)
