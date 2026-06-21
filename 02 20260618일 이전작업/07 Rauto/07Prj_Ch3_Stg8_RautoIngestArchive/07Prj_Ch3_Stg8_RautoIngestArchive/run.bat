@echo off
REM [07Prj_Ch3_Stg8_RautoIngestArchive] 라이브 수집·아카이브 — test 후 check (모의 피드)
REM 의존성: pip install pyarrow websocket-client pandas
REM 실 Binance 접속(start_live)은 이 PC/AWS 네트워크에서 검증. WS 라우팅 경로(/public 등)는 라이브 전 문서 확인.
chcp 65001 >nul
echo === test (모의 수집 + 아카이브 + 보존정리 시연) ===
python test_07Prj_Ch3_Stg8_RautoIngestArchive.py
echo.
echo === check (12 시나리오 검증 + 00WorkHstr 기록) ===
python check_07Prj_Ch3_Stg8_RautoIngestArchive.py
echo.
pause
