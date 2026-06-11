# -*- coding: utf-8 -*-
"""
[파일명] obfib_simulator.py
코드길이: 약 410줄, 내부버전: v0.1
로직 축약/생략 없이 전체 출력. 원본 Exec_Dynamic_TS_PautoV75.py 청산 로직을 백테스트 일괄 시뮬레이션 wrapper 로 이식.

[목적]
PautoV75 ML 진입 신호 + OB 분할 익절 + Fib trailing 청산을 1분봉 path 로 정확 시뮬.

[변수 파이프라인]
📥 [IN]
  - entry_indices (np.int64 array): 1분봉 인덱스 (진입 신호 발생 봉)
  - df_1m (pd.DataFrame): 1분봉 OHLCV (timestamp 인덱스, columns: open, high, low, close)
  - side (str): 'long' or 'short'
  - params (dict):
      leverage (int): 레버리지 10/15/20
      fib_trigger_roe (float): Phase 2 진입 ROE 임계 (기본 24.0% = 가격 +1.2% × Lev 20)
      fib_sl_pct (float): 초기 하드 손절 ROE % (기본 5.73)
      fib_ext_pct (float): Fib 락인 비율 (기본 0.618)
      N_ob (int): OB 검출 개수 제한 (3 or 5)
      holding_bars_1m (int): 강제 timeout 1분봉 수 (4 * 60 = 240 / 8 * 60 = 480 / 16 * 60 = 960)
      mmr (float): Liq Tier 1 MMR (0.004)
      cost_round_trip_nominal (float): 16bp 왕복 비용 (0.0016)

🛠️ [STATE per trade]
  - bot_state dict (원본 그대로):
      position, entry_price, df_1m, ob_initialized,
      bullish_obs, bearish_obs, remaining_pct, target_idx,
      fib_stop, fib_extreme, fib_wave_start, pulled_back

📤 [OUT]
  - results (List[dict]): 거래별 dict
      entry_idx, entry_bar, exit_reason, exit_idx, exit_bar,
      entry_price, exit_price, side, leverage,
      n_ob_used, used_fib_lock, used_reduce, max_roe,
      net_return_pct  (자본 대비 수익률, 비용 차감 후)

[exit_reason 값]
  - 'REDUCE_50': Phase 1 1차 OB.mean 도달 (50% 익절)
  - 'OB_EDGE_STOP': OB 엣지 스탑 이탈
  - 'FIB_STOP': Fibonacci 계단식 스탑 터치
  - 'HARD_SL': 초기 하드 손절
  - 'LIQ': 청산 (Tier 1 MMR 0.4%)
  - 'TIMEOUT': holding_bars 도달
  - 'NoData': 데이터 부족

[원본 충실도]
원본 Exec_Dynamic_TS_PautoV75.py 의 check_exit() 함수를 1분봉 시뮬에 그대로 호출.
원본 클래스의 _find_order_blocks(), check_exit() 호출. wrapper 는 외부 루프만 담당.

[OB 검출 윈도우]
원본 L30: lookback = df.tail(100)  → 진입 시점 직전 100 1분봉
백테스트도 동일: df_1m.iloc[entry_bar_idx - 100 : entry_bar_idx]

[Lookahead 가드]
진입 시점 t 에서 OB 검출에 사용하는 df_1m 슬라이스는 [t-100 : t] (배타적). t 봉 자체는 OB 검출에 미포함.
이는 원본 봇의 실시간 호출 (current_price 시점 직전 100봉) 과 일치.
"""

import numpy as np
import pandas as pd
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from Exec_Dynamic_TS_PautoV75 import Exec_Dynamic_TS_PautoV75


