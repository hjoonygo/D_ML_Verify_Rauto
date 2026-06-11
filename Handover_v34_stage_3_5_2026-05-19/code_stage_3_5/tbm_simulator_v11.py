# -*- coding: utf-8 -*-
"""
[파일명] tbm_simulator_v11.py
코드길이: 약 920줄, 내부버전명: v11.0 (stage_3_5_regime_policy), 로직 축약/생략 없이 전체 출력

[목적]
  Stage 3.5 시뮬레이터 — regime별 차별 정책 적용
  
[v10 -> v11 변경]
  * 신규: regime_at_entry 인자 (외부에서 사전 계산해 전달)
  * 신규: uptrend long 진입 게이트 차단 (exit_reason='regime_blocked_uptrend_long')
  * 신규: hivol_range long에 대해 SL_MAX/TIMEOUT을 인자로 전달
        - 기본: 500bp / 18H (사용자 결정)
  * 신규: 그 외 regime은 기존 v10 정책 (SL 동적 ATR기반 / TIMEOUT 4H)
  * 신규: enable_regime_policy 토글 (False면 v10 동작과 동일, baseline 비교용)
  * 유지: compute_dynamic_sl, OB SL vs ATR SL 비교, 3단계 스텝업

[상수 정의]
  COST_NOMINAL = 0.0016 (왕복 수수료)
  SL_GATE = 0.0032 (32bp), TP_GATE = 0.0048 (48bp), RR_MIN = 1.5
  
  # v10 유동 SL 파라미터
  SL_MIN = 0.0032, SL_MAX_DEFAULT = 0.0150
  ATR_BUCKET_LOW = 0.0025, ATR_BUCKET_HIGH = 0.0045
  MULT_LOWVOL = 3.5, MULT_MIDVOL = 3.0, MULT_HIGHVOL = 2.0
  
  # v11 신규 — hivol_range long 전용 정책
  HIVOL_LONG_SL_MAX_DEFAULT = 0.0500 (500bp, 휩쏘 견디기)
  HIVOL_LONG_TIMEOUT_DEFAULT = 1080 (18H, 가상 시뮬 sweet spot)
  
  # 3단계 스텝업 (v10과 동일)
  STEP1_TRIGGER = 0.0100, STEP1_RATIO = 0.5
  STEP2_TRIGGER = 0.01618, STEP2_RATIO = 0.618
  STEP3_TRIGGER = 0.01963, STEP3_RATIO = 0.764
  
  TIMEOUT_MINUTES_DEFAULT = 240 (4H, 기본)

[함수 In/Out]
  compute_atr(...), compute_dynamic_sl(...) — v10과 동일
  
  resolve_regime_policy(regime, side, enable_regime_policy, 
                         hivol_long_sl_max, hivol_long_timeout) -> Dict (v11 신규)
    IN: regime 문자열('uptrend'/'downtrend'/'hivol_range'/'lovol_range'), side('long'/'short'),
        enable_regime_policy(bool), hivol_long_sl_max(float), hivol_long_timeout(int)
    OUT: dict {
      'block_entry': bool,
      'sl_max': float (이 거래용 SL_MAX),
      'timeout_min': int (이 거래용 timeout),
      'policy_label': str (디버깅),
    }
  
  check_entry_gate(...) (v10과 동일)
  
  simulate_position_v11(...) -> Dict
    IN: v10 시그니처 + regime_at_entry, hivol_long_sl_max, hivol_long_timeout, enable_regime_policy
    OUT: 거래 결과 dict (v11 신규 컬럼 포함: regime_at_entry, policy_label, timeout_applied)
  
  batch_simulate_v11(...) -> pd.DataFrame
    IN: v10 시그니처 + regime_per_signal 배열 + 위 인자들
    OUT: DataFrame
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd
from typing import Optional, List, Dict, Any, Tuple

from ob_provider_v2 import OB, get_levels_above, get_levels_below


# ============================================================
# 상수 — Stage 3.5 regime policy
# ============================================================
COST_NOMINAL = 0.0016

# 진입 게이트
SL_GATE = 0.0032
TP_GATE = 0.0048
RR_MIN = 1.5

# v10 유동 SL 파라미터 (그대로)
SL_MIN = 0.0032
SL_MAX_DEFAULT = 0.0150
ATR_BUCKET_LOW = 0.0025
ATR_BUCKET_HIGH = 0.0045
MULT_LOWVOL = 3.5
MULT_MIDVOL = 3.0
MULT_HIGHVOL = 2.0

# v11 신규 — hivol_range long 전용
HIVOL_LONG_SL_MAX_DEFAULT = 0.0500   # 500bp (사용자 결정)
HIVOL_LONG_TIMEOUT_DEFAULT = 1080    # 18H (가상 시뮬 sweet spot)

# 3단계 스텝업
STEP1_TRIGGER = 0.0100
STEP1_RATIO = 0.5
STEP2_TRIGGER = 0.01618
STEP2_RATIO = 0.618
STEP3_TRIGGER = 0.01963
STEP3_RATIO = 0.764

# Timeout 기본 (다른 regime용)
TIMEOUT_MINUTES_DEFAULT = 240  # 4H

# 호환성 alias (기존 코드에서 TIMEOUT_MINUTES 참조)
TIMEOUT_MINUTES = TIMEOUT_MINUTES_DEFAULT

# ATR (regime 판단용 유지)
ATR_PERIOD = 20


def compute_atr(high, low, close, period=ATR_PERIOD):
    """Wilder ATR. 3항 TR. NaN 처리."""
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


def compute_dynamic_sl(
    atr_pct_at_entry: float,
    sl_max: float = SL_MAX_DEFAULT,
) -> Tuple[float, float]:
    """
    v10 신규 — 진입 시점 ATR_pct에 따라 동적 SL 거리 계산.
    
    IN:
      atr_pct_at_entry: 진입 시점의 15m ATR_pct (e.g. 0.0033 = 0.33%)
      sl_max: SL 절대 상한 (그리드: 0.012/0.015/0.018)
    OUT:
      (sl_dist, multiplier_used)
        sl_dist: float — 최종 SL 거리 (32bp ~ sl_max bp)
        multiplier_used: float — 어떤 배수가 적용됐는지 (디버깅용)
    
    [로직]
      1. ATR_pct 구간별 multiplier 결정:
         < 0.25% → 3.5 (저변동, 여유)
         0.25%~0.45% → 3.0 (중변동, 표준)
         ≥ 0.45% → 2.0 (고변동, 좁게)
      2. sl_raw = atr_pct × multiplier
      3. SL_MIN(32bp) ~ sl_max로 클램프
    
    [NaN 처리] atr_pct가 NaN/0/inf면 보수적으로 sl_max 적용
    """
    # 비정상 입력 가드
    if not np.isfinite(atr_pct_at_entry) or atr_pct_at_entry <= 0:
        return sl_max, np.nan  # 보수적
    
    # multiplier 선택
    if atr_pct_at_entry < ATR_BUCKET_LOW:
        multiplier = MULT_LOWVOL
    elif atr_pct_at_entry < ATR_BUCKET_HIGH:
        multiplier = MULT_MIDVOL
    else:
        multiplier = MULT_HIGHVOL
    
    sl_raw = atr_pct_at_entry * multiplier
    
    # 상하한 클램프
    sl_dist = max(SL_MIN, min(sl_max, sl_raw))
    
    return sl_dist, multiplier


def resolve_regime_policy(
    regime: str,
    side: str,
    enable_regime_policy: bool = True,
    hivol_long_sl_max: float = HIVOL_LONG_SL_MAX_DEFAULT,
    hivol_long_timeout: int = HIVOL_LONG_TIMEOUT_DEFAULT,
    default_sl_max: float = SL_MAX_DEFAULT,
    default_timeout: int = TIMEOUT_MINUTES_DEFAULT,
) -> Dict[str, Any]:
    """
    v11 신규 — regime별 차별 정책 해석.
    
    IN:
      regime: 'uptrend' / 'downtrend' / 'hivol_range' / 'lovol_range' / 'unknown' / None
      side: 'long' / 'short'
      enable_regime_policy: False면 모든 거래 default 정책 (v10 동작)
      hivol_long_sl_max: hivol_range long에 적용할 SL_MAX
      hivol_long_timeout: hivol_range long에 적용할 timeout (분)
      default_sl_max: 기본 SL_MAX (다른 regime용)
      default_timeout: 기본 timeout (분)
    
    OUT:
      dict {
        'block_entry': bool — True면 진입 거부 (uptrend long)
        'sl_max': float — 이 거래에 적용할 SL_MAX
        'timeout_min': int — 이 거래에 적용할 timeout (분)
        'policy_label': str — 디버깅용
      }
    
    [정책]
      - enable_regime_policy=False: 모든 거래에 default 정책 (v10 동작)
      - uptrend + long: 진입 거부
      - hivol_range + long: SL=500bp, timeout=18H
      - 그 외: default (SL=150bp, timeout=4H)
    """
    if not enable_regime_policy:
        return {
            'block_entry': False,
            'sl_max': default_sl_max,
            'timeout_min': default_timeout,
            'policy_label': 'v10_default',
        }
    
    # uptrend long 진입 차단
    if regime == 'uptrend' and side == 'long':
        return {
            'block_entry': True,
            'sl_max': default_sl_max,
            'timeout_min': default_timeout,
            'policy_label': 'uptrend_long_blocked',
        }
    
    # hivol_range long 특별 정책
    if regime == 'hivol_range' and side == 'long':
        return {
            'block_entry': False,
            'sl_max': hivol_long_sl_max,
            'timeout_min': hivol_long_timeout,
            'policy_label': f'hivol_long_sl{int(hivol_long_sl_max*10000)}bp_to{hivol_long_timeout}min',
        }
    
    # 그 외: 기본 정책
    return {
        'block_entry': False,
        'sl_max': default_sl_max,
        'timeout_min': default_timeout,
        'policy_label': 'default',
    }


def check_entry_gate(
    candidate_price: float,
    side: str,
    df_ob_tf: pd.DataFrame,
    ob_tf_idx: int,
    w: int,
    N: int,
    atr_pct_at_entry: float = None,
    sl_max: float = SL_MAX_DEFAULT,
) -> Dict[str, Any]:
    """
    v10 — 진입 게이트 검사. 유동 SL 적용.
    
    IN:
      candidate_price: 검사할 후보 진입가
      side: 'long' / 'short'
      df_ob_tf: OB TF DataFrame
      ob_tf_idx: 현재 OB TF 인덱스
      w: OB pivot window
      N: OB 검색 개수
      atr_pct_at_entry: 진입 시점 ATR_pct (v10 신규, 필수)
      sl_max: SL 절대 상한 (v10 신규, 그리드)
    
    OUT:
      dict {
        'pass': bool,
        'fail_reason': str or None,
        'sl_dist_effective': float — 실제 SL 거리 (OB SL vs ATR SL 중 작은 쪽),
        'ob_tp_dist': float,
        'ob_sl_dist': float — OB SL 원본 거리,
        'atr_sl_dist': float — ATR 기반 SL 거리 (v10 신규),
        'sl_method': str — 'ob_natural' (OB SL 더 가까움) / 'atr_dynamic' (ATR SL 더 가까움),
        'multiplier_used': float — ATR multiplier (v10 신규),
        'rr': float,
        'ob_tp_price': float,
        'ob_sl_price': float,
      }
    """
    res = {
        'pass': False, 'fail_reason': None,
        'sl_dist_effective': None, 'ob_tp_dist': None, 'ob_sl_dist': None,
        'atr_sl_dist': None, 'sl_method': None, 'multiplier_used': None,
        'rr': None,
        'ob_tp_price': None, 'ob_sl_price': None,
    }
    
    # ATR SL 사전 계산 (atr_pct이 없으면 SL_MAX 사용)
    if atr_pct_at_entry is None or not np.isfinite(atr_pct_at_entry) or atr_pct_at_entry <= 0:
        atr_sl_dist = sl_max
        multiplier_used = np.nan
    else:
        atr_sl_dist, multiplier_used = compute_dynamic_sl(atr_pct_at_entry, sl_max)
    res['atr_sl_dist'] = atr_sl_dist
    res['multiplier_used'] = multiplier_used
    
    if side == 'long':
        tp_obs = get_levels_above(ob_tf_idx, candidate_price, N, df_ob_tf, w)
        sl_obs_list = get_levels_below(ob_tf_idx, candidate_price, 1, df_ob_tf, w)
    else:
        tp_obs = get_levels_below(ob_tf_idx, candidate_price, N, df_ob_tf, w)
        sl_obs_list = get_levels_above(ob_tf_idx, candidate_price, 1, df_ob_tf, w)
    
    if len(tp_obs) == 0:
        res['fail_reason'] = 'no_tp_ob'
        return res
    
    if side == 'long':
        ob_tp_price = float(tp_obs[0].top)
        ob_tp_dist = (ob_tp_price - candidate_price) / candidate_price
    else:
        ob_tp_price = float(tp_obs[0].bottom)
        ob_tp_dist = (candidate_price - ob_tp_price) / candidate_price
    res['ob_tp_price'] = ob_tp_price
    res['ob_tp_dist'] = ob_tp_dist
    
    # OB SL 거리 계산 (있으면 사용, 없으면 ATR만 사용)
    if len(sl_obs_list) == 0:
        # OB SL 없음 → ATR SL만 사용
        ob_sl_price = None
        ob_sl_dist = float('inf')  # 비교 시 ATR SL이 항상 작음
    else:
        if side == 'long':
            ob_sl_price = float(sl_obs_list[0].bottom)
            ob_sl_dist = (candidate_price - ob_sl_price) / candidate_price
        else:
            ob_sl_price = float(sl_obs_list[0].top)
            ob_sl_dist = (ob_sl_price - candidate_price) / candidate_price
    res['ob_sl_price'] = ob_sl_price
    res['ob_sl_dist'] = ob_sl_dist if ob_sl_dist != float('inf') else None
    
    # 유동 SL 결정: OB SL vs ATR SL 중 더 작은 쪽 (보수적, 사용자 결정 Q2:A)
    if ob_sl_dist < atr_sl_dist:
        sl_dist_effective = ob_sl_dist
        sl_method = 'ob_natural'
    else:
        sl_dist_effective = atr_sl_dist
        sl_method = 'atr_dynamic'
    res['sl_dist_effective'] = sl_dist_effective
    res['sl_method'] = sl_method
    
    # 1) SL 게이트 — 최종 SL이 32bp 이상
    if sl_dist_effective < SL_GATE:
        res['fail_reason'] = f'sl_gate_fail (sl={sl_dist_effective:.5f}<{SL_GATE})'
        return res
    
    # 2) TP 게이트 — 정상 48bp만 사용 (클램프 케이스 161.8bp 게이트 제거)
    if ob_tp_dist < TP_GATE:
        res['fail_reason'] = f'tp_gate_fail (tp={ob_tp_dist:.5f}<{TP_GATE})'
        return res
    
    # 3) RR 게이트
    rr = ob_tp_dist / max(sl_dist_effective, 1e-8)
    res['rr'] = rr
    if rr < RR_MIN:
        res['fail_reason'] = f'rr_gate_fail (rr={rr:.3f}<{RR_MIN})'
        return res
    
    res['pass'] = True
    return res


def compute_step_sl(side: str, entry_price: float, extreme: float, step_active: int) -> float:
    """
    현재 활성 단계와 극값에 따라 새 SL 가격 계산.
    
    IN:
      side: 'long' / 'short'
      entry_price: 진입가
      extreme: long이면 현재까지 고점, short이면 저점
      step_active: 1 / 2 / 3
    OUT:
      new_sl_price: 새 SL 가격
    """
    if step_active == 1:
        ratio = STEP1_RATIO
    elif step_active == 2:
        ratio = STEP2_RATIO
    elif step_active == 3:
        ratio = STEP3_RATIO
    else:
        return None
    
    if side == 'long':
        # SL = entry + (high - entry) × ratio
        new_sl = entry_price + (extreme - entry_price) * ratio
    else:
        # SL = entry - (entry - low) × ratio
        new_sl = entry_price - (entry_price - extreme) * ratio
    return new_sl


def simulate_position_v11(
    entry_signal_idx_1m: int,
    side: str,
    df_1m: pd.DataFrame,
    df_ob_tf: pd.DataFrame,
    df_2h: pd.DataFrame,
    atr_ob_tf: np.ndarray,
    leverage: int = 10,
    w: int = 5,
    N: int = 5,
    ob_tf_minutes: int = 60,
    enable_2h_reversal: bool = True,
    regime_master = None,
    enable_wait_entry: bool = True,
    wait_timeout_minutes: int = 120,
    other_side_signals: set = None,
    same_side_signals: set = None,
    atr_pct_at_entry: float = None,
    sl_max: float = SL_MAX_DEFAULT,  # 호환성용 (v11에서는 regime_policy로 결정됨)
    # v11 신규 인자
    regime_at_entry: str = None,
    enable_regime_policy: bool = True,
    hivol_long_sl_max: float = HIVOL_LONG_SL_MAX_DEFAULT,
    hivol_long_timeout: int = HIVOL_LONG_TIMEOUT_DEFAULT,
) -> Dict[str, Any]:
    """
    v11 — 한 신호에 대한 시뮬레이션 1회. regime별 차별 정책 적용.

    IN:
      (v10 IN과 동일) + 
      regime_at_entry: 진입 시점 regime ('uptrend'/'downtrend'/'hivol_range'/'lovol_range')
      enable_regime_policy: True면 regime 정책 적용, False면 v10 동작 (baseline)
      hivol_long_sl_max: hivol_range long용 SL_MAX
      hivol_long_timeout: hivol_range long용 timeout
    
    OUT:
      result dict
      v11 신규 컬럼: regime_at_entry, policy_label, timeout_applied
    """
    # v11 — regime 정책 해석 (가장 먼저)
    policy = resolve_regime_policy(
        regime=regime_at_entry, side=side,
        enable_regime_policy=enable_regime_policy,
        hivol_long_sl_max=hivol_long_sl_max,
        hivol_long_timeout=hivol_long_timeout,
        default_sl_max=sl_max,  # 외부에서 전달된 sl_max를 기본값으로
        default_timeout=TIMEOUT_MINUTES_DEFAULT,
    )
    
    # 결과 dict 초기화 (v11 신규 컬럼 포함)
    result = {
        'entry_signal_idx_1m': entry_signal_idx_1m, 'side': side,
        'exit_reason': None, 'price_roe': 0.0, 'net_return': 0.0,
        'step_active_max': 0, 'n_ob_used': 0, 'bars_held_1m': 0,
        'gate_fail_reason': None,
        'entry_t': None, 'entry_price': None, 'exit_price': None, 'exit_t': None,
        'initial_sl': None, 'initial_sl_dist': None,
        'ob_tp_dist': None,
        'sl_clamped': False,
        'final_stop': None, 'final_step': 0,
        'leverage': leverage,
        'reversal_2h_triggered': False,
        'rr_at_entry': None,
        'wait_minutes': 0,
        # v10 컬럼
        'atr_pct_at_entry': atr_pct_at_entry,
        'sl_method': None,
        'multiplier_used': None,
        'atr_sl_dist': None,
        'ob_sl_dist': None,
        'sl_max_grid': policy['sl_max'],
        # v11 신규 컬럼
        'regime_at_entry': regime_at_entry,
        'policy_label': policy['policy_label'],
        'timeout_applied': policy['timeout_min'],
    }
    
    # v11 — uptrend long 즉시 차단 (cost도 차감 안 함, 진입 자체가 거부됨)
    if policy['block_entry']:
        result['exit_reason'] = 'regime_blocked'
        result['gate_fail_reason'] = policy['policy_label']
        result['net_return'] = 0.0  # 진입 자체 안 했으므로 비용 0
        return result
    
    # 이 거래에 적용할 sl_max와 timeout
    sl_max_this_trade = policy['sl_max']
    timeout_this_trade = policy['timeout_min']
    
    # 비용 차감 (진입 시작)
    result['net_return'] = -COST_NOMINAL

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
    # 임시 저장 (대기 로직에서 변경 가능)
    result['entry_t'] = entry_ts
    result['entry_price'] = entry_price

    # ========== 대기 진입 로직 + 게이트 검사 통합 ==========
    # 진입 시작 후보 시점 entry_t_1m에서 시작.
    # 게이트 통과 시 즉시 진입, 미달 시 wait_timeout_minutes 동안 매 1m봉마다 재검사.
    # 대기 중 같은 방향 신호 없으면 (=ML 신호 사라짐) 취소.
    # 대기 중 반대 방향 신호 나오면 취소 (새 신호로 갱신은 상위 batch에서 처리).
    
    wait_minutes = 0
    found_entry = False
    actual_entry_t_1m = entry_t_1m  # 실제 진입할 1m 인덱스 (대기 후 변경 가능)
    actual_entry_price = entry_price
    actual_entry_ts = entry_ts
    gate_check = None
    n_wait_attempts = 0
    
    while wait_minutes <= (wait_timeout_minutes if enable_wait_entry else 0):
        # 현재 후보 시점의 가격
        if actual_entry_t_1m >= n_1m:
            result['exit_reason'] = 'wait_timeout_no_data'
            return result
        
        actual_entry_price = float(df_1m['open'].iloc[actual_entry_t_1m])
        if not np.isfinite(actual_entry_price) or actual_entry_price <= 0:
            actual_entry_t_1m += 1
            wait_minutes += 1
            continue
        actual_entry_ts = df_1m.index[actual_entry_t_1m]
        
        # OB TF 인덱스 갱신
        try:
            current_ob_tf_idx = df_ob_tf.index.searchsorted(actual_entry_ts, side='right') - 1
        except Exception:
            result['exit_reason'] = 'no_ob_tf_idx'
            return result
        if current_ob_tf_idx < 0 or current_ob_tf_idx >= len(df_ob_tf):
            result['exit_reason'] = 'no_ob_tf_idx'
            return result
        
        # 게이트 검사
        gate_check = check_entry_gate(
            candidate_price=actual_entry_price,
            side=side,
            df_ob_tf=df_ob_tf,
            ob_tf_idx=current_ob_tf_idx,
            w=w, N=N,
            atr_pct_at_entry=atr_pct_at_entry,
            sl_max=sl_max_this_trade,   # ★ v11 — regime 정책 적용된 SL_MAX
        )
        n_wait_attempts += 1
        
        if gate_check['pass']:
            found_entry = True
            break
        
        # 게이트 미달 — 대기 진행
        if not enable_wait_entry:
            # 대기 안 함 — 즉시 실패
            break
        
        # 대기 중 ML 신호 확인 (옵션 — 신호 집합이 주어지면)
        # 신호는 일반적으로 ML wrapper에서 추출한 시간 인덱스이므로,
        # 현재 시점에 같은 방향 신호가 없으면 ML 신호 사라진 것으로 간주
        if same_side_signals is not None:
            # 현재 시점 또는 인접 ±3분에 같은 방향 신호 있는지 확인 (느슨한 확인)
            if not any((actual_entry_t_1m - 3 <= s <= actual_entry_t_1m + 3) for s in same_side_signals):
                # 같은 방향 신호 없음 — 대기 취소
                result['exit_reason'] = 'wait_cancel_no_signal'
                result['gate_fail_reason'] = f'wait_cancel: no same-side signal at t={actual_entry_t_1m}, attempts={n_wait_attempts}'
                return result
        
        if other_side_signals is not None:
            # 현재 시점에 반대 방향 신호가 새로 나오면 대기 취소
            if any((actual_entry_t_1m - 1 <= s <= actual_entry_t_1m + 1) for s in other_side_signals):
                result['exit_reason'] = 'wait_cancel_opposite_signal'
                result['gate_fail_reason'] = f'wait_cancel: opposite signal at t={actual_entry_t_1m}'
                return result
        
        # 다음 1m봉으로 대기 진행
        actual_entry_t_1m += 1
        wait_minutes += 1
    
    if not found_entry:
        # 대기 타임아웃
        result['exit_reason'] = 'wait_timeout'
        result['gate_fail_reason'] = gate_check.get('fail_reason') if gate_check else 'unknown'
        result['bars_held_1m'] = wait_minutes
        return result
    
    # ============ 진입 확정 ============
    # 대기 후 진입 시점으로 update
    entry_t_1m = actual_entry_t_1m
    entry_price = actual_entry_price
    entry_ts = actual_entry_ts
    result['entry_t'] = entry_ts
    result['entry_price'] = entry_price
    
    # 게이트 검사 결과 활용
    sl_dist_effective = gate_check['sl_dist_effective']
    ob_tp_dist = gate_check['ob_tp_dist']
    ob_sl_dist = gate_check['ob_sl_dist']
    atr_sl_dist = gate_check['atr_sl_dist']
    sl_method = gate_check['sl_method']
    multiplier_used = gate_check['multiplier_used']
    rr = gate_check['rr']
    
    result['initial_sl_dist'] = sl_dist_effective
    result['sl_clamped'] = False  # v10에서는 항상 False (호환성)
    result['rr_at_entry'] = rr
    result['ob_tp_dist'] = ob_tp_dist
    result['ob_sl_dist'] = ob_sl_dist
    result['atr_sl_dist'] = atr_sl_dist
    result['sl_method'] = sl_method
    result['multiplier_used'] = multiplier_used
    result['wait_minutes'] = wait_minutes
    
    if side == 'long':
        initial_sl = entry_price * (1 - sl_dist_effective)
    else:
        initial_sl = entry_price * (1 + sl_dist_effective)
    result['initial_sl'] = initial_sl

    # ========== 진입 후 상태 변수 초기화 ==========
    stop_line = initial_sl  # 현재 활성 SL
    step_active = 0          # 0=아직 발동 안 함, 1/2/3=발동 단계
    
    # v10: 클램프 케이스 없으므로 STEP1 트리거 일원화 (항상 STEP1_TRIGGER = 100bp)
    step1_trigger_for_this_trade = STEP1_TRIGGER
    
    # 극값 추적
    if side == 'long':
        extreme = entry_price  # 고점 추적
    else:
        extreme = entry_price  # 저점 추적
    
    # 1m path 확보 (v11: timeout_this_trade 만큼 — regime 정책 반영)
    end_ts = entry_ts + pd.Timedelta(minutes=timeout_this_trade)
    try:
        path = df_1m.loc[entry_ts:end_ts]
    except KeyError:
        result['exit_reason'] = 'no_1m_path'
        result['final_stop'] = stop_line
        return result

    if len(path) == 0:
        result['exit_reason'] = 'no_1m_path'
        return result

    # 2h reversal 감지 준비
    prev_2h_regime = None
    if enable_2h_reversal and regime_master is not None and df_2h is not None and len(df_2h) >= 120:
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
        c = closes_1m[k]
        ts = path_index[k]

        # (1) SL 발동 체크 (초기 SL 또는 스텝업 SL)
        if side == 'long':
            sl_hit = l <= stop_line
        else:
            sl_hit = h >= stop_line
        
        if sl_hit:
            exit_price = stop_line  # SL 가격에 청산 (지정가 가정)
            price_roe = (exit_price - entry_price) / entry_price if side == 'long' else (entry_price - exit_price) / entry_price
            
            if step_active == 0:
                result['exit_reason'] = 'initial_sl'  # 초기 SL 발동
            else:
                result['exit_reason'] = f'step{step_active}_sl'  # 스텝업 SL 발동
            
            result['exit_price'] = exit_price
            result['exit_t'] = ts
            result['price_roe'] = price_roe
            result['net_return'] = price_roe - COST_NOMINAL
            result['step_active_max'] = step_active
            result['bars_held_1m'] = k + 1
            result['final_stop'] = stop_line
            result['final_step'] = step_active
            exit_set = True
            break

        # (2) 극값 갱신
        if side == 'long':
            if h > extreme:
                extreme = h
        else:
            if l < extreme:
                extreme = l

        # (3) 단계 발동 / 승격 체크
        # 진입가 대비 현재 극값의 유리한 이동 거리
        if side == 'long':
            favorable_dist = (extreme - entry_price) / entry_price
        else:
            favorable_dist = (entry_price - extreme) / entry_price
        
        # 단계 승격 (강등 없음 — 한 방향만)
        new_step = step_active
        if favorable_dist >= STEP3_TRIGGER and step_active < 3:
            new_step = 3
        elif favorable_dist >= STEP2_TRIGGER and step_active < 2:
            new_step = 2
        elif favorable_dist >= step1_trigger_for_this_trade and step_active < 1:
            new_step = 1
        
        # 단계 변경 또는 고점 갱신 시 SL 재계산
        if new_step > step_active:
            step_active = new_step
            new_sl = compute_step_sl(side, entry_price, extreme, step_active)
            if new_sl is not None:
                # SL은 한 방향으로만 (long은 위로만, short은 아래로만)
                if side == 'long':
                    stop_line = max(stop_line, new_sl)
                else:
                    stop_line = min(stop_line, new_sl)
        elif step_active >= 1:
            # 같은 단계 내에서 극값 갱신 시 SL 재계산
            new_sl = compute_step_sl(side, entry_price, extreme, step_active)
            if new_sl is not None:
                if side == 'long':
                    stop_line = max(stop_line, new_sl)
                else:
                    stop_line = min(stop_line, new_sl)

        # (4) 2h reversal 체크 (선택적)
        if enable_2h_reversal and regime_master is not None and df_2h is not None and prev_2h_regime is not None:
            try:
                # 매 30분마다 체크 (계산 비용 절감)
                if k > 0 and k % 30 == 0:
                    current_2h_idx = df_2h.index.searchsorted(ts, side='right') - 1
                    if current_2h_idx >= 120:
                        window_2h = df_2h.iloc[current_2h_idx-119:current_2h_idx+1]
                        current_2h_regime = regime_master.get_regime_2h(window_2h)
                        reversal = regime_master.detect_reversal(prev_2h_regime, current_2h_regime)
                        
                        should_exit = False
                        if side == 'long' and reversal == 'long_to_short_reversal':
                            should_exit = True
                        elif side == 'short' and reversal == 'short_to_long_reversal':
                            should_exit = True
                        
                        if should_exit:
                            exit_price = c
                            price_roe = (exit_price - entry_price) / entry_price if side == 'long' else (entry_price - exit_price) / entry_price
                            result['exit_reason'] = 'reversal_2h'
                            result['exit_price'] = exit_price
                            result['exit_t'] = ts
                            result['price_roe'] = price_roe
                            result['net_return'] = price_roe - COST_NOMINAL
                            result['step_active_max'] = step_active
                            result['bars_held_1m'] = k + 1
                            result['final_stop'] = stop_line
                            result['final_step'] = step_active
                            result['reversal_2h_triggered'] = True
                            exit_set = True
                            break
                        prev_2h_regime = current_2h_regime
            except Exception:
                pass

    # ========== timeout 청산 처리 (v11: regime 정책 반영) ==========
    if not exit_set:
        # timeout 경과. exit_reason은 timeout_this_trade에 따라 동적
        last_close = float(closes_1m[-1])
        price_roe = (last_close - entry_price) / entry_price if side == 'long' else (entry_price - last_close) / entry_price
        
        # exit_reason 명명: 기본은 timeout_4h, hivol long(18H 등)이면 timeout_18h 등
        timeout_hours = timeout_this_trade // 60
        if step_active >= 1:
            result['exit_reason'] = 'timeout_step_active'
        else:
            # v11: timeout_4h (기존 호환) / timeout_18h (hivol_range long)
            if timeout_this_trade == 240:
                result['exit_reason'] = 'timeout_4h'
            else:
                result['exit_reason'] = f'timeout_{timeout_hours}h'
        
        result['exit_price'] = last_close
        result['exit_t'] = path_index[-1]
        result['price_roe'] = price_roe
        result['net_return'] = price_roe - COST_NOMINAL
        result['step_active_max'] = step_active
        result['bars_held_1m'] = n_path
        result['final_stop'] = stop_line
        result['final_step'] = step_active

    return result


def batch_simulate_v11(
    long_signal_indices_1m: List[int],
    short_signal_indices_1m: List[int],
    df_1m: pd.DataFrame,
    df_ob_tf: pd.DataFrame,
    df_2h: pd.DataFrame,
    atr_ob_tf: np.ndarray,
    atr_15m_pct_per_1m: np.ndarray,
    regime_per_1m: np.ndarray,         # ★ v11 신규 — 1m봉별 regime
    sl_max: float = SL_MAX_DEFAULT,
    leverage: int = 10,
    w: int = 5,
    N: int = 5,
    ob_tf_minutes: int = 60,
    enable_2h_reversal: bool = True,
    regime_master = None,
    enable_wait_entry: bool = True,
    wait_timeout_minutes: int = 120,
    verbose: bool = True,
    # v11 신규
    enable_regime_policy: bool = True,
    hivol_long_sl_max: float = HIVOL_LONG_SL_MAX_DEFAULT,
    hivol_long_timeout: int = HIVOL_LONG_TIMEOUT_DEFAULT,
) -> pd.DataFrame:
    """
    v11 배치 시뮬레이션. regime별 차별 정책 적용.
    
    IN: (v10 IN과 동일) +
      regime_per_1m: 1m봉별 regime 배열 (외부에서 사전 계산, lookahead 차단)
      enable_regime_policy: True면 regime 정책 적용
      hivol_long_sl_max: hivol_range long용 SL_MAX
      hivol_long_timeout: hivol_range long용 timeout (분)
    OUT:
      DataFrame (v11 신규 컬럼 포함)
    """
    results = []
    last_exit_t_1m = -1

    long_set = set(long_signal_indices_1m)
    short_set = set(short_signal_indices_1m)
    
    all_signals = []
    for s in long_signal_indices_1m:
        all_signals.append((s, 'long'))
    for s in short_signal_indices_1m:
        all_signals.append((s, 'short'))
    all_signals.sort(key=lambda x: x[0])

    n_total = len(all_signals)
    n_atr = len(atr_15m_pct_per_1m)
    n_regime = len(regime_per_1m)
    
    for i, (sig_idx, side) in enumerate(all_signals):
        if verbose and i % 500 == 0:
            print(f"    sim {i}/{n_total}…")

        # 단일 포지션 제약
        if sig_idx <= last_exit_t_1m:
            results.append({
                'entry_signal_idx_1m': sig_idx, 'side': side,
                'exit_reason': 'blocked_single_pos',
                'price_roe': 0.0, 'net_return': 0.0,
                'step_active_max': 0, 'n_ob_used': 0, 'bars_held_1m': 0,
                'gate_fail_reason': None,
                'entry_t': None, 'entry_price': None,
                'exit_price': None, 'exit_t': None,
                'initial_sl': None, 'initial_sl_dist': None,
                'ob_tp_dist': None, 'sl_clamped': False,
                'final_stop': None, 'final_step': 0,
                'leverage': leverage,
                'reversal_2h_triggered': False,
                'rr_at_entry': None,
                'wait_minutes': 0,
                # v10 신규
                'atr_pct_at_entry': None,
                'sl_method': None,
                'multiplier_used': None,
                'atr_sl_dist': None,
                'ob_sl_dist': None,
                'sl_max_grid': sl_max,
                # v11 신규
                'regime_at_entry': None,
                'policy_label': 'blocked_single_pos',
                'timeout_applied': None,
            })
            continue

        if side == 'long':
            same_side = long_set
            other_side = short_set
        else:
            same_side = short_set
            other_side = long_set

        entry_t_1m = sig_idx + 1
        # ATR 진입 시점
        if 0 <= entry_t_1m < n_atr:
            atr_at_entry = float(atr_15m_pct_per_1m[entry_t_1m])
        else:
            atr_at_entry = None
        # ★ v11 — regime 진입 시점
        if 0 <= entry_t_1m < n_regime:
            reg_at_entry = str(regime_per_1m[entry_t_1m])
        else:
            reg_at_entry = None

        r = simulate_position_v11(
            sig_idx, side, df_1m, df_ob_tf, df_2h, atr_ob_tf,
            leverage=leverage, w=w, N=N,
            ob_tf_minutes=ob_tf_minutes,
            enable_2h_reversal=enable_2h_reversal,
            regime_master=regime_master,
            enable_wait_entry=enable_wait_entry,
            wait_timeout_minutes=wait_timeout_minutes,
            other_side_signals=other_side,
            same_side_signals=same_side,
            atr_pct_at_entry=atr_at_entry,
            sl_max=sl_max,
            # v11 신규
            regime_at_entry=reg_at_entry,
            enable_regime_policy=enable_regime_policy,
            hivol_long_sl_max=hivol_long_sl_max,
            hivol_long_timeout=hivol_long_timeout,
        )
        results.append(r)

        if r.get('exit_t') is not None:
            try:
                exit_1m_idx = df_1m.index.get_indexer([r['exit_t'].floor('1min')])[0]
                if exit_1m_idx >= 0:
                    last_exit_t_1m = exit_1m_idx
            except Exception:
                last_exit_t_1m = sig_idx + max(timeout_this_trade if 'timeout_this_trade' in dir() else 240, 240)

    df = pd.DataFrame(results)
    return df


# 호환성 alias
def batch_simulate_v10(*args, **kwargs):
    """호환성 — v11로 위임 (regime 정책 없이)."""
    # regime_per_1m이 없으면 모두 None으로
    if 'regime_per_1m' not in kwargs and len(args) < 8:
        # 임시 빈 배열
        df_1m = kwargs.get('df_1m', args[2] if len(args) > 2 else None)
        if df_1m is not None:
            kwargs['regime_per_1m'] = np.array([None] * len(df_1m))
    kwargs['enable_regime_policy'] = kwargs.get('enable_regime_policy', False)
    return batch_simulate_v11(*args, **kwargs)


def simulate_position_v10(*args, **kwargs):
    """호환성 — v11로 위임 (regime 정책 없이)."""
    kwargs['enable_regime_policy'] = kwargs.get('enable_regime_policy', False)
    return simulate_position_v11(*args, **kwargs)


def batch_simulate_v9(*args, **kwargs):
    return batch_simulate_v10(*args, **kwargs)


def simulate_position_v9(*args, **kwargs):
    return simulate_position_v10(*args, **kwargs)


# ============================================================
# 단위 테스트 — Stage 2 v9 핵심 시나리오 8개
# ============================================================
if __name__ == "__main__":
    print("="*70)
    print("[tbm_simulator_v10 inline 단위 테스트 - compute_dynamic_sl 위주]")
    print("="*70)
    
    # T1: 저변동 (0.15% ATR) → mult 3.5 → 52.5bp
    sl, m = compute_dynamic_sl(0.0015)
    expected = 0.0015 * 3.5
    print(f"\n[T1] 저변동 ATR 15bp → SL={sl*10000:.1f}bp, mult={m} (기대 SL={expected*10000:.1f}bp)")
    print(f"  → {'OK' if abs(sl-expected)<1e-6 and m==MULT_LOWVOL else 'FAIL'}")
    
    # T2: 중변동 (0.35% ATR) → mult 3.0 → 105bp
    sl, m = compute_dynamic_sl(0.0035)
    expected = 0.0035 * 3.0
    print(f"\n[T2] 중변동 ATR 35bp → SL={sl*10000:.1f}bp, mult={m} (기대 SL={expected*10000:.1f}bp)")
    print(f"  → {'OK' if abs(sl-expected)<1e-6 and m==MULT_MIDVOL else 'FAIL'}")
    
    # T3: 고변동 (0.55% ATR) → mult 2.0 → 110bp
    sl, m = compute_dynamic_sl(0.0055)
    expected = 0.0055 * 2.0
    print(f"\n[T3] 고변동 ATR 55bp → SL={sl*10000:.1f}bp, mult={m} (기대 SL={expected*10000:.1f}bp)")
    print(f"  → {'OK' if abs(sl-expected)<1e-6 and m==MULT_HIGHVOL else 'FAIL'}")
    
    # T4: 극저변동 (0.05% ATR) → 하한 32bp 적용
    sl, m = compute_dynamic_sl(0.0005)
    raw = 0.0005 * 3.5
    print(f"\n[T4] 극저변동 ATR 5bp → SL={sl*10000:.1f}bp (raw={raw*10000:.1f}, 하한 {SL_MIN*10000:.0f}bp 적용)")
    print(f"  → {'OK' if sl==SL_MIN else 'FAIL'}")
    
    # T5: 극고변동 (1.0% ATR) → 상한 150bp 적용
    sl, m = compute_dynamic_sl(0.0100)
    raw = 0.0100 * 2.0
    print(f"\n[T5] 극고변동 ATR 100bp → SL={sl*10000:.1f}bp (raw={raw*10000:.1f}, 상한 {SL_MAX_DEFAULT*10000:.0f}bp 적용)")
    print(f"  → {'OK' if sl==SL_MAX_DEFAULT else 'FAIL'}")
    
    # T6: 경계값 0.0024% (BUCKET_LOW 직전) → mult 3.5
    sl, m = compute_dynamic_sl(0.0024)
    print(f"\n[T6] 경계 ATR 24bp (BUCKET_LOW 직전) → mult={m}")
    print(f"  → {'OK' if m==MULT_LOWVOL else 'FAIL'}")
    
    # T7: 경계값 0.0025% (BUCKET_LOW) → mult 3.0
    sl, m = compute_dynamic_sl(0.0025)
    print(f"\n[T7] 경계 ATR 25bp (=BUCKET_LOW) → mult={m}")
    print(f"  → {'OK' if m==MULT_MIDVOL else 'FAIL'}")
    
    # T8: 비정상 입력 (NaN) → sl_max로 fallback
    sl, m = compute_dynamic_sl(np.nan, sl_max=0.012)
    print(f"\n[T8] NaN 입력 → SL={sl*10000:.1f}bp (sl_max=120bp로 fallback)")
    print(f"  → {'OK' if sl==0.012 else 'FAIL'}")
    
    # T9: compute_step_sl 검증 (변경 없음, 회귀 테스트)
    sl_step = compute_step_sl('long', 100000, 101000, 1)
    print(f"\n[T9] 회귀: compute_step_sl 롱 +100bp 1단계 → SL={sl_step}")
    print(f"  → {'OK' if abs(sl_step-100500)<0.01 else 'FAIL'}")
    
    # T10: 다른 sl_max 그리드 효과
    sl_120, _ = compute_dynamic_sl(0.0100, sl_max=0.012)  # 100bp ATR + 상한 120bp
    sl_180, _ = compute_dynamic_sl(0.0100, sl_max=0.018)  # 100bp ATR + 상한 180bp
    print(f"\n[T10] 그리드 효과 (ATR 100bp):")
    print(f"  sl_max=120bp → SL={sl_120*10000:.1f}bp")
    print(f"  sl_max=180bp → SL={sl_180*10000:.1f}bp")
    print(f"  → {'OK' if sl_120==0.012 and sl_180==0.018 else 'FAIL'}")
    
    # T11-T14: v11 신규 — resolve_regime_policy 검증
    print("\n[T11] v11: uptrend long → block_entry=True")
    p = resolve_regime_policy('uptrend', 'long')
    print(f"  block_entry={p['block_entry']}, label={p['policy_label']}")
    print(f"  → {'OK' if p['block_entry']==True else 'FAIL'}")
    
    print("\n[T12] v11: hivol_range long → SL 500bp + 18H(1080min)")
    p = resolve_regime_policy('hivol_range', 'long')
    print(f"  sl_max={p['sl_max']*10000:.0f}bp, timeout={p['timeout_min']}min, label={p['policy_label']}")
    print(f"  → {'OK' if p['sl_max']==0.05 and p['timeout_min']==1080 else 'FAIL'}")
    
    print("\n[T13] v11: downtrend long → default (변경 없음)")
    p = resolve_regime_policy('downtrend', 'long')
    print(f"  sl_max={p['sl_max']*10000:.0f}bp, timeout={p['timeout_min']}min")
    print(f"  → {'OK' if p['sl_max']==SL_MAX_DEFAULT and p['timeout_min']==240 else 'FAIL'}")
    
    print("\n[T14] v11: hivol_range short → default (regime 정책 long만)")
    p = resolve_regime_policy('hivol_range', 'short')
    print(f"  sl_max={p['sl_max']*10000:.0f}bp, timeout={p['timeout_min']}min")
    print(f"  → {'OK' if p['sl_max']==SL_MAX_DEFAULT and p['timeout_min']==240 else 'FAIL'}")
    
    print("\n[T15] v11: enable_regime_policy=False → 항상 default")
    p = resolve_regime_policy('uptrend', 'long', enable_regime_policy=False)
    print(f"  block={p['block_entry']}, sl_max={p['sl_max']*10000:.0f}bp")
    print(f"  → {'OK' if p['block_entry']==False and p['sl_max']==SL_MAX_DEFAULT else 'FAIL'}")
    
    print("\n" + "="*70)
    print("[v11 inline 테스트 완료]")
    print("="*70)
