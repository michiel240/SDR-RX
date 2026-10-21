@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
title SDR Studio RX by M@rcello v0.8.2 beta - RTL-SDR + Airspy R2
color 07
echo.
echo ================================================================
echo  SDR Studio RX by M@rcello v0.8.2 beta  -  STARTER MET USB-DIAGNOSE
echo ================================================================
echo  Startbestand: %~f0
echo  Programmamap: %CD%
echo.
set "ENV_PY=%~dp0.venv\Scripts\python.exe"

rem Gebruik een bestaande omgeving alleen als die nog werkt.
if exist "%ENV_PY%" goto verify_venv
goto find_python

:verify_venv
"%ENV_PY%" -c "import sys,struct; assert (3,11) <= sys.version_info[:2] < (3,15) and struct.calcsize('P') == 8" >nul 2>&1
if not errorlevel 1 goto check_dependencies
echo [LET OP] De .venv bestaat, maar de Python daarin werkt niet.
echo           Hernoem de map .venv naar .venv-oud en start opnieuw.
goto failure

:find_python
echo [1/3] Werkelijk geinstalleerde Python zoeken (64-bit, 3.11 - 3.14)...
set "BASE_PY="
call :probe python
if defined BASE_PY goto create_venv
call :probe py -3.13
if defined BASE_PY goto create_venv
call :probe py -3.11
if defined BASE_PY goto create_venv
call :probe py -3.12
if defined BASE_PY goto create_venv
call :probe py -3.14
if defined BASE_PY goto create_venv
call :probe py -3
if defined BASE_PY goto create_venv
call :probe py
if defined BASE_PY goto create_venv
call :probe python3
if defined BASE_PY goto create_venv

echo.
echo FOUT: Geen werkende 64-bit Python 3.11 tot 3.14 gevonden.
echo Voer deze opdrachten uit in CMD om te zien wat geinstalleerd is:
echo     python --version
echo     py -0p
echo Download anders Python 3.13 (64-bit) op https://www.python.org/downloads/windows/
echo Python 3.12 is NIET verplicht.
goto failure

:probe
rem BELANGRIJK: 'py -3.12' kan door Windows Python Manager ten onrechte
rem succes teruggeven terwijl die versie ontbreekt. Daarom nooit alleen
rem ERRORLEVEL testen; we accepteren uitsluitend onze exacte bewijsregel.
for /f "delims=" %%Q in ('%* -c "import sys,struct; print('SDR_RX_PYTHON_OK' if (3,11) <= sys.version_info[:2] < (3,15) and struct.calcsize('P') == 8 else 'ONGESCHIKT')" 2^>nul') do (
    if "%%Q"=="SDR_RX_PYTHON_OK" set "BASE_PY=%*"
)
exit /b 0

:create_venv
echo [1/3] Gecontroleerde Python: %BASE_PY%
echo [2/3] Python-omgeving aanmaken...
%BASE_PY% -m venv "%~dp0.venv"
if errorlevel 1 goto venv_failed
if not exist "%ENV_PY%" goto venv_failed

:check_dependencies
echo [2/3] Bibliotheken controleren...
"%ENV_PY%" -c "import numpy, scipy, PySide6, pyqtgraph, sounddevice; import importlib.metadata as md; md.version('pyrtlsdr')" >nul 2>&1
if not errorlevel 1 goto launch

echo [2/3] Bibliotheken installeren (eerste keer internet nodig)...
"%ENV_PY%" -m pip install --disable-pip-version-check -r "%~dp0requirements.txt"
if errorlevel 1 goto install_failed
"%ENV_PY%" -c "import numpy, scipy, PySide6, pyqtgraph, sounddevice; import importlib.metadata as md; md.version('pyrtlsdr')" >nul 2>&1
if errorlevel 1 goto install_failed

:launch
echo [3/3] SDR Studio RX by M@rcello starten...
"%ENV_PY%" -m sdr_studio
if errorlevel 1 goto application_failed
exit /b 0

:venv_failed
echo FOUT: Aanmaken van de virtuele omgeving mislukt.
goto failure
:install_failed
echo FOUT: Installatie van Python-bibliotheken mislukt.
echo Controleer de meldingen hierboven en de internetverbinding.
goto failure
:application_failed
echo FOUT: SDR Studio RX kan niet worden gestart.
echo Kopieer de foutmelding hierboven.
goto failure
:failure
echo.
echo  LET OP: Kijk bovenaan of er v0.8.2 beta STARTER MET USB-DIAGNOSE staat.
echo  Staat daar nog Python-omgeving maken zonder versienummer?
echo  Gebruik START_HIER_v0.8.bat in de nieuwe map.
echo.
pause
exit /b 1
