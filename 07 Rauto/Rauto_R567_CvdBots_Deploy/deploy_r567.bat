@echo off
echo R5/R6/R7 CVD bots deploy
set PY=C:\Users\Administrator\AppData\Local\Programs\Python\Python310\python.exe
if not exist C:\Rauto5 mkdir C:\Rauto5
if not exist C:\Rauto5\bots xcopy /E /I /Y C:\Rauto2\bots C:\Rauto5\bots
if not exist C:\Rauto6 mkdir C:\Rauto6
if not exist C:\Rauto6\bots xcopy /E /I /Y C:\Rauto2\bots C:\Rauto6\bots
if not exist C:\Rauto7 mkdir C:\Rauto7
if not exist C:\Rauto7\bots xcopy /E /I /Y C:\Rauto2\bots C:\Rauto7\bots
copy /Y "%~dp0bot_stop_quality.py" "C:\Rauto5\bots\"
copy /Y "%~dp0bot_cvd_stop.py" "C:\Rauto5\bots\"
copy /Y "%~dp0test_Rauto_cvd.py" "C:\Rauto5\"
copy /Y "%~dp0bot_stop_quality.py" "C:\Rauto6\bots\"
copy /Y "%~dp0bot_cvd_stop.py" "C:\Rauto6\bots\"
copy /Y "%~dp0test_Rauto_cvd.py" "C:\Rauto6\"
copy /Y "%~dp0bot_stop_quality.py" "C:\Rauto7\bots\"
copy /Y "%~dp0bot_cvd_stop.py" "C:\Rauto7\bots\"
copy /Y "%~dp0test_Rauto_cvd.py" "C:\Rauto7\"
echo --- run R5 ---
cd /d C:\Rauto5
set CVD_SLOT=R5
"%PY%" test_Rauto_cvd.py
echo --- run R6 ---
cd /d C:\Rauto6
set CVD_SLOT=R6
"%PY%" test_Rauto_cvd.py
echo --- run R7 ---
cd /d C:\Rauto7
set CVD_SLOT=R7
"%PY%" test_Rauto_cvd.py
echo DONE - refresh dashboard
pause
