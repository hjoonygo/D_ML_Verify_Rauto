@echo off
echo R3/R4 fix : deploy + rerun
set PY=C:\Users\Administrator\AppData\Local\Programs\Python\Python310\python.exe
copy /Y "%~dp0test_dual_runner.py" "C:\Rauto3\test_dual_runner.py"
copy /Y "%~dp0test_dual_runner.py" "C:\Rauto4\test_dual_runner.py"
echo --- run R3 ---
cd /d C:\Rauto3
set DUAL_SLOT=R3
"%PY%" test_dual_runner.py
echo --- run R4 ---
cd /d C:\Rauto4
set DUAL_SLOT=R4
"%PY%" test_dual_runner.py
echo DONE - refresh dashboard
pause
