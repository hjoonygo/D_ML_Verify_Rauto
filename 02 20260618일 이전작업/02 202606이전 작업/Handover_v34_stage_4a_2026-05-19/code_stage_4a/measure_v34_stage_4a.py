# -*- coding: utf-8 -*-
"""
[파일명] measure_v34_stage_4a.py
코드길이: 약 600줄, 내부버전명: v2.0_verified_no_estimation
검증: pautov75_signal_wrapper_v4 / tbm_simulator_v11 / tf_aggregator_v2 / Regime_Master_v2 /
      Predict_ML_v2 시그니처를 인수인계 zip 코드에서 직접 확인 후 사용 (추정 0%)

[목적] Stage 4A Phase 1 측정 — 메타라벨링 효과 검증
  Stage 3.5 measure를 베이스로 5 시나리오 + Step 0 사전측정 + Step 1 Train시뮬 추가

[사용자 결정 사항]
  결정1(Y): 5 시나리오 (base_no_meta + meta_simple + meta_purged + meta_regime + meta_oos_only)
  결정2(b): PF 임계값 1.2/0.95
  결정3:    사전 의사결정 트리 + 우선순위 (1=lookahead 2=M2효과 3=feature)
  결정4(a): 분별력 임계 10%/90%
  A:b — Train+OOS 통합 (단 meta_oos_only는 OOS만)
  B:d — Binary + |net_return| weight
  d:0.5 — M2 threshold
  e:XGBoost binary:logistic
  f:없음 정규화

[Step 흐름 — 단일 실행]
  Step 0: Regime_Master 분포 측정 + 분별력 검증 (10/90)
  Step 1: Train 70% 기간 시뮬 (M2 학습 데이터 + features 캐시 생성)
  중간:    train_meta_model_v1.py subprocess 자동 호출
  Step 2: OOS 5 시나리오 시뮬 (M2 필터 적용)
  Step 3: 사전 의사결정 트리 자동 평가 + 추가 측정

[출력 — outputs_stage_4a/ 폴더 (통합 1개)]
  Step 0: additional_regime_master_distribution.csv, regime_master_at_entry.pkl
  Step 1: trades_train_phase_4a.csv, signal_features_train_4a.pkl, signal_features_oos_4a.pkl
  중간:   M2_meta_*.json + _meta.json (8개)
  Step 2: trades_base_no_meta.csv ~ trades_meta_oos_only.csv (5개)
  Step 3: all_scenarios_stage_4a.csv, decision_tree_evaluation.csv
  추가:   additional_m1_prob_distribution.csv
  로그:   measure_log_4a.txt
"""
import os
import sys
import time
import pickle
import json
import subprocess
import numpy as np
import pandas as pd
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ★ 검증된 import — 인수인계 zip 코드에서 직접 확인한 시그니처
from tf_aggregator_v2 import aggregate_ohlcv
from tbm_simulator_v11 import (
    compute_atr, batch_simulate_v11,
    HIVOL_LONG_SL_MAX_DEFAULT, HIVOL_LONG_TIMEOUT_DEFAULT,
    SL_MAX_DEFAULT,
)
from pautov75_signal_wrapper_v4 import (
    extract_signals_v4, compute_atr_15m_pct_per_1m, process_signals_with_wait_v4
)
from Regime_Master_v2 import Regime_Master_v2
from Predict_ML_v2 import Predict_ML_v2


# 경로
WORK_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(WORK_DIR, "outputs_stage_4a")
LOG_PATH = os.path.join(OUTPUT_DIR, "measure_log_4a.txt")

# 사용자 결정 상수
M2_THRESHOLD = 0.5
DISCRIMINATIVE_LOW = 0.10
DISCRIMINATIVE_HIGH = 0.90
PF_EFFECT_THRESHOLD = 1.20
PF_AMBIGUOUS_THRESHOLD = 0.95
PF_PURGED_RATIO_ALERT = 0.85
PF_OOS_ONLY_RATIO_ALERT = 0.70
PF_REGIME_JUMP = 0.15

# 시뮬 고정값 (Stage 3.5와 동일)
TRAIN_RATIO = 0.70
OB_TF = 60
LEV = 10
W = 5
N = 5
ROLLING_LOOKBACK = 14 * 1440  # 14일
ENABLE_WAIT_ENTRY = True
WAIT_TIMEOUT_MINUTES = 120
SL_MAX_STAGE_3_BEST = 0.0180  # Stage 3 최우승값 (검증됨)

# Phase 1 시나리오 정의 (5개)
PHASE_1_SCENARIOS = [
    'base_no_meta',
    'meta_simple',
    'meta_purged',
    'meta_regime',
    'meta_oos_only',
]


