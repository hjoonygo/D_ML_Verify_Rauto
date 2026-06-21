set PYTHONIOENCODING=utf-8
cd /d %~dp0
python measure_M1_poc_revert.py
python measure_M2_sweep_reversal.py
python build_summary.py
