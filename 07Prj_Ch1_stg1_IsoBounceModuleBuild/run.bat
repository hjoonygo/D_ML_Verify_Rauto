@echo off
cd /d %~dp0
python test_07Prj_Ch1_stg1_IsoBounceModuleBuild.py
python check_07Prj_Ch1_stg1_IsoBounceModuleBuild.py
pause
