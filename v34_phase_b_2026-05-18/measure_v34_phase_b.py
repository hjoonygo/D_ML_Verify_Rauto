# -*- coding: utf-8 -*-
"""
[파일명] measure_v34_phase_b.py
코드길이: 약 320줄, 내부버전명: v7.0 (phase_b), 로직 축약/생략 없이 전체 출력

[목적] Phase B 사용자 PC 36mo 실측 — 안 A+D 12 그리드.
       Phase A 합성 데이터에서 작동 확인 완료. 실측 검증.

[그리드 (Phase A → Phase B 변경)]
  Phase A: ATR multi [1.5, 2.0, 3.0] × Lev [5, 10, 15] × Filter 3개 = 27 시나리오
  Phase B: ATR multi [1.5, 2.0, 2.5, 3.0] × Lev [10] 고정 × Filter 3개 = 12 시나리오
  
  ★ 변경 이유 (사용자 결정):
    - Lev 5/10/15 동일 결과 이슈 (max 로직)는 보류
    - Lev = 10 고정 → 자본 ROE 일관
    - ATR multi에 2.5 신규 추가 → 1.5와 3.0 사이 sweet spot 탐색

[고정 변수]
  - OB TF: 60m
  - Holding: 28봉
  - fib_trigger: 1.2%
  - Rolling lookback: 14일 (20,160분)
  - Leverage: 10
  - 학습 IS: 첫 70% / OOS 30%

[데이터 경로 (Windows 가정)]
  DATA_PATH: D:\\ML\\Verify\\Merged_Data.csv
  MODEL_PATH: D:\\ML\\Verify\\PautoV75_XGB_3class_v2.json
  OUTPUT_DIR: D:\\ML\\Verify\\v34_phase_b_2026-05-18\\outputs_phase_b\\

[사용 파일]
  ML_Predictor_Pipeline_v2.py (학습)
  Predict_ML_v2.py (추론)
  Regime_Master_v2.py (장세)
  tf_aggregator_v2.py (TF 변환)
  ob_provider_v2.py (OB 검출)
  tbm_simulator_v7.py (안 A 동적 SL)
  pautov75_signal_wrapper_v3.py (안 D 필터)
"""
import os
import sys
import time
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tf_aggregator_v2 import aggregate_ohlcv
from tbm_simulator_v7 import compute_atr, batch_simulate_v7
from pautov75_signal_wrapper_v3 import extract_signals_v3, compute_atr_15m_pct_per_1m
from Regime_Master_v2 import Regime_Master_v2


# ============================================================
# 경로 설정 (사용자 PC Windows 환경)
# ============================================================
WORK_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(WORK_DIR, "..", "Merged_Data.csv")
OUTPUT_DIR = os.path.join(WORK_DIR, "outputs_phase_b")
LOG_PATH = os.path.join(OUTPUT_DIR, "measure_log.txt")

# ============================================================
# Phase B 그리드 (사용자 결정)
# ============================================================
ATR_MULTIPLIER_LIST = [1.5, 2.0, 2.5, 3.0]  # 4개 (2.5 신규)
LEV_LIST = [10]                              # 고정 (이전 27 그리드에서 축약)
FILTER_LIST = ['off', 'p20_p80', 'p10_p90']  # 3개

# 고정
OB_TF = 60          # OB TF 60m (v34 best)
HOLDING = 28        # Holding 28봉 (v34 best)
ROLLING_LOOKBACK = 14 * 1440  # 14일 = 20,160분

# OOS 비율 (학습 70% / OOS 30%)
TRAIN_RATIO = 0.70


def log(msg, log_lines):
    print(msg)
    log_lines.append(msg)


