set PYTHONIOENCODING=utf-8
cd /d %~dp0
:loop
python dauto_collector.py
echo [run_collector] collector exited %date% %time% — 10s 후 자동재시작 >> C:\BinanceData\dauto_health.log
timeout /t 10 /nobreak >nul
goto loop
