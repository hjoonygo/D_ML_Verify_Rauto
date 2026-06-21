@echo off
cd /d %~dp0
echo [1/2] test running...
python test_07Prj_Ch2_Stg2_TrendStack_OPVnNSweep.py
echo [2/2] check verifying...
python check_07Prj_Ch2_Stg2_TrendStack_OPVnNSweep.py
pause
