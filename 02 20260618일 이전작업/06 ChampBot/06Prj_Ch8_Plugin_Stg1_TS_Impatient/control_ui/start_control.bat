@echo off
set PYTHONIOENCODING=utf-8
chcp 65001 >nul
REM Rauto control dashboard server (double-click to run). Ctrl+C to stop, then press Y.

if exist "C:\Rauto1\state.json" (
  set RAUTO_STATE_JSON=C:\Rauto1\state.json
  set RAUTO_FLAG_DIR=C:\Rauto1
) else (
  set RAUTO_STATE_JSON=%~dp0state_example.json
  set RAUTO_FLAG_DIR=C:\Rauto1
)
set RAUTO_CTRL_PORT=8787

echo ==================================================
echo   Rauto Control Server   ( Ctrl+C = stop, then Y )
echo --------------------------------------------------
echo   PC  (this computer) : http://localhost:8787
echo   Phone (same Wi-Fi)  : http://192.168.219.111:8787
echo   (if IP changed: run ipconfig, use the IPv4 line)
echo --------------------------------------------------
echo   state file = %RAUTO_STATE_JSON%
echo   flags dir  = %RAUTO_FLAG_DIR%
echo ==================================================
echo.
python "%~dp0control_server.py"
pause
