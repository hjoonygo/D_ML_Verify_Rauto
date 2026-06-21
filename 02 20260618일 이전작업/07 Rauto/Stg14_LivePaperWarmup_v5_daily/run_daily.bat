set PYTHONIOENCODING=utf-8
cd /d %~dp0
python test_07Prj_Ch4_RunAWS_Stg14_LivePaperWarmup.py
python check_07Prj_Ch4_RunAWS_Stg14_LivePaperWarmup.py
python daily_health.py
