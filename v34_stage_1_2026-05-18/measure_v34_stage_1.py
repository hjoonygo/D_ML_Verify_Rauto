# -*- coding: utf-8 -*-
"""
[FILE] measure_v34_stage_1.py
[Length] ~340 lines, [Version] v8.0 (stage_1)

[Purpose] Stage 1 측정 - 안 X 그리드 9개 시나리오 (fib_trigger × SL multi).

[Grid - 안 X (SL >= fib 조건 충족 9개)]
  fib_trigger_atr_multi  SL atr_multiplier
  ─────────────────────────────────────────
  0.5                    1.0
  0.5                    1.5
  0.5                    2.0
  1.0                    1.0  (SL = fib)
  1.0                    1.5
  1.0                    2.0
  1.5                    1.5  (SL = fib)
  1.5                    2.0
  2.0                    2.0  (SL = fib)

[Fixed]
  - OB TF: 60m
  - Holding: 28 bars
  - Filter: off (안 D 비활성, 변수 단순화)
  - Lev: 10
  - Rolling lookback: 14 days

[Data]
  DATA: ../Merged_Data.csv
  MODEL: PautoV75_XGB_3class_v2.json (재학습 안 함, Phase B와 동일)
  OUTPUT: outputs_stage_1/

[Files used]
  tf_aggregator_v2.py
  tbm_simulator_v8.py
  pautov75_signal_wrapper_v3.py (filter='off' 사용)
  Regime_Master_v2.py
"""
import os
import sys
import time
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tf_aggregator_v2 import aggregate_ohlcv
from tbm_simulator_v8 import compute_atr, batch_simulate_v8
from pautov75_signal_wrapper_v3 import extract_signals_v3, compute_atr_15m_pct_per_1m
from Regime_Master_v2 import Regime_Master_v2


WORK_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(WORK_DIR, "..", "Merged_Data.csv")
OUTPUT_DIR = os.path.join(WORK_DIR, "outputs_stage_1")
LOG_PATH = os.path.join(OUTPUT_DIR, "measure_log.txt")

# Stage 1 그리드 - 안 X (SL >= fib 조건)
STAGE1_GRID = [
    # (fib_trigger_atr_multi, sl_atr_multiplier)
    (0.5, 1.0),
    (0.5, 1.5),
    (0.5, 2.0),
    (1.0, 1.0),
    (1.0, 1.5),
    (1.0, 2.0),
    (1.5, 1.5),
    (1.5, 2.0),
    (2.0, 2.0),
]

# Fixed
OB_TF = 60
HOLDING = 28
LEV = 10
FILTER = 'off'
ROLLING_LOOKBACK = 14 * 1440
TRAIN_RATIO = 0.70


def log(msg, log_lines):
    print(msg)
    log_lines.append(msg)


def assign_regime_v33(df_1m):
    """4장세 사후 분류"""
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