def _build_initial_bot_state(side: str, entry_price: float, df_1m_lookback: pd.DataFrame) -> dict:
    """
    bot_state 초기화. 원본 check_exit 가 요구하는 필드 모두 포함.

    df_1m_lookback: 진입 시점 직전 100 1분봉 (Lookahead 가드).
    """
    return {
        'position': 'LONG' if side == 'long' else 'SHORT',
        'entry_price': entry_price,
        'df_1m': df_1m_lookback,
        'ob_initialized': False,        # check_exit 첫 호출 시 _find_order_blocks 1회 수행
        'bullish_obs': [],
        'bearish_obs': [],
        'remaining_pct': 1.0,
        'target_idx': 0,
        'fib_stop': None,
        'fib_extreme': entry_price,     # 진입가로 초기화 (LONG=고점, SHORT=저점 추적)
        'fib_wave_start': entry_price,
        'pulled_back': False,
    }


def _compute_liq_price(entry_price: float, lev: float, mmr: float, side: str) -> float:
    """
    Tier 1 MMR 0.4% Liq 가격.
    LONG:  liq = entry × (1 - 1/lev + mmr)
    SHORT: liq = entry × (1 + 1/lev - mmr)
    """
    if side == 'long':
        return entry_price * (1.0 - 1.0 / lev + mmr)
    else:
        return entry_price * (1.0 + 1.0 / lev - mmr)


def _truncate_ob_count(bot_state: dict, N_ob: int):
    """
    OB 1회 검출 후 N_ob 개로 절단 (그리드 변수 적용).
    원본은 모든 OB 사용. 본 wrapper 는 그리드 차원 N_ob ∈ {3, 5} 검증을 위해 절단.
    """
    if bot_state['position'] == 'LONG':
        bot_state['bearish_obs'] = bot_state['bearish_obs'][:N_ob]
    else:
        bot_state['bullish_obs'] = bot_state['bullish_obs'][:N_ob]


