# -*- coding: utf-8 -*-
"""
[파일명] tbm_simulator_v6.py
코드길이: 약 520줄, 내부버전명: v6.0 (v3.4_fib), 로직 축약/생략 없이 전체 출력.

[목적] v5 기반 + v3.4 인터페이스 + 결함 #2 정정 + 2h 반전 처리

[변경 사항 vs v5]
  - v3.4 어댑터: 1m 그리드 + Lev/Holding/장세 그리드 호환
  - 결함 #2 정정: Phase 1에도 hard_sl 적용 (Phase 1 무방어 → 방어)
  - 2h 반전 신호 처리: 2h봉 regime 반전 시 청산 + 반대 prob ≥ 0.35면 반대 진입
  - OB Provider TF 분기: 호출 측에서 15m/30m/1h df 전달

[v5 → v6 호환]
  - 함수명/시그니처 비슷하지만 *df_ob_tf* 인자 추가 (OB 검출용 별도 TF df)
  - timeout_bars 단위가 *OB TF*의 봉 수
  - 결함 #2 정정: Phase 1 내부에서도 hard_sl 체크

[상수]
  COST_NOMINAL = 0.0016  # round-trip 16bp
  BEP_PLUS_PCT = 0.0024
  SL_GATE = 0.0016
  TP_GATE = 0.0024
  FIB_TRIGGER = 0.012    # 가격 +1.2%
  FIB_EXT = 0.618
  ATR_K = 0.5
  ATR_PERIOD = 20
  HARD_SL_ROE = 0.03     # 자본 -3% ROE (결함 #2 정정: Phase 1에도 적용)

[함수 In/Out]
  compute_atr(high, low, close, period) -> np.ndarray
  simulate_position_v6(...) -> dict
  batch_simulate_v6(...) -> pd.DataFrame
  resample_to_ob_tf(df_1m, tf_minutes) -> pd.DataFrame
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
HARD_SL_ROE = 0.03  # 자본 -3% ROE (결함 #2)


def compute_atr(high, low, close, period=ATR_PERIOD):
    """Wilder ATR. 3항 TR. NaN 처리. """
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


def simulate_position_v6(
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
) -> Dict[str, Any]:
    """
    한 신호에 대한 시뮬레이션 1회.

    IN:
      entry_signal_idx_1m: 1m봉 인덱스 (PautoV75 ML 신호 발생 시점)
      side: 'long' or 'short'
      df_1m: 1m봉 전체 OHLC (path 추적용)
      df_ob_tf: OB 검출용 TF df (15m/30m/1h)
      df_2h: 2h봉 df (reversal 감지용)
      atr_ob_tf: OB TF의 ATR 배열
      leverage: 5/10/15/20
      w, N: OB Provider 파라미터
      timeout_bars_ob_tf: OB TF 기준 timeout (7/14/28)
      ob_tf_minutes: OB TF (15/30/60)
      enable_2h_reversal: 2h 반전 처리 On/Off
      regime_master: Regime_Master_v2 인스턴스 (2h 반전 감지용)
    OUT:
      result dict (exit_reason, net_return, etc.)
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

    # OB TF 인덱스: entry_ts에 해당하는 OB TF 봉
    try:
        ob_tf_idx = df_ob_tf.index.searchsorted(entry_ts, side='right') - 1
    except Exception:
        result['exit_reason'] = 'no_ob_tf_idx'
        return result
    if ob_tf_idx < 0 or ob_tf_idx >= len(df_ob_tf):
        result['exit_reason'] = 'no_ob_tf_idx'
        return result

    # OB Provider 호출 — OB TF 데이터로
    if side == 'long':
        tp_obs = get_levels_above(ob_tf_idx, entry_price, N, df_ob_tf, w)
        sl_obs_list = get_levels_below(ob_tf_idx, entry_price, 1, df_ob_tf, w)
    else:
        tp_obs = get_levels_below(ob_tf_idx, entry_price, N, df_ob_tf, w)
        sl_obs_list = get_levels_above(ob_tf_idx, entry_price, 1, df_ob_tf, w)

    if len(tp_obs) == 0:
        result['exit_reason'] = 'no_tp_ob'
        return result

    # 초기 TP
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

    # 초기 SL — F4' 가상 SL 가능
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

    # 결함 #2 정정: Hard SL (가격 기준)
    # entry × (1 - HARD_SL_ROE / leverage) [LONG]
    if side == 'long':
        hard_sl_price = entry_price * (1 - HARD_SL_ROE / leverage)
    else:
        hard_sl_price = entry_price * (1 + HARD_SL_ROE / leverage)

    # 상태
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

    # 1m path — entry_ts부터 (entry + timeout_bars × ob_tf_minutes)분까지
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

    # 2h reversal 감지용 — 진입 시점의 prev 2h regime
    prev_2h_regime = None
    if enable_2h_reversal and regime_master is not None and df_2h is not None and len(df_2h) >= 120:
        # entry 시점의 직전 2h봉까지 가져옴
        try:
            entry_2h_idx = df_2h.index.searchsorted(entry_ts, side='right') - 1
            if entry_2h_idx >= 120:
                window_2h = df_2h.iloc[entry_2h_idx-119:entry_2h_idx+1]
                prev_2h_regime = regime_master.get_regime_2h(window_2h)
        except Exception:
            prev_2h_regime = None

    # 메인 1m 루프
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

        # (Z) Hard SL 체크 — 결함 #2 정정: Phase 1에도 적용
        if side == 'long':
            hard_sl_hit = l <= hard_sl_price
        else:
            hard_sl_hit = h >= hard_sl_price
        if hard_sl_hit and not fib_lock_active:
            # Phase 1 또는 Phase 2 트리거 전 hard_sl 작동
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

        # (A) TP 도달 — OB Phase 1
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

        # (B) Phase 2 트리거 (가격 +1.2%)
        if not fib_lock_active:
            if side == 'long':
                if h >= fib_trigger_price:
                    fib_lock_active = True
            else:
                if l <= fib_trigger_price:
                    fib_lock_active = True

        # (C) Phase 2: extreme + fib_lock
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

        # (C+) 2h 반전 신호 — *매 2h봉 마감 시점에 체크*
        # 2h봉 마감 = ts.minute == 0 and ts.hour % 2 == 0
        # 진입 후 새 2h봉이 마감되면 그 봉의 regime이 prev와 다른지 확인
        if enable_2h_reversal and regime_master is not None and df_2h is not None and prev_2h_regime is not None:
            # ts가 2h봉 마감 시점인지
            if ts.minute == 0 and ts.hour % 2 == 0 and ts > entry_ts + pd.Timedelta(hours=2):
                # 새 2h봉 마감 시점
                try:
                    curr_2h_idx = df_2h.index.searchsorted(ts, side='right') - 1
                    if curr_2h_idx >= 120:
                        window_2h_curr = df_2h.iloc[curr_2h_idx-119:curr_2h_idx+1]
                        curr_2h_regime = regime_master.get_regime_2h(window_2h_curr)
                        reversal = regime_master.detect_reversal(prev_2h_regime, curr_2h_regime)
                        # LONG 포지션 + long_to_short_reversal → 청산
                        # SHORT 포지션 + short_to_long_reversal → 청산
                        should_close = False
                        if side == 'long' and reversal == 'long_to_short_reversal':
                            should_close = True
                        elif side == 'short' and reversal == 'short_to_long_reversal':
                            should_close = True

                        if should_close:
                            # 다음 1m봉 시가에 청산 (Lookahead 방지)
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
                        # regime 갱신
                        prev_2h_regime = curr_2h_regime
                except Exception:
                    pass

        # (D) SL 터치
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
        # Timeout
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


def batch_simulate_v6(
    long_signal_indices_1m: List[int],
    short_signal_indices_1m: List[int],
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
    verbose: bool = True,
) -> pd.DataFrame:
    """
    배치 시뮬레이션. 양방향 진입 + single_pos_filter.

    IN: long/short 신호 인덱스 (1m 기준)
    OUT: DataFrame
    """
    results = []
    last_exit_t_1m = -1

    # 양방향 신호를 한 리스트로 정렬
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
            })
            continue

        r = simulate_position_v6(
            sig_idx, side, df_1m, df_ob_tf, df_2h, atr_ob_tf,
            leverage=leverage, w=w, N=N,
            timeout_bars_ob_tf=timeout_bars_ob_tf,
            ob_tf_minutes=ob_tf_minutes,
            enable_2h_reversal=enable_2h_reversal,
            regime_master=regime_master,
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
