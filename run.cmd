@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

rem --- python: prefer a local .venv, otherwise fall back to a plain `python` ---
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

if not exist "%PY%" (
  echo [error] Python interpreter not found:
  echo   %PY%
  echo Create a .venv first:  py -3.11 -m venv .venv
  pause
  exit /b 1
)

echo.
echo   Voice-X - local speech-to-text (Russian)
echo   python: %PY%
echo.
"%PY%" app.py
echo.
echo Voice-X exited (code %ERRORLEVEL%).
pause
endlocal