def assign_regime_v33(df_1m):
    """4장세 사후 분류 (uptrend/downtrend/hivol_range/lovol_range)"""
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
    """v6 측정과 동일"""
    df_valid = df_trades[df_trades['exit_reason'].notna() & (df_trades['exit_reason'] != 'blocked_single_pos')].copy()
    n_valid = len(df_valid)
    if n_valid == 0:
        return {
            'scenario': label, 'regime': regime_label,
            'n_valid': 0, 'pf': 0, 'win_rate': 0,
            'net_sum': 0, 'avg_return': 0, 'mdd_pct': 0, 'sharpe': 0,
            'n_fib_lock': 0, 'n_hard_sl': 0, 'n_sl': 0, 'n_ob_partial': 0, 'n_timeout': 0,
            'n_reversal_2h': 0, 'n_no_tp_ob': 0, 'n_gate_fail': 0,
            'avg_dynamic_sl_dist': 0, 'avg_atr_pct_at_entry': 0,
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
    avg_atr = df_valid['atr_pct_at_entry'].mean() if 'atr_pct_at_entry' in df_valid.columns else 0

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
        'n_sl': int(reasons.get('sl', 0)) + int(reasons.get('ratchet_sl', 0)),
        'n_ob_partial': int(reasons.get('timeout_after_ob', 0)),
        'n_timeout': int(reasons.get('timeout_no_ob', 0)) + int(reasons.get('timeout_after_ob', 0)),
        'n_reversal_2h': int(reasons.get('reversal_2h', 0)),
        'n_no_tp_ob': int(reasons.get('no_tp_ob', 0)),
        'n_gate_fail': int(reasons.get('tp_gate_fail', 0)) + int(reasons.get('sl_gate_fail', 0)),
        'avg_dynamic_sl_dist': round(avg_sl_dist, 5) if avg_sl_dist else 0,
        'avg_atr_pct_at_entry': round(avg_atr, 5) if avg_atr else 0,
    }