def find_file(filename):
    """Verify 폴더 구조에서 자동 탐색 (run_all_stage_3_5와 동일 로직)."""
    candidates = [
        os.path.join(OUTPUT_DIR, filename),
        os.path.join(WORK_DIR, filename),
        os.path.join(WORK_DIR, "..", filename),
        os.path.join(WORK_DIR, "..", "..", filename),
    ]
    grandparent = os.path.abspath(os.path.join(WORK_DIR, "..", ".."))
    if os.path.isdir(grandparent):
        try:
            for entry in os.listdir(grandparent):
                subpath = os.path.join(grandparent, entry)
                if os.path.isdir(subpath):
                    candidates.append(os.path.join(subpath, filename))
                    try:
                        for entry2 in os.listdir(subpath):
                            sub2 = os.path.join(subpath, entry2)
                            if os.path.isdir(sub2):
                                candidates.append(os.path.join(sub2, filename))
                    except (PermissionError, OSError):
                        pass
        except (PermissionError, OSError):
            pass
    for path in candidates:
        if os.path.exists(path):
            return os.path.abspath(path)
    return None


def log(msg, log_lines):
    print(msg)
    log_lines.append(msg)


# =============================================================================
# regime_v33 사후 분류 (Stage 3.5 동일 — lookahead 차단)
# =============================================================================
def assign_regime_v33_fixed(df_1m, atr_med_fixed):
    """Stage 3.5 검증된 함수 그대로."""
    close = df_1m['close'].values
    ema_60 = pd.Series(close).ewm(span=60, adjust=False).mean().values
    ema_240 = pd.Series(close).ewm(span=240, adjust=False).mean().values
    atr = pd.Series((df_1m['high'] - df_1m['low']).values).rolling(60).mean().fillna(0).values
    atr_pct = atr / close * 100

    regime = np.full(len(df_1m), "lovol_range", dtype=object)
    is_up = ema_60 > ema_240
    is_down = ema_60 < ema_240
    is_hivol = atr_pct > atr_med_fixed * 1.5
    is_lovol = atr_pct < atr_med_fixed * 0.5

    regime[is_up & ~is_hivol & ~is_lovol] = "uptrend"
    regime[is_down & ~is_hivol & ~is_lovol] = "downtrend"
    regime[is_hivol] = "hivol_range"
    return regime


def compute_train_atr_med(df_train_1m):
    """Stage 3.5 검증된 함수 그대로."""
    close = df_train_1m['close'].values
    atr = pd.Series((df_train_1m['high'] - df_train_1m['low']).values).rolling(60).mean().fillna(0).values
    atr_pct = atr / close * 100
    valid = atr_pct[atr_pct > 0]
    if len(valid) == 0:
        return 0.1
    return float(np.nanmedian(valid))


# =============================================================================
# 분별력 검증 (사용자 결정 4:a)
# =============================================================================
def check_discriminative_power(counts_dict, label="regime"):
    """카테고리 분포 분별력 검증 (10%/90%)."""
    if not counts_dict:
        return False, f"{label}: empty"
    total = sum(counts_dict.values())
    if total == 0:
        return False, f"{label}: total=0"
    fractions = {k: v / total for k, v in counts_dict.items()}
    max_frac = max(fractions.values())
    min_frac = min(fractions.values()) if len(fractions) > 1 else max_frac
    if max_frac > DISCRIMINATIVE_HIGH:
        return False, f"{label}: max {max_frac:.1%} > {DISCRIMINATIVE_HIGH:.0%} (분별력 부족)"
    if min_frac < DISCRIMINATIVE_LOW and len(fractions) > 2:
        weak = [k for k, v in fractions.items() if v < DISCRIMINATIVE_LOW]
        return True, f"{label}: 약함 ({weak} < {DISCRIMINATIVE_LOW:.0%})"
    return True, f"{label}: OK (max {max_frac:.1%}, min {min_frac:.1%})"


# =============================================================================
# Step 0: Regime_Master 분포 측정
# =============================================================================
def measure_regime_master_distribution(df, oos_start_idx, log_lines):
    """OOS 기간 Regime_Master 출력 분포 + lookup pkl 생성."""
    log("\n[Step 0] Regime_Master 분포 측정", log_lines)
    rm = Regime_Master_v2()
    rm_outputs = {}
    counts = {'BULLISH_EXPANSION': 0, 'BEARISH_EXPANSION': 0, 'CHOPPY': 0}
    sample_step = 60  # 60분 간격 샘플링
    t0 = time.time()

    for idx in range(oos_start_idx, len(df), sample_step):
        if idx < 120:
            continue
        window = df.iloc[max(0, idx - 240):idx + 1]
        if len(window) < 120:
            continue
        try:
            reg = rm.get_regime(window)
            ts = df.index[idx]
            rm_outputs[ts] = reg
            counts[reg] = counts.get(reg, 0) + 1
        except Exception:
            pass

    elapsed = time.time() - t0
    total = sum(counts.values())
    log(f"  샘플 {total}개, 소요 {elapsed:.1f}초", log_lines)
    for k, v in counts.items():
        pct = 100 * v / total if total > 0 else 0
        log(f"    {k}: {v} ({pct:.1f}%)", log_lines)

    passed, msg = check_discriminative_power(counts, label="Regime_Master")
    log(f"  분별력 ({DISCRIMINATIVE_LOW:.0%}/{DISCRIMINATIVE_HIGH:.0%}): {msg}", log_lines)

    dist_df = pd.DataFrame([
        {'category': k, 'count': v, 'fraction': v / total if total > 0 else 0}
        for k, v in counts.items()
    ])
    dist_df.to_csv(os.path.join(OUTPUT_DIR, 'additional_regime_master_distribution.csv'),
                   index=False)

    with open(os.path.join(OUTPUT_DIR, 'regime_master_at_entry.pkl'), 'wb') as f:
        pickle.dump(rm_outputs, f)
    log(f"  저장: regime_master_at_entry.pkl ({len(rm_outputs)} 샘플)", log_lines)

    return rm_outputs, passed