def compute_stats(df_trades, label, regime_label='overall'):
    df_valid = df_trades[df_trades['exit_reason'].notna() & (df_trades['exit_reason'] != 'blocked_single_pos')].copy()
    n_valid = len(df_valid)
    if n_valid == 0:
        return {
            'scenario': label, 'regime': regime_label,
            'n_valid': 0, 'pf': 0, 'win_rate': 0,
            'net_sum': 0, 'avg_return': 0, 'mdd_pct': 0, 'sharpe': 0,
            'n_fib_lock': 0, 'n_hard_sl': 0, 'n_sl': 0, 'n_ratchet_sl': 0,
            'n_timeout': 0, 'n_reversal_2h': 0, 'n_no_tp_ob': 0, 'n_gate_fail': 0,
            'avg_dynamic_sl_dist': 0, 'avg_fib_trigger_dist': 0, 'avg_atr_pct_at_entry': 0,
            'fib_lock_activation_rate': 0,
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
    avg_sl_dist = df_valid['dynamic_sl_dist'].mean() if 'dynamic_sl_dist' in df_valid.columns else 0
    avg_fib = df_valid['fib_trigger_dist'].mean() if 'fib_trigger_dist' in df_valid.columns else 0
    avg_atr = df_valid['atr_pct_at_entry'].mean() if 'atr_pct_at_entry' in df_valid.columns else 0
    
    # ★ phase2 활성 비율 (fib_lock 발동률)
    if 'phase2_active' in df_valid.columns:
        phase2_rate = df_valid['phase2_active'].sum() / n_valid
    else:
        phase2_rate = 0

    return {
        'scenario': label, 'regime': regime_label,
        'n_valid': n_valid,
        'pf': round(pf, 3),
        'win_rate': round(win_rate, 4),
        'net_sum': round(nets.sum(), 4),
        'avg_return': round(nets.mean(), 5),
        'mdd_pct': round(mdd * 100, 3),
        'sharpe': round(sharpe, 3),
        'n_fib_lock': int(reasons.get('fib_lock', 0)),
        'n_hard_sl': int(reasons.get('hard_sl', 0)),
        'n_sl': int(reasons.get('sl', 0)),
        'n_ratchet_sl': int(reasons.get('ratchet_sl', 0)),
        'n_timeout': int(reasons.get('timeout_no_ob', 0)) + int(reasons.get('timeout_after_ob', 0)),
        'n_reversal_2h': int(reasons.get('reversal_2h', 0)),
        'n_no_tp_ob': int(reasons.get('no_tp_ob', 0)),
        'n_gate_fail': int(reasons.get('tp_gate_fail', 0)) + int(reasons.get('sl_gate_fail', 0)),
        'avg_dynamic_sl_dist': round(avg_sl_dist, 5) if avg_sl_dist else 0,
        'avg_fib_trigger_dist': round(avg_fib, 5) if avg_fib else 0,
        'avg_atr_pct_at_entry': round(avg_atr, 5) if avg_atr else 0,
        'fib_lock_activation_rate': round(phase2_rate, 4),
    }


def main():
    t_start = time.time()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    log_lines = []

    log("\n" + "="*70, log_lines)
    log(f"[Stage 1 측정 시작] {pd.Timestamp.now()}", log_lines)
    log("="*70 + "\n", log_lines)
    log(f"그리드: 안 X 9개 시나리오 (fib_trigger × SL multi)", log_lines)
    for i, (fib, sl) in enumerate(STAGE1_GRID):
        log(f"  S{i+1}. fib_trigger=ATR×{fib}, SL=ATR×{sl}", log_lines)
    log(f"\n고정: OB TF {OB_TF}m, Holding {HOLDING}, Lev {LEV}, Filter {FILTER}", log_lines)

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
    log(f"\n[3/6] ML 신호 추출 (filter=off, 1회)", log_lines)
    t_sig = time.time()
    long_idx, short_idx, sig_stats = extract_signals_v3(
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

    # 4. 4장세 사후 분류
    log(f"\n[4/6] 4장세 사후 분류", log_lines)
    df_oos_only = df.iloc[oos_start_idx:oos_end_idx]
    regime_series = assign_regime_v33(df_oos_only)
    log(f"  분포: {pd.Series(regime_series).value_counts().to_dict()}", log_lines)

    # 5. TF aggregate
    log(f"\n[5/6] TF aggregate", log_lines)
    df_reset = df.reset_index()
    df_2h = aggregate_ohlcv(df_reset, 120).set_index('timestamp')
    df_ob = aggregate_ohlcv(df_reset, OB_TF).set_index('timestamp')
    atr_ob = compute_atr(df_ob['high'].values, df_ob['low'].values, df_ob['close'].values, period=20)
    log(f"  2h봉: {len(df_2h)}, {OB_TF}m봉: {len(df_ob)}", log_lines)

    # 6. 9 시나리오 시뮬레이션
    log(f"\n[6/6] 9 시나리오 시뮬레이션", log_lines)
    all_results = []
    rm = Regime_Master_v2()

    for sc_idx, (fib_multi, sl_multi) in enumerate(STAGE1_GRID):
        label = f"fib{fib_multi}_sl{sl_multi}"
        t_sc = time.time()
        log(f"  [{sc_idx+1}/9] {label}...", log_lines)

        trades_df = batch_simulate_v8(
            long_signal_indices_1m=long_idx.tolist(),
            short_signal_indices_1m=short_idx.tolist(),
            df_1m=df, df_ob_tf=df_ob, df_2h=df_2h,
            atr_ob_tf=atr_ob,
            atr_15m_pct_per_1m=atr_15m_pct_per_1m,
            leverage=LEV,
            w=5, N=5,
            timeout_bars_ob_tf=HOLDING,
            ob_tf_minutes=OB_TF,
            enable_2h_reversal=True,
            regime_master=rm,
            atr_multiplier=sl_multi,
            use_dynamic_hard_sl=True,
            fib_trigger_atr_multi=fib_multi,
            verbose=False,
        )

        # 4장세 분류
        trades_df['regime'] = trades_df['entry_signal_idx_1m'].apply(
            lambda x: regime_series[x - oos_start_idx] if 0 <= x - oos_start_idx < len(regime_series) else 'unknown'
        )

        stats_overall = compute_stats(trades_df, label, 'overall')
        all_results.append(stats_overall)

        # 4장세별
        for reg in ['uptrend','downtrend','hivol_range','lovol_range']:
            sub = trades_df[trades_df['regime']==reg]
            if len(sub) > 0:
                sub_stats = compute_stats(sub, label, reg)
                all_results.append(sub_stats)

        # 시나리오별 trade log
        trade_path = os.path.join(OUTPUT_DIR, f"trades_{label}.csv")
        trades_df.to_csv(trade_path, index=False)

        t_elapsed = time.time() - t_sc
        log(f"    n_valid={stats_overall['n_valid']}, pf={stats_overall['pf']}, "
            f"win={stats_overall['win_rate']:.3f}, fib_lock={stats_overall['n_fib_lock']}, "
            f"fib_act_rate={stats_overall['fib_lock_activation_rate']:.3f}, "
            f"hard_sl={stats_overall['n_hard_sl']}, ratchet={stats_overall['n_ratchet_sl']}, "
            f"({t_elapsed:.1f}s)", log_lines)

    # 결과 저장
    df_summary = pd.DataFrame(all_results)
    summary_path = os.path.join(OUTPUT_DIR, "all_scenarios_stage_1.csv")
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
        log(df_break[['scenario','n_valid','pf','win_rate','net_sum','n_fib_lock','fib_lock_activation_rate']].to_string(index=False), log_lines)

    t_total = time.time() - t_start
    log(f"\n[총 소요: {t_total:.1f}초 = {t_total/60:.1f}분 = {t_total/3600:.2f}시간]", log_lines)

    with open(LOG_PATH, 'w', encoding='utf-8') as f:
        f.write('\n'.join(log_lines))

    return df_summary


if __name__ == "__main__":
    main()
