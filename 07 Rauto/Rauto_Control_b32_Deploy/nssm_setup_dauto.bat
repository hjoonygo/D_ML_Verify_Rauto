@echo off
where python > "%TEMP%\rauto_py.txt"
set /p PY=<"%TEMP%\rauto_py.txt"
"%~dp0nssm.exe" stop DautoCollector
"%~dp0nssm.exe" remove DautoCollector confirm
"%~dp0nssm.exe" install DautoCollector "%PY%" "C:\dauto\dauto_collector.py"
"%~dp0nssm.exe" set DautoCollector AppDirectory "C:\dauto"
"%~dp0nssm.exe" set DautoCollector AppEnvironmentExtra PYTHONIOENCODING=utf-8
"%~dp0nssm.exe" set DautoCollector AppExit Default Restart
"%~dp0nssm.exe" set DautoCollector Start SERVICE_AUTO_START
"%~dp0nssm.exe" start DautoCollector
"%~dp0nssm.exe" status DautoCollector
pause
