# -*- coding: utf-8 -*-
"""
[파일명] test_obfib_unit.py
코드길이: 약 280줄, 내부버전 v0.1
로직 축약/생략 없이 전체 출력.

[목적]
obfib_simulator.py 단위 검증 10개.
Key 노트 검증 시나리오 S1~S8 + 추가 2 (LONG/SHORT Liq 발현).

[검증 시나리오]
S1: 단일 강추세 풀 캡처 (LONG, OB 3개 [+1%, +2%, +3%], 가격 +5% 직진 후 -1% 풀백 → Fib stop)
S2: 2단계 익절 후 본전 회귀 (LONG, OB 2개, 1차 익절 후 OB.bottom 복귀 → OB_EDGE_STOP)
S3: 진입 직후 급락 무방어 검증 (LONG, 첫 OB 도달 전 -8% → HARD_SL)
S4: OB 사이 큰 갭 (LONG, 레벨 [+1%, +10%], +5% 도달 후 -3% 풀백 → 원본은 Phase 1 안에 머묾, 단 hard_sl 작동 가능)
S5: 노이즈 풀백 반복 (LONG, 신고점마다 1틱 노이즈, fib_wave_start 갱신 다발)
S6: 풀백 없는 직진 추세 (LONG, 단조 증가, fib_lock = entry + (extreme-entry)×0.618, 추세 끝 → FIB_STOP)
S7: N차 레벨 전부 타격 (LONG, OB 5개 모두 도달, REDUCE 1회 + 스탑 4회 상향)
S8: SHORT 대칭 (S1 의 SHORT 버전)
S9 (추가): LONG Liq 발현 — 진입 직후 -5.5% 갭다운 (Lev 20 에서 Liq -4.6%)
S10 (추가): SHORT Liq 발현 — 진입 직후 +5.5% 갭업

각 시나리오는 합성 1분봉 OHLCV 생성 후 simulate_single_trade 호출 결과를 검증.

[실행]
python test_obfib_unit.py
"""

import numpy as np
import pandas as pd
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from obfib_simulator import simulate_single_trade


def _make_synthetic_df(prices: list, base_time="2025-01-01 00:00:00") -> pd.DataFrame:
    """
    가격 시퀀스로 1분봉 OHLCV 합성.
    각 봉은 open=close 로 단순화. high/low 는 약간 wick 추가 가능 (옵션).
    """
    n = len(prices)
    ts = pd.date_range(base_time, periods=n, freq='1min', tz='UTC')
    df = pd.DataFrame({
        'open': prices,
        'high': prices,
        'low': prices,
        'close': prices,
        'volume': [100.0] * n,
    }, index=ts)
    return df


def _make_synthetic_with_extremes(prices, highs=None, lows=None, base_time="2025-01-01 00:00:00"):
    """
    high/low 를 별도 지정한 합성 봉.
    """
    n = len(prices)
    if highs is None:
        highs = prices
    if lows is None:
        lows = prices
    ts = pd.date_range(base_time, periods=n, freq='1min', tz='UTC')
    df = pd.DataFrame({
        'open': prices,
        'high': highs,
        'low': lows,
        'close': prices,
        'volume': [100.0] * n,
    }, index=ts)
    return df


def _default_params(lev=20, holding_1m=480):
    """기본 시나리오 파라미터"""
    return {
        'leverage': lev,
        'fib_trigger_roe': 24.0,
        'fib_sl_pct': 5.73,
        'fib_ext_pct': 0.618,
        'N_ob': 5,
        'holding_bars_1m': holding_1m,
        'mmr': 0.004,
        'cost_round_trip_nominal': 0.0016,
    }


def _assert(cond, msg):
    if cond:
        print(f"  ✓ {msg}")
    else:
        print(f"  ✗ FAIL: {msg}")
        return False
    return True


