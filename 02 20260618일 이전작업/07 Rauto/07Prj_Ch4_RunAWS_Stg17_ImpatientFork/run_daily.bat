set PYTHONIOENCODING=utf-8
cd /d %~dp0
set PY=python
if defined RAUTO_PY set PY=%RAUTO_PY%
REM ==== fork isolation: never collide with live C:\run_Rauto ====
set RAUTO_DIR=%~dp0
set RAUTO_OPS_STATE=%~dp0ops_state.json
set RAUTO_OPS_LOG=%~dp0ops_alert.log
REM RAUTO_DAUTO_DIR=C:\BinanceData shared input. TELEGRAM_* machine vars shared (same phone, tag [PAPER-IMP]).
set LOGF=%~dp0rauto_daily.log
echo ===== [%date% %time%] Rauto_Impatient START (PY=%PY%) =====>>"%LOGF%"
echo [%date% %time%] STEP1 test (impatient paper full-replay)>>"%LOGF%"
"%PY%" test_07Prj_Ch4_RunAWS_Stg17_ImpatientFork.py >>"%LOGF%" 2>&1
echo [%date% %time%] STEP2 check (contamination+hash)>>"%LOGF%"
"%PY%" check_07Prj_Ch4_RunAWS_Stg17_ImpatientFork.py >>"%LOGF%" 2>&1
echo [%date% %time%] STEP3 daily_health (gate)>>"%LOGF%"
"%PY%" daily_health.py >>"%LOGF%" 2>&1
echo [%date% %time%] STEP4 alert_check (telegram diff, [PAPER-IMP])>>"%LOGF%"
"%PY%" alert_check.py >>"%LOGF%" 2>&1
echo ===== [%date% %time%] Rauto_Impatient END =====>>"%LOGF%"
