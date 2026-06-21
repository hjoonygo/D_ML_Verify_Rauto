@echo off
where python > "%TEMP%\rauto_py.txt"
set /p PY=<"%TEMP%\rauto_py.txt"
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8787"') do taskkill /F /PID %%P
"%~dp0nssm.exe" stop RautoControl
"%~dp0nssm.exe" remove RautoControl confirm
"%~dp0nssm.exe" install RautoControl "%PY%" "%~dp0control_server.py"
"%~dp0nssm.exe" set RautoControl AppDirectory "%~dp0."
"%~dp0nssm.exe" set RautoControl AppEnvironmentExtra PYTHONIOENCODING=utf-8
"%~dp0nssm.exe" set RautoControl AppStdout "%~dp0log_control.txt"
"%~dp0nssm.exe" set RautoControl AppStderr "%~dp0log_control.txt"
"%~dp0nssm.exe" set RautoControl AppExit Default Restart
"%~dp0nssm.exe" set RautoControl Start SERVICE_AUTO_START
"%~dp0nssm.exe" start RautoControl
"%~dp0nssm.exe" status RautoControl
pause