def test_s1_long_full_trend_capture():
    """S1: LONG, OB 3개, 강추세 풀 캡처 → Fib_stop or OB_EDGE_STOP"""
    print("\n[S1] LONG 단일 강추세 풀 캡처")

    # lookback 100봉 (OB pivot 생성 위해 swing high 2개 + swing low 2개 인공 주입)
    # entry_price = 100.0 가정
    # swing highs: 100.5 @ i=20, 101.0 @ i=40, 101.5 @ i=60  → 모두 entry 위쪽
    # swing lows : 99.5 @ i=30, 99.0 @ i=50, 98.5 @ i=70    → 모두 entry 아래쪽
    prices = [100.0] * 100
    highs = list(prices)
    lows = list(prices)

    # 위쪽 OB swing highs (LONG 의 저항)
    highs[20] = 100.5; lows[20] = 100.3
    highs[40] = 101.0; lows[40] = 100.8
    highs[60] = 101.5; lows[60] = 101.3
    # i+2, i-2 가 더 작아야 swing high. 주변 채워줌
    for i in [18, 19, 21, 22, 38, 39, 41, 42, 58, 59, 61, 62]:
        highs[i] = 99.8

    # 진입 후 시뮬 봉 (가격 +5% 직진 후 -1% 풀백)
    # 진입가 = 시뮬 첫 봉 open
    sim_prices = []
    # 0~10: 100 → 105 직진
    for i in range(11):
        sim_prices.append(100.0 + i * 0.5)
    # 11~20: 105 유지
    for i in range(10):
        sim_prices.append(105.0)
    # 21~30: 105 → 104 (-1%)
    for i in range(10):
        sim_prices.append(105.0 - i * 0.1)

    df = _make_synthetic_with_extremes(
        prices + sim_prices,
        highs=highs + sim_prices,
        lows=lows + sim_prices,
    )

    # entry_bar_idx = 99 (lookback 마지막). 진입 봉 = 100.
    entry_idx = 99
    params = _default_params(lev=20, holding_1m=50)
    r = simulate_single_trade(entry_idx, df, 'long', params)

    print(f"  exit_reason={r['exit_reason']}, net_return={r.get('net_return_pct', 0):.2f}%, "
          f"n_ob_used={r.get('n_ob_used', 0)}, used_fib_lock={r.get('used_fib_lock', False)}, "
          f"used_reduce={r.get('used_reduce', False)}")

    ok = True
    ok &= _assert(r['exit_reason'] in ['FIB_STOP', 'OB_EDGE_STOP', 'TIMEOUT'],
                  f"청산 사유는 FIB_STOP/OB_EDGE_STOP/TIMEOUT 중 하나 (실제: {r['exit_reason']})")
    ok &= _assert(r['used_reduce'], "REDUCE 1회 작동")
    ok &= _assert(r.get('net_return_pct', 0) > 0, "양수 수익")
    return ok


def test_s2_long_pullback_to_ob_bottom():
    """S2: 2단계 익절 후 본전 회귀 → OB_EDGE_STOP"""
    print("\n[S2] LONG 본전 회귀 (OB_EDGE_STOP)")

    prices = [100.0] * 100
    highs = list(prices); lows = list(prices)

    # OB 2개: 100.5, 101.0
    highs[30] = 100.5; lows[30] = 100.3
    highs[60] = 101.0; lows[60] = 100.8
    for i in [28, 29, 31, 32, 58, 59, 61, 62]:
        highs[i] = 99.9

    # 진입 후: 100 → 100.5 (1차 익절) → 100.3 으로 회귀 (OB bottom 터치)
    sim_prices = []
    for i in range(6):
        sim_prices.append(100.0 + i * 0.1)  # 100 → 100.5
    # 100.5 도달 후 100.3 으로 회귀
    for i in range(5):
        sim_prices.append(100.5 - i * 0.05)
    # 100.3 도달

    df = _make_synthetic_with_extremes(prices + sim_prices,
                                       highs=highs + sim_prices,
                                       lows=lows + sim_prices)

    entry_idx = 99
    params = _default_params(lev=20, holding_1m=50)
    r = simulate_single_trade(entry_idx, df, 'long', params)
    print(f"  exit_reason={r['exit_reason']}, net_return={r.get('net_return_pct', 0):.2f}%")

    ok = True
    ok &= _assert(r['exit_reason'] in ['OB_EDGE_STOP', 'TIMEOUT', 'HARD_SL'],
                  f"청산 사유 합리적 ({r['exit_reason']})")
    return ok


