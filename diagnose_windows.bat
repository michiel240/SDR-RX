@echo off
setlocal
cd /d "%~dp0"
set "ENV_PY=%CD%\.venv\Scripts\python.exe"
if not exist "%ENV_PY%" (
  echo Nog geen virtuele omgeving gevonden. Start eerst start_windows.bat.
  pause
  exit /b 1
)
"%ENV_PY%" -m sdr_studio.diagnose
echo.
pause
