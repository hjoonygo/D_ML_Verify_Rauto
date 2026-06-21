@echo off
chcp 65001 >nul
cd /d %~dp0
echo ============================================================
echo  TrendStack Signal Bot (Stg9) - verify bot == source engine
echo ============================================================
echo [deps] numpy, pandas
pip install numpy pandas --quiet
echo.
echo ========== TEST ==========
python test_07Prj_Ch3_Stg9_TrendStackSignalBot.py
echo.
echo ========== CHECK ==========
python check_07Prj_Ch3_Stg9_TrendStackSignalBot.py
echo.
echo [note] +827%% compound number needs PC real data (Merged_Data_with_Regime_Features.csv ~698MB).
echo        This package verifies signal-logic identity to source + sizing + 1m-to-7h resample.
pause
