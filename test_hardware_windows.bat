@echo off
setlocal
cd /d "%~dp0"
set "ENV_PY=%CD%\.venv\Scripts\python.exe"
if not exist "%ENV_PY%" (
 echo FOUT: start eerst start_windows.bat om Python te installeren.
 pause
 exit /b 1
)
echo.
echo SDR Studio RX by M@rcello v0.3 - USB-test voor RTL-SDR en Airspy R2
echo Sluit eerst SDR++, SDR#, andere SDR programma's en decoders.
echo [1/3] Drivers en aangesloten apparaten zoeken...
"%ENV_PY%" -m sdr_studio.diagnose
echo.
echo [2/3] Test RTL-SDR (100 MHz, 2.5 seconden)...
"%ENV_PY%" -m sdr_studio.hardware_test rtl
if errorlevel 1 echo RTL-SDR ontvangsttest mislukt. Zie melding hierboven.
echo.
echo [3/3] Test Airspy R2 (100 MHz, 2.5 seconden)...
"%ENV_PY%" -m sdr_studio.hardware_test airspy
if errorlevel 1 echo Airspy R2 ontvangsttest mislukt. Zie melding hierboven.
echo.
echo.
echo RTL-SDR: LIBUSB_ERROR_IO betekent dat USB-toegang nog niet werkt, geen Python-fout.
echo Airspy: ontbrekende libairspy.dll betekent dat de x64 DLL nog in drivers moet.
echo.
echo Let op: elke test opent maar EEN SDR tegelijk en sluit die direct.
echo Kopieer de uitvoer bij problemen; afsluiten met toets.
pause