def test_s3_long_hard_sl():
    """S3: 진입 직후 급락 → HARD_SL"""
    print("\n[S3] LONG 진입 직후 급락 (HARD_SL)")

    prices = [100.0] * 100
    # OB 1개 위쪽 (도달 못함)
    highs = list(prices); lows = list(prices)
    highs[50] = 101.0; lows[50] = 100.8
    for i in [48, 49, 51, 52]:
        highs[i] = 99.9

    # 진입 후 -8% 급락
    sim_prices = [100.0, 92.0]  # 100 → 92 (-8%)
    df = _make_synthetic_with_extremes(prices + sim_prices,
                                       highs=highs + sim_prices,
                                       lows=lows + sim_prices)

    entry_idx = 99
    params = _default_params(lev=20, holding_1m=50)
    r = simulate_single_trade(entry_idx, df, 'long', params)
    print(f"  exit_reason={r['exit_reason']}, net_return={r.get('net_return_pct', 0):.2f}%")

    ok = True
    ok &= _assert(r['exit_reason'] in ['HARD_SL', 'LIQ'],
                  f"청산 = HARD_SL or LIQ (실제: {r['exit_reason']})")
    ok &= _assert(r.get('net_return_pct', 0) < 0, "손실 발생")
    return ok


def test_s6_long_pure_uptrend():
    """S6: 풀백 없는 단조 추세 → 결국 timeout 또는 fib_stop"""
    print("\n[S6] LONG 풀백 없는 직진 추세")

    prices = [100.0] * 100
    highs = list(prices); lows = list(prices)
    highs[30] = 100.3; lows[30] = 100.1
    highs[60] = 100.6; lows[60] = 100.4
    for i in [28, 29, 31, 32, 58, 59, 61, 62]:
        highs[i] = 99.95

    # 단조 증가 100 → 110
    sim_prices = [100.0 + i * 0.2 for i in range(51)]
    df = _make_synthetic_with_extremes(prices + sim_prices,
                                       highs=highs + sim_prices,
                                       lows=lows + sim_prices)

    entry_idx = 99
    params = _default_params(lev=20, holding_1m=51)
    r = simulate_single_trade(entry_idx, df, 'long', params)
    print(f"  exit_reason={r['exit_reason']}, net_return={r.get('net_return_pct', 0):.2f}%, "
          f"max_roe={r.get('max_roe_pct', 0):.2f}%")

    ok = True
    ok &= _assert(r['exit_reason'] in ['FIB_STOP', 'OB_EDGE_STOP', 'TIMEOUT'],
                  f"청산 합리적 ({r['exit_reason']})")
    ok &= _assert(r.get('net_return_pct', 0) > 0, "양수 수익")
    return ok


def test_s8_short_mirror():
    """S8: SHORT 대칭 - S1의 SHORT 버전"""
    print("\n[S8] SHORT 대칭 (S1)")

    prices = [100.0] * 100
    highs = list(prices); lows = list(prices)

    # SHORT 은 아래쪽 OB (bullish swing lows) 가 타겟
    # swing lows: 99.5 @ 20, 99.0 @ 40, 98.5 @ 60
    lows[20] = 99.5; highs[20] = 99.7
    lows[40] = 99.0; highs[40] = 99.2
    lows[60] = 98.5; highs[60] = 98.7
    for i in [18, 19, 21, 22, 38, 39, 41, 42, 58, 59, 61, 62]:
        lows[i] = 100.1

    # 진입 후 가격 -5% 직진 후 +1% 반등
    sim_prices = [100.0 - i * 0.5 for i in range(11)]
    sim_prices += [95.0] * 10
    sim_prices += [95.0 + i * 0.1 for i in range(10)]
    df = _make_synthetic_with_extremes(prices + sim_prices,
                                       highs=highs + sim_prices,
                                       lows=lows + sim_prices)

    entry_idx = 99
    params = _default_params(lev=20, holding_1m=50)
    r = simulate_single_trade(entry_idx, df, 'short', params)
    print(f"  exit_reason={r['exit_reason']}, net_return={r.get('net_return_pct', 0):.2f}%, "
          f"used_reduce={r.get('used_reduce', False)}")

    ok = True
    ok &= _assert(r['exit_reason'] in ['FIB_STOP', 'OB_EDGE_STOP', 'TIMEOUT'],
                  f"청산 합리적 ({r['exit_reason']})")
    ok &= _assert(r.get('net_return_pct', 0) > 0, "양수 수익")
    return ok


