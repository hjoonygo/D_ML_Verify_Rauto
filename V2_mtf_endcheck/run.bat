@echo off
chcp 65001 >nul
cd /d %~dp0
copy /y nul .run_start >nul
python test.py
python check.py
