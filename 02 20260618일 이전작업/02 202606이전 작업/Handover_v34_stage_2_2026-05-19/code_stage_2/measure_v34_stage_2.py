# -*- coding: utf-8 -*-
"""
[파일명] measure_v34_stage_2.py
[코드길이] 약 380줄, [내부버전명] v9.0 (stage_2_new_rules)

[목적] Stage 2 측정 — 새 규칙 일괄 반영 + OB TF 그리드 (사용자/Gemini 합의)

[Grid - OB TF 4개]
  scenario_id    OB TF (분)   비고
  ─────────────────────────────────────────────
  obtf_15m       15           SMC LTF zone
  obtf_30m       30           중간
  obtf_60m       60           Stage 1 기준선
  obtf_240m      240          SMC HTF 권장값

[Fixed (Stage 2)]
  - 모든 진입 게이트: TP≥48bp, SL≥32bp, RR≥1.5
  - SL 클램프: 100bp 초과 시 100bp, TP_gate=161.8bp
  - 3단계 스텝업: 100bp/0.5, 161.8bp/0.618, 196.3bp/0.764
  - 4H timeout (240분), 스텝업 활성 거래 제외
  - 대기 진입: 최대 2H (120분)
  - Holding: 4 × OB TF (시뮬 내부 path 확보용)
  - Filter: off (Stage 1과 동일 변수 단순화)
  - Lev: 10
  
[Files used]
  tf_aggregator_v2.py
  tbm_simulator_v9.py
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
from tbm_simulator_v9 import compute_atr, batch_simulate_v9
from pautov75_signal_wrapper_v4 import extract_signals_v4, compute_atr_15m_pct_per_1m, process_signals_with_wait_v4
from Regime_Master_v2 import Regime_Master_v2


WORK_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(WORK_DIR, "..", "Merged_Data.csv")
OUTPUT_DIR = os.path.join(WORK_DIR, "outputs_stage_2")
LOG_PATH = os.path.join(OUTPUT_DIR, "measure_log.txt")

# Stage 2 그리드 - OB TF 4개
STAGE2_GRID = [
    # (scenario_id, ob_tf_minutes)
    ('obtf_15m', 15),
    ('obtf_30m', 30),
    ('obtf_60m', 60),
    ('obtf_240m', 240),
]

# Fixed
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
    """4장세 사후 분류 (Stage 1과 동일)"""
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


def compute_stats_v9(df_trades, label, regime_label='overall'):
    """v9 — 새 컬럼 반영 통계"""
    # 진입 성공 거래만 (blocked, gate_fail, wait_cancel 등 제외)
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
            'n_clamped': 0, 'step_activation_rate': 0,
            'avg_wait_minutes': 0, 'avg_rr_at_entry': 0,
            # 게이트 실패 카운트
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
    
    # 단계 활성 비율 (1+ 단계 발동된 거래)
    step_activation_rate = (df_valid['step_active_max'] >= 1).sum() / n_valid if n_valid > 0 else 0
    
    # 게이트 실패 카운트 (df_trades 전체 기준)
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
        'n_clamped': int(df_valid['sl_clamped'].sum()) if 'sl_clamped' in df_valid.columns else 0,
        'step_activation_rate': round(step_activation_rate, 4),
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
    log(f"[Stage 2 측정 시작] {pd.Timestamp.now()}", log_lines)
    log("="*70 + "\n", log_lines)
    log(f"그리드: OB TF 4개 (15/30/60/240분)", log_lines)
    for sc_id, ob_tf in STAGE2_GRID:
        log(f"  {sc_id}: OB TF {ob_tf}분", log_lines)
    log(f"\n새 규칙:", log_lines)
    log(f"  진입 게이트: TP≥48bp, SL≥32bp, RR≥1.5", log_lines)
    log(f"  SL 클램프: OB SL>100bp 시 SL=100bp, TP_gate=161.8bp", log_lines)
    log(f"  3단계 스텝업: 100bp/0.5, 161.8bp/0.618, 196.3bp/0.764", log_lines)
    log(f"  대기 진입: 최대 {WAIT_TIMEOUT_MINUTES}분 ({WAIT_TIMEOUT_MINUTES/60}H)", log_lines)
    log(f"  Timeout: 240분 (4H), 스텝업 활성 거래는 SL 끝까지 추적", log_lines)
    log(f"  Lev: {LEV}, Filter: {FILTER}", log_lines)

    # 1. 데이터 로드
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

    # 2. ATR_pct 사전 계산
    log(f"\n[2/6] 1m별 15m ATR_pct 사전 계산", log_lines)
    t_atr = time.time()
    atr_15m_pct_per_1m = compute_atr_15m_pct_per_1m(df)
    log(f"  계산 시간: {time.time()-t_atr:.1f}초", log_lines)
    log(f"  ATR_pct mean: {np.nanmean(atr_15m_pct_per_1m)*100:.4f}%", log_lines)

    # 3. ML 신호 추출 (filter=off 1번만)
    log(f"\n[3/6] ML 신호 추출 (filter=off, 1회 — 4개 시나리오 공유)", log_lines)
    t_sig = time.time()
    long_idx, short_idx, sig_stats = extract_signals_v4(
        df, atr_15m_pct_per_1m,
        threshold_long=0.35, threshold_short=0.35,
        window_size=120,
        filter_mode='off',
        rolling_lookback_minutes=ROLLING_LOOKBACK,
        start_idx=oos_start_idx,
        end_idx=oos_end_idx,
        verbose_every=200000,
    )
    log(f"  Long {len(long_idx)}, Short {len(short_idx)}, total {len(long_idx)+len(short_idx)}", log_lines)
    log(f"  추출 시간: {(time.time()-t_sig)/60:.1f}분", log_lines)
    
    # 충돌 제거
    long_idx, short_idx, wait_pre_stats = process_signals_with_wait_v4(
        long_idx, short_idx, df, None, 60, 5,
        enable_wait=ENABLE_WAIT_ENTRY,
        wait_timeout_minutes=WAIT_TIMEOUT_MINUTES,
        verbose=False,
    )
    log(f"  충돌 제거 후: Long {len(long_idx)}, Short {len(short_idx)}", log_lines)
    log(f"  충돌 제거 건수: {wait_pre_stats['n_conflict_removed']}", log_lines)

    # 4. 4장세 사후 분류
    log(f"\n[4/6] 4장세 사후 분류", log_lines)
    df_oos_only = df.iloc[oos_start_idx:oos_end_idx]
    regime_series = assign_regime_v33(df_oos_only)
    log(f"  분포: {pd.Series(regime_series).value_counts().to_dict()}", log_lines)

    # 5. TF aggregate (시나리오마다 다른 OB TF — 루프 안에서 처리)
    log(f"\n[5/6] 2h aggregate (공유)", log_lines)
    df_reset = df.reset_index()
    df_2h = aggregate_ohlcv(df_reset, 120).set_index('timestamp')
    log(f"  2h봉: {len(df_2h)}", log_lines)

    # 6. 4 시나리오 시뮬레이션
    log(f"\n[6/6] 4 시나리오 시뮬레이션", log_lines)
    all_results = []
    rm = Regime_Master_v2()

    for sc_idx, (sc_id, ob_tf_min) in enumerate(STAGE2_GRID):
        label = sc_id
        t_sc = time.time()
        log(f"  [{sc_idx+1}/4] {label} (OB TF={ob_tf_min}분)...", log_lines)

        # 시나리오별 OB TF aggregate
        df_ob = aggregate_ohlcv(df_reset, ob_tf_min).set_index('timestamp')
        atr_ob = compute_atr(df_ob['high'].values, df_ob['low'].values, df_ob['close'].values, period=20)
        log(f"    {ob_tf_min}m봉: {len(df_ob)}", log_lines)

        trades_df = batch_simulate_v9(
            long_signal_indices_1m=long_idx.tolist(),
            short_signal_indices_1m=short_idx.tolist(),
            df_1m=df, df_ob_tf=df_ob, df_2h=df_2h,
            atr_ob_tf=atr_ob,
            leverage=LEV,
            w=5, N=5,
            ob_tf_minutes=ob_tf_min,
            enable_2h_reversal=True,
            regime_master=rm,
            enable_wait_entry=ENABLE_WAIT_ENTRY,
            wait_timeout_minutes=WAIT_TIMEOUT_MINUTES,
            verbose=False,
        )

        # 4장세 분류
        trades_df['regime'] = trades_df['entry_signal_idx_1m'].apply(
            lambda x: regime_series[x - oos_start_idx] if 0 <= x - oos_start_idx < len(regime_series) else 'unknown'
        )

        stats_overall = compute_stats_v9(trades_df, label, 'overall')
        all_results.append(stats_overall)

        # 4장세별
        for reg in ['uptrend','downtrend','hivol_range','lovol_range']:
            sub = trades_df[trades_df['regime']==reg]
            if len(sub) > 0:
                sub_stats = compute_stats_v9(sub, label, reg)
                all_results.append(sub_stats)
        
        # side별 (long/short)
        for s in ['long','short']:
            sub_side = trades_df[trades_df['side']==s]
            if len(sub_side) > 0:
                side_stats = compute_stats_v9(sub_side, label, f'side_{s}')
                all_results.append(side_stats)

        # 시나리오별 trade log
        trade_path = os.path.join(OUTPUT_DIR, f"trades_{label}.csv")
        trades_df.to_csv(trade_path, index=False)

        t_elapsed = time.time() - t_sc
        log(f"    n_valid={stats_overall['n_valid']}, pf={stats_overall['pf']}, "
            f"win={stats_overall['win_rate']:.3f}, "
            f"step_act={stats_overall['step_activation_rate']:.3f}, "
            f"clamped={stats_overall['n_clamped']}, "
            f"wait_cancel={stats_overall['n_wait_cancel']}, "
            f"({t_elapsed:.1f}s = {t_elapsed/60:.1f}분)", log_lines)

    # 결과 저장
    df_summary = pd.DataFrame(all_results)
    summary_path = os.path.join(OUTPUT_DIR, "all_scenarios_stage_2.csv")
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
        log(df_break[['scenario','n_valid','pf','win_rate','net_sum','step_activation_rate']].to_string(index=False), log_lines)

    t_total = time.time() - t_start
    log(f"\n[총 소요: {t_total:.1f}초 = {t_total/60:.1f}분 = {t_total/3600:.2f}시간]", log_lines)

    with open(LOG_PATH, 'w', encoding='utf-8') as f:
        f.write('\n'.join(log_lines))

    return df_summary


if __name__ == "__main__":
    main()
