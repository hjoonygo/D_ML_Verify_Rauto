@echo off
REM Rauto service manager (run as administrator) - RautoControl + DautoCollector
set NSSM=C:\RautoControl\nssm.exe
echo ================= Rauto service manager =================
echo   1 = status both    2 = start both    3 = stop both
echo   4 = restart both   5 = control log   6 = dauto log
echo =========================================================
set /p X=choose 1-6 then Enter: 
if "%X%"=="1" "%NSSM%" status RautoControl
if "%X%"=="1" "%NSSM%" status DautoCollector
if "%X%"=="2" "%NSSM%" start RautoControl
if "%X%"=="2" "%NSSM%" start DautoCollector
if "%X%"=="3" "%NSSM%" stop RautoControl
if "%X%"=="3" "%NSSM%" stop DautoCollector
if "%X%"=="4" "%NSSM%" restart RautoControl
if "%X%"=="4" "%NSSM%" restart DautoCollector
if "%X%"=="5" type C:\RautoControl\log_control.txt
if "%X%"=="6" type C:\RautoControl\log_dauto.txt
pause
