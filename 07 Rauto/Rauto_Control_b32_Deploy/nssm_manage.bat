@echo off
set /p X=1=status 2=start 3=stop : 
if "%X%"=="1" "%~dp0nssm.exe" status RautoControl
if "%X%"=="2" "%~dp0nssm.exe" start RautoControl
if "%X%"=="3" "%~dp0nssm.exe" stop RautoControl
pause
