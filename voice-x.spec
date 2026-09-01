# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec для Voice-X: onedir, windowed, с треем и моделью.

Собирает самодостаточную папку dist/Voice-X:
    Voice-X.exe          — запуск без консоли
    bin/ffmpeg.exe       — забандленный ffmpeg (для декодирования)
    bin/ffprobe.exe      — забандленный ffprobe (для probe/duration)
    _internal/models/    — модель GigaAM (214 MB)
    _internal/...        — python runtime + зависимые пакеты

ffmpeg/ffprobe бандлятся в bin/ дистрибутива (всё в одном месте, на целевой
машине внешний ffmpeg не требуется). services/ffmpeg._find ищет их первым
делом в resource_dir()/bin, затем как fallback — через WinGet Lines/PATH.

Запуск сборки:
    <venv>\\python.exe -m PyInstaller voice-x.spec --noconfirm --clean
"""
import os

from PyInstaller.utils.hooks import collect_all

ROOT = r"E:\Code\Python\voice-x"

datas = []
binaries = []
hiddenimports = ["darkdetect", "ui.native_file_dialog"]

# модель GigaAM (config.json + v3_e2e_ctc.int8.onnx + vocab) -> _internal/models
datas += [(r"E:\Code\Python\writher-V.1.1.0\models", "models")]

# ffmpeg/ffprobe -> bin/ дистрибутива (возле exe; ищет services/ffmpeg._find)
datas += [
    (os.path.join(ROOT, "bin", "ffmpeg.exe"), "bin"),
    (os.path.join(ROOT, "bin", "ffprobe.exe"), "bin"),
]

# пакеты со своими data/binaries (темы customtkinter, tkdnd, onnx_asr configs)
for pkg in ("customtkinter", "tkinterdnd2", "onnx_asr"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    [ROOT + "\\app.py"],
    pathex=[ROOT],
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
    icon=ROOT + "\\voice-x.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Voice-X",
)