# =============================================================================
# 신호 idx에서 features + probs 캐시 추출
# (M2 학습/추론용. wrapper_v4는 idx만 반환하므로 별도 추출)
# =============================================================================
def extract_features_and_probs_for_signals(df_1m, signal_indices, window_size=120):
    """각 신호 idx에 대해 9 features + 3 probs 캐시 생성.
    Predict_ML_v2.get_signal()을 호출하면서 그 안의 features 계산 로직을 따름.

    IN: df_1m, signal_indices (np.array of int), window_size
    OUT: dict {idx: {features..., prob_long, prob_short, prob_stay, regime}}
    """
    rm = Regime_Master_v2()
    predict = Predict_ML_v2()
    if not predict.model_loaded:
        raise RuntimeError("Predict_ML_v2 모델 로드 실패")

    params = {'ml_long_threshold': 0.35, 'ml_short_threshold': 0.35}
    cache = {}

    for idx in signal_indices:
        idx = int(idx)
        if idx < window_size:
            continue
        window = df_1m.iloc[idx - window_size + 1: idx + 1]
        # Regime
        try:
            reg = rm.get_regime(window)
        except Exception:
            reg = "CHOPPY"
        # Signal (probs 포함)
        sig = predict.get_signal(window, reg, params)
        # 9 features 재계산 (Predict_ML_v2와 동일 공식)
        feats = _compute_9_features(window)
        if feats is None:
            continue
        cache[idx] = {
            **feats,
            'prob_long': sig.get('prob_long', 0.0),
            'prob_short': sig.get('prob_short', 0.0),
            'prob_stay': sig.get('prob_stay', 1.0),
            'regime_master': reg,
            'action': sig.get('action', 'WAIT'),
        }
    return cache


def _compute_9_features(window):
    """Predict_ML_v2.get_signal과 동일 공식 (검증된 코드)."""
    if len(window) < 50:
        return None
    closed = window.iloc[:-1].copy()

    delta_px = closed['close'].diff()
    gain = (delta_px.where(delta_px > 0, 0)).rolling(14).mean()
    loss = (-delta_px.where(delta_px < 0, 0)).rolling(14).mean()
    rsi_14 = 100 - (100 / (1 + gain / loss))

    ema_20 = closed['close'].ewm(span=20, adjust=False).mean()
    ema_50 = closed['close'].ewm(span=50, adjust=False).mean()
    ema_dist = (ema_20 - ema_50) / ema_50 * 100

    h_l = closed['high'] - closed['low']
    h_c = np.abs(closed['high'] - closed['close'].shift())
    l_c = np.abs(closed['low'] - closed['close'].shift())
    tr = np.max(pd.concat([h_l, h_c, l_c], axis=1), axis=1)
    atr_14 = tr.rolling(14).mean()

    fvg_bull = (closed['low'] > closed['high'].shift(2)).astype(int)
    fvg_bear = (closed['high'] < closed['low'].shift(2)).astype(int)

    if 'open_interest' in closed.columns:
        oi_col = 'open_interest'
    elif 'oi_sum' in closed.columns:
        oi_col = 'oi_sum'
    elif 'oi_value' in closed.columns:
        oi_col = 'oi_value'
    else:
        oi_col = None
    if oi_col:
        oi_delta = closed[oi_col].pct_change(periods=3).fillna(0) * 100
    else:
        oi_delta = pd.Series(0.0, index=closed.index)

    rvol_20 = closed['volume'] / (closed['volume'].rolling(20).mean() + 1e-8)
    vol_accel = closed['volume'].pct_change().fillna(0).replace([np.inf, -np.inf], 0)

    buy_pressure = (closed['close'] - closed['low']) / (closed['high'] - closed['low'] + 1e-8)
    order_delta = closed['volume'] * (buy_pressure * 2 - 1)
    delta_sign = np.sign(order_delta)
    delta_streak = delta_sign.groupby((delta_sign != delta_sign.shift()).cumsum()).cumsum()

    try:
        feats = {
            'rsi_14': float(rsi_14.iloc[-1]),
            'ema_dist': float(ema_dist.iloc[-1]),
            'atr_14': float(atr_14.iloc[-1]),
            'fvg_bull': int(fvg_bull.iloc[-1]),
            'fvg_bear': int(fvg_bear.iloc[-1]),
            'oi_delta': float(oi_delta.iloc[-1]),
            'rvol_20': float(rvol_20.iloc[-1]),
            'vol_accel': float(vol_accel.iloc[-1]),
            'delta_streak': float(delta_streak.iloc[-1]),
        }
        if pd.isna(list(feats.values())).any():
            return None
        return feats
    except Exception:
        return None


