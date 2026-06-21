@echo off
cd /d "%~dp0"
python backtest.py
python check.py
