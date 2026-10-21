@echo off
setlocal
cd /d "%~dp0"
title SDRStudio RX - Airspy DLL importeren
if not exist ".venv\Scripts\python.exe" (
  echo Start eerst START_HIER_v0.3.bat om Python in te richten.
  pause
  exit /b 1
)
echo.
echo Selecteer de OFFICIELE Windows x64 Airspy Host Tools ZIP.
echo Download: https://github.com/airspy/airspyone_host/releases/tag/v1.0.10
echo.
".venv\Scripts\python.exe" -m sdr_studio.airspy_install %*
echo.
pause
