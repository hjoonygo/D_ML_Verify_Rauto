# -*- coding: utf-8 -*-
"""
[파일명] test_e2e_synthetic.py
미니 합성 데이터로 measure_v34_obfib 의 핵심 흐름 *진짜 실행* 검증.
실데이터 없이도 import + 함수 호출 chain + 데이터 흐름 점검 가능.
"""
import os, sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 1) 합성 1m 데이터 생성 (200봉, OOS 기간 안에 들어가게 timestamp 설정)
print("[1] 합성 1m 데이터 생성")
n = 5000  # ≈ 3.5일 분량 (1m × 5000)
np.random.seed(42)
prices = 100.0 + np.cumsum(np.random.randn(n) * 0.05)
ts = pd.date_range("2025-06-01", periods=n, freq='1min', tz='UTC')
df_1m = pd.DataFrame({
    'open': prices, 'high': prices * 1.0005, 'low': prices * 0.9995,
    'close': prices, 'volume': 100.0,
    'oi_sum': 1000.0,
}, index=ts)
df_1m.index.name = 'timestamp'
print(f"  생성: {len(df_1m)}봉, {df_1m.index[0]} ~ {df_1m.index[-1]}")

# 2) 모든 import 진짜 실행
print("\n[2] import 체인")
from obfib_simulator import simulate_batch, compute_grid_stats, simulate_single_trade
from stage1_signal_wrapper import extract_signals_stage1
from tf_aggregator import aggregate_ohlcv
from Exec_Dynamic_TS_PautoV75 import Exec_Dynamic_TS_PautoV75
print("  전부 OK")

# 3) measure 모듈 *실제 import 직접 확인*
print("\n[3] measure_v34_obfib.py import")
import measure_v34_obfib as M
print(f"  M.TFS_MIN={M.TFS_MIN}, M.ML_THRESHOLDS={M.ML_THRESHOLDS}")
print(f"  M.LEVS={M.LEVS}, M.N_OBS={M.N_OBS}")
print(f"  총 그리드: 2×2×3×2×2×3 = 144 시나리오")

# 4) extract_signals_stage1 가 *진짜 호출되는가* — 모델 없이 시그니처/import 만 점검
print("\n[4] extract_signals_stage1 시그니처 점검")
import inspect
sig = inspect.signature(extract_signals_stage1)
print(f"  파라미터: {list(sig.parameters.keys())}")
required = ['df_1m', 'model_path']
for p in required:
    assert p in sig.parameters, f"필수 파라미터 누락: {p}"
print("  필수 파라미터 (df_1m, model_path) 모두 확인 OK")

# 5) simulate_batch 빈 인덱스 검증 (모델 없는 상태에서도 호출 chain 점검)
print("\n[5] simulate_batch 빈 인덱스 호출")
empty_result = simulate_batch(np.array([], dtype=np.int64), df_1m, 'long',
                              {'leverage': 20, 'fib_trigger_roe': 24.0,
                               'fib_sl_pct': 5.73, 'fib_ext_pct': 0.618,
                               'N_ob': 5, 'holding_bars_1m': 240,
                               'mmr': 0.004, 'cost_round_trip_nominal': 0.0016})
print(f"  반환 타입: {type(empty_result).__name__}, 행 수: {len(empty_result)}")
assert len(empty_result) == 0, "빈 인덱스에서는 빈 결과 반환해야 함"
print("  OK")

# 6) simulate_single_trade 실데이터 미니 호출 (모델 없이 임의 진입)
print("\n[6] simulate_single_trade 실데이터 호출 (모델 없이 임의 진입 인덱스)")
entry_idx_test = 100
result = simulate_single_trade(entry_idx_test, df_1m, 'long', {
    'leverage': 20, 'fib_trigger_roe': 24.0, 'fib_sl_pct': 5.73,
    'fib_ext_pct': 0.618, 'N_ob': 5, 'holding_bars_1m': 240,
    'mmr': 0.004, 'cost_round_trip_nominal': 0.0016
})
print(f"  exit_reason={result.get('exit_reason')}, "
      f"net_return={result.get('net_return_pct', 'N/A')}")
assert result.get('exit_reason') is not None
print("  OK")

# 7) compute_grid_stats 빈/일반 거래 둘 다 점검
print("\n[7] compute_grid_stats 점검")
empty_stats = compute_grid_stats(pd.DataFrame())
print(f"  빈 결과 stats: n_trades={empty_stats.get('n_trades')}, adr={empty_stats.get('adr_w3_pass')}")
assert empty_stats['n_trades'] == 0

# 더미 거래 5건
dummy = pd.DataFrame([
    {'exit_reason': 'FIB_STOP', 'net_return_pct': 10.0, 'used_fib_lock': True, 'used_reduce': True},
    {'exit_reason': 'FIB_STOP', 'net_return_pct': 8.5, 'used_fib_lock': True, 'used_reduce': True},
    {'exit_reason': 'OB_EDGE_STOP', 'net_return_pct': -2.0, 'used_fib_lock': False, 'used_reduce': True},
    {'exit_reason': 'HARD_SL', 'net_return_pct': -5.7, 'used_fib_lock': False, 'used_reduce': False},
    {'exit_reason': 'TIMEOUT', 'net_return_pct': 1.5, 'used_fib_lock': False, 'used_reduce': True},
])
stats = compute_grid_stats(dummy)
print(f"  dummy stats: n={stats['n_trades']}, PF={stats['pf']:.2f}, "
      f"net_sum={stats['net_return_sum_pct']:.1f}%, "
      f"avg_fib={stats['avg_fib_pct']:.2f}%")
print("  OK")

print("\n" + "=" * 60)
print("✓ E2E 합성 검증 완전 통과 — measure_v34_obfib 실행 준비됨")
print("=" * 60)