# =============================================================================
# M2 필터 — 신호 idx에 M2 적용 후 통과한 idx만 반환
# =============================================================================
def apply_m2_to_signals(long_idx, short_idx, features_cache, m2_model, m2_feature_names,
                       regime_per_1m, rm_lookup, df_1m,
                       scenario_name, threshold=M2_THRESHOLD):
    """M2 통과 신호만 반환.

    IN: long_idx, short_idx (np.array), features_cache (dict from extract_features_and_probs_for_signals),
        m2_model (xgb.XGBClassifier), m2_feature_names (list), regime_per_1m (np.array),
        rm_lookup (dict ts->regime), df_1m, scenario_name, threshold
    OUT: (long_filtered, short_filtered, n_rejected)
    """
    if m2_model is None or scenario_name == 'base_no_meta':
        return long_idx, short_idx, 0

    import xgboost as xgb
    long_pass = []
    short_pass = []
    n_rejected = 0

    for idx in long_idx:
        idx = int(idx)
        feats = features_cache.get(idx)
        if feats is None:
            long_pass.append(idx)  # features 없으면 통과 (안전)
            continue
        x = _build_m2_input(feats, idx, 'long', m2_feature_names,
                           regime_per_1m, rm_lookup, df_1m, scenario_name)
        try:
            prob = float(m2_model.predict_proba(np.array([x]))[0, 1])
            if prob >= threshold:
                long_pass.append(idx)
            else:
                n_rejected += 1
        except Exception:
            long_pass.append(idx)

    for idx in short_idx:
        idx = int(idx)
        feats = features_cache.get(idx)
        if feats is None:
            short_pass.append(idx)
            continue
        x = _build_m2_input(feats, idx, 'short', m2_feature_names,
                           regime_per_1m, rm_lookup, df_1m, scenario_name)
        try:
            prob = float(m2_model.predict_proba(np.array([x]))[0, 1])
            if prob >= threshold:
                short_pass.append(idx)
            else:
                n_rejected += 1
        except Exception:
            short_pass.append(idx)

    return (np.array(long_pass, dtype=np.int64),
            np.array(short_pass, dtype=np.int64),
            n_rejected)


def _build_m2_input(feats, idx, side, feature_names, regime_per_1m, rm_lookup,
                    df_1m, scenario_name):
    """M2 입력 벡터 (feature_names 순서)."""
    out = {
        'rsi_14': feats['rsi_14'], 'ema_dist': feats['ema_dist'],
        'atr_14': feats['atr_14'], 'fvg_bull': feats['fvg_bull'],
        'fvg_bear': feats['fvg_bear'], 'oi_delta': feats['oi_delta'],
        'rvol_20': feats['rvol_20'], 'vol_accel': feats['vol_accel'],
        'delta_streak': feats['delta_streak'],
        'prob_long': feats['prob_long'], 'prob_short': feats['prob_short'],
        'prob_stay': feats['prob_stay'],
        'side_long': 1 if side == 'long' else 0,
        'side_short': 1 if side == 'short' else 0,
    }
    if scenario_name == 'meta_regime':
        reg_v33 = regime_per_1m[idx] if idx < len(regime_per_1m) else 'lovol_range'
        for r in ['uptrend', 'downtrend', 'hivol_range', 'lovol_range']:
            out[f'regime_v33_{r}'] = 1 if reg_v33 == r else 0
        ts = df_1m.index[idx] if idx < len(df_1m) else None
        rm = 'CHOPPY'
        if rm_lookup and ts is not None:
            for delta_min in range(0, 121, 15):
                cand = ts - pd.Timedelta(minutes=delta_min)
                if cand in rm_lookup:
                    rm = rm_lookup[cand]
                    break
        for r in ['BULLISH_EXPANSION', 'BEARISH_EXPANSION', 'CHOPPY']:
            out[f'regime_master_{r}'] = 1 if rm == r else 0
    return [out[f] for f in feature_names]


# =============================================================================
# 메트릭 계산 (Stage 3.5의 compute_stats_v11 축약본)
# =============================================================================
def compute_metrics(trades_df, scenario_name):
    """5 시나리오 비교용 핵심 메트릭."""
    valid_exits = ['initial_sl', 'step1_sl', 'step2_sl', 'step3_sl',
                   'timeout_4h', 'timeout_16h', 'timeout_18h',
                   'timeout_step_active', 'reversal_2h']
    is_valid = trades_df['exit_reason'].apply(
        lambda r: isinstance(r, str) and (
            r in valid_exits or r.startswith('timeout_')
        )
    )
    valid = trades_df[is_valid]
    if len(valid) == 0:
        return {'scenario': scenario_name, 'n_valid': 0, 'pf': 0,
                'win_rate': 0, 'net_sum': 0, 'mdd_pct': 0}

    nets = valid['net_return'].values
    wins = nets[nets > 0]
    losses = nets[nets <= 0]
    pf = wins.sum() / abs(losses.sum()) if abs(losses.sum()) > 0 else 999.0
    win_rate = len(wins) / len(valid)
    cum = nets.cumsum()
    running_max = np.maximum.accumulate(cum)
    mdd = float((cum - running_max).min())

    return {
        'scenario': scenario_name,
        'n_valid': int(len(valid)),
        'pf': round(pf, 3),
        'win_rate': round(win_rate, 4),
        'net_sum': round(float(nets.sum()), 4),
        'mdd_pct': round(mdd * 100, 3),
    }