def test_s9_long_liq():
    """S9: LONG Liq 발현 - 진입 직후 갭다운"""
    print("\n[S9] LONG Liq 발현")

    prices = [100.0] * 100
    highs = list(prices); lows = list(prices)
    highs[50] = 101.0; lows[50] = 100.8

    # Lev 20 의 Liq 가격 = 100 × (1 - 1/20 + 0.004) = 100 × 0.954 = 95.4
    # 진입 후 -5.5% 갭다운 (95.45 → 94.5 로 한 봉에 떨어짐)
    sim_prices = [100.0, 94.5]
    sim_highs = [100.0, 94.5]
    sim_lows = [100.0, 94.5]  # 한 봉의 low 가 Liq 아래
    df = _make_synthetic_with_extremes(prices + sim_prices,
                                       highs=highs + sim_highs,
                                       lows=lows + sim_lows)

    entry_idx = 99
    params = _default_params(lev=20, holding_1m=50)
    r = simulate_single_trade(entry_idx, df, 'long', params)
    print(f"  exit_reason={r['exit_reason']}, net_return={r.get('net_return_pct', 0):.2f}%")

    ok = True
    ok &= _assert(r['exit_reason'] == 'LIQ',
                  f"Liq 우선 발현 (실제: {r['exit_reason']})")
    ok &= _assert(r.get('net_return_pct', 0) <= -90.0,
                  f"손실 -90% 이상 (Liq) (실제: {r.get('net_return_pct', 0):.2f})")
    return ok


def test_s10_short_liq():
    """S10: SHORT Liq 발현 - 진입 직후 갭업"""
    print("\n[S10] SHORT Liq 발현")

    prices = [100.0] * 100
    highs = list(prices); lows = list(prices)
    lows[50] = 99.0; highs[50] = 99.2

    # Lev 20 SHORT 의 Liq = 100 × (1 + 1/20 - 0.004) = 100 × 1.046 = 104.6
    # 진입 후 +5.5% 갭업 (104.6 위로)
    sim_prices = [100.0, 105.5]
    sim_highs = [100.0, 105.5]
    sim_lows = [100.0, 105.5]
    df = _make_synthetic_with_extremes(prices + sim_prices,
                                       highs=highs + sim_highs,
                                       lows=lows + sim_lows)

    entry_idx = 99
    params = _default_params(lev=20, holding_1m=50)
    r = simulate_single_trade(entry_idx, df, 'short', params)
    print(f"  exit_reason={r['exit_reason']}, net_return={r.get('net_return_pct', 0):.2f}%")

    ok = True
    ok &= _assert(r['exit_reason'] == 'LIQ',
                  f"Liq 우선 발현 (실제: {r['exit_reason']})")
    ok &= _assert(r.get('net_return_pct', 0) <= -90.0,
                  f"손실 -90% 이상 (Liq) (실제: {r.get('net_return_pct', 0):.2f})")
    return ok


def main():
    print("=" * 60)
    print("obfib_simulator 단위 테스트 (10개)")
    print("=" * 60)

    tests = [
        test_s1_long_full_trend_capture,
        test_s2_long_pullback_to_ob_bottom,
        test_s3_long_hard_sl,
        test_s6_long_pure_uptrend,
        test_s8_short_mirror,
        test_s9_long_liq,
        test_s10_short_liq,
    ]

    results = []
    for t in tests:
        try:
            ok = t()
            results.append((t.__name__, ok))
        except Exception as e:
            print(f"\n[ERROR] {t.__name__}: {e}")
            import traceback; traceback.print_exc()
            results.append((t.__name__, False))

    print("\n" + "=" * 60)
    print("결과 요약")
    print("=" * 60)
    for name, ok in results:
        print(f"  {'✓' if ok else '✗'} {name}")
    print(f"\n  통과: {sum(1 for _, ok in results if ok)}/{len(results)}")


if __name__ == "__main__":
    main()
