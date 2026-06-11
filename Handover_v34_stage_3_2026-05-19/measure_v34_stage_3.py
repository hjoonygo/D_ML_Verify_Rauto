# -*- coding: utf-8 -*-
"""
[파일명] measure_v34_stage_3.py
[코드길이] 약 380줄, [내부버전명] v10.0 (stage_3_dynamic_sl)

[목적] Stage 3 측정 — 유동 SL 효과 검증, 4개 SL_MAX 그리드

[Grid - SL_MAX 4개 (Stage 2 60m 기준선 + 유동 SL)]
  scenario_id        sl_max     비고
  ─────────────────────────────────────────────
  sl_fixed_100bp     0.0100     베이스라인 — Stage 2와 동일 (고정 100bp)
                                실제로는 ATR 기반이지만 상한 100bp로 강제
  sl_max_120bp       0.0120     상한 120bp (보수적)
  sl_max_150bp       0.0150     상한 150bp (기본 권장)
  sl_max_180bp       0.0180     상한 180bp (공격적)

[Fixed (Stage 3)]
  - OB TF: 60m (Stage 2에서 가장 좋았던 값)
  - 진입 게이트: TP≥48bp, SL≥32bp, RR≥1.5
  - 유동 SL 로직:
    ATR_pct < 0.25%: mult 3.5
    0.25% ≤ ATR < 0.45%: mult 3.0
    ATR_pct ≥ 0.45%: mult 2.0
  - OB SL과 ATR SL 중 더 작은 쪽 사용 (보수적)
  - 3단계 스텝업: 100bp/0.5, 161.8bp/0.618, 196.3bp/0.764 (변경 없음)
  - 4H timeout (240분), 대기 진입 2H
  - Lev: 10, Filter: off
  
[Files used]
  tf_aggregator_v2.py
  tbm_simulator_v10.py
  pautov75_signal_wrapper_v4.py
  Regime_Master_v2.py
"""
import os
import sys
import time
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tf_aggregator_v2 import aggregate_ohlcv
from tbm_simulator_v10 import compute_atr, batch_simulate_v10
from pautov75_signal_wrapper_v4 import extract_signals_v4, compute_atr_15m_pct_per_1m, process_signals_with_wait_v4
from Regime_Master_v2 import Regime_Master_v2


WORK_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(WORK_DIR, "..", "Merged_Data.csv")
OUTPUT_DIR = os.path.join(WORK_DIR, "outputs_stage_3")
LOG_PATH = os.path.join(OUTPUT_DIR, "measure_log.txt")

# Stage 3 그리드 - SL_MAX 4개
STAGE3_GRID = [
    ('sl_fixed_100bp', 0.0100),    # 베이스라인 (Stage 2 비교)
    ('sl_max_120bp', 0.0120),
    ('sl_max_150bp', 0.0150),      # 기본 권장
    ('sl_max_180bp', 0.0180),
]

# Fixed (Stage 3)
OB_TF = 60
LEV = 10
FILTER = 'off'
ROLLING_LOOKBACK = 14 * 1440
TRAIN_RATIO = 0.70
ENABLE_WAIT_ENTRY = True
WAIT_TIMEOUT_MINUTES = 120  # 2H


def log(msg, log_lines):
    print(msg)
    log_lines.append(msg)


def assign_regime_v33(df_1m):
    """4장세 사후 분류 (Stage 1/2와 동일)"""
    close = df_1m['close'].values
    ema_60 = pd.Series(close).ewm(span=60, adjust=False).mean().values
    ema_240 = pd.Series(close).ewm(span=240, adjust=False).mean().values
    atr = pd.Series((df_1m['high'] - df_1m['low']).values).rolling(60).mean().fillna(0).values
    atr_pct = atr / close * 100
    atr_med = np.nanmedian(atr_pct[atr_pct > 0]) if (atr_pct > 0).any() else 0.1

    regime = np.full(len(df_1m), "lovol_range", dtype=object)
    is_up = ema_60 > ema_240
    is_down = ema_60 < ema_240
    is_hivol = atr_pct > atr_med * 1.5
    is_lovol = atr_pct < atr_med * 0.5

    regime[is_up & ~is_hivol & ~is_lovol] = "uptrend"
    regime[is_down & ~is_hivol & ~is_lovol] = "downtrend"
    regime[is_hivol] = "hivol_range"
    return regime


