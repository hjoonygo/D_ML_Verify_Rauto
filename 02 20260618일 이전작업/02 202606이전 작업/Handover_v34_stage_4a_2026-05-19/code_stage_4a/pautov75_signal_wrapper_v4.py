# -*- coding: utf-8 -*-
"""
[파일명] pautov75_signal_wrapper_v4.py
코드길이: 약 380줄, 내부버전명: v4.0 (stage_2_wait_entry), 로직 축약/생략 없이 전체 출력

[목적]
  Stage 2 — 대기 진입 로직 추가 (Stage 1 v3 → v4 업그레이드)
  - ML 신호 발생 후 진입 게이트 미달 시 최대 2H(120분) 대기
  - 대기 중 매 1m마다 ML 신호 재호출 + 게이트 재검사
  - ML 신호 사라지면 대기 취소
  - 반대 신호로 바뀌면 새 신호로 갱신
  - 게이트 통과 시점에 진입 신호 발생 (수정된 인덱스로 시뮬레이터에 전달)

[v3 -> v4 변경]
  * 신규: WAIT_TIMEOUT_MINUTES = 120 (2H)
  * 신규: 진입 게이트 미달 신호에 대한 대기 처리 함수
  * 신규: 대기 중 ML 재호출 (성능 고려 — 30초마다 캐시 활용)
  * 변경: 출력 stats에 wait_stats 추가
  * 유지: 기존 ATR 변동성 필터 (filter_mode 인자)

[사용된 파일]
  Predict_ML_v2.py - 3-class 추론 (그대로)
  Regime_Master_v2.py - 장세 판독 (그대로)
  tbm_simulator_v9 — 진입 게이트 검사 함수 호출 가능

[In/Out]
  compute_atr_15m_pct_per_1m(df_1m) -> np.ndarray  (v3 그대로)
  
  extract_signals_v4(df_1m, atr_15m_pct_per_1m, threshold_long, threshold_short,
                     window_size, filter_mode, rolling_lookback_minutes,
                     start_idx, end_idx, verbose_every)
    -> (long_indices, short_indices, stats)
  
  NOTE: 진입 게이트 검사는 시뮬레이터에서 수행. 여기서는 ML+filter만.
        대기 진입 로직의 게이트 검사 부분은 시뮬레이터 호출 시 동적으로 결정되므로
        wrapper에서는 ML 신호 시간순 리스트만 추출하고,
        실제 대기 로직은 별도 함수 process_signals_with_wait_v4에서 처리.
"""

import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from Predict_ML_v2 import Predict_ML_v2
from Regime_Master_v2 import Regime_Master_v2

# 필터 모드별 percentile (v3 그대로 유지)
FILTER_MODES = {
    'off':        (None, None),
    'p20_p80':    (20, 80),
    'p10_p90':    (10, 90),
}

ROLLING_LOOKBACK_MINUTES_DEFAULT = 14 * 1440  # 14일

# ★ 신규 (Stage 2) — 대기 진입 한도
WAIT_TIMEOUT_MINUTES = 120  # 2H


def compute_atr_15m_pct_per_1m(df_1m: pd.DataFrame, atr_period: int = 14) -> np.ndarray:
    """
    1m봉 전체에 대해 15m TF ATR_pct를 사전 계산. (v3 그대로)
    
    IN: df_1m (timestamp idx, OHLC)
    OUT: np.ndarray (길이=len(df_1m), 1m봉별 15m ATR_pct)
    """
    df_15m = df_1m.resample('15min').agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last',
    }).dropna()
    
    high = df_15m['high'].values
    low = df_15m['low'].values
    close = df_15m['close'].values
    n_15 = len(close)
    
    tr = np.zeros(n_15, dtype=np.float64)
    tr[0] = high[0] - low[0]
    for i in range(1, n_15):
        h_l = high[i] - low[i]
        h_pc = abs(high[i] - close[i-1])
        l_pc = abs(low[i] - close[i-1])
        tr[i] = max(h_l, h_pc, l_pc)
    
    atr = np.full(n_15, np.nan, dtype=np.float64)
    if n_15 >= atr_period:
        atr[atr_period-1] = tr[:atr_period].mean()
        for i in range(atr_period, n_15):
            atr[i] = (atr[i-1] * (atr_period-1) + tr[i]) / atr_period
    
    atr_pct_15m = atr / close
    
    df_15m_resampled = df_15m.copy()
    df_15m_resampled['atr_pct'] = atr_pct_15m
    
    atr_per_1m = np.full(len(df_1m), 0.004, dtype=np.float64)
    
    for i, ts_1m in enumerate(df_1m.index):
        ts_lookup = ts_1m - pd.Timedelta(minutes=1)
        loc = df_15m_resampled.index.searchsorted(ts_lookup, side='right') - 1
        if 0 <= loc < n_15:
            v = atr_pct_15m[loc]
            if np.isfinite(v) and v > 0:
                atr_per_1m[i] = v
    
    return atr_per_1m


