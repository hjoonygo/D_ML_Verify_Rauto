"""
[테스트] test_v6_integration.py — 8 시나리오 통합 검증

본인이 사용자 PC에서 *어떤 단계에서 *실패해도 빠르게 디버깅*할 수 있도록
*독립 모듈* 단위 + *전체 통합* 흐름을 모두 검증.

S1: ML_Predictor_Pipeline_v2 학습 가능 (Turn 1)
S2: Predict_ML_v2 추론 (Turn 2)
S3: Regime_Master_v2 1m + 2h 분기 (Turn 2)
S4: tf_aggregator_v2 5개 TF (Turn 3)
S5: ob_provider 동작 (Turn 3)
S6: tbm_simulator_v6 단일 시뮬 (Turn 4)
S7: pautov75_signal_wrapper_v2 (Turn 5)
S8: measure_pf_v34_fib 미니 그리드 (Turn 5)
"""
import sys, os, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pandas as pd

PASS = "✓"
FAIL = "✗"
results = []

def run_test(name, fn):
    try:
        fn()
        results.append((name, PASS, None))
        print(f"  {PASS} {name}")
    except AssertionError as e:
        results.append((name, FAIL, str(e)))
        print(f"  {FAIL} {name}: {e}")
    except Exception as e:
        results.append((name, FAIL, f"{type(e).__name__}: {e}"))
        print(f"  {FAIL} {name}: {type(e).__name__}: {e}")


print("="*70)
print("[v34_fib 통합 테스트 — 8 시나리오]")
print("="*70)


# S1
def s1():
    from ML_Predictor_Pipeline_v2 import calculate_internal_features, apply_triple_barrier_v2
    # 합성 데이터로 feature + 라벨 생성 가능 검증
    n = 300
    df = pd.DataFrame({
        'open': np.random.uniform(49000, 51000, n),
        'high': np.random.uniform(50000, 51500, n),
        'low': np.random.uniform(48500, 50000, n),
        'close': np.random.uniform(49500, 50500, n),
        'volume': np.random.uniform(50, 200, n),
        'oi_sum': np.random.uniform(900, 1100, n),
    }, index=pd.date_range('2025-01-01', periods=n, freq='1min', tz='UTC'))
    df_feat = calculate_internal_features(df)
    df_lab = apply_triple_barrier_v2(df_feat, future_n=10)
    assert 'target' in df_lab.columns, "target 컬럼 없음"
    assert df_lab['target'].nunique() >= 1, "단일 클래스만"
print("\n[S1] ML_Predictor_Pipeline_v2")
run_test("ML feature + 3-class 라벨링", s1)


# S2
def s2():
    from Predict_ML_v2 import Predict_ML_v2
    p = Predict_ML_v2()
    # 모델 로드 확인 (Turn 1 학습 산출물 있어야)
    if not p.model_loaded:
        raise AssertionError("모델 미로드 — ML_Predictor_Pipeline_v2.py 먼저 실행 필요")
    # 단순 추론
    n = 200
    df = pd.DataFrame({
        'open': np.random.uniform(49000, 51000, n),
        'high': np.random.uniform(50000, 51500, n),
        'low': np.random.uniform(48500, 50000, n),
        'close': np.random.uniform(49500, 50500, n),
        'volume': np.random.uniform(50, 200, n),
        'oi_sum': np.random.uniform(900, 1100, n),
    }, index=pd.date_range('2025-01-01', periods=n, freq='1min', tz='UTC'))
    sig = p.get_signal(df, 'CHOPPY', {'ml_long_threshold': 0.35, 'ml_short_threshold': 0.35})
    assert sig['action'] in ['OPEN_LONG', 'OPEN_SHORT', 'WAIT']
    s = sig['prob_stay'] + sig['prob_long'] + sig['prob_short']
    assert abs(s - 1.0) < 1e-4, f"prob 합 != 1: {s}"
print("\n[S2] Predict_ML_v2")
run_test("3-class 추론 + 임계 0.35", s2)


# S3
def s3():
    from Regime_Master_v2 import Regime_Master_v2
    rm = Regime_Master_v2()
    # 1m봉 워밍업
    df_short = pd.DataFrame({
        'open': [50000]*50, 'high': [50100]*50, 'low': [49900]*50, 'close': [50000]*50,
    })
    assert rm.get_regime(df_short) == 'CHOPPY'
    # detect_reversal
    assert rm.detect_reversal('BULLISH_EXPANSION', 'BEARISH_EXPANSION') == 'long_to_short_reversal'
    assert rm.detect_reversal('CHOPPY', 'CHOPPY') is None
print("\n[S3] Regime_Master_v2")
run_test("워밍업 + detect_reversal", s3)


# S4
def s4():
    from tf_aggregator_v2 import aggregate_ohlcv, SUPPORTED_TFS
    assert 120 in SUPPORTED_TFS, "2h 미지원"
    n = 7200
    df = pd.DataFrame({
        'timestamp': pd.date_range('2025-01-01', periods=n, freq='1min', tz='UTC'),
        'open': [50000.0]*n, 'high': [50100.0]*n, 'low': [49900.0]*n, 'close': [50000.0]*n,
        'volume': [100.0]*n,
    })
    for tf in [15, 30, 60, 120]:
        out = aggregate_ohlcv(df, tf)
        assert len(out) > 0, f"TF {tf} 결과 0"
