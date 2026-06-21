@echo off
echo Rauto Control redeploy b31 (window mode) : RBAC + Bot-load + remove + cert
set PY=C:\Users\Administrator\AppData\Local\Programs\Python\Python310\python.exe
if not exist "%PY%" set PY=python
echo --- stop ONLY the server on port 8787 (data collector stays alive) ---
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8787"') do taskkill /PID %%P /F
echo --- copy b31 files into C:\RautoControl ---
if not exist "C:\RautoControl" mkdir "C:\RautoControl"
copy /Y "%~dp0control_server.py" "C:\RautoControl\control_server.py"
copy /Y "%~dp0control_dashboard.html" "C:\RautoControl\control_dashboard.html"
echo --- settings (RAUTO_REPO needed so Bot-load can find runner files) ---
set RAUTO_REPO=C:\RautoRepo
set RAUTO_GIT_PULL=1
set RAUTO_STATE_GLOB=C:\Rauto*\state.json
set RAUTO_FLAG_DIR=C:\Rauto1
set RAUTO_CTRL_PORT=8787
echo --- start server (KEEP THIS WINDOW OPEN) ---
cd /d C:\RautoControl
"%PY%" control_server.py
pause