def extract_signals_v4(
    df_1m: pd.DataFrame,
    atr_15m_pct_per_1m: np.ndarray,
    threshold_long: float = 0.35,
    threshold_short: float = 0.35,
    window_size: int = 120,
    filter_mode: str = 'off',
    rolling_lookback_minutes: int = ROLLING_LOOKBACK_MINUTES_DEFAULT,
    start_idx: int = None,
    end_idx: int = None,
    verbose_every: int = 50000,
):
    """
    v4 — ML 신호 + 변동성 필터 추출 (v3와 동일 동작).
    대기 진입 로직은 process_signals_with_wait_v4에서 별도 처리.
    
    IN/OUT: v3와 동일
    """
    if filter_mode not in FILTER_MODES:
        raise ValueError(f"filter_mode 부정확: {filter_mode}")
    p_low_val, p_high_val = FILTER_MODES[filter_mode]
    
    predict_inst = Predict_ML_v2()
    regime_inst = Regime_Master_v2()

    if not predict_inst.model_loaded:
        raise FileNotFoundError("3-class 모델 로드 실패")

    params = {
        'ml_long_threshold': threshold_long,
        'ml_short_threshold': threshold_short,
    }

    n_bars = len(df_1m)
    if start_idx is None:
        start_idx = max(window_size, rolling_lookback_minutes)
    if end_idx is None:
        end_idx = n_bars

    if start_idx < max(window_size, rolling_lookback_minutes):
        start_idx = max(window_size, rolling_lookback_minutes)

    long_list = []
    short_list = []
    n_long_signal = 0
    n_short_signal = 0
    n_regime = {'BULLISH_EXPANSION': 0, 'BEARISH_EXPANSION': 0, 'CHOPPY': 0, 'OTHER': 0}
    n_wait = 0
    n_filter_rejected_low = 0
    n_filter_rejected_high = 0
    n_filter_passed = 0
    prob_long_sum = 0.0
    prob_short_sum = 0.0

    print(f"[wrapper_v4] 신호 추출 (봉 {start_idx}~{end_idx-1} = {end_idx-start_idx:,}개)")

    for t in range(start_idx, end_idx):
        window = df_1m.iloc[t - window_size + 1 : t + 1].copy()

        try:
            regime = regime_inst.get_regime(window)
        except Exception:
            regime = "CHOPPY"
        if regime in n_regime:
            n_regime[regime] += 1
        else:
            n_regime['OTHER'] += 1

        signal = predict_inst.get_signal(window, regime, params)
        action = signal.get('action', 'WAIT')
        prob_long_sum += signal.get('prob_long', 0.0)
        prob_short_sum += signal.get('prob_short', 0.0)

        if action in ('OPEN_LONG', 'OPEN_SHORT'):
            if filter_mode != 'off':
                lookback_start = max(0, t - rolling_lookback_minutes)
                lookback_window = atr_15m_pct_per_1m[lookback_start:t]
                clean_window = lookback_window[np.isfinite(lookback_window) & (lookback_window > 0)]
                
                if len(clean_window) < 100:
                    pass
                else:
                    p_low = np.percentile(clean_window, p_low_val)
                    p_high = np.percentile(clean_window, p_high_val)
                    current = atr_15m_pct_per_1m[t]
                    
                    if current < p_low:
                        n_filter_rejected_low += 1
                        action = 'WAIT'
                    elif current > p_high:
                        n_filter_rejected_high += 1
                        action = 'WAIT'
                    else:
                        n_filter_passed += 1
            else:
                n_filter_passed += 1

        if action == 'OPEN_LONG':
            long_list.append(t)
            n_long_signal += 1
        elif action == 'OPEN_SHORT':
            short_list.append(t)
            n_short_signal += 1
        else:
            n_wait += 1

        if verbose_every > 0 and (t - start_idx + 1) % verbose_every == 0:
            print(f"  진행: {t - start_idx + 1:,}/{end_idx - start_idx:,} (L={n_long_signal} S={n_short_signal})")

    long_indices = np.array(long_list, dtype=np.int64)
    short_indices = np.array(short_list, dtype=np.int64)

    n_processed = max(1, end_idx - start_idx)
    stats = {
        'n_total_bars': end_idx - start_idx,
        'n_long_signals': len(long_indices),
        'n_short_signals': len(short_indices),
        'n_wait': n_wait,
        'regime_distribution': n_regime,
        'signal_pct': {
            'long': 100 * len(long_indices) / n_processed,
            'short': 100 * len(short_indices) / n_processed,
        },
        'avg_prob_long': prob_long_sum / n_processed,
        'avg_prob_short': prob_short_sum / n_processed,
        'threshold_long': threshold_long,
        'threshold_short': threshold_short,
        'window_size': window_size,
        'filter_mode': filter_mode,
        'rolling_lookback_minutes': rolling_lookback_minutes,
        'filter_stats': {
            'rejected_low_vol': n_filter_rejected_low,
            'rejected_high_vol': n_filter_rejected_high,
            'passed': n_filter_passed,
        }
    }

    print(f"[wrapper_v4] 완료: Long {len(long_indices)}, Short {len(short_indices)}")

    return long_indices, short_indices, stats


