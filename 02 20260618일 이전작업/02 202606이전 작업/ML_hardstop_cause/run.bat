@echo off
chcp 65001 >nul
cd /d %~dp0
copy /y nul .run_start >nul
python -c "import sklearn" 2>nul || pip install scikit-learn -q
python ml_test.py
python check.py
