@echo off
setlocal
cd /d "%~dp0"
title SDR Studio RX - Externe decoders controleren
set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
  echo Eerst START_HIER_v0.5.bat starten om Python in te stellen.
  goto done
)
"%PYTHON_EXE%" -m sdr_studio.check_decoders
:done
pause