# =============================================================================
# 사전 의사결정 트리 자동 평가
# =============================================================================
def evaluate_decision_tree(metrics_dict, log_lines):
    """5 시나리오 PF 결과로 우선순위 1/2/3 자동 평가."""
    log("\n" + "=" * 72, log_lines)
    log("[Step 3] 사전 의사결정 트리 자동 평가", log_lines)
    log("=" * 72, log_lines)

    pf_base = metrics_dict.get('base_no_meta', {}).get('pf', 0)
    pf_simple = metrics_dict.get('meta_simple', {}).get('pf', 0)
    pf_purged = metrics_dict.get('meta_purged', {}).get('pf', 0)
    pf_regime = metrics_dict.get('meta_regime', {}).get('pf', 0)
    pf_oos_only = metrics_dict.get('meta_oos_only', {}).get('pf', 0)

    log(f"\nPF 요약:", log_lines)
    log(f"  base_no_meta:   {pf_base:.3f}", log_lines)
    log(f"  meta_simple:    {pf_simple:.3f}", log_lines)
    log(f"  meta_purged:    {pf_purged:.3f}", log_lines)
    log(f"  meta_regime:    {pf_regime:.3f}", log_lines)
    log(f"  meta_oos_only:  {pf_oos_only:.3f}", log_lines)

    log(f"\n[1순위] Lookahead 안전성", log_lines)
    p1_alerts = []
    if pf_simple > 0 and pf_purged < pf_simple * PF_PURGED_RATIO_ALERT:
        msg = f"  ⚠️ CV lookahead 의심: purged({pf_purged:.3f}) < simple×{PF_PURGED_RATIO_ALERT}={pf_simple * PF_PURGED_RATIO_ALERT:.3f}"
        p1_alerts.append(msg); log(msg, log_lines)
    else:
        log(f"  ✓ CV 안전", log_lines)
    if pf_simple > 0 and pf_oos_only < pf_simple * PF_OOS_ONLY_RATIO_ALERT:
        msg = f"  ⚠️ A:b lookahead 의심: oos_only({pf_oos_only:.3f}) < simple×{PF_OOS_ONLY_RATIO_ALERT}={pf_simple * PF_OOS_ONLY_RATIO_ALERT:.3f}"
        p1_alerts.append(msg); log(msg, log_lines)
    else:
        log(f"  ✓ A:b 안전", log_lines)

    p1_safe = len(p1_alerts) == 0
    log(f"  → 1순위: {'안전 ✓' if p1_safe else '의심 ⚠️'}", log_lines)

    log(f"\n[2순위] M2 효과", log_lines)
    if pf_simple >= PF_EFFECT_THRESHOLD:
        p2 = f"효과 입증 (PF {pf_simple:.3f}) → Phase 2 feature 확장"
    elif pf_simple >= PF_AMBIGUOUS_THRESHOLD:
        p2 = f"효과 모호 (PF {pf_simple:.3f}) → m1_retrain_60bar 우선"
    else:
        p2 = f"효과 없음 (PF {pf_simple:.3f}) → m1_trend_scanning 우선"
    log(f"  → 2순위: {p2}", log_lines)

    log(f"\n[3순위] Feature 확장", log_lines)
    jump = pf_regime - pf_simple
    if jump >= PF_REGIME_JUMP:
        p3 = f"Regime 강력 (점프 +{jump:.3f}) → Stage 4A 우선"
    else:
        p3 = f"Regime 약함 (점프 {jump:+.3f})"
    log(f"  → 3순위: {p3}", log_lines)

    result = {
        'p1_safe': p1_safe, 'p1_alerts': '; '.join(p1_alerts) if p1_alerts else '안전',
        'p2_result': p2, 'p3_result': p3,
        'pf_base': pf_base, 'pf_meta_simple': pf_simple,
        'pf_meta_purged': pf_purged, 'pf_meta_regime': pf_regime,
        'pf_meta_oos_only': pf_oos_only,
    }
    pd.DataFrame([result]).to_csv(
        os.path.join(OUTPUT_DIR, 'decision_tree_evaluation.csv'), index=False)
    log(f"\n저장: decision_tree_evaluation.csv", log_lines)
    return result


