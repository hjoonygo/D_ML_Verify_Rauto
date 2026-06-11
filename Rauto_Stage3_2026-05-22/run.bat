@echo off
chcp 65001 >nul
echo. > .run_start
python test.py
python check.py
