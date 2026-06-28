@echo off
REM === Delete OLD Rauto (b32) on this AWS box. Double-click to run. ===
REM Self-elevates to admin, runs the cleanup (discovery -> type DELETE -> remove -> verify).
net session >nul 2>&1
if %errorlevel% neq 0 (
  echo Requesting administrator rights...
  powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0AWS_cleanup_old_rauto.ps1"
echo.
pause
