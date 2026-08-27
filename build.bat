@echo off
chcp 65001 >nul
setlocal
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
cd /d "%~dp0"

rem Portability: pass your venv python as the first argument, otherwise the
rem script looks for a local ".venv\Scripts\python.exe".
rem   build.bat                      -> uses .venv\Scripts\python.exe
rem   build.bat C:\Path\py.exe       -> uses the given interpreter
set "PY_VER=%~1"
if "%PY_VER%"=="" set "PY_VER=.venv\Scripts\python.exe"

if not exist "%PY_VER%" (
  echo Build venv python not found: %PY_VER%
  echo Create one with:  py -3.11 -m venv .venv && .venv\Scripts\python -m pip install -r requirements.txt
  pause
  exit /b 1
)

echo === 1/2 Icon ===
"%PY_VER%" build_icon.py

echo === 2/2 Build onedir ===
"%PY_VER%" -m PyInstaller voice-x.spec --noconfirm --clean

echo.
echo Done: dist\Voice-X\Voice-X.exe
pause
endlocal
