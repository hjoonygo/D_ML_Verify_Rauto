@echo off
echo Rauto Control redeploy : champ-auto + 2tables + email/telegram
set PY=C:\Users\Administrator\AppData\Local\Programs\Python\Python310\python.exe
echo --- stop ONLY the server on port 8787 (keep data collector alive) ---
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8787"') do taskkill /PID %%P /F
echo --- copy new files to C:\RautoControl ---
copy /Y "%~dp0control_server.py" "C:\RautoControl\control_server.py"
copy /Y "%~dp0control_dashboard.html" "C:\RautoControl\control_dashboard.html"
echo --- restart server (THIS window becomes the server, keep it open) ---
cd /d C:\RautoControl
"%PY%" control_server.py
