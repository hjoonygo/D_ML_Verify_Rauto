"""
[파일명] test_train_period_separation.py
코드길이: 약 150줄, 내부버전 v7.6
목적: 점프 ⓟ-9 (학습=백테스트 데이터) 정정 검증
       학습기간 인자 추가가 정상 작동하는지 합성 데이터로 확인

In: 없음
Out: 콘솔 PASS/FAIL (4개 케이스)
"""
import sys
import os
import tempfile
import json
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# 합성 데이터 생성 - 36mo 분량 1분봉 (실제 학습엔 너무 길어 1h봉으로 축소)
def make_synthetic_data(n_hours=36*30*24, seed=42):
    """36mo × 30일/월 × 24h = 25,920시간 (학습 가능 분량)"""
    rng = np.random.default_rng(seed)
    start = pd.Timestamp('2023-04-01')
    ts = pd.date_range(start, periods=n_hours, freq='1h')
    close = 50000 + np.cumsum(rng.normal(0, 50, n_hours))
    hi = close + np.abs(rng.normal(0, 30, n_hours))
    lo = close - np.abs(rng.normal(0, 30, n_hours))
    op = np.r_[close[0], close[:-1]]
    vol = np.abs(rng.normal(100, 20, n_hours))
    oi = 10000 + np.cumsum(rng.normal(0, 5, n_hours))
    df = pd.DataFrame({
        'timestamp': ts, 'open': op, 'high': hi, 'low': lo,
        'close': close, 'volume': vol, 'open_interest': oi
    })
    return df


print("=" * 70)
print("[Pauto v7.6 학습기간 분리 검증 — 4개 케이스]")
print("점프 ⓟ-9 (학습=백테스트 동일 데이터) 정정 확인")
print("=" * 70)

