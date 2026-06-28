@echo off
rem Rauto2 control server as a Windows service via NSSM (no console, auto-restart). ASCII only.
set NSSM=nssm
set SVC=Rauto2Server
%NSSM% install %SVC% "python" "%~dp0260626_02_Rauto2_Sys_server.py"
%NSSM% set %SVC% AppDirectory "%~dp0"
%NSSM% set %SVC% AppEnvironmentExtra PYTHONIOENCODING=utf-8 RAUTO2_PORT=8788
%NSSM% set %SVC% Start SERVICE_AUTO_START
%NSSM% set %SVC% AppStdout "%~dp0log_rauto2.txt"
%NSSM% set %SVC% AppStderr "%~dp0log_rauto2.txt"
%NSSM% start %SVC%