def compute_stats_v10(df_trades, label, regime_label='overall'):
    """v10 — 유동 SL 신규 컬럼 반영 통계"""
    valid_exits = ['initial_sl', 'step1_sl', 'step2_sl', 'step3_sl', 
                   'timeout_4h', 'timeout_step_active', 'reversal_2h']
    df_valid = df_trades[df_trades['exit_reason'].isin(valid_exits)].copy()
    n_valid = len(df_valid)
    
    if n_valid == 0:
        return {
            'scenario': label, 'regime': regime_label,
            'n_valid': 0, 'pf': 0, 'win_rate': 0,
            'net_sum': 0, 'avg_return': 0, 'mdd_pct': 0, 'sharpe': 0,
            'n_initial_sl': 0, 'n_step1_sl': 0, 'n_step2_sl': 0, 'n_step3_sl': 0,
            'n_timeout_4h': 0, 'n_timeout_step_active': 0, 'n_reversal_2h': 0,
            'step_activation_rate': 0,
            'avg_initial_sl_dist_bp': 0,
            'avg_atr_pct_at_entry': 0,
            'n_sl_method_atr': 0, 'n_sl_method_ob': 0,
            'avg_multiplier': 0,
            'avg_wait_minutes': 0, 'avg_rr_at_entry': 0,
            'n_blocked': 0, 'n_gate_fail': 0, 'n_wait_cancel': 0, 'n_wait_timeout': 0,
        }

    nets = df_valid['net_return'].values
    wins = nets[nets > 0]
    losses = nets[nets <= 0]
    pf = wins.sum() / abs(losses.sum()) if abs(losses.sum()) > 0 else float('inf')
    win_rate = len(wins) / n_valid

    cum = nets.cumsum()
    running_max = np.maximum.accumulate(cum)
    dd = cum - running_max
    mdd = dd.min()

    sharpe = nets.mean() / nets.std() * np.sqrt(252 * 24 * 60 / 60) if nets.std() > 0 else 0

    reasons = df_valid['exit_reason'].value_counts()
    step_activation_rate = (df_valid['step_active_max'] >= 1).sum() / n_valid if n_valid > 0 else 0
    
    n_sl_method_atr = (df_valid['sl_method'] == 'atr_dynamic').sum() if 'sl_method' in df_valid.columns else 0
    n_sl_method_ob = (df_valid['sl_method'] == 'ob_natural').sum() if 'sl_method' in df_valid.columns else 0
    avg_mult = df_valid['multiplier_used'].mean() if 'multiplier_used' in df_valid.columns and df_valid['multiplier_used'].notna().any() else 0
    avg_atr = df_valid['atr_pct_at_entry'].mean() if 'atr_pct_at_entry' in df_valid.columns and df_valid['atr_pct_at_entry'].notna().any() else 0
    avg_sl_dist_bp = df_valid['initial_sl_dist'].mean() * 10000 if 'initial_sl_dist' in df_valid.columns else 0
    
    all_reasons = df_trades['exit_reason'].value_counts()
    n_blocked = int(all_reasons.get('blocked_single_pos', 0))
    n_gate_fail = (int(all_reasons.get('sl_gate_fail', 0)) + int(all_reasons.get('tp_gate_fail', 0))
                   + int(all_reasons.get('rr_gate_fail', 0)))
    n_wait_cancel = (int(all_reasons.get('wait_cancel_no_signal', 0))
                     + int(all_reasons.get('wait_cancel_opposite_signal', 0)))
    n_wait_timeout = int(all_reasons.get('wait_timeout', 0))

    return {
        'scenario': label, 'regime': regime_label,
        'n_valid': n_valid,
        'pf': round(pf, 3),
        'win_rate': round(win_rate, 4),
        'net_sum': round(nets.sum(), 4),
        'avg_return': round(nets.mean(), 5),
        'mdd_pct': round(mdd * 100, 3),
        'sharpe': round(sharpe, 3),
        'n_initial_sl': int(reasons.get('initial_sl', 0)),
        'n_step1_sl': int(reasons.get('step1_sl', 0)),
        'n_step2_sl': int(reasons.get('step2_sl', 0)),
        'n_step3_sl': int(reasons.get('step3_sl', 0)),
        'n_timeout_4h': int(reasons.get('timeout_4h', 0)),
        'n_timeout_step_active': int(reasons.get('timeout_step_active', 0)),
        'n_reversal_2h': int(reasons.get('reversal_2h', 0)),
        'step_activation_rate': round(step_activation_rate, 4),
        'avg_initial_sl_dist_bp': round(avg_sl_dist_bp, 1),
        'avg_atr_pct_at_entry': round(avg_atr, 5),
        'n_sl_method_atr': int(n_sl_method_atr),
        'n_sl_method_ob': int(n_sl_method_ob),
        'avg_multiplier': round(avg_mult, 3) if avg_mult else 0,
        'avg_wait_minutes': round(df_valid['wait_minutes'].mean(), 2) if 'wait_minutes' in df_valid.columns else 0,
        'avg_rr_at_entry': round(df_valid['rr_at_entry'].mean(), 3) if 'rr_at_entry' in df_valid.columns and df_valid['rr_at_entry'].notna().any() else 0,
        'n_blocked': n_blocked,
        'n_gate_fail': n_gate_fail,
        'n_wait_cancel': n_wait_cancel,
        'n_wait_timeout': n_wait_timeout,
    }