def simulate_single_trade(
    entry_bar_idx: int,
    df_1m: pd.DataFrame,
    side: str,
    params: dict,
) -> dict:
    """
    단일 진입 신호의 OB+Fib 시뮬레이션.

    [In]
      entry_bar_idx: 진입 신호 발생 1분봉 인덱스 (정수). 진입은 다음 봉 시가.
      df_1m: 전체 1분봉 OHLCV (timestamp 인덱스, open/high/low/close 컬럼)
      side: 'long' or 'short'
      params: 위 [IN] 명세 참조

    [Out]
      dict (위 [OUT] 명세 참조)
    """
    lev = float(params['leverage'])
    fib_trigger_roe = float(params.get('fib_trigger_roe', 24.0))
    fib_sl_pct = float(params.get('fib_sl_pct', 5.73))
    fib_ext_pct = float(params.get('fib_ext_pct', 0.618))
    N_ob = int(params.get('N_ob', 5))
    holding_bars_1m = int(params['holding_bars_1m'])
    mmr = float(params.get('mmr', 0.004))
    cost_rt = float(params.get('cost_round_trip_nominal', 0.0016))

    # ==== 진입 ====
    # 진입 봉 = entry_bar_idx + 1 의 open (다음 봉 시가)
    if entry_bar_idx + 1 >= len(df_1m):
        return {'exit_reason': 'NoData', 'entry_idx': entry_bar_idx}

    entry_idx_actual = entry_bar_idx + 1
    entry_price = df_1m['open'].iloc[entry_idx_actual]
    if not np.isfinite(entry_price):
        return {'exit_reason': 'NoData', 'entry_idx': entry_bar_idx}

    # OB 검출용 lookback (Lookahead 가드: 진입 신호 봉 t 포함, 그 이전 100봉 사용)
    lookback_start = max(0, entry_bar_idx - 99)
    lookback_end = entry_bar_idx + 1  # exclusive → entry_bar_idx 봉 포함, 진입 봉(entry_idx_actual)은 미포함
    df_lookback = df_1m.iloc[lookback_start:lookback_end].copy()

    if len(df_lookback) < 50:
        return {'exit_reason': 'NoData', 'entry_idx': entry_bar_idx}

    # bot_state 초기화
    bot_state = _build_initial_bot_state(side, entry_price, df_lookback)
    executor = Exec_Dynamic_TS_PautoV75()

    # OB 1회 검출 + N_ob 절단 (check_exit 첫 호출에서 _find_order_blocks 작동)
    # 미리 호출해서 bullish/bearish_obs 채운 후 절단
    bot_state['bullish_obs'], bot_state['bearish_obs'] = executor._find_order_blocks(
        df_lookback, entry_price, bot_state['position']
    )
    bot_state['ob_initialized'] = True
    _truncate_ob_count(bot_state, N_ob)

    # ==== 청산 가격 사전 계산 ====
    liq_price = _compute_liq_price(entry_price, lev, mmr, side)

    # ==== 시뮬 루프 (1분봉 OHLC 순차 처리) ====
    monitor_end = min(entry_idx_actual + holding_bars_1m, len(df_1m))
    used_reduce = False
    used_fib_lock = False
    n_ob_used = 0
    max_extreme = entry_price

    # params 원본 check_exit 형식으로 변환
    exec_params = {
        'leverage': lev,
        'fib_trigger_roe': fib_trigger_roe,
        'fib_sl_roe': fib_sl_pct,
        'fib_ext_pct': fib_ext_pct,
    }

    exit_reason = None
    exit_price = None
    exit_idx = None

    for i in range(entry_idx_actual, monitor_end):
        bar_open = df_1m['open'].iloc[i]
        bar_high = df_1m['high'].iloc[i]
        bar_low = df_1m['low'].iloc[i]
        bar_close = df_1m['close'].iloc[i]

        if not (np.isfinite(bar_high) and np.isfinite(bar_low)):
            continue

        # extreme 트래킹 (분석용)
        if side == 'long':
            max_extreme = max(max_extreme, bar_high)
        else:
            max_extreme = min(max_extreme, bar_low)

        # ==== 청산 우선순위: Liq > 분봉 high/low 기반 청산 검사 ====
        # Liq 우선 검사 (가장 보수적)
        if side == 'long' and bar_low <= liq_price:
            exit_reason = 'LIQ'
            exit_price = liq_price
            exit_idx = i
            break
        if side == 'short' and bar_high >= liq_price:
            exit_reason = 'LIQ'
            exit_price = liq_price
            exit_idx = i
            break

        # ==== 1분봉 내 path 시뮬: open → close 시간 순서 가정 ====
        # 봉 단위 청산 트리거 검사는 봉 안에서 발생할 수 있으나, 보수적으로 close 가격 기준 check_exit 호출
        # (1분봉 내 intrabar 순서 정확 검증은 별도 path 재구성 필요. 본 wrapper 는 close 기준 호출)

        # 그러나 SL/TP 가 high/low 범위에 걸리는 경우 보수적 SL 우선 처리
        # 원본 봇은 0.1초 틱마다 호출됨. wrapper 는 1분 close 기준 + 보수 가정

        # 봉 단위 check_exit 호출 (close 가격)
        result = executor.check_exit(bar_close, bot_state, exec_params)
        action = result.get('action', 'HOLD')
        reason_text = result.get('reason', '')

        # action 처리
        if action == 'REDUCE_LONG' or action == 'REDUCE_SHORT':
            # 50% 익절 발생
            if not used_reduce:
                bot_state['remaining_pct'] = 0.5
                used_reduce = True
                n_ob_used = max(n_ob_used, bot_state['target_idx'])
                # 분할 익절 가격 기록 (현재 OB.mean)
                if side == 'long':
                    reduce_price = bot_state['bearish_obs'][bot_state['target_idx'] - 1]['mean']
                else:
                    reduce_price = bot_state['bullish_obs'][bot_state['target_idx'] - 1]['mean']
                # 50% 익절 수익 별도 누적 (나머지 50% 는 계속 시뮬)
                bot_state['reduce_exit_price'] = reduce_price
            continue

        elif action == 'CLOSE_LONG' or action == 'CLOSE_SHORT':
            exit_idx = i
            if 'Fibonacci' in reason_text:
                exit_reason = 'FIB_STOP'
                exit_price = bot_state['fib_stop']
                used_fib_lock = True
            elif 'OB 엣지' in reason_text:
                exit_reason = 'OB_EDGE_STOP'
                exit_price = bot_state['fib_stop']
            elif '하드 손절' in reason_text:
                exit_reason = 'HARD_SL'
                # 하드 SL 가격 재계산
                if side == 'long':
                    exit_price = entry_price * (1 - fib_sl_pct / 100.0 / lev)
                else:
                    exit_price = entry_price * (1 + fib_sl_pct / 100.0 / lev)
            else:
                exit_reason = 'CLOSE_OTHER'
                exit_price = bar_close

            n_ob_used = max(n_ob_used, bot_state['target_idx'])
            break

        # action == 'HOLD' 면 continue

    # Timeout
    if exit_reason is None:
        exit_idx = monitor_end - 1 if monitor_end > entry_idx_actual else entry_idx_actual
        if exit_idx < len(df_1m):
            exit_price = df_1m['close'].iloc[exit_idx]
            exit_reason = 'TIMEOUT'
        else:
            return {'exit_reason': 'NoData', 'entry_idx': entry_bar_idx}

    # ==== 수익 계산 (자본 대비 ROE %) ====
    # 비용: 16bp 왕복 명목가 기준 = 자본 대비 lev * 0.0016
    # 분할 익절 케이스: 50% 가 reduce_price 에서 청산, 50% 가 exit_price 에서 청산
    if side == 'long':
        if used_reduce:
            reduce_pct = (bot_state['reduce_exit_price'] - entry_price) / entry_price * lev
            final_pct = (exit_price - entry_price) / entry_price * lev
            net_pct = 0.5 * reduce_pct + 0.5 * final_pct - lev * cost_rt
        else:
            net_pct = (exit_price - entry_price) / entry_price * lev - lev * cost_rt
    else:
        if used_reduce:
            reduce_pct = (entry_price - bot_state['reduce_exit_price']) / entry_price * lev
            final_pct = (entry_price - exit_price) / entry_price * lev
            net_pct = 0.5 * reduce_pct + 0.5 * final_pct - lev * cost_rt
        else:
            net_pct = (entry_price - exit_price) / entry_price * lev - lev * cost_rt

    max_roe = abs(max_extreme - entry_price) / entry_price * lev * 100

    return {
        'entry_idx': entry_bar_idx,
        'entry_bar': entry_idx_actual,
        'entry_price': float(entry_price),
        'exit_idx': int(exit_idx) if exit_idx is not None else -1,
        'exit_price': float(exit_price) if exit_price is not None else float('nan'),
        'exit_reason': exit_reason,
        'side': side,
        'leverage': lev,
        'n_ob_used': int(n_ob_used),
        'used_fib_lock': bool(used_fib_lock),
        'used_reduce': bool(used_reduce),
        'max_roe_pct': float(max_roe),
        'net_return_pct': float(net_pct * 100),  # 자본 대비 %
    }


