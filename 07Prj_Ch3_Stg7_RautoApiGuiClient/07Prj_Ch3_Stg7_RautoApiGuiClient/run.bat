@echo off
REM [07Prj_Ch3_Stg7_RautoApiGuiClient] 얇은 API + GUI 클라이언트 — test 후 check
REM 데이터(원장/devledger/featcache)는 상위 D:\ML\verify 에서 ".." 상대탐지
REM PC에서 실제 차트 GUI를 쓰려면: pip install pyqtgraph + RautoV80k_UI_Components.py 동일폴더
chcp 65001 >nul
echo === test (서버 기동 + API 구동 + GUI 배선) ===
python test_07Prj_Ch3_Stg7_RautoApiGuiClient.py
echo.
echo === check (10 시나리오 검증 + 00WorkHstr 기록) ===
python check_07Prj_Ch3_Stg7_RautoApiGuiClient.py
echo.
pause
