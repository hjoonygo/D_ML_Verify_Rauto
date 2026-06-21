@echo off
chcp 65001 >nul
echo === Rauto Control b26 재배포 (AWS RDP cmd에서 실행) ===
echo [진단] C드라이브의 control_dashboard.html 위치(=서버가 읽는 폴더):
where /r C:\ control_dashboard.html 2>nul
echo.
echo [배포] 발견된 모든 위치 + C:\RautoControl 에 새파일 복사
for /f "delims=" %%D in ('where /r C:\ control_dashboard.html 2^>nul') do (
  copy /Y "%~dp0control_dashboard.html" "%%D" >nul
  copy /Y "%~dp0control_server.py" "%%~dpDcontrol_server.py" >nul
  echo   복사됨: %%~dpD
)
if exist C:\RautoControl ( copy /Y "%~dp0control_dashboard.html" "C:\RautoControl\" >nul & copy /Y "%~dp0control_server.py" "C:\RautoControl\" >nul )
echo [재시작] RautoControlServer
schtasks /End /TN "RautoControlServer" 2>nul
timeout /t 2 >nul
schtasks /Run /TN "RautoControlServer"
echo [확인] 서버 응답에 b26/Gho 있나:
timeout /t 3 >nul
curl -s http://localhost:8787/ | findstr /C:"b26" /C:"Gho"
echo.
echo === 완료. 폰: 앱 완전종료(최근앱서 스와이프) 후 재실행. PWA캐시 때문에 그냥 새로고침으론 안 바뀔 수 있음 ===
echo (Gmail발송: setx /M RAUTO_GMAIL_APP_PW "구글앱비밀번호" 후 위 재시작 1회 더)
pause