def main():
    t_start = time.time()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    log_lines = []

    log("\n" + "="*70, log_lines)
    log(f"[Stage 3 측정 시작] {pd.Timestamp.now()}", log_lines)
    log("="*70 + "\n", log_lines)
    log(f"그리드: SL_MAX 4개", log_lines)
    for sc_id, sl_max in STAGE3_GRID:
        log(f"  {sc_id}: SL_MAX={sl_max*10000:.0f}bp", log_lines)
    log(f"\nStage 3 새 규칙:", log_lines)
    log(f"  유동 SL = atr_pct_at_entry × multiplier", log_lines)
    log(f"  multiplier: 저변동(ATR<0.25%) 3.5 / 중변동 3.0 / 고변동(ATR>=0.45%) 2.0", log_lines)
    log(f"  SL 거리 = max(32bp, min(SL_MAX, ATR x multiplier))", log_lines)
    log(f"  OB SL과 ATR SL 충돌 시 더 작은 쪽 사용 (보수적)", log_lines)
    log(f"\n고정: OB TF {OB_TF}m, Lev {LEV}, Filter {FILTER}", log_lines)

    if not os.path.exists(DATA_PATH):
        log(f"X 데이터 파일 없음: {DATA_PATH}", log_lines)
        return

    log(f"\n[1/6] 데이터 로드", log_lines)
    df = pd.read_csv(DATA_PATH, parse_dates=['timestamp']).set_index('timestamp')
    if df.index.tz is None:
        df.index = df.index.tz_localize('UTC')
    log(f"  전체: {df.index.min()} ~ {df.index.max()} ({len(df):,}봉)", log_lines)

    n_train = int(len(df) * TRAIN_RATIO)
    oos_start_idx = n_train
    oos_end_idx = len(df)
    log(f"  OOS: idx {oos_start_idx}~{oos_end_idx-1} ({oos_end_idx-oos_start_idx:,}봉)", log_lines)

    log(f"\n[2/6] 1m별 15m ATR_pct 사전 계산", log_lines)
    t_atr = time.time()
    atr_15m_pct_per_1m = compute_atr_15m_pct_per_1m(df)
    log(f"  계산 시간: {time.time()-t_atr:.1f}초", log_lines)
    log(f"  ATR_pct mean: {np.nanmean(atr_15m_pct_per_1m)*100:.4f}%", log_lines)
    log(f"  -> SL 유동화에 사용됨", log_lines)

    # 3. ML 신호 추출 (캐시 확인 — Stage 2 캐시도 사용 가능)
    cache_path = os.path.join(WORK_DIR, "signals_cache_stage_3.pkl")
    cache_path_s2 = os.path.join(WORK_DIR, "signals_cache.pkl")  # Stage 2 호환
    
    cache_to_use = None
    if os.path.exists(cache_path):
        cache_to_use = cache_path
    elif os.path.exists(cache_path_s2):
        cache_to_use = cache_path_s2
        log(f"  Stage 2 캐시 발견, 재사용", log_lines)
    
    if cache_to_use is not None:
        log(f"\n[3/6] ML 신호 캐시 로드: {cache_to_use}", log_lines)
        import pickle
        with open(cache_to_use, 'rb') as f:
            cached = pickle.load(f)
        long_idx = cached['long_idx']
        short_idx = cached['short_idx']
        log(f"  Long {len(long_idx)}, Short {len(short_idx)}", log_lines)
    else:
        log(f"\n[3/6] ML 신호 추출 (filter=off, 1회 — 4개 시나리오 공유)", log_lines)
        t_sig = time.time()
        long_idx_raw, short_idx_raw, sig_stats = extract_signals_v4(
            df, atr_15m_pct_per_1m,
            threshold_long=0.35, threshold_short=0.35,
            window_size=120,
            filter_mode='off',
            rolling_lookback_minutes=ROLLING_LOOKBACK,
            start_idx=oos_start_idx,
            end_idx=oos_end_idx,
            verbose_every=200000,
        )
        log(f"  Long {len(long_idx_raw)}, Short {len(short_idx_raw)}", log_lines)
        log(f"  추출 시간: {(time.time()-t_sig)/60:.1f}분", log_lines)
        
        long_idx, short_idx, _ = process_signals_with_wait_v4(
            long_idx_raw, short_idx_raw, df, None, OB_TF, 5,
            enable_wait=ENABLE_WAIT_ENTRY,
            wait_timeout_minutes=WAIT_TIMEOUT_MINUTES,
            verbose=False,
        )
        log(f"  충돌 제거 후: Long {len(long_idx)}, Short {len(short_idx)}", log_lines)
        
        import pickle
        with open(cache_path, 'wb') as f:
            pickle.dump({'long_idx': long_idx, 'short_idx': short_idx}, f)
        log(f"  캐시 저장: {cache_path}", log_lines)

    log(f"\n[4/6] 4장세 사후 분류", log_lines)
    df_oos_only = df.iloc[oos_start_idx:oos_end_idx]
    regime_series = assign_regime_v33(df_oos_only)
    log(f"  분포: {pd.Series(regime_series).value_counts().to_dict()}", log_lines)

    log(f"\n[5/6] TF aggregate (60m + 2h)", log_lines)
    df_reset = df.reset_index()
    df_2h = aggregate_ohlcv(df_reset, 120).set_index('timestamp')
    df_ob = aggregate_ohlcv(df_reset, OB_TF).set_index('timestamp')
    atr_ob = compute_atr(df_ob['high'].values, df_ob['low'].values, df_ob['close'].values, period=20)
    log(f"  2h봉: {len(df_2h)}, {OB_TF}m봉: {len(df_ob)}", log_lines)

    log(f"\n[6/6] 4 시나리오 시뮬레이션 (OB TF 60m 고정, SL_MAX 그리드)", log_lines)
    all_results = []
    rm = Regime_Master_v2()

    for sc_idx, (sc_id, sl_max) in enumerate(STAGE3_GRID):
        label = sc_id
        t_sc = time.time()
        log(f"  [{sc_idx+1}/4] {label} (SL_MAX={sl_max*10000:.0f}bp)...", log_lines)

        trades_df = batch_simulate_v10(
            long_signal_indices_1m=long_idx.tolist(),
            short_signal_indices_1m=short_idx.tolist(),
            df_1m=df, df_ob_tf=df_ob, df_2h=df_2h,
            atr_ob_tf=atr_ob,
            atr_15m_pct_per_1m=atr_15m_pct_per_1m,
            sl_max=sl_max,
            leverage=LEV,
            w=5, N=5,
            ob_tf_minutes=OB_TF,
            enable_2h_reversal=True,
            regime_master=rm,
            enable_wait_entry=ENABLE_WAIT_ENTRY,
            wait_timeout_minutes=WAIT_TIMEOUT_MINUTES,
            verbose=False,
        )

        trades_df['regime'] = trades_df['entry_signal_idx_1m'].apply(
            lambda x: regime_series[x - oos_start_idx] if 0 <= x - oos_start_idx < len(regime_series) else 'unknown'
        )

        stats_overall = compute_stats_v10(trades_df, label, 'overall')
        all_results.append(stats_overall)

        for reg in ['uptrend','downtrend','hivol_range','lovol_range']:
            sub = trades_df[trades_df['regime']==reg]
            if len(sub) > 0:
                sub_stats = compute_stats_v10(sub, label, reg)
                all_results.append(sub_stats)
        
        for s in ['long','short']:
            sub_side = trades_df[trades_df['side']==s]
            if len(sub_side) > 0:
                side_stats = compute_stats_v10(sub_side, label, f'side_{s}')
                all_results.append(side_stats)

        trade_path = os.path.join(OUTPUT_DIR, f"trades_{label}.csv")
        trades_df.to_csv(trade_path, index=False)

        t_elapsed = time.time() - t_sc
        log(f"    n_valid={stats_overall['n_valid']}, pf={stats_overall['pf']}, "
            f"win={stats_overall['win_rate']:.3f}, "
            f"step_act={stats_overall['step_activation_rate']:.3f}, "
            f"avg_SL={stats_overall['avg_initial_sl_dist_bp']:.0f}bp, "
            f"atr_dyn={stats_overall['n_sl_method_atr']} ob_nat={stats_overall['n_sl_method_ob']}, "
            f"({t_elapsed:.1f}s)", log_lines)

    df_summary = pd.DataFrame(all_results)
    summary_path = os.path.join(OUTPUT_DIR, "all_scenarios_stage_3.csv")
    df_summary.to_csv(summary_path, index=False, encoding='utf-8-sig')
    log(f"\n  요약: {summary_path}", log_lines)

    df_overall = df_summary[df_summary['regime']=='overall']
    df_alpha = df_overall[(df_overall['pf']>=1.3) & (df_overall['n_valid']>=30)]
    log(f"\n[알파 후보 (PF>=1.3, n>=30, overall)]: {len(df_alpha)}건", log_lines)
    if len(df_alpha)>0:
        log(df_alpha.to_string(index=False), log_lines)

    df_break = df_overall[df_overall['pf']>=1.0]
    log(f"\n[본전 이상 (PF>=1.0, overall)]: {len(df_break)}건", log_lines)
    if len(df_break)>0:
        log(df_break[['scenario','n_valid','pf','win_rate','net_sum','step_activation_rate','avg_initial_sl_dist_bp']].to_string(index=False), log_lines)

    t_total = time.time() - t_start
    log(f"\n[총 소요: {t_total:.1f}초 = {t_total/60:.1f}분]", log_lines)

    with open(LOG_PATH, 'w', encoding='utf-8') as f:
        f.write('\n'.join(log_lines))

    return df_summary


if __name__ == "__main__":
    main()
