set PYTHONIOENCODING=utf-8
pip install -q numpy pandas smartmoneyconcepts
cd /d %~dp0
python test_07Prj_Ch4_RunAWS_Stg14_LivePaperWarmup.py
python check_07Prj_Ch4_RunAWS_Stg14_LivePaperWarmup.py
pause
