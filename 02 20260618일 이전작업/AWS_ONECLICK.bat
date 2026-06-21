@echo off
chcp 65001 >nul
set HERE=%~dp0
set PY=python
REM If "python" is not found below, run:  where python  and paste the full path here:
REM set PY=C:\Users\Administrator\AppData\Local\Programs\Python\Python310\python.exe

echo ============================================================
echo   Rauto UPDATE (one click)
echo ============================================================
echo [1/5] Stop old server (free files / port 8787)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8787 ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>nul
schtasks /end /tn "RautoControlServer" >nul 2>nul

echo [2/5] Update dashboard -> C:\RautoControl
powershell -NoProfile -Command "Expand-Archive -Path '%HERE%Rauto_ControlApp_PWA.zip' -DestinationPath 'C:\RautoControl' -Force"

echo [3/5] Update bot -> C:\Rauto1
powershell -NoProfile -Command "Expand-Archive -Path '%HERE%Rauto1_deploy.zip' -DestinationPath 'C:\Rauto1' -Force"

echo [4/5] Run bot once (make chart data)
pushd C:\Rauto1
"%PY%" test_Rauto1.py
popd

echo [5/5] Start server (new window - keep it open)
start "Rauto Server" cmd /k "C:\RautoControl\start_control_aws.bat"
timeout /t 4 >nul

echo --- verify (chart candles ^> 0) ---
"%PY%" -c "import json,urllib.request;d=json.load(urllib.request.urlopen('http://localhost:8787/state.json'));s=(d.get('slots') or [{}])[0];print('OK: slots',len(d.get('slots') or []),'| candles',len(s.get('px') or []),'| trades',len(s.get('trades') or []))"
echo.
echo DONE.  Phone: close and reopen the app.   Browser: press Ctrl+Shift+R
pause
