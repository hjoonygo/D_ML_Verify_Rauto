set PYTHONIOENCODING=utf-8
cd /d %~dp0
rem ============================================================================
rem aws_emergency_setup.bat — Stg16 응급 수습 원샷 (AWS 관리자 cmd에서 1회 실행)
rem A) Rauto_Daily  B) Kill_Guard  C) Telegram_Poll  D) RAUTO_DIR setx
rem 안전수칙: 변경 전 health AUTO-CHANGE 1줄 + aws_workhstr.log 기록 (무기록 금지)
rem 전제: 본 폴더 = C:\run_Rauto (Stg14+Stg16 전 파일 + bots\ 동거)
rem ============================================================================
echo AUTO-CHANGE: %date% %time% emergency_setup 개시 — schtasks 3종+RAUTO_DIR setx 예정 (Stg16 응급 수습, 캡틴 지시 2026-06-13)>>"%~dp0stg14_health.log"

rem [D] 환경변수 — RAUTO_DIR 주입 + 토큰 존재 확인(평문 출력 금지)
setx RAUTO_DIR "C:\run_Rauto" /M
if defined TELEGRAM_BOT_TOKEN (echo TELEGRAM_BOT_TOKEN: 설정됨) else (echo TELEGRAM_BOT_TOKEN: 미설정 — setx 후 재실행 필요)
if defined TELEGRAM_CHAT_ID (echo TELEGRAM_CHAT_ID: 설정됨) else (echo TELEGRAM_CHAT_ID: 미설정 — setx 후 재실행 필요)

rem [F] bots 표준 위치 확인
if not exist "%~dp0bots\" (echo [경고] %~dp0bots 부재 — Stg14 zip의 bots\ 를 C:\run_Rauto\bots\ 로 복사 후 재실행) else (echo bots: OK)

rem [A/B/C] schtasks 등록 (/F = 멱등)
schtasks /Create /TN "Rauto_Daily" /TR "C:\run_Rauto\run_daily.bat" /SC DAILY /ST 00:10 /RU SYSTEM /RL HIGHEST /F
schtasks /Create /TN "Kill_Guard" /TR "python C:\run_Rauto\kill_guard.py" /SC MINUTE /MO 1 /RU SYSTEM /RL HIGHEST /F
schtasks /Create /TN "Telegram_Poll" /TR "python C:\run_Rauto\telegram_poll.py" /SC MINUTE /MO 1 /RU SYSTEM /RL HIGHEST /F
echo %date% %time% AUTO-CHANGE: schtasks Rauto_Daily+Kill_Guard+Telegram_Poll 등록, setx RAUTO_DIR=C:\run_Rauto /M (Stg16 응급 수습)>>"%~dp0aws_workhstr.log"

rem [검증 1] test 8/8 + check (오염검사 — aws_workhstr.log 자동 기록)
python test_07Prj_Ch4_RunAWS_Stg16_OpsGuard.py
python check_07Prj_Ch4_RunAWS_Stg16_OpsGuard.py

rem [검증 2] 실발송 1회만 — 캡틴 폰 수신 확인용(이후 자동 알림은 diff 신규분만)
python -c "import alert_telegram as t; print('실발송:', t.send('[TEST] Rauto OpsGuard 발사검증'))"

rem [검증 4] Rauto_Daily 즉시 1회 — 끝나면 type rauto_daily.log / paper_ledger.csv 확인
schtasks /Run /TN "Rauto_Daily"
echo.
echo ==== 완료. 이후: 폰에서 /status 송신(4축 회신 확인), /kill은 실험 시 태스크 재활성 잊지 말 것 ====
