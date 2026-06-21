set PYTHONIOENCODING=utf-8
cd /d %~dp0
set PY=python
if defined RAUTO_PY set PY=%RAUTO_PY%
set LOGF=%~dp0rauto_daily.log
echo ===== [%date% %time%] Rauto_Daily START (PY=%PY%) =====>>"%LOGF%"
echo [%date% %time%] STEP1 test (paper full-replay)>>"%LOGF%"
"%PY%" test_07Prj_Ch4_RunAWS_Stg14_LivePaperWarmup.py >>"%LOGF%" 2>&1
echo [%date% %time%] STEP2 check (contamination)>>"%LOGF%"
"%PY%" check_07Prj_Ch4_RunAWS_Stg14_LivePaperWarmup.py >>"%LOGF%" 2>&1
echo [%date% %time%] STEP3 daily_health (gate)>>"%LOGF%"
"%PY%" daily_health.py >>"%LOGF%" 2>&1
echo [%date% %time%] STEP4 alert_check (telegram diff)>>"%LOGF%"
if exist "%~dp0alert_check.py" ("%PY%" "%~dp0alert_check.py" >>"%LOGF%" 2>&1) else ("%PY%" "%~dp0..\07Prj_Ch4_RunAWS_Stg16_OpsGuard\alert_check.py" >>"%LOGF%" 2>&1)
echo ===== [%date% %time%] Rauto_Daily END =====>>"%LOGF%"
