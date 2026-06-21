@echo off
REM Register ONLY the Dauto price collector as a service (run as administrator)
set NSSM=C:\RautoControl\nssm.exe
set PY=
for /f "delims=" %%i in ('where python 2^>nul') do set "PY=%%i"
if not exist "%PY%" set PY=C:\Users\Administrator\AppData\Local\Programs\Python\Python310\python.exe

echo --- using python: %PY% ---
echo --- (re)install DautoCollector service (c:\dauto\dauto_collector.py) ---
"%NSSM%" stop DautoCollector
"%NSSM%" remove DautoCollector confirm
"%NSSM%" install DautoCollector "%PY%" "C:\dauto\dauto_collector.py"
"%NSSM%" set DautoCollector AppDirectory "C:\dauto"
"%NSSM%" set DautoCollector AppEnvironmentExtra PYTHONIOENCODING=utf-8
"%NSSM%" set DautoCollector AppExit Default Restart
"%NSSM%" set DautoCollector AppRestartDelay 30000
"%NSSM%" set DautoCollector AppStdout C:\RautoControl\log_dauto.txt
"%NSSM%" set DautoCollector AppStderr C:\RautoControl\log_dauto.txt
"%NSSM%" set DautoCollector Start SERVICE_AUTO_START
"%NSSM%" start DautoCollector
echo.
"%NSSM%" status DautoCollector
pause
