@echo off
REM ============================================================
REM V80k_Verify_3 PC 학습 환경 - 한 명령 셋업 (정정판 v2)
REM 실행: setup_env.bat
REM ============================================================
REM 핵심 두 개만 박제 (pandas/numpy는 기존 시스템 버전 사용)
REM   xgboost   3.2.0   ★ V8.0.k 모델 호환 필수 (1.x/2.x 사용 금지)
REM   sklearn   1.4.2   ★ xgboost save_model 충돌 회피 (1.6+ 사용 금지)
REM
REM pandas/numpy는 굳이 박제 X:
REM   - pandas 2.0.3은 Python 3.12에서 wheel 빌드 실패
REM   - 시스템에 이미 있는 pandas 2.x / numpy 호환 OK
REM ============================================================

echo.
echo ============================================================
echo V80k_Verify_3 환경 박제 시작
echo ============================================================
echo.

python -c "import sys; print('Python:', sys.version.split()[0])"
echo.

echo [1/2] xgboost 3.2.0 설치 (V8.0.k 모델 호환 필수)...
pip install "xgboost==3.2.0" --upgrade
if errorlevel 1 goto err

echo.
echo [2/2] scikit-learn 1.4.2 설치 (save_model 호환)...
pip install "scikit-learn==1.4.2" --upgrade
if errorlevel 1 goto err

echo.
echo ============================================================
echo 설치 완료 - 버전 확인
echo ============================================================
python -c "import xgboost, sklearn, pandas, numpy; print('xgboost ', xgboost.__version__, '   ', '<- 3.2.0' if xgboost.__version__ == '3.2.0' else '<- !!! 3.2.0 아님'); print('sklearn ', sklearn.__version__, '   ', '<- 1.4.2' if sklearn.__version__ == '1.4.2' else '<- !!! 1.4.2 아님'); print('pandas  ', pandas.__version__, '   (시스템 그대로)'); print('numpy   ', numpy.__version__, '   (시스템 그대로)')"
echo.
echo ============================================================
echo OK. 다음 명령으로 학습 시작:
echo   rmdir /s /q pc_pipeline_output
echo   python pc_pipeline_V80k_Verify_3.py --data Merged_21mo.csv
echo ============================================================
goto end

:err
echo.
echo ============================================================
echo [X] 설치 실패. 네트워크 또는 pip 권한 확인.
echo ============================================================
exit /b 1

:end