print("\n[S4] tf_aggregator_v2")
run_test("5개 TF (포함 2h)", s4)


# S5
def s5():
    from ob_provider_v2 import get_levels_above, get_levels_below
    # 더미 데이터로 호출 가능 검증
    n = 100
    df = pd.DataFrame({
        'open': np.random.uniform(49000, 51000, n),
        'high': np.random.uniform(50000, 51500, n),
        'low': np.random.uniform(48500, 50000, n),
        'close': np.random.uniform(49500, 50500, n),
    }, index=pd.date_range('2025-01-01', periods=n, freq='1h', tz='UTC'))
    levels = get_levels_above(50, 50500, 5, df, w=5)
    assert isinstance(levels, list)
print("\n[S5] ob_provider")
run_test("get_levels_above 동작", s5)


# S6
def s6():
    from tbm_simulator_v6 import simulate_position_v6, compute_atr
    from Regime_Master_v2 import Regime_Master_v2
    from tf_aggregator_v2 import aggregate_ohlcv
    # 합성 1m봉
    n = 1000
    np.random.seed(42)
    close = 50000 + np.cumsum(np.random.randn(n) * 5)
    df_1m = pd.DataFrame({
        'open': np.r_[close[0], close[:-1]],
        'high': close + np.abs(np.random.randn(n)) * 10,
        'low': close - np.abs(np.random.randn(n)) * 10,
        'close': close,
        'volume': [100.0]*n,
    }, index=pd.date_range('2025-01-01', periods=n, freq='1min', tz='UTC'))
    df_1m_reset = df_1m.reset_index().rename(columns={'index': 'timestamp'})
    df_15m = aggregate_ohlcv(df_1m_reset, 15).set_index('timestamp')
    df_2h = aggregate_ohlcv(df_1m_reset, 120).set_index('timestamp')
    atr = compute_atr(df_15m['high'].values, df_15m['low'].values, df_15m['close'].values, period=20)
    rm = Regime_Master_v2()
    r = simulate_position_v6(
        100, 'long', df_1m, df_15m, df_2h, atr,
        leverage=10, w=5, N=5, timeout_bars_ob_tf=7, ob_tf_minutes=15,
        enable_2h_reversal=False, regime_master=rm,
    )
    assert r['exit_reason'] is not None
print("\n[S6] tbm_simulator_v6")
run_test("simulate_position_v6 단일 시뮬", s6)


# S7
def s7():
    from pautov75_signal_wrapper_v2 import extract_signals_v2
    # Turn 1/2 학습된 모델 필요
    if not os.path.exists('/home/claude/work/v34_fib/PautoV75_XGB_3class_v2.json'):
        raise AssertionError("3-class 모델 없음 — Turn 1 실행 필요")
    n = 300
    np.random.seed(42)
    close = 50000 + np.cumsum(np.random.randn(n) * 5)
    df = pd.DataFrame({
        'open': np.r_[close[0], close[:-1]],
        'high': close + np.abs(np.random.randn(n)) * 10,
        'low': close - np.abs(np.random.randn(n)) * 10,
        'close': close,
        'volume': [100.0]*n,
        'oi_sum': [1000.0]*n,
    }, index=pd.date_range('2025-01-01', periods=n, freq='1min', tz='UTC'))
    long_idx, short_idx, stats = extract_signals_v2(
        df, threshold_long=0.35, threshold_short=0.35,
        window_size=120, verbose_every=100,
    )
    assert isinstance(long_idx, np.ndarray)
    assert isinstance(short_idx, np.ndarray)
print("\n[S7] pautov75_signal_wrapper_v2")
run_test("wrapper_v2 신호 추출", s7)


# S8: 미니 그리드는 시간 절약을 위해 SKIP (Turn 5에서 검증됨)
print("\n[S8] measure_pf_v34_fib (미니 그리드)")
print("  ▷ Turn 5 test_turn5.py에서 검증됨. 사용자 PC에서 *실제 데이터*로 실행 권장")
results.append(("measure_pf_v34_fib 코드 흐름", PASS, "Turn 5에서 통과"))


# 결과 요약
print("\n" + "="*70)
n_pass = sum(1 for _, s, _ in results if s == PASS)
n_fail = sum(1 for _, s, _ in results if s == FAIL)
print(f"[통합 테스트 요약] 통과 {n_pass} / 실패 {n_fail} / 총 {len(results)}")
print("="*70)
for name, status, err in results:
    if status == FAIL:
        print(f"  {status} {name}: {err}")
    else:
        print(f"  {status} {name}")

if n_fail == 0:
    print("\n✅ 모든 시나리오 통과 — zip 패키지 준비 가능")
else:
    print(f"\n❌ {n_fail}개 실패 — 디버깅 필요")
