@echo off
set PYTHONIOENCODING=utf-8
chcp 65001 >nul
REM ===== Rauto Control Server (git clone에서 실행 + 자동 pull) =====
REM 이 파일은 클론된 repo 안의 control_ui 폴더에서 더블클릭. 서버가 180초마다 git pull로 자기 갱신.
set PY=python
REM (SYSTEM에서 python 못찾으면 풀경로:) REM set PY=C:\Users\Administrator\AppData\Local\Programs\Python\Python310\python.exe

set RAUTO_REPO=C:\RautoRepo
set RAUTO_GIT_PULL=1
set RAUTO_STATE_GLOB=C:\Rauto*\state.json
set RAUTO_FLAG_DIR=C:\Rauto1
set RAUTO_CTRL_PORT=8787

echo ==================================================
echo   Rauto Control Server (git auto-pull) port 8787
echo   repo=%RAUTO_REPO%  (180s마다 자동 pull)
echo   Local : http://localhost:8787
echo   Ctrl+C = stop
echo ==================================================
"%PY%" "%~dp0control_server.py"
pause