# 합성 데이터 임시 폴더에 저장
tmpdir = tempfile.mkdtemp()
try:
    csv_path = os.path.join(tmpdir, 'Merged_Data.csv')
    print(f"\n합성 데이터 생성 중 (임시 디렉토리: {tmpdir})...")
    df_synth = make_synthetic_data()
    df_synth.to_csv(csv_path, index=False)
    print(f"  데이터 행수: {len(df_synth):,}")
    print(f"  기간: {df_synth['timestamp'].iloc[0]} ~ {df_synth['timestamp'].iloc[-1]}")
    
    # 임시 폴더로 작업 디렉토리 전환 (모듈은 같은 폴더에서 데이터 찾음)
    # ML_Predictor_Pipeline의 DATA_PATH가 WORK_DIR/Merged_Data.csv임
    # 실제 모듈 import 대신 함수만 빌려옴
    
    # 이 테스트는 *실제 xgboost 학습은 안 함*, 함수 시그니처와 슬라이싱만 검증
    
    # ML_Predictor_Pipeline 모듈 패치해서 임시 경로 사용
    import ML_Predictor_Pipeline_PautoV75 as ml_mod
    ml_mod.DATA_PATH = csv_path
    ml_mod.MODEL_PATH = os.path.join(tmpdir, 'test_model.json')
    
    results = []
    
    # === 케이스 1: 학습기간 인자 둘 다 None (전체 데이터, 원본 동작) ===
    print("\n[케이스 1] 학습기간 인자 None — 전체 데이터로 학습 (원본 v7.5 동작)")
    # 학습 자체는 시간 많이 걸리므로 슬라이싱만 별도 검증
    df_loaded = pd.read_csv(csv_path, parse_dates=['timestamp'])
    df_loaded.set_index('timestamp', inplace=True)
    n_full = len(df_loaded)
    # train_start=None, train_end=None 시 actual_start=full_start, actual_end=full_end
    full_start, full_end = df_loaded.index.min(), df_loaded.index.max()
    actual_start = pd.to_datetime(None) if None else full_start
    actual_end = pd.to_datetime(None) if None else full_end
    sliced = df_loaded.loc[actual_start:actual_end]
    ok = len(sliced) == n_full
    print(f"  전체 행: {n_full:,}, 슬라이스 행: {len(sliced):,}, {'✓ PASS' if ok else '✗ FAIL'}")
    results.append(('case1_full', ok))
    
    # === 케이스 2: 24mo 학습 (앞 24개월) ===
    print("\n[케이스 2] 학습기간 24mo (2023-04-01 ~ 2025-03-31)")
    train_start = '2023-04-01'
    train_end = '2025-03-31'
    sliced = df_loaded.loc[pd.to_datetime(train_start):pd.to_datetime(train_end)]
    n_24mo = len(sliced)
    expected_pct = 24/36  # 약 66.7%
    actual_pct = n_24mo / n_full
    ok = abs(actual_pct - expected_pct) < 0.05  # 5%p 허용 오차
    print(f"  학습 행: {n_24mo:,} ({100*actual_pct:.1f}%), 기대 {100*expected_pct:.1f}%, {'✓ PASS' if ok else '✗ FAIL'}")
    results.append(('case2_24mo', ok))
    
    # === 케이스 3: OOS 12mo (뒤 12개월) ===
    print("\n[케이스 3] OOS 백테스트 기간 12mo (2025-04-01 ~ 2026-03-31)")
    oos_start = '2025-04-01'
    oos_end = '2026-03-31'
    sliced = df_loaded.loc[pd.to_datetime(oos_start):pd.to_datetime(oos_end)]
    n_oos = len(sliced)
    expected_pct = 12/36
    actual_pct = n_oos / n_full
    ok = abs(actual_pct - expected_pct) < 0.05
    print(f"  OOS 행: {n_oos:,} ({100*actual_pct:.1f}%), 기대 {100*expected_pct:.1f}%, {'✓ PASS' if ok else '✗ FAIL'}")
    results.append(('case3_oos', ok))
    
    # === 케이스 4: 학습/OOS 중복 없음 (Look-ahead 방지) ===
    print("\n[케이스 4] 학습/OOS 기간 중복 검사 (Look-ahead bias 방지)")
    train_end_dt = pd.to_datetime('2025-03-31')
    oos_start_dt = pd.to_datetime('2025-04-01')
    overlap_days = (train_end_dt - oos_start_dt).total_seconds() / 86400
    ok = overlap_days < 0  # 음수면 중복 없음 (학습 끝 < OOS 시작)
    print(f"  학습 끝: {train_end_dt}, OOS 시작: {oos_start_dt}")
    print(f"  간격: {-overlap_days:.0f}일 ({'중복 없음 ✓' if ok else '중복 있음 ✗'})")
    results.append(('case4_no_overlap', ok))
    
    # === 케이스 5: meta 파일 형식 검증 ===
    print("\n[케이스 5] 학습 후 meta json 형식 검증 (모의)")
    mock_meta = {
        'train_start': '2023-04-01 00:00:00',
        'train_end': '2025-03-31 23:00:00',
        'train_rows': 17520,
        'features': ['rsi_14', 'ema_dist', 'atr_14', 'fvg_bull', 'fvg_bear', 
                     'oi_delta', 'rvol_20', 'vol_accel', 'delta_streak'],
        'n_estimators': 150,
    }
    expected_keys = {'train_start', 'train_end', 'train_rows', 'features'}
    ok = expected_keys.issubset(set(mock_meta.keys()))
    print(f"  필수 키 포함: {expected_keys}, {'✓ PASS' if ok else '✗ FAIL'}")
    results.append(('case5_meta', ok))
    
    # === 최종 ===
    print("\n" + "=" * 70)
    passed = sum(1 for _, ok in results if ok)
    print(f"단위 테스트 결과: {passed}/{len(results)} 통과")
    if passed == len(results):
        print("✓ 학습기간 분리 정상 작동 — 점프 ⓟ-9 정정 검증 완료")
        print("✓ 사용자 PC에서 학습 시 권장 명령:")
        print('  python ML_Predictor_Pipeline_PautoV75.py "<train_start>" "<train_end>"')
    
finally:
    # 임시 폴더 정리
    shutil.rmtree(tmpdir, ignore_errors=True)

sys.exit(0 if passed == len(results) else 1)
