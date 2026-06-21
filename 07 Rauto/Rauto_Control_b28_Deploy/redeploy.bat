@echo off
echo Rauto Control redeploy b28 : RBAC + auth + audit + PII mask
set PY=C:\Users\Administrator\AppData\Local\Programs\Python\Python310\python.exe
echo --- stop ONLY the server on port 8787 (keep data collector alive) ---
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8787"') do taskkill /PID %%P /F
echo --- copy new files to C:\RautoControl ---
copy /Y "%~dp0control_server.py" "C:\RautoControl\control_server.py"
copy /Y "%~dp0control_dashboard.html" "C:\RautoControl\control_dashboard.html"
echo --- RBAC: if RAUTO_TOKENS is empty, auth is OFF (open). Run set_tokens.bat first to enable. ---
echo RAUTO_TOKENS=%RAUTO_TOKENS%
echo --- restart server (THIS window becomes the server, keep it open) ---
cd /d C:\RautoControl
"%PY%" control_server.py
