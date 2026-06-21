# -*- coding: utf-8 -*-
# [FILE] test_v8_stage_1.py
# [Version] v8.0 (stage_1)
# [Purpose] 4 핵심 단위 테스트 - 안 X (fib_trigger ATR 기반)

import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tbm_simulator_v8 import (
    simulate_position_v8, batch_simulate_v8, compute_atr,
    FIB_TRIGGER_DEFAULT, DEFAULT_FIB_TRIGGER_ATR_MULTI,
    DEFAULT_ATR_MULTIPLIER, FIB_EXT,
)
from tf_aggregator_v2 import aggregate_ohlcv


def make_synth_df(n=600, seed=42):
    rng = np.random.default_rng(seed)
    ts = pd.date_range('2025-01-01', periods=n, freq='1min', tz='UTC')
    close = 50000 + np.cumsum(rng.normal(0, 30, n))
    df = pd.DataFrame({
        'open': np.r_[close[0], close[:-1]],
        'high': close + np.abs(rng.normal(0, 20, n)),
        'low': close - np.abs(rng.normal(0, 20, n)),
        'close': close,
        'volume': np.abs(rng.normal(100, 20, n)) + 10,
        'oi_sum': 86000 + np.cumsum(rng.normal(0, 10, n)),
    }, index=ts)
    df.index.name = 'timestamp'
    return df


def setup():
    df = make_synth_df(600)
    df_2h = aggregate_ohlcv(df.reset_index(), 120).set_index('timestamp')
    df_ob = aggregate_ohlcv(df.reset_index(), 60).set_index('timestamp')
    atr_ob = compute_atr(df_ob['high'].values, df_ob['low'].values, df_ob['close'].values, period=20)
    return df, df_2h, df_ob, atr_ob


def test_C1_fib_trigger_dist_calc():
    """C1: fib_trigger_dist = atr_at_entry_pct * fib_trigger_atr_multi"""
    print("\n=== C1: fib_trigger_dist 계산 ===")
    df, df_2h, df_ob, atr_ob = setup()
    all_ok = True
    for fib_multi in [0.5, 1.0, 1.5, 2.0]:
        r = simulate_position_v8(
            entry_signal_idx_1m=200, side='long',
            df_1m=df, df_ob_tf=df_ob, df_2h=df_2h, atr_ob_tf=atr_ob,
            leverage=10, timeout_bars_ob_tf=7, ob_tf_minutes=60,
            atr_at_entry_pct=0.005, atr_multiplier=2.0,
            fib_trigger_atr_multi=fib_multi,
            enable_2h_reversal=False,
        )
        expected = 0.005 * fib_multi
        actual = r.get('fib_trigger_dist')
        ok = (actual is not None) and abs(actual - expected) < 1e-9
        status = "OK" if ok else "FAIL"
        print(f"  fib_multi={fib_multi}: expected={expected:.4f}, actual={actual}, [{status}]")
        if not ok: all_ok = False
    return all_ok


def test_C2_short_side():
    """C2: short side에서도 fib_trigger_dist 정상 동작"""
    print("\n=== C2: short side fib_trigger_dist ===")
    df, df_2h, df_ob, atr_ob = setup()
    r = simulate_position_v8(
        entry_signal_idx_1m=200, side='short',
        df_1m=df, df_ob_tf=df_ob, df_2h=df_2h, atr_ob_tf=atr_ob,
        leverage=10, timeout_bars_ob_tf=7, ob_tf_minutes=60,
        atr_at_entry_pct=0.005, atr_multiplier=2.0,
        fib_trigger_atr_multi=1.0,
        enable_2h_reversal=False,
    )
    expected = 0.005
    actual = r.get('fib_trigger_dist')
    ok = (actual is not None) and abs(actual - expected) < 1e-9
    status = "OK" if ok else "FAIL"
    print(f"  short fib_trigger_dist: expected={expected}, actual={actual}, [{status}]")
    return ok


def test_C3_result_keys():
    """C3: result dict에 새 키 모두 존재"""
    print("\n=== C3: result dict 키 확인 ===")
    df, df_2h, df_ob, atr_ob = setup()
    r = simulate_position_v8(
        entry_signal_idx_1m=200, side='long',
        df_1m=df, df_ob_tf=df_ob, df_2h=df_2h, atr_ob_tf=atr_ob,
        leverage=10, timeout_bars_ob_tf=7, ob_tf_minutes=60,
        atr_at_entry_pct=0.005, atr_multiplier=2.0,
        fib_trigger_atr_multi=1.0,
        enable_2h_reversal=False,
    )
    keys = ['fib_trigger_atr_multi','fib_trigger_dist','dynamic_sl_dist','atr_pct_at_entry']
    all_ok = True
    for k in keys:
        in_dict = k in r
        status = "OK" if in_dict else "FAIL"
        print(f"  {k}: {in_dict} [{status}]")
        if not in_dict: all_ok = False
    return all_ok


def test_C4_batch_simulate():
    """C4: batch_simulate_v8 정상 동작"""
    print("\n=== C4: batch_simulate_v8 ===")
    df, df_2h, df_ob, atr_ob = setup()
    from pautov75_signal_wrapper_v3 import compute_atr_15m_pct_per_1m
    atr_15m_pct = compute_atr_15m_pct_per_1m(df)
    
    trades = batch_simulate_v8(
        long_signal_indices_1m=[200, 400],
        short_signal_indices_1m=[300],
        df_1m=df, df_ob_tf=df_ob, df_2h=df_2h, atr_ob_tf=atr_ob,
        atr_15m_pct_per_1m=atr_15m_pct,
        leverage=10, timeout_bars_ob_tf=7, ob_tf_minutes=60,
        enable_2h_reversal=False,
        atr_multiplier=2.0,
        use_dynamic_hard_sl=True,
        fib_trigger_atr_multi=1.0,
        verbose=False,
    )
    print(f"  trades shape: {trades.shape}")
    print(f"  columns: {trades.columns.tolist()}")
    ok = len(trades) == 3 and 'fib_trigger_dist' in trades.columns
    status = "OK" if ok else "FAIL"
    print(f"  [{status}]")
    return ok


if __name__ == "__main__":
    print("="*70)
    print("[v8 Stage 1 단위 테스트]")
    print("="*70)
    
    tests = [
        ('C1 fib_trigger_dist 계산', test_C1_fib_trigger_dist_calc),
        ('C2 short side', test_C2_short_side),
        ('C3 result keys', test_C3_result_keys),
        ('C4 batch_simulate', test_C4_batch_simulate),
    ]
    
    passed, failed = 0, 0
    for name, t in tests:
        try:
            if t():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"\n  EXCEPTION {name}: {e}")
            import traceback; traceback.print_exc()
            failed += 1
    
    print(f"\n{'='*70}")
    print(f"[결과] 통과 {passed} / 실패 {failed} / 전체 {len(tests)}")
    print("="*70)
    sys.exit(0 if failed == 0 else 1)
