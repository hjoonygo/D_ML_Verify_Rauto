@echo off
chcp 65001 >nul
cd /d %~dp0
echo ==================================================================
echo  TrendStack self-contained sizing (Stg10)
echo  signal == source engine + live OPVnN(POC/dev) + feat_struct_8
echo ==================================================================
echo [deps] numpy, pandas, smartmoneyconcepts
pip install numpy pandas smartmoneyconcepts --quiet
echo.
echo ========== TEST ==========
python test_07Prj_Ch3_Stg10_TrendStackSelfContainedSizing.py
echo.
echo ========== CHECK ==========
python check_07Prj_Ch3_Stg10_TrendStackSelfContainedSizing.py
echo.
echo [note] +827%% number and feat_struct ground-truth need PC real data (Merged_Data_with_Regime_Features ~698MB).
echo        Bar-bin origin (7h/4H) must be calibrated to the historical resample on PC.
pause
