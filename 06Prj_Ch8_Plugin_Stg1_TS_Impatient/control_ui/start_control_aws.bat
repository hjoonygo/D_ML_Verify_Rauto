@echo off
set PYTHONIOENCODING=utf-8
chcp 65001 >nul
REM ===== Rauto Control Server for AWS (always-on via schtasks) =====
REM If launched as SYSTEM by Task Scheduler and "python" is not found,
REM set the FULL python path on the next line (run: where python  to find it):
set PY=python
REM   example: set PY=C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe

set RAUTO_STATE_JSON=C:\Rauto1\state.json
set RAUTO_FLAG_DIR=C:\Rauto1
set RAUTO_CTRL_PORT=8787
if not exist "C:\Rauto1\state.json" set RAUTO_STATE_JSON=%~dp0state_example.json

echo ==================================================
echo   Rauto Control Server (AWS)  port 8787
echo   Local : http://localhost:8787
echo   Phone : via Tailscale  https://<your-machine>.ts.net
echo   state = %RAUTO_STATE_JSON%
echo ==================================================
"%PY%" "%~dp0control_server.py"
pause