# =============================================================================
# main
# =============================================================================
def main():
    t_start = time.time()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    log_lines = []

    log("\n" + "=" * 78, log_lines)
    log(f"[Stage 4A Phase 1 측정] {datetime.now()}", log_lines)
    log(f"내부버전: v2.0_verified_no_estimation", log_lines)
    log("=" * 78, log_lines)
    log(f"실행 폴더: {WORK_DIR}", log_lines)
    log(f"결과 폴더: {OUTPUT_DIR}", log_lines)
    log(f"\n사용자 결정:", log_lines)
    log(f"  결정1(Y): 5 시나리오 ({', '.join(PHASE_1_SCENARIOS)})", log_lines)
    log(f"  결정2(b): PF 임계 {PF_EFFECT_THRESHOLD}/{PF_AMBIGUOUS_THRESHOLD}", log_lines)
    log(f"  결정3: 사전 의사결정 트리 + 우선순위 1/2/3", log_lines)
    log(f"  결정4(a): 분별력 {DISCRIMINATIVE_LOW:.0%}/{DISCRIMINATIVE_HIGH:.0%}", log_lines)
    log(f"  M2 threshold: {M2_THRESHOLD}", log_lines)

    # 데이터 로드
    data_path = find_file('Merged_Data.csv')
    if not data_path:
        log(f"\n❌ Merged_Data.csv 못 찾음", log_lines)
        return False

    log(f"\n[1/8] 데이터 로드: {data_path}", log_lines)
    df = pd.read_csv(data_path, parse_dates=['timestamp']).set_index('timestamp')
    if df.index.tz is None:
        df.index = df.index.tz_localize('UTC')
    log(f"  전체: {df.index.min()} ~ {df.index.max()} ({len(df):,}봉)", log_lines)

    n_train = int(len(df) * TRAIN_RATIO)
    oos_start_idx = n_train
    oos_end_idx = len(df)
    log(f"  Train: idx 0~{oos_start_idx-1} ({oos_start_idx:,}봉)", log_lines)
    log(f"  OOS:   idx {oos_start_idx}~{oos_end_idx-1} ({oos_end_idx-oos_start_idx:,}봉)", log_lines)

    # Train atr_med (lookahead 차단)
    log(f"\n[2/8] Train atr_med 계산", log_lines)
    df_train = df.iloc[:oos_start_idx]
    atr_med_fixed = compute_train_atr_med(df_train)
    log(f"  Train atr_med: {atr_med_fixed:.6f}%", log_lines)

    # 15m ATR_pct 사전 계산
    log(f"\n[3/8] 15m ATR_pct 사전 계산", log_lines)
    t_atr = time.time()
    atr_15m_pct_per_1m = compute_atr_15m_pct_per_1m(df)
    log(f"  소요 {time.time()-t_atr:.1f}초, mean={np.nanmean(atr_15m_pct_per_1m)*100:.4f}%", log_lines)

    # Step 0: Regime_Master 분포
    log(f"\n[4/8] Step 0 — Regime_Master 분포 측정", log_lines)
    rm_lookup, _ = measure_regime_master_distribution(df, oos_start_idx, log_lines)

    # Regime per 1m (전체)
    regime_per_1m_full = assign_regime_v33_fixed(df, atr_med_fixed)
    log(f"  4장세 분포: {pd.Series(regime_per_1m_full).value_counts().to_dict()}", log_lines)

    # TF aggregate (Stage 3.5와 동일)
    log(f"\n[5/8] TF aggregate", log_lines)
    df_reset = df.reset_index()
    df_2h = aggregate_ohlcv(df_reset, 120).set_index('timestamp')
    df_ob = aggregate_ohlcv(df_reset, OB_TF).set_index('timestamp')
    atr_ob = compute_atr(df_ob['high'].values, df_ob['low'].values, df_ob['close'].values, period=20)
    log(f"  2h봉: {len(df_2h)}, {OB_TF}m봉: {len(df_ob)}", log_lines)

    # OOS 신호 (캐시 활용)
    log(f"\n[6/8] OOS 신호 추출/로드", log_lines)
    cache_oos_path = find_file('signals_cache_stage_3_5.pkl')
    if cache_oos_path and os.path.exists(cache_oos_path) and os.path.getsize(cache_oos_path) > 100:
        log(f"  OOS 신호 캐시 로드: {cache_oos_path}", log_lines)
        with open(cache_oos_path, 'rb') as f:
            cached = pickle.load(f)
        oos_long_idx = np.array(cached['long_idx'], dtype=np.int64)
        oos_short_idx = np.array(cached['short_idx'], dtype=np.int64)
        log(f"    Long {len(oos_long_idx)}, Short {len(oos_short_idx)}", log_lines)
    else:
        log(f"  OOS 신호 추출 (90분 예상)", log_lines)
        t_sig = time.time()
        long_raw, short_raw, _ = extract_signals_v4(
            df, atr_15m_pct_per_1m,
            threshold_long=0.35, threshold_short=0.35,
            window_size=120, filter_mode='off',
            rolling_lookback_minutes=ROLLING_LOOKBACK,
            start_idx=oos_start_idx, end_idx=oos_end_idx,
            verbose_every=200000,
        )
        oos_long_idx, oos_short_idx, _ = process_signals_with_wait_v4(
            long_raw, short_raw, df, None, OB_TF, W,
            enable_wait=ENABLE_WAIT_ENTRY, wait_timeout_minutes=WAIT_TIMEOUT_MINUTES,
            verbose=False,
        )
        log(f"    Long {len(oos_long_idx)}, Short {len(oos_short_idx)}, 소요 {(time.time()-t_sig)/60:.1f}분", log_lines)
        # 캐시 저장
        with open(os.path.join(OUTPUT_DIR, 'signals_cache_stage_3_5.pkl'), 'wb') as f:
            pickle.dump({'long_idx': oos_long_idx, 'short_idx': oos_short_idx}, f)

    # Step 1: Train 시뮬 (M2 학습 데이터 생성)
    log(f"\n[7/8] Step 1 — Train 기간 시뮬 + features 캐시", log_lines)
    train_trades_path = os.path.join(OUTPUT_DIR, 'trades_train_phase_4a.csv')
    train_features_path = os.path.join(OUTPUT_DIR, 'signal_features_train_4a.pkl')
    oos_features_path = os.path.join(OUTPUT_DIR, 'signal_features_oos_4a.pkl')

    if os.path.exists(train_trades_path) and os.path.exists(train_features_path):
        log(f"  Train 시뮬 캐시 발견, 재사용", log_lines)
        train_trades = pd.read_csv(train_trades_path, parse_dates=['entry_t', 'exit_t'])
        with open(train_features_path, 'rb') as f:
            train_features_cache = pickle.load(f)
    else:
        log(f"  Train 신호 추출 (90~120분 예상)", log_lines)
        t_train = time.time()
        train_long_raw, train_short_raw, _ = extract_signals_v4(
            df, atr_15m_pct_per_1m,
            threshold_long=0.35, threshold_short=0.35,
            window_size=120, filter_mode='off',
            rolling_lookback_minutes=ROLLING_LOOKBACK,
            start_idx=ROLLING_LOOKBACK, end_idx=oos_start_idx,
            verbose_every=200000,
        )
        train_long_idx, train_short_idx, _ = process_signals_with_wait_v4(
            train_long_raw, train_short_raw, df, None, OB_TF, W,
            enable_wait=ENABLE_WAIT_ENTRY, wait_timeout_minutes=WAIT_TIMEOUT_MINUTES,
            verbose=False,
        )
        log(f"    Long {len(train_long_idx)}, Short {len(train_short_idx)}, 소요 {(time.time()-t_train)/60:.1f}분", log_lines)

        # Train 시뮬 (base 정책)
        log(f"  Train 시뮬 (base 정책)", log_lines)
        t_sim = time.time()
        train_trades = batch_simulate_v11(
            long_signal_indices_1m=train_long_idx.tolist(),
            short_signal_indices_1m=train_short_idx.tolist(),
            df_1m=df, df_ob_tf=df_ob, df_2h=df_2h,
            atr_ob_tf=atr_ob, atr_15m_pct_per_1m=atr_15m_pct_per_1m,
            regime_per_1m=regime_per_1m_full,
            sl_max=SL_MAX_STAGE_3_BEST,
            leverage=LEV, w=W, N=N,
            ob_tf_minutes=OB_TF, enable_2h_reversal=True,
            regime_master=Regime_Master_v2(),
            enable_wait_entry=ENABLE_WAIT_ENTRY,
            wait_timeout_minutes=WAIT_TIMEOUT_MINUTES,
            verbose=False, enable_regime_policy=False,
        )
        log(f"    Train 거래 {len(train_trades)}, 소요 {(time.time()-t_sim)/60:.1f}분", log_lines)
        train_trades.to_csv(train_trades_path, index=False)

        # Train features 캐시
        log(f"  Train features+probs 캐시 생성", log_lines)
        t_feat = time.time()
        all_train_idx = np.concatenate([train_long_idx, train_short_idx])
        train_features_cache = extract_features_and_probs_for_signals(df, all_train_idx)
        with open(train_features_path, 'wb') as f:
            pickle.dump(train_features_cache, f)
        log(f"    {len(train_features_cache)}개, 소요 {(time.time()-t_feat)/60:.1f}분", log_lines)

    # OOS features 캐시
    if os.path.exists(oos_features_path):
        log(f"  OOS features 캐시 재사용", log_lines)
        with open(oos_features_path, 'rb') as f:
            oos_features_cache = pickle.load(f)
    else:
        log(f"  OOS features+probs 캐시 생성", log_lines)
        t_feat = time.time()
        all_oos_idx = np.concatenate([oos_long_idx, oos_short_idx])
        oos_features_cache = extract_features_and_probs_for_signals(df, all_oos_idx)
        with open(oos_features_path, 'wb') as f:
            pickle.dump(oos_features_cache, f)
        log(f"    {len(oos_features_cache)}개, 소요 {(time.time()-t_feat)/60:.1f}분", log_lines)

    # 중간: train_meta_model_v1.py 자동 호출
    log(f"\n[중간] train_meta_model_v1.py subprocess 호출", log_lines)
    train_script = os.path.join(WORK_DIR, 'train_meta_model_v1.py')
    if not os.path.exists(train_script):
        log(f"  ❌ train_meta_model_v1.py 없음", log_lines)
        return False
    t_train = time.time()
    result = subprocess.run([sys.executable, train_script], cwd=WORK_DIR,
                           capture_output=True, text=True, timeout=1800,
                           encoding='utf-8', errors='replace',
                           env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
    log(f"  소요 {(time.time()-t_train)/60:.1f}분, returncode={result.returncode}", log_lines)
    if result.returncode != 0:
        log(f"  ⚠️ 학습 실패:\n{result.stderr[-800:]}", log_lines)
        return False

    # Step 2: OOS 5 시나리오 시뮬
    log(f"\n[8/8] Step 2 — OOS 5 시나리오 시뮬", log_lines)
    import xgboost as xgb
    rm_module = Regime_Master_v2()
    all_metrics = {}

    for scenario in PHASE_1_SCENARIOS:
        log(f"\n  ---- {scenario} ----", log_lines)
        t_sc = time.time()

        # M2 모델 로드 (base_no_meta 제외)
        m2_model = None
        m2_features = None
        if scenario != 'base_no_meta':
            m2_path = os.path.join(OUTPUT_DIR, f'M2_{scenario}.json')
            m2_meta_path = os.path.join(OUTPUT_DIR, f'M2_{scenario}_meta.json')
            if not os.path.exists(m2_path):
                log(f"    ❌ M2 모델 없음: {m2_path}", log_lines)
                all_metrics[scenario] = {'scenario': scenario, 'n_valid': 0, 'pf': 0}
                continue
            m2_model = xgb.XGBClassifier()
            m2_model.load_model(m2_path)
            with open(m2_meta_path, encoding='utf-8') as f:
                m2_meta = json.load(f)
            m2_features = m2_meta.get('features', [])
            log(f"    M2 로드: features={len(m2_features)}", log_lines)

        # M2 필터링
        long_filt, short_filt, n_rej = apply_m2_to_signals(
            oos_long_idx, oos_short_idx, oos_features_cache,
            m2_model, m2_features, regime_per_1m_full, rm_lookup, df,
            scenario, threshold=M2_THRESHOLD,
        )
        log(f"    M2 통과: Long {len(long_filt)}/{len(oos_long_idx)}, Short {len(short_filt)}/{len(oos_short_idx)}, 거부 {n_rej}", log_lines)

        # 시뮬
        trades = batch_simulate_v11(
            long_signal_indices_1m=long_filt.tolist(),
            short_signal_indices_1m=short_filt.tolist(),
            df_1m=df, df_ob_tf=df_ob, df_2h=df_2h,
            atr_ob_tf=atr_ob, atr_15m_pct_per_1m=atr_15m_pct_per_1m,
            regime_per_1m=regime_per_1m_full,
            sl_max=SL_MAX_STAGE_3_BEST,
            leverage=LEV, w=W, N=N,
            ob_tf_minutes=OB_TF, enable_2h_reversal=True,
            regime_master=rm_module,
            enable_wait_entry=ENABLE_WAIT_ENTRY,
            wait_timeout_minutes=WAIT_TIMEOUT_MINUTES,
            verbose=False, enable_regime_policy=False,
        )
        trade_path = os.path.join(OUTPUT_DIR, f'trades_{scenario}.csv')
        trades.to_csv(trade_path, index=False)

        metrics = compute_metrics(trades, scenario)
        all_metrics[scenario] = metrics
        log(f"    n={metrics['n_valid']}, PF={metrics['pf']}, win={metrics['win_rate']}, "
            f"net={metrics['net_sum']*100:+.2f}%, mdd={metrics['mdd_pct']:.2f}%, "
            f"({(time.time()-t_sc):.1f}s)", log_lines)

    # 요약 저장
    summary_df = pd.DataFrame.from_dict(all_metrics, orient='index')
    summary_df.to_csv(os.path.join(OUTPUT_DIR, 'all_scenarios_stage_4a.csv'))
    log(f"\n저장: all_scenarios_stage_4a.csv", log_lines)

    # Step 3: 사전 의사결정 트리
    evaluate_decision_tree(all_metrics, log_lines)

    # 추가 측정: M1 prob 분포
    log(f"\n[추가] M1 prob 분포", log_lines)
    prob_rows = []
    for cache, source in [(train_features_cache, 'train'), (oos_features_cache, 'oos')]:
        for idx, feats in cache.items():
            prob_rows.append({
                'source': source, 'idx': idx,
                'prob_long': feats['prob_long'],
                'prob_short': feats['prob_short'],
                'prob_stay': feats['prob_stay'],
            })
    if prob_rows:
        prob_df = pd.DataFrame(prob_rows)
        summary = prob_df.groupby('source').agg(
            n=('prob_long', 'count'),
            prob_long_mean=('prob_long', 'mean'),
            prob_short_mean=('prob_short', 'mean'),
            prob_stay_mean=('prob_stay', 'mean'),
        ).reset_index()
        summary.to_csv(os.path.join(OUTPUT_DIR, 'additional_m1_prob_distribution.csv'), index=False)
        log(f"  저장: additional_m1_prob_distribution.csv", log_lines)

    # 로그 저장
    with open(LOG_PATH, 'w', encoding='utf-8') as f:
        f.write('\n'.join(log_lines))

    log(f"\n[총 소요: {(time.time()-t_start)/60:.1f}분]", log_lines)
    log(f"결과: {OUTPUT_DIR}", log_lines)
    return True


if __name__ == "__main__":
    main()
