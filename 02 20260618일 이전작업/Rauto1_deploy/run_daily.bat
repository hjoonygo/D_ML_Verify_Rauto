set PYTHONIOENCODING=utf-8
cd /d %~dp0
set PY=python
if defined RAUTO_PY set PY=%RAUTO_PY%
REM ==== slot R1 isolation (do not touch C:\run_Rauto / C:\run_Rauto_Impatient) ====
set RAUTO_DIR=%~dp0
set RAUTO_OPS_STATE=%~dp0ops_state.json
set RAUTO_OPS_LOG=%~dp0ops_alert.log
set RAUTO_KILL_FLAG=%~dp0kill.flag
set RAUTO_MODE=[R1]
set RAUTO_DAUTO_DIR=C:\BinanceData
set LOGF=%~dp0rauto1.log
echo ===== [%date% %time%] Rauto1 START (PY=%PY%) =====>>"%LOGF%"
"%PY%" test_Rauto1.py >>"%LOGF%" 2>&1
"%PY%" alert_check.py >>"%LOGF%" 2>&1
echo ===== [%date% %time%] Rauto1 END =====>>"%LOGF%"
