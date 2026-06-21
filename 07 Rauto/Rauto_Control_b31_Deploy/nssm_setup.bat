@echo off
REM ============================================================
REM  Rauto NSSM service setup  (RIGHT-CLICK -> Run as administrator)
REM  Registers TWO always-on services: RautoControl + DautoCollector.
REM  Closing cmd windows / logoff / reboot will NOT kill them.
REM  PREREQ: nssm.exe must be at C:\RautoControl\nssm.exe
REM ============================================================

set NSSM=C:\RautoControl\nssm.exe
REM auto-detect python; falls back to the full path below if not found
set PY=
for /f "delims=" %%i in ('where python 2^>nul') do set "PY=%%i"
if not exist "%PY%" set PY=C:\Users\Administrator\AppData\Local\Programs\Python\Python310\python.exe

set CTRL=C:\RautoControl

echo --- using python: %PY% ---
echo --- using nssm  : %NSSM% ---

echo --- copy b30 files into %CTRL% ---
if not exist "%CTRL%" mkdir "%CTRL%"
copy /Y "%~dp0control_server.py" "%CTRL%\control_server.py"
copy /Y "%~dp0control_dashboard.html" "%CTRL%\control_dashboard.html"

echo --- stop any window-server on port 8787 ---
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8787"') do taskkill /PID %%P /F

echo --- (re)install RautoControl service (dashboard + bot auto-run) ---
"%NSSM%" stop RautoControl
"%NSSM%" remove RautoControl confirm
"%NSSM%" install RautoControl "%PY%" "%CTRL%\control_server.py"
"%NSSM%" set RautoControl AppDirectory "%CTRL%"
"%NSSM%" set RautoControl AppEnvironmentExtra PYTHONIOENCODING=utf-8 RAUTO_REPO=C:\RautoRepo RAUTO_GIT_PULL=1 RAUTO_STATE_GLOB=C:\Rauto*\state.json RAUTO_FLAG_DIR=C:\Rauto1 RAUTO_CTRL_PORT=8787
"%NSSM%" set RautoControl AppExit Default Restart
"%NSSM%" set RautoControl AppRestartDelay 30000
"%NSSM%" set RautoControl AppStdout %CTRL%\log_control.txt
"%NSSM%" set RautoControl AppStderr %CTRL%\log_control.txt
"%NSSM%" set RautoControl Start SERVICE_AUTO_START
"%NSSM%" start RautoControl

echo --- (re)install DautoCollector service (price collector) ---
"%NSSM%" stop DautoCollector
"%NSSM%" remove DautoCollector confirm
"%NSSM%" install DautoCollector "%PY%" "C:\dauto\dauto_collector.py"
"%NSSM%" set DautoCollector AppDirectory "C:\dauto"
"%NSSM%" set DautoCollector AppEnvironmentExtra PYTHONIOENCODING=utf-8
"%NSSM%" set DautoCollector AppExit Default Restart
"%NSSM%" set DautoCollector AppRestartDelay 30000
"%NSSM%" set DautoCollector AppStdout %CTRL%\log_dauto.txt
"%NSSM%" set DautoCollector AppStderr %CTRL%\log_dauto.txt
"%NSSM%" set DautoCollector Start SERVICE_AUTO_START
"%NSSM%" start DautoCollector

echo.
echo --- status (both should say SERVICE_RUNNING) ---
"%NSSM%" status RautoControl
"%NSSM%" status DautoCollector
echo.
echo DONE. You can now CLOSE every cmd window. Both services keep running.
pause
