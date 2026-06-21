set PYTHONIOENCODING=utf-8
cd /d %~dp0
set MODE=%1
if "%MODE%"=="" set MODE=MANUAL
if not exist C:\BinanceData mkdir C:\BinanceData
echo [run_collector][%MODE%] start %date% %time% >> C:\BinanceData\dauto_health.log
:loop
python dauto_collector.py
echo [run_collector][%MODE%] collector exited %date% %time% — 10s 후 자동재시작 >> C:\BinanceData\dauto_health.log
timeout /t 10 /nobreak >nul
goto loop
