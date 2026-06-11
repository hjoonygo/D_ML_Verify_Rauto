# -*- coding: utf-8 -*-
"""
[파일명] tbm_simulator_v7.py
코드길이: 약 560줄, 내부버전명: v7.0 (phase_a), 로직 축약/생략 없이 전체 출력.

[목적] v6 (v3.4_fib) + 안 A (동적 Hard SL ATR 기반)

[v6 -> v7 변경 사항]
  * 새 상수: USE_DYNAMIC_HARD_SL = True
  * 새 인자: atr_at_entry_pct (진입 시점 15m ATR_pct)
  * 새 인자: atr_multiplier (1.5/2.0/3.0)
  * 변경: hard_sl_price 계산 - 동적 ATR 기반
  * 추가: result에 'atr_pct_at_entry', 'dynamic_sl_dist' 컬럼

[다른 변경 없음] v6의 모든 로직 (Phase 1/2, fib_lock, 2h reversal 등)은 그대로

[사용된 파일]
  ob_provider_v2.py — OB 검출 (그대로)

[상수]
  COST_NOMINAL = 0.0016 (변경 없음)
  BEP_PLUS_PCT = 0.0024
  SL_GATE = 0.0016
  TP_GATE = 0.0024
  FIB_TRIGGER = 0.012
  FIB_EXT = 0.618
  ATR_K = 0.5
  ATR_PERIOD = 20
  HARD_SL_ROE = 0.03  (현재 자본 ROE -3% 기준)
  USE_DYNAMIC_HARD_SL = True  (★ 신규)
  DEFAULT_ATR_MULTIPLIER = 1.5  (★ 신규)

[함수 In/Out]
  compute_atr(high, low, close, period) -> np.ndarray  (변경 없음)
  
  simulate_position_v7(entry_signal_idx_1m, side, df_1m, df_ob_tf, df_2h,
                        atr_ob_tf, leverage, w, N, timeout_bars_ob_tf,
                        ob_tf_minutes, enable_2h_reversal, regime_master,
                        atr_at_entry_pct, atr_multiplier,            # ★ 신규
                        use_dynamic_hard_sl)                          # ★ 신규
    -> dict
    
  batch_simulate_v7(long_signal_indices_1m, short_signal_indices_1m,
                     df_1m, df_ob_tf, df_2h, atr_ob_tf,
                     atr_15m_pct_per_1m,                              # ★ 신규 (1m봉별 15m ATR_pct)
                     leverage, w, N, timeout_bars_ob_tf, ob_tf_minutes,
                     enable_2h_reversal, regime_master,
                     atr_multiplier, use_dynamic_hard_sl,             # ★ 신규
                     verbose) -> pd.DataFrame
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd
from typing import Optional, List, Dict, Any

from ob_provider_v2 import OB, get_levels_above, get_levels_below


# ============================================================
# 상수
# ============================================================
COST_NOMINAL = 0.0016
BEP_PLUS_PCT = 0.0024
SL_GATE = 0.0016
TP_GATE = 0.0024
FIB_TRIGGER = 0.012
FIB_EXT = 0.618
ATR_K = 0.5
ATR_PERIOD = 20
HARD_SL_ROE = 0.03

# ★ 신규 상수 (안 A)
USE_DYNAMIC_HARD_SL = True
DEFAULT_ATR_MULTIPLIER = 1.5


def compute_atr(high, low, close, period=ATR_PERIOD):
    """Wilder ATR. 3항 TR. NaN 처리. (v6 그대로)"""
    n = len(close)
    tr = np.zeros(n, dtype=np.float64)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        h_l = high[i] - low[i]
        h_pc = abs(high[i] - close[i-1])
        l_pc = abs(low[i] - close[i-1])
        tr[i] = max(h_l, h_pc, l_pc)
    atr = np.full(n, np.nan, dtype=np.float64)
    if n < period:
        return atr
    atr[period-1] = tr[:period].mean()
    for i in range(period, n):
        atr[i] = (atr[i-1] * (period-1) + tr[i]) / period
    return atr


def simulate_position_v7(
    entry_signal_idx_1m: int,
    side: str,
    df_1m: pd.DataFrame,
    df_ob_tf: pd.DataFrame,
    df_2h: pd.DataFrame,
    atr_ob_tf: np.ndarray,
    leverage: int = 5,
    w: int = 5,
    N: int = 5,
    timeout_bars_ob_tf: int = 7,
    ob_tf_minutes: int = 60,
    enable_2h_reversal: bool = True,
    regime_master = None,
    atr_at_entry_pct: float = 0.004,  # ★ 신규 (default 0.4%)
    atr_multiplier: float = DEFAULT_ATR_MULTIPLIER,  # ★ 신규
    use_dynamic_hard_sl: bool = USE_DYNAMIC_HARD_SL,  # ★ 신규
) -> Dict[str, Any]:
    """
    v7 — 한 신호에 대한 시뮬레이션 1회. v6 + 안 A (동적 Hard SL).

    IN: (v6와 동일 + 3개 신규)
      atr_at_entry_pct: 진입 시점 15m ATR_pct (가격 대비 %)
      atr_multiplier: ATR 멀티플라이어 (1.5/2.0/3.0)
      use_dynamic_hard_sl: 동적 SL 사용 여부 (False면 v6와 동일)
    OUT:
      result dict (v6 + 'atr_pct_at_entry', 'dynamic_sl_dist')
    """
    result = {
        'entry_signal_idx_1m': entry_signal_idx_1m, 'side': side,
        'exit_reason': None, 'price_roe': 0.0, 'net_return': -COST_NOMINAL,
        'phase2_active': False, 'n_ob_used': 0, 'bars_held_1m': 0,
        'used_f4p': False, 'gate_fail_reason': None,
        'entry_t': None, 'entry_price': None, 'exit_price': None, 'exit_t': None,
        'initial_sl': None, 'initial_tp': None, 'final_stop': None, 'final_tp': None,
        'leverage': leverage,
        'reversal_2h_triggered': False,
        'reverse_entry_attempted': False,
        # ★ 신규 컬럼
        'atr_pct_at_entry': atr_at_entry_pct,
        'dynamic_sl_dist': None,
        'hard_sl_mode': 'dynamic' if use_dynamic_hard_sl else 'fixed',
    }

    n_1m = len(df_1m)
    entry_t_1m = entry_signal_idx_1m + 1
    if entry_t_1m >= n_1m:
        result['exit_reason'] = 'no_data'
        return result

    entry_price = float(df_1m['open'].iloc[entry_t_1m])
    if not np.isfinite(entry_price) or entry_price <= 0:
        result['exit_reason'] = 'no_data'
        return result
    entry_ts = df_1m.index[entry_t_1m]
    result['entry_t'] = entry_ts
    result['entry_price'] = entry_price

    # ★★★ 안 A 신규: 동적 Hard SL 계산 (early return 전에 항상 계산) ★★★
    if use_dynamic_hard_sl and np.isfinite(atr_at_entry_pct) and atr_at_entry_pct > 0:
        atr_based_dist = atr_at_entry_pct * atr_multiplier
        fixed_based_dist = HARD_SL_ROE / leverage
        dynamic_sl_dist = max(atr_based_dist, fixed_based_dist)
    else:
        dynamic_sl_dist = HARD_SL_ROE / leverage
    result['dynamic_sl_dist'] = dynamic_sl_dist

    # OB TF 인덱스 (v6 그대로)
    try:
        ob_tf_idx = df_ob_tf.index.searchsorted(entry_ts, side='right') - 1
    except Exception:
        result['exit_reason'] = 'no_ob_tf_idx'
        return result
    if ob_tf_idx < 0 or ob_tf_idx >= len(df_ob_tf):
        result['exit_reason'] = 'no_ob_tf_idx'
        return result

    # OB Provider 호출 (v6 그대로)
    if side == 'long':
        tp_obs = get_levels_above(ob_tf_idx, entry_price, N, df_ob_tf, w)
        sl_obs_list = get_levels_below(ob_tf_idx, entry_price, 1, df_ob_tf, w)
    else:
        tp_obs = get_levels_below(ob_tf_idx, entry_price, N, df_ob_tf, w)
        sl_obs_list = get_levels_above(ob_tf_idx, entry_price, 1, df_ob_tf, w)

    if len(tp_obs) == 0:
        result['exit_reason'] = 'no_tp_ob'
        return result

    # 초기 TP (v6 그대로)
    if side == 'long':
        initial_tp = float(tp_obs[0].top)
        tp_dist = (initial_tp - entry_price) / entry_price
    else:
        initial_tp = float(tp_obs[0].bottom)
        tp_dist = (entry_price - initial_tp) / entry_price

    if tp_dist < TP_GATE:
        result['exit_reason'] = 'tp_gate_fail'
        result['gate_fail_reason'] = f'tp_dist={tp_dist:.5f}<{TP_GATE}'
        return result

    # 초기 SL — F4' 가상 SL 가능 (v6 그대로)
    used_f4p = False
    if len(sl_obs_list) > 0:
        if side == 'long':
            initial_sl = float(sl_obs_list[0].bottom)
            sl_dist = (entry_price - initial_sl) / entry_price
        else:
            initial_sl = float(sl_obs_list[0].top)
            sl_dist = (initial_sl - entry_price) / entry_price
    else:
        atr_now = atr_ob_tf[ob_tf_idx]
        if not np.isfinite(atr_now) or atr_now <= 0:
            result['exit_reason'] = 'no_atr'
            return result
        sl_offset = atr_now * ATR_K
        initial_sl = entry_price - sl_offset if side == 'long' else entry_price + sl_offset
        sl_dist = sl_offset / entry_price
        used_f4p = True

    if sl_dist < SL_GATE:
        result['exit_reason'] = 'sl_gate_fail'
        result['gate_fail_reason'] = f'sl_dist={sl_dist:.5f}<{SL_GATE}'
        result['used_f4p'] = used_f4p
        return result

    result['used_f4p'] = used_f4p
    result['initial_sl'] = initial_sl
    result['initial_tp'] = initial_tp

    # 동적 SL 거리는 위에서 이미 계산됨 (result['dynamic_sl_dist'])
    if side == 'long':
        hard_sl_price = entry_price * (1 - dynamic_sl_dist)
    else:
        hard_sl_price = entry_price * (1 + dynamic_sl_dist)

    # 상태 변수 (v6 그대로)
    target_idx = 0
    current_tp = initial_tp
    stop_line = initial_sl
    fib_lock_active = False
    extreme = entry_price
    wave_start = entry_price
    n_ob_used = 0

    if side == 'long':
        bep_plus = entry_price * (1 + BEP_PLUS_PCT)
        fib_trigger_price = entry_price * (1 + FIB_TRIGGER)
    else:
        bep_plus = entry_price * (1 - BEP_PLUS_PCT)
        fib_trigger_price = entry_price * (1 - FIB_TRIGGER)

    # 1m path 확보 (v6 그대로)
    timeout_minutes = timeout_bars_ob_tf * ob_tf_minutes
    end_ts = entry_ts + pd.Timedelta(minutes=timeout_minutes)
    try:
        path = df_1m.loc[entry_ts:end_ts]
    except KeyError:
        result['exit_reason'] = 'no_1m_path'
        result['final_stop'] = stop_line
        result['final_tp'] = current_tp
        return result

    if len(path) == 0:
        result['exit_reason'] = 'no_1m_path'
        return result

    # 2h reversal 감지 준비 (v6 그대로)
    prev_2h_regime = None
    if enable_2h_reversal and regime_master is not None and df_2h is not None and len(df_2h) >= 120:
        try:
            entry_2h_idx = df_2h.index.searchsorted(entry_ts, side='right') - 1
            if entry_2h_idx >= 120:
                window_2h = df_2h.iloc[entry_2h_idx-119:entry_2h_idx+1]
                prev_2h_regime = regime_master.get_regime_2h(window_2h)
        except Exception:
            prev_2h_regime = None

    # 메인 1m 루프 (v6 그대로)
    highs_1m = path['high'].values
    lows_1m = path['low'].values
    closes_1m = path['close'].values
    path_index = path.index
    n_path = len(path)

    exit_set = False
    for k in range(n_path):
        h = highs_1m[k]
        l = lows_1m[k]
        ts = path_index[k]

        # (Z) Hard SL 체크 (v6 그대로 - 단 hard_sl_price만 동적)
        if side == 'long':
            hard_sl_hit = l <= hard_sl_price
        else:
            hard_sl_hit = h >= hard_sl_price
        if hard_sl_hit and not fib_lock_active:
            exit_price = hard_sl_price
            price_roe = (exit_price - entry_price) / entry_price if side == 'long' else (entry_price - exit_price) / entry_price
            result['exit_reason'] = 'hard_sl'
            result['exit_price'] = exit_price
            result['exit_t'] = ts
            result['price_roe'] = price_roe
            result['net_return'] = price_roe - COST_NOMINAL
            result['phase2_active'] = fib_lock_active
            result['n_ob_used'] = n_ob_used
            result['bars_held_1m'] = k + 1
            result['final_stop'] = stop_line
            result['final_tp'] = current_tp
            exit_set = True
            break

        # (A) TP 도달 (v6 그대로)
        tp_hit = False
        if current_tp is not None:
            tp_hit = (h >= current_tp) if side == 'long' else (l <= current_tp)

        if tp_hit:
            broken_ob = tp_obs[target_idx]
            if side == 'long':
                candidate_sl = max(float(broken_ob.bottom), bep_plus)
                stop_line = max(stop_line, candidate_sl)
            else:
                candidate_sl = min(float(broken_ob.top), bep_plus)
                stop_line = min(stop_line, candidate_sl)
            target_idx += 1
            n_ob_used += 1
            if target_idx < len(tp_obs):
                next_ob = tp_obs[target_idx]
                current_tp = float(next_ob.top) if side == 'long' else float(next_ob.bottom)
            else:
                fib_lock_active = True
                current_tp = None

        # (B) Phase 2 트리거 (v6 그대로)
        if not fib_lock_active:
            if side == 'long':
                if h >= fib_trigger_price:
                    fib_lock_active = True
            else:
                if l <= fib_trigger_price:
                    fib_lock_active = True

        # (C) Phase 2: extreme + fib_lock (v6 그대로)
        if fib_lock_active:
            if side == 'long':
                if h > extreme:
                    extreme = h
                fib_lock = entry_price + (extreme - entry_price) * FIB_EXT
                stop_line = max(stop_line, fib_lock)
            else:
                if l < extreme:
                    extreme = l
                fib_lock = entry_price - (entry_price - extreme) * FIB_EXT
                stop_line = min(stop_line, fib_lock)

        # (C+) 2h 반전 신호 (v6 그대로)
        if enable_2h_reversal and regime_master is not None and df_2h is not None and prev_2h_regime is not None:
            if ts.minute == 0 and ts.hour % 2 == 0 and ts > entry_ts + pd.Timedelta(hours=2):
                try:
                    curr_2h_idx = df_2h.index.searchsorted(ts, side='right') - 1
                    if curr_2h_idx >= 120:
                        window_2h_curr = df_2h.iloc[curr_2h_idx-119:curr_2h_idx+1]
                        curr_2h_regime = regime_master.get_regime_2h(window_2h_curr)
                        reversal = regime_master.detect_reversal(prev_2h_regime, curr_2h_regime)
                        should_close = False
                        if side == 'long' and reversal == 'long_to_short_reversal':
                            should_close = True
                        elif side == 'short' and reversal == 'short_to_long_reversal':
                            should_close = True

                        if should_close:
                            if k + 1 < n_path:
                                exit_price = float(df_1m['open'].iloc[df_1m.index.get_loc(path_index[k+1])])
                            else:
                                exit_price = closes_1m[k]
                            price_roe = (exit_price - entry_price) / entry_price if side == 'long' else (entry_price - exit_price) / entry_price
                            result['exit_reason'] = 'reversal_2h'
                            result['exit_price'] = exit_price
                            result['exit_t'] = ts
                            result['price_roe'] = price_roe
                            result['net_return'] = price_roe - COST_NOMINAL
                            result['phase2_active'] = fib_lock_active
                            result['n_ob_used'] = n_ob_used
                            result['bars_held_1m'] = k + 1
                            result['final_stop'] = stop_line
                            result['final_tp'] = current_tp
                            result['reversal_2h_triggered'] = True
                            exit_set = True
                            break
                        prev_2h_regime = curr_2h_regime
                except Exception:
                    pass

        # (D) SL 터치 (v6 그대로)
        sl_hit = (l <= stop_line) if side == 'long' else (h >= stop_line)
        if sl_hit:
            exit_price = stop_line
            price_roe = (exit_price - entry_price) / entry_price if side == 'long' else (entry_price - exit_price) / entry_price
            if not fib_lock_active:
                result['exit_reason'] = 'sl'
            elif n_ob_used >= len(tp_obs):
                result['exit_reason'] = 'fib_lock'
            else:
                result['exit_reason'] = 'ratchet_sl'
            result['exit_price'] = exit_price
            result['exit_t'] = ts
            result['price_roe'] = price_roe
            result['net_return'] = price_roe - COST_NOMINAL
            result['phase2_active'] = fib_lock_active
            result['n_ob_used'] = n_ob_used
            result['bars_held_1m'] = k + 1
            result['final_stop'] = stop_line
            result['final_tp'] = current_tp
            exit_set = True
            break

    if not exit_set:
        last_close = float(closes_1m[-1])
        price_roe = (last_close - entry_price) / entry_price if side == 'long' else (entry_price - last_close) / entry_price
        result['exit_reason'] = 'timeout_no_ob' if n_ob_used == 0 else 'timeout_after_ob'
        result['exit_price'] = last_close
        result['exit_t'] = path_index[-1]
        result['price_roe'] = price_roe
        result['net_return'] = price_roe - COST_NOMINAL
        result['phase2_active'] = fib_lock_active
        result['n_ob_used'] = n_ob_used
        result['bars_held_1m'] = n_path
        result['final_stop'] = stop_line
        result['final_tp'] = current_tp

    return result


def batch_simulate_v7(
    long_signal_indices_1m: List[int],
    short_signal_indices_1m: List[int],
    df_1m: pd.DataFrame,
    df_ob_tf: pd.DataFrame,
    df_2h: pd.DataFrame,
    atr_ob_tf: np.ndarray,
    atr_15m_pct_per_1m: np.ndarray,  # ★ 신규: 1m봉별 15m ATR_pct
    leverage: int = 5,
    w: int = 5,
    N: int = 5,
    timeout_bars_ob_tf: int = 7,
    ob_tf_minutes: int = 60,
    enable_2h_reversal: bool = True,
    regime_master = None,
    atr_multiplier: float = DEFAULT_ATR_MULTIPLIER,
    use_dynamic_hard_sl: bool = USE_DYNAMIC_HARD_SL,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    v7 배치 시뮬레이션. v6 + 안 A.

    IN: (v6와 동일 + atr_15m_pct_per_1m, atr_multiplier, use_dynamic_hard_sl)
      atr_15m_pct_per_1m: 1m봉별 15m ATR_pct (float64 array, 길이=len(df_1m))
                         진입 시점에서 ATR_pct 조회용
      atr_multiplier: ATR 멀티플라이어
      use_dynamic_hard_sl: 동적 SL 활성화
    OUT: DataFrame
    """
    results = []
    last_exit_t_1m = -1

    all_signals = []
    for s in long_signal_indices_1m:
        all_signals.append((s, 'long'))
    for s in short_signal_indices_1m:
        all_signals.append((s, 'short'))
    all_signals.sort(key=lambda x: x[0])

    n_total = len(all_signals)
    for i, (sig_idx, side) in enumerate(all_signals):
        if verbose and i % 500 == 0:
            print(f"    sim {i}/{n_total}…")

        if sig_idx <= last_exit_t_1m:
            results.append({
                'entry_signal_idx_1m': sig_idx, 'side': side,
                'exit_reason': 'blocked_single_pos',
                'price_roe': 0.0, 'net_return': 0.0,
                'phase2_active': False, 'n_ob_used': 0, 'bars_held_1m': 0,
                'used_f4p': False, 'gate_fail_reason': None,
                'entry_t': None, 'entry_price': None,
                'exit_price': None, 'exit_t': None,
                'initial_sl': None, 'initial_tp': None,
                'final_stop': None, 'final_tp': None,
                'leverage': leverage,
                'reversal_2h_triggered': False,
                'reverse_entry_attempted': False,
                'atr_pct_at_entry': None,
                'dynamic_sl_dist': None,
                'hard_sl_mode': 'dynamic' if use_dynamic_hard_sl else 'fixed',
            })
            continue

        # ★ 진입 시점 ATR_pct 조회
        entry_t = sig_idx + 1  # 진입 봉
        if 0 <= entry_t < len(atr_15m_pct_per_1m):
            atr_at_entry_pct = float(atr_15m_pct_per_1m[entry_t])
        else:
            atr_at_entry_pct = 0.004  # default fallback

        r = simulate_position_v7(
            sig_idx, side, df_1m, df_ob_tf, df_2h, atr_ob_tf,
            leverage=leverage, w=w, N=N,
            timeout_bars_ob_tf=timeout_bars_ob_tf,
            ob_tf_minutes=ob_tf_minutes,
            enable_2h_reversal=enable_2h_reversal,
            regime_master=regime_master,
            atr_at_entry_pct=atr_at_entry_pct,
            atr_multiplier=atr_multiplier,
            use_dynamic_hard_sl=use_dynamic_hard_sl,
        )
        results.append(r)

        if r.get('exit_t') is not None:
            try:
                exit_1m_idx = df_1m.index.get_indexer([r['exit_t'].floor('1min')])[0]
                if exit_1m_idx >= 0:
                    last_exit_t_1m = exit_1m_idx
            except Exception:
                last_exit_t_1m = sig_idx + 60 * (timeout_bars_ob_tf * ob_tf_minutes)

    df = pd.DataFrame(results)
    return df
