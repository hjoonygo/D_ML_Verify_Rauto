@echo off
REM [07Prj_Ch3_Stg6_RautoSlotChampGuard] 슬롯매니저+챔피언+안전 — test 후 check
REM 데이터(원장/devledger/featcache)는 상위 D:\ML\verify 에서 ".." 상대탐지
chcp 65001 >nul
echo === test (슬롯 로드/언로드 시연 + 통합 리플레이) ===
python test_07Prj_Ch3_Stg6_RautoSlotChampGuard.py
echo.
echo === check (12 시나리오 검증 + 00WorkHstr 기록) ===
python check_07Prj_Ch3_Stg6_RautoSlotChampGuard.py
echo.
pause
