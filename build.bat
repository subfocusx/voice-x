@echo off
chcp 65001 >nul
setlocal
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
cd /d "%~dp0"

set "PY_VER=..\writher-V.1.1.0\venv_v2\Scripts\python.exe"
if not exist "%PY_VER%" (
  echo НЕ найден venv построения: %PY_VER%
  echo Ожидается: E:\Code\Python\writher-V.1.1.0\venv_v2\Scripts\python.exe
  pause
  exit /b 1
)

echo === 1/2 Иконка ===
"%PY_VER%" build_icon.py

echo === 2/2 Сборка onedir ===
"%PY_VER%" -m PyInstaller voice-x.spec --noconfirm --clean

echo.
echo Готово: dist\Voice-X\Voice-X.exe
pause
endlocal
