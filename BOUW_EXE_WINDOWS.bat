@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
title SDR Studio RX - Windows EXE bouwen en testen

echo.
echo ==========================================================
echo   SDR Studio RX by M@rcello - EXE BOUWER (v0.8.2)
echo ==========================================================
echo.
echo Projectmap: %CD%
echo.

if not exist "sdr_studio\app.py" goto missing_project
if not exist "requirements.txt" goto missing_project
if not exist "requirements-tests.txt" goto missing_project

set "PY=%CD%\.venv\Scripts\python.exe"
if not exist "%PY%" goto missing_venv
"%PY%" -c "import sys,struct; assert (3,11) <= sys.version_info[:2] < (3,15) and struct.calcsize('P') == 8" >nul 2>&1
if errorlevel 1 goto wrong_python

:install
echo [1/4] Benodigde bouw- en testmodules installeren...
"%PY%" -m pip install --disable-pip-version-check -r requirements.txt -r requirements-tests.txt "pyinstaller>=6.0"
if errorlevel 1 goto install_error

echo.
echo [2/4] Alle softwaretests uitvoeren...
"%PY%" -m pytest -q
if errorlevel 1 goto test_error

echo.
echo [3/4] Test-EXE bouwen. Dit kan enkele minuten duren...
if not exist "_build_tools" mkdir "_build_tools"
> "_build_tools\sdr_rx_entry.py" echo from sdr_studio.app import main
>> "_build_tools\sdr_rx_entry.py" echo if __name__ == '__main__':
>> "_build_tools\sdr_rx_entry.py" echo     main()

rem --console toont fouten bij de eerste Windows/hardwaretests.
rem --contents-directory . houdt drivers naast de EXE beschikbaar.
"%PY%" -m PyInstaller --noconfirm --clean --onedir --console --contents-directory . --name SDR-Studio-RX --paths "%CD%" --collect-all rtlsdr --collect-all pyrtlsdrlib --collect-all _sounddevice_data "_build_tools\sdr_rx_entry.py"
if errorlevel 1 goto build_error

set "OUT=%CD%\dist\SDR-Studio-RX"
if not exist "%OUT%\SDR-Studio-RX.exe" goto build_error
if not exist "%OUT%\drivers" mkdir "%OUT%\drivers"
if not exist "%OUT%\decoders\bin" mkdir "%OUT%\decoders\bin"

rem Kopieer ALLEEN lokaal aanwezige driver-DLL's voor eigen gebruik.
if exist "drivers\*.dll" (
    echo Werkende lokale driver-DLLs kopieren...
    xcopy /I /Y "drivers\*.dll" "%OUT%\drivers\" >nul
)

echo.
echo [4/4] Gereed!
echo.
echo   EXE: "%OUT%\SDR-Studio-RX.exe"
echo.
echo TEST: open deze EXE en kies eerst Demo (geen hardware).
echo Daarna RTL-SDR of Airspy R2 testen met echte hardware.
echo Houd de gehele map 'dist\SDR-Studio-RX' bij elkaar.
echo De zwarte console is opzettelijk zichtbaar om fouten te kunnen lezen.
echo.
pause
exit /b 0

:missing_project
echo FOUT: Zet dit BAT-bestand in de hoofdmap van het uitgepakte project.
echo Daar moeten 'sdr_studio' en 'requirements.txt' staan.
goto failure
:missing_venv
echo FOUT: De Python-omgeving .venv ontbreekt.
echo Dubbelklik eerst op START_HIER_v0.8.2.bat en sluit daarna de SDR-app.
echo Start vervolgens dit EXE-bouwbestand opnieuw.
goto failure
:wrong_python
echo FOUT: .venv gebruikt geen werkende 64-bit Python 3.11 tot en met 3.14.
goto failure
:install_error
echo FOUT: Modules installeren is mislukt. Controleer internet en de meldingen hierboven.
goto failure
:test_error
echo FOUT: Een of meer softwaretests zijn niet geslaagd. EXE is NIET gebouwd.
echo Gebruik de bijgewerkte GitHub-broncode met de Windows-testfix.
goto failure
:build_error
echo FOUT: PyInstaller kon de EXE niet bouwen.
echo Controleer de foutmelding hierboven.
goto failure
:failure
echo.
pause
exit /b 1
