@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ====================================================================
echo  [V34 Phase B - 안 A (동적 Hard SL) + 안 D (변동성 필터) 통합 측정]
echo  날짜: 2026-05-18
echo  그리드: 12 시나리오 (ATR multi 4 x Lev 1 x Filter 3)
echo ====================================================================
echo.

REM === 0. 환경 확인 ===
echo [0/3] 환경 확인...
where python > nul 2>&1
if errorlevel 1 (
    echo X Python을 찾을 수 없습니다. python 경로를 확인하세요.
    pause
    exit /b 1
)

REM 데이터 파일 확인
if not exist "..\Merged_Data.csv" (
    echo X ..\Merged_Data.csv 없음.
    echo   D:\ML\Verify\Merged_Data.csv 위치 확인 후 재시도.
    pause
    exit /b 1
)
echo   - Python OK
echo   - Merged_Data.csv 확인됨
echo.

REM === 1. 모델 학습 ===
set MODEL_PATH=PautoV75_XGB_3class_v2.json
set REUSE=N

if exist "%MODEL_PATH%" (
    echo [1/3] 기존 모델 발견: %MODEL_PATH%
    set /p REUSE="기존 모델 재사용? (Y/N) [N]: "
    if /i "!REUSE!"=="Y" (
        echo   - 기존 모델 재사용
        goto SKIP_TRAIN
    )
)

echo [1/3] 모델 학습 시작 (10~20분 소요)...

REM 기존 모델 백업
if exist "%MODEL_PATH%" (
    set BACKUP_NAME=PautoV75_XGB_3class_v2_backup_%date:~0,4%-%date:~5,2%-%date:~8,2%.json
    set BACKUP_NAME=!BACKUP_NAME: =0!
    echo   - 기존 모델 백업: !BACKUP_NAME!
    move /y "%MODEL_PATH%" "..\!BACKUP_NAME!" > nul
)

python train_phase_b.py
if errorlevel 1 (
    echo X 학습 실패
    pause
    exit /b 1
)
echo   - 학습 완료
echo.

:SKIP_TRAIN

REM === 2. 단위 테스트 (선택) ===
echo [2/3] 단위 테스트 (3분 소요)...
python test_v7_phase_a.py
if errorlevel 1 (
    echo ! 단위 테스트 실패 - 계속 진행할지 확인 필요
    set /p CONTINUE="계속 진행? (Y/N) [N]: "
    if /i not "!CONTINUE!"=="Y" exit /b 1
)
echo.

REM === 3. Phase B 측정 ===
echo [3/3] Phase B 측정 시작 (1~3시간 소요)...
echo   시작 시간: %time%
python measure_v34_phase_b.py
if errorlevel 1 (
    echo X 측정 실패
    pause
    exit /b 1
)
echo   완료 시간: %time%
echo.

echo ====================================================================
echo  [완료]
echo  결과 위치: %cd%\outputs_phase_b\
echo  - all_scenarios_phase_b.csv (요약)
echo  - trades_*.csv (12개 시나리오별 trade log)
echo  - measure_log.txt (로그)
echo.
echo  이 폴더(v34_phase_b_2026-05-18)를 통째로 zip해서 업로드하세요.
echo ====================================================================
pause