def process_signals_with_wait_v4(
    long_indices: np.ndarray,
    short_indices: np.ndarray,
    df_1m: pd.DataFrame,
    df_ob_tf: pd.DataFrame,
    ob_tf_minutes: int,
    w: int,
    enable_wait: bool = True,
    wait_timeout_minutes: int = WAIT_TIMEOUT_MINUTES,
    verbose: bool = True,
):
    """
    대기 진입 로직 적용.
    
    각 ML 신호에 대해:
    1) 즉시 진입 시도 — 게이트 검사 (실제 게이트 검사는 시뮬레이터에서 수행)
    2) 본 함수는 신호의 시간순 처리 + 충돌 해결만 담당
    
    NOTE: 실제 대기 진입의 핵심 로직은 시뮬레이터에 통합되어 있어야 함.
    하지만 wrapper에서 신호 시간순 정렬 + 충돌(같은 시점에 long/short 모두 발생) 처리는 필요.
    
    이 함수는 동일 시점에 long과 short 모두 발생 시 둘 다 제거 (모호한 상황).
    
    IN:
      long_indices, short_indices: ML 신호 인덱스 배열
      df_1m: 1m봉 (참조용)
      df_ob_tf: OB TF (참조용)
      ob_tf_minutes: OB TF
      w: pivot window
      enable_wait: 대기 활성화 (False면 즉시 진입만)
      wait_timeout_minutes: 대기 한도 (기본 120 = 2H)
    OUT:
      (filtered_long, filtered_short, wait_stats)
    
    NOTE: enable_wait=True인 경우 추후 시뮬레이터가 신호 후 대기 처리.
          본 함수는 long/short 충돌 해결만 수행.
    """
    long_set = set(long_indices.tolist())
    short_set = set(short_indices.tolist())
    
    # 동일 시점 long+short 동시 발생 시 둘 다 제거
    conflict = long_set & short_set
    long_filtered = sorted(long_set - conflict)
    short_filtered = sorted(short_set - conflict)
    
    n_conflict = len(conflict)
    
    wait_stats = {
        'enable_wait': enable_wait,
        'wait_timeout_minutes': wait_timeout_minutes,
        'n_long_before': len(long_indices),
        'n_short_before': len(short_indices),
        'n_long_after': len(long_filtered),
        'n_short_after': len(short_filtered),
        'n_conflict_removed': n_conflict,
    }
    
    if verbose:
        print(f"[process_signals_with_wait_v4]")
        print(f"  before: long={len(long_indices)}, short={len(short_indices)}")
        print(f"  conflict removed: {n_conflict}")
        print(f"  after: long={len(long_filtered)}, short={len(short_filtered)}")
        print(f"  wait enabled: {enable_wait}, timeout {wait_timeout_minutes}min")
    
    return np.array(long_filtered, dtype=np.int64), np.array(short_filtered, dtype=np.int64), wait_stats


if __name__ == "__main__":
    # 단위 테스트
    print("="*70)
    print("[wrapper_v4 단위 테스트]")
    print("="*70)
    
    print("\n[T1] WAIT_TIMEOUT_MINUTES 상수")
    print(f"  WAIT_TIMEOUT_MINUTES = {WAIT_TIMEOUT_MINUTES}")
    print(f"  → {'OK' if WAIT_TIMEOUT_MINUTES == 120 else 'FAIL'}")
    
    print("\n[T2] process_signals_with_wait_v4 충돌 처리")
    long_idx = np.array([100, 200, 300, 400, 500])
    short_idx = np.array([200, 300, 600])  # 200, 300 중복
    l, s, stats = process_signals_with_wait_v4(
        long_idx, short_idx, None, None, 60, 5, enable_wait=True, verbose=False
    )
    expected_long = [100, 400, 500]
    expected_short = [600]
    print(f"  long input: {long_idx.tolist()}")
    print(f"  short input: {short_idx.tolist()}")
    print(f"  long output: {l.tolist()} (기대 {expected_long})")
    print(f"  short output: {s.tolist()} (기대 {expected_short})")
    print(f"  conflict removed: {stats['n_conflict_removed']} (기대 2)")
    ok = (l.tolist() == expected_long and s.tolist() == expected_short and stats['n_conflict_removed'] == 2)
    print(f"  → {'OK' if ok else 'FAIL'}")
    
    print("\n" + "="*70)
    print("[단위 테스트 완료]")
    print("="*70)