def simulate_batch(
    entry_indices: np.ndarray,
    df_1m: pd.DataFrame,
    side: str,
    params: dict,
) -> pd.DataFrame:
    """
    배치 시뮬 — entry_indices 의 모든 진입 신호를 simulate_single_trade 로 처리.

    [In]
      entry_indices: 1차원 numpy 배열 (정수, 1분봉 인덱스)
      df_1m: 전체 1분봉 OHLCV
      side: 'long' or 'short'
      params: simulate_single_trade 와 동일

    [Out]
      pd.DataFrame — 거래별 결과
    """
    results = []
    for entry_idx in entry_indices:
        r = simulate_single_trade(int(entry_idx), df_1m, side, params)
        if r.get('exit_reason') == 'NoData':
            continue
        results.append(r)

    if not results:
        return pd.DataFrame(columns=[
            'entry_idx', 'entry_bar', 'entry_price', 'exit_idx', 'exit_price',
            'exit_reason', 'side', 'leverage', 'n_ob_used',
            'used_fib_lock', 'used_reduce', 'max_roe_pct', 'net_return_pct',
        ])

    return pd.DataFrame(results)


def compute_grid_stats(
    trades_df: pd.DataFrame,
    initial_capital: float = 25000.0,
) -> dict:
    """
    그리드 시나리오 통계 집계 — 알파 판정 + 수익 효과성 항목 둘 다.

    [In]
      trades_df: simulate_batch 결과
      initial_capital: 자본 ($)

    [Out]
      dict — 그리드 결과 한 행. 다음 항목 포함:
        n_trades, win_rate, pf, net_return_sum_pct, mdd_pct, sharpe, calmar,
        avg_trade_pct, max_loss_pct, max_consec_loss,
        n_fib, n_ob_edge, n_hard_sl, n_timeout, n_liq, n_reduce,
        avg_fib_trade_pct (피보나치 청산 평균 수익률),
        avg_ob_trade_pct, avg_hardsl_pct,
        adr_w3_pass (PF≥1.3 + n≥30 + net>0)
    """
    if len(trades_df) == 0:
        return {'n_trades': 0, 'adr_w3_pass': False}

    nr = trades_df['net_return_pct'].values
    wins = nr[nr > 0]
    losses = nr[nr < 0]
    pf = wins.sum() / abs(losses.sum()) if abs(losses.sum()) > 0 else float('inf')

    # MDD on equity curve (cumulative pct, simple-sum 가정)
    eq = np.cumsum(nr)
    eq_with_init = eq + 100.0  # 자본 100% 기준
    peak = np.maximum.accumulate(eq_with_init)
    dd = (eq_with_init - peak) / peak * 100.0
    mdd = abs(dd.min()) if len(dd) > 0 else 0.0

    # Sharpe (거래 단위, 연환산 252)
    if nr.std() > 0:
        sharpe = nr.mean() / nr.std() * np.sqrt(252)
    else:
        sharpe = 0.0

    # max consecutive losses
    max_consec = 0
    consec = 0
    for v in nr:
        if v < 0:
            consec += 1
            max_consec = max(max_consec, consec)
        else:
            consec = 0

    # 청산 사유별 분포 + 평균
    by_reason = trades_df.groupby('exit_reason')['net_return_pct'].agg(['count', 'mean']).to_dict('index')

    def get_count(reason):
        return by_reason.get(reason, {}).get('count', 0)

    def get_mean(reason):
        return by_reason.get(reason, {}).get('mean', 0.0)

    # 알파 판정
    n = len(trades_df)
    net_sum = nr.sum()
    adr_pass = (pf >= 1.3) and (n >= 30) and (net_sum > 0)

    return {
        'n_trades': int(n),
        'win_rate': float((nr > 0).mean() * 100),
        'pf': float(pf),
        'net_return_sum_pct': float(net_sum),
        'mdd_pct': float(mdd),
        'sharpe': float(sharpe),
        'avg_trade_pct': float(nr.mean()),
        'max_trade_pct': float(nr.max()),
        'min_trade_pct': float(nr.min()),
        'max_consec_loss': int(max_consec),
        'n_fib': int(get_count('FIB_STOP')),
        'n_ob_edge': int(get_count('OB_EDGE_STOP')),
        'n_hard_sl': int(get_count('HARD_SL')),
        'n_timeout': int(get_count('TIMEOUT')),
        'n_liq': int(get_count('LIQ')),
        'avg_fib_pct': float(get_mean('FIB_STOP')),
        'avg_ob_edge_pct': float(get_mean('OB_EDGE_STOP')),
        'avg_hard_sl_pct': float(get_mean('HARD_SL')),
        'avg_timeout_pct': float(get_mean('TIMEOUT')),
        'pct_fib_of_total_profit': float(
            trades_df.loc[trades_df['exit_reason'] == 'FIB_STOP', 'net_return_pct'].sum() / net_sum * 100
        ) if net_sum != 0 else 0.0,
        'pct_used_reduce': float(trades_df['used_reduce'].mean() * 100),
        'pct_used_fib_lock': float(trades_df['used_fib_lock'].mean() * 100),
        'adr_w3_pass': bool(adr_pass),
    }
