@echo off
REM [파일명] run_07Prj_Ch1_stg1_IsoBounceModuleBuild.bat
REM 격리튕김 모듈 빌드 + 자가검증 + 8시나리오 오염검사 순차 실행
REM 실행 위치: D:\ML\verify\07Prj_Ch1_stg1_IsoBounceModuleBuild\

setlocal
chcp 65001 > nul
set CODE_DIR=%~dp0code
cd /d "%CODE_DIR%"

echo ============================================================
echo [stg1 IsoBounceModuleBuild] 모듈 빌드 + 자가검증 + 오염검사
echo ============================================================
echo.

echo [1/3] 모듈 자가검증 (isolated_bounce_simulator.py 단독 실행)
python isolated_bounce_simulator.py
if errorlevel 1 (
    echo [ERR] 모듈 자가검증 실패
    pause
    exit /b 1
)
echo.

echo [2/3] test 실행 (합성 격자 + 경계검증 + 데모 적용)
python test_07Prj_Ch1_stg1_IsoBounceModuleBuild.py
if errorlevel 1 (
    echo [ERR] test 실행 실패
    pause
    exit /b 1
)
echo.

echo [3/3] check 실행 (8시나리오 오염검사)
python check_07Prj_Ch1_stg1_IsoBounceModuleBuild.py
if errorlevel 1 (
    echo [ERR] check 실행 실패
    pause
    exit /b 1
)
echo.

echo ============================================================
echo 완료. 결과 CSV: %CODE_DIR%
echo 분석txt: D:\ML\verify\00WorkHstr\(YYYYMMDD_HHMM).txt
echo INDEX 추가: D:\ML\verify\00WorkHstr\00WorkHstr_INDEX.txt
echo ============================================================
pause
endlocal
