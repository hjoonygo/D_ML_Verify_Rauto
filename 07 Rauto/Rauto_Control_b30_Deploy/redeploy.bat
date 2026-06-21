@echo off
echo Rauto Control redeploy b30 : RBAC + audit + PII mask + token expiry + SECRET FILE fallback
set PY=C:\Users\Administrator\AppData\Local\Programs\Python\Python310\python.exe
echo --- stop ONLY the server on port 8787 (keep data collector alive) ---
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8787"') do taskkill /PID %%P /F
echo --- copy new files to C:\RautoControl (rauto_secrets.txt is NOT touched) ---
copy /Y "%~dp0control_server.py" "C:\RautoControl\control_server.py"
copy /Y "%~dp0control_dashboard.html" "C:\RautoControl\control_dashboard.html"
echo --- IMPORTANT: put secrets in C:\RautoControl\rauto_secrets.txt (see rauto_secrets.SAMPLE.txt) ---
echo --- restart server (THIS window becomes the server, keep it open) ---
cd /d C:\RautoControl
"%PY%" control_server.py