def main():
    t_start = time.time()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    log_lines = []

    log(f"\n{'='*70}", log_lines)
    log(f"[Phase B 측정 시작] {pd.Timestamp.now()}", log_lines)
    log(f"{'='*70}\n", log_lines)
    log(f"그리드: ATR_multi {ATR_MULTIPLIER_LIST} × Lev {LEV_LIST} × Filter {FILTER_LIST} = {len(ATR_MULTIPLIER_LIST)*len(LEV_LIST)*len(FILTER_LIST)} 시나리오", log_lines)
    log(f"고정: OB TF {OB_TF}m, Holding {HOLDING}봉, Rolling lookback {ROLLING_LOOKBACK//1440}일", log_lines)
    log(f"학습/OOS 비율: {TRAIN_RATIO*100:.0f}% / {(1-TRAIN_RATIO)*100:.0f}%\n", log_lines)

    # 1. 데이터 로드
    if not os.path.exists(DATA_PATH):
        log(f"❌ {DATA_PATH} 없음. D:\\ML\\Verify\\Merged_Data.csv 확인하세요.", log_lines)
        return

    log(f"[1/6] 데이터 로드: {DATA_PATH}", log_lines)
    df = pd.read_csv(DATA_PATH, parse_dates=['timestamp']).set_index('timestamp')
    
    # tz 처리
    if df.index.tz is None:
        df.index = df.index.tz_localize('UTC')
    
    log(f"  전체: {df.index.min()} ~ {df.index.max()} ({len(df):,}봉)", log_lines)

    # OOS 분리 (시간 기준)
    n_train = int(len(df) * TRAIN_RATIO)
    oos_start_idx = n_train
    oos_end_idx = len(df)
    log(f"  학습 IS: idx 0~{n_train-1} ({n_train:,}봉, {df.index[0]} ~ {df.index[n_train-1]})", log_lines)
    log(f"  OOS: idx {oos_start_idx}~{oos_end_idx-1} ({oos_end_idx-oos_start_idx:,}봉, {df.index[oos_start_idx]} ~ {df.index[-1]})", log_lines)

    # 2. ATR_pct 사전 계산 (전체 데이터)
    log(f"\n[2/6] 1m봉별 15m ATR_pct 사전 계산", log_lines)
    t_atr = time.time()
    atr_15m_pct_per_1m = compute_atr_15m_pct_per_1m(df)
    log(f"  계산 시간: {time.time()-t_atr:.1f}초", log_lines)
    log(f"  ATR_pct mean: {np.nanmean(atr_15m_pct_per_1m):.4%}", log_lines)
    log(f"  ATR_pct min/max: {np.nanmin(atr_15m_pct_per_1m):.4%} / {np.nanmax(atr_15m_pct_per_1m):.4%}", log_lines)

    # 3. 각 filter_mode별로 신호 추출 (3번 - 시간 많이 걸림)
    log(f"\n[3/6] ML 신호 추출 (3개 필터 모드)", log_lines)
    signals_per_filter = {}
    for filter_mode in FILTER_LIST:
        log(f"\n  filter_mode={filter_mode} (예상 시간: 10~30분)", log_lines)
        t_sig = time.time()
        long_idx, short_idx, sig_stats = extract_signals_v3(
            df, atr_15m_pct_per_1m,
            threshold_long=0.35, threshold_short=0.35,
            window_size=120,
            filter_mode=filter_mode,
            rolling_lookback_minutes=ROLLING_LOOKBACK,
            start_idx=oos_start_idx,
            end_idx=oos_end_idx,
            verbose_every=200000,
        )
        signals_per_filter[filter_mode] = (long_idx, short_idx, sig_stats)
        log(f"    Long {len(long_idx)}, Short {len(short_idx)}, total {len(long_idx)+len(short_idx)}", log_lines)
        log(f"    필터 거부 (저변동): {sig_stats['filter_stats']['rejected_low_vol']}", log_lines)
        log(f"    필터 거부 (고변동): {sig_stats['filter_stats']['rejected_high_vol']}", log_lines)
        log(f"    필터 통과: {sig_stats['filter_stats']['passed']}", log_lines)
        log(f"    거부율: {sig_stats['filter_stats']['rejection_rate_pct']:.2f}%", log_lines)
        log(f"    추출 시간: {(time.time()-t_sig)/60:.1f}분", log_lines)

    # 4. 4장세 사후 분류
    log(f"\n[4/6] 4장세 사후 분류", log_lines)
    df_oos_only = df.iloc[oos_start_idx:oos_end_idx]
    regime_series = assign_regime_v33(df_oos_only)
    log(f"  4장세 분포: {pd.Series(regime_series).value_counts().to_dict()}", log_lines)

    # 5. OB TF aggregate
    log(f"\n[5/6] OB TF {OB_TF}m + 2h aggregate", log_lines)
    df_reset = df.reset_index()
    df_2h = aggregate_ohlcv(df_reset, 120).set_index('timestamp')
    df_ob = aggregate_ohlcv(df_reset, OB_TF).set_index('timestamp')
    atr_ob = compute_atr(df_ob['high'].values, df_ob['low'].values, df_ob['close'].values, period=20)
    log(f"  2h봉: {len(df_2h)}, {OB_TF}m봉: {len(df_ob)}", log_lines)

    # 6. 12 시나리오 시뮬레이션
    log(f"\n[6/6] 12 시나리오 시뮬레이션", log_lines)
    all_results = []
    rm = Regime_Master_v2()

    scenario_idx = 0
    n_total = len(ATR_MULTIPLIER_LIST) * len(LEV_LIST) * len(FILTER_LIST)
    for atr_multi in ATR_MULTIPLIER_LIST:
        for lev in LEV_LIST:
            for filter_mode in FILTER_LIST:
                scenario_idx += 1
                label = f"atr{atr_multi}_lev{lev}_filter{filter_mode}"
                t_sc = time.time()
                log(f"  [{scenario_idx}/{n_total}] {label}...", log_lines)

                long_idx, short_idx, _ = signals_per_filter[filter_mode]
                if len(long_idx) == 0 and len(short_idx) == 0:
                    log(f"    신호 0건. 건너뛰기.", log_lines)
                    stats_overall = compute_stats(pd.DataFrame(), label, 'overall')
                    all_results.append(stats_overall)
                    continue

                trades_df = batch_simulate_v7(
                    long_signal_indices_1m=long_idx.tolist(),
                    short_signal_indices_1m=short_idx.tolist(),
                    df_1m=df,
                    df_ob_tf=df_ob,
                    df_2h=df_2h,
                    atr_ob_tf=atr_ob,
                    atr_15m_pct_per_1m=atr_15m_pct_per_1m,
                    leverage=lev,
                    w=5, N=5,
                    timeout_bars_ob_tf=HOLDING,
                    ob_tf_minutes=OB_TF,
                    enable_2h_reversal=True,
                    regime_master=rm,
                    atr_multiplier=atr_multi,
                    use_dynamic_hard_sl=True,
                    verbose=False,
                )

                # 4장세 분류
                trades_df['regime'] = trades_df['entry_signal_idx_1m'].apply(
                    lambda x: regime_series[x - oos_start_idx] if 0 <= x - oos_start_idx < len(regime_series) else 'unknown'
                )

                stats_overall = compute_stats(trades_df, label, 'overall')
                all_results.append(stats_overall)
                
                # 4장세 별 분류
                for reg in ['uptrend', 'downtrend', 'hivol_range', 'lovol_range']:
                    sub = trades_df[trades_df['regime'] == reg]
                    if len(sub) > 0:
                        sub_stats = compute_stats(sub, label, reg)
                        all_results.append(sub_stats)

                # 시나리오별 trade log 저장
                trade_path = os.path.join(OUTPUT_DIR, f"trades_{label}.csv")
                trades_df.to_csv(trade_path, index=False)

                t_elapsed = time.time() - t_sc
                log(f"    n_valid={stats_overall['n_valid']}, pf={stats_overall['pf']}, "
                    f"win={stats_overall['win_rate']:.3f}, fib_lock={stats_overall['n_fib_lock']}, "
                    f"hard_sl={stats_overall['n_hard_sl']}, "
                    f"avg_sl_dist={stats_overall['avg_dynamic_sl_dist']:.4f} ({t_elapsed:.1f}s)",
                    log_lines)

    # 결과 저장
    df_summary = pd.DataFrame(all_results)
    summary_path = os.path.join(OUTPUT_DIR, "all_scenarios_phase_b.csv")
    df_summary.to_csv(summary_path, index=False, encoding='utf-8-sig')
    log(f"\n  ✓ 요약: {summary_path}", log_lines)

    # 알파 후보 (PF >= 1.3 + n >= 30, overall만)
    df_overall = df_summary[df_summary['regime'] == 'overall']
    df_alpha = df_overall[(df_overall['pf'] >= 1.3) & (df_overall['n_valid'] >= 30)]
    log(f"\n[알파 후보 (PF≥1.3 + n≥30, overall)]: {len(df_alpha)}건", log_lines)
    if len(df_alpha) > 0:
        log(df_alpha.to_string(index=False), log_lines)

    # 본전 후보 (PF >= 1.0)
    df_break = df_overall[df_overall['pf'] >= 1.0]
    log(f"\n[본전 이상 (PF≥1.0, overall)]: {len(df_break)}건", log_lines)
    if len(df_break) > 0:
        log(df_break[['scenario', 'n_valid', 'pf', 'win_rate', 'net_sum']].to_string(index=False), log_lines)

    t_total = time.time() - t_start
    log(f"\n[총 소요: {t_total:.1f}초 = {t_total/60:.1f}분 = {t_total/3600:.2f}시간]", log_lines)

    with open(LOG_PATH, 'w', encoding='utf-8') as f:
        f.write('\n'.join(log_lines))

    print(f"\n  결과 위치: {OUTPUT_DIR}\\")
    print(f"  - all_scenarios_phase_b.csv (요약)")
    print(f"  - trades_<scenario>.csv (12개)")
    print(f"  - measure_log.txt (로그)")

    return df_summary


if __name__ == "__main__":
    main()
