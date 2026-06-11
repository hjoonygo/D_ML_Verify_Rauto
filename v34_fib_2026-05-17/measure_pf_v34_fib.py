"""
[파일명] measure_pf_v34_fib.py
코드길이: 약 350줄, 내부버전명: v6.0 (v3.4_fib), 로직 축약/생략 없이 전체 출력

[목적] PautoV75 v2 진입 + OB+Fib 청산 결합 측정 — 27 시나리오 × 4장세

[그리드]
  - OB TF: [15m, 30m, 1h]
  - Lev:   [10, 15, 20]
  - Holding: [7봉, 14봉, 28봉] (OB TF 기준)
  - 합: 3 × 3 × 3 = 27 시나리오

[측정 흐름]
  1. Merged_Data.csv 로드
  2. OOS 기간 슬라이싱 (기본: 2025-05-01 ~ 2026-04-30)
  3. PautoV75 v2 ML 신호 추출 (window 120, 임계 0.35)
  4. 각 OB TF에 대해 aggregate (15m/30m/1h)
  5. 27 시나리오 batch_simulate_v6 실행
  6. 4장세 사후 분류 후 108행 결과 csv 저장

[출력]
  - outputs_v34_fib/all_scenarios_v34_fib.csv (108행)
  - outputs_v34_fib/tradelog_<scenario>.csv (각 시나리오별)
  - outputs_v34_fib/measure_log.txt
"""
import os
import sys
import time
import json
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tf_aggregator_v2 import aggregate_ohlcv
from tbm_simulator_v6 import compute_atr, batch_simulate_v6
from pautov75_signal_wrapper_v2 import extract_signals_v2
from Regime_Master_v2 import Regime_Master_v2


# 설정
WORK_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(WORK_DIR, "Merged_Data.csv")
OUTPUT_DIR = os.path.join(WORK_DIR, "outputs_v34_fib")
LOG_PATH = os.path.join(OUTPUT_DIR, "measure_log.txt")

# OOS 기본 기간
OOS_START = "2025-05-01"
OOS_END = "2026-04-30"

# 그리드
OB_TF_LIST = [15, 30, 60]   # 분
LEV_LIST = [10, 15, 20]
HOLDING_LIST = [7, 14, 28]  # OB TF 봉 수


def log(msg, log_lines):
    print(msg)
    log_lines.append(msg)


def assign_regime_v33(df_1m):
    """
    v3.3 4장세 사후 분류 (uptrend/downtrend/hivol_range/lovol_range)
    """
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
    """거래 결과 DataFrame에서 통계 계산"""
    df_valid = df_trades[df_trades['exit_reason'].notna() & (df_trades['exit_reason'] != 'blocked_single_pos')].copy()
    n_valid = len(df_valid)
    if n_valid == 0:
        return {
            'scenario': label, 'regime': regime_label,
            'n_valid': 0, 'pf': 0, 'win_rate': 0,
            'net_sum': 0, 'avg_return': 0,
            'mdd_pct': 0, 'sharpe': 0,
            'n_fib_lock': 0, 'n_hard_sl': 0, 'n_ob_partial': 0, 'n_timeout': 0,
        }

    nets = df_valid['net_return'].values
    wins = nets[nets > 0]
    losses = nets[nets <= 0]
    pf = wins.sum() / abs(losses.sum()) if abs(losses.sum()) > 0 else float('inf')
    win_rate = len(wins) / n_valid

    # MDD (cumulative net)
    cum = nets.cumsum()
    running_max = np.maximum.accumulate(cum)
    dd = cum - running_max
    mdd = dd.min()

    # Sharpe (단순)
    sharpe = nets.mean() / nets.std() * np.sqrt(252 * 24 * 60 / 60) if nets.std() > 0 else 0  # 시간 단위 환산은 단순화

    # 청산 사유별
    reasons = df_valid['exit_reason'].value_counts()
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
    }


def main():
    t_start = time.time()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    log_lines = []

    log(f"\n{'='*70}", log_lines)
    log(f"[v3.4_fib 측정 시작] {pd.Timestamp.now()}", log_lines)
    log(f"{'='*70}\n", log_lines)

    # 1. 데이터 로드
    if not os.path.exists(DATA_PATH):
        log(f"❌ {DATA_PATH} 없음. 데이터 먼저 준비 필요.", log_lines)
        return

    log(f"[1/6] 데이터 로드: {DATA_PATH}", log_lines)
    df = pd.read_csv(DATA_PATH, parse_dates=['timestamp'])
    df.set_index('timestamp', inplace=True)
    log(f"  전체: {df.index.min()} ~ {df.index.max()} ({len(df):,}봉)", log_lines)

    # OOS 슬라이싱
    oos_start = pd.to_datetime(OOS_START)
    oos_end = pd.to_datetime(OOS_END)
    if df.index.tz is not None:
        oos_start = oos_start.tz_localize(df.index.tz)
        oos_end = oos_end.tz_localize(df.index.tz)
    df_oos = df.loc[oos_start:oos_end].copy()
    log(f"  OOS ({OOS_START} ~ {OOS_END}): {len(df_oos):,}봉", log_lines)

    # 2. ML 신호 추출
    log(f"\n[2/6] ML 신호 추출 (PautoV75 v2, 임계 0.35, window 120)", log_lines)
    long_idx, short_idx, sig_stats = extract_signals_v2(
        df_oos, threshold_long=0.35, threshold_short=0.35,
        window_size=120, verbose_every=100000,
    )
    log(f"  Long {len(long_idx):,}, Short {len(short_idx):,}, total {len(long_idx)+len(short_idx):,}", log_lines)
    log(f"  avg prob_long={sig_stats['avg_prob_long']:.4f}, prob_short={sig_stats['avg_prob_short']:.4f}", log_lines)
    log(f"  regime 분포: {sig_stats['regime_distribution']}", log_lines)

    # 3. 4장세 사후 분류
    log(f"\n[3/6] 4장세 사후 분류", log_lines)
    regime_series = assign_regime_v33(df_oos)
    regime_counts = pd.Series(regime_series).value_counts().to_dict()
    log(f"  4장세 분포: {regime_counts}", log_lines)

    # 4. OB TF별 aggregate
    log(f"\n[4/6] OB TF 변환", log_lines)
    df_oos_reset = df_oos.reset_index()
    df_ob_tf_dict = {}
    df_2h = aggregate_ohlcv(df_oos_reset, 120).set_index('timestamp')
    log(f"  2h봉: {len(df_2h)}봉", log_lines)
    for tf in OB_TF_LIST:
        df_tf = aggregate_ohlcv(df_oos_reset, tf).set_index('timestamp')
        df_ob_tf_dict[tf] = df_tf
        log(f"  {tf}m봉: {len(df_tf)}봉", log_lines)

    # 5. 27 시나리오 시뮬레이션
    log(f"\n[5/6] 27 시나리오 시뮬레이션", log_lines)
    all_results = []
    rm = Regime_Master_v2()

    scenario_idx = 0
    for ob_tf in OB_TF_LIST:
        df_ob = df_ob_tf_dict[ob_tf]
        atr_ob = compute_atr(df_ob['high'].values, df_ob['low'].values, df_ob['close'].values, period=20)

        for lev in LEV_LIST:
            for holding in HOLDING_LIST:
                scenario_idx += 1
                label = f"tf{ob_tf}_lev{lev}_h{holding}"
                t_sc = time.time()
                log(f"  [{scenario_idx}/27] {label}...", log_lines)

                trades_df = batch_simulate_v6(
                    long_signal_indices_1m=long_idx.tolist(),
                    short_signal_indices_1m=short_idx.tolist(),
                    df_1m=df_oos,
                    df_ob_tf=df_ob,
                    df_2h=df_2h,
                    atr_ob_tf=atr_ob,
                    leverage=lev,
                    w=5, N=5,
                    timeout_bars_ob_tf=holding,
                    ob_tf_minutes=ob_tf,
                    enable_2h_reversal=True,
                    regime_master=rm,
                    verbose=False,
                )

                # 4장세 분류: 진입 시점의 1m봉의 regime
                trades_df['regime'] = trades_df['entry_signal_idx_1m'].apply(
                    lambda x: regime_series[x] if 0 <= x < len(regime_series) else 'unknown'
                )

                # overall + 4장세 통계
                stats_overall = compute_stats(trades_df, label, 'overall')
                all_results.append(stats_overall)
                for reg in ['uptrend', 'downtrend', 'hivol_range', 'lovol_range']:
                    df_r = trades_df[trades_df['regime'] == reg]
                    stats_r = compute_stats(df_r, label, reg)
                    all_results.append(stats_r)

                # 시나리오별 trade log 저장
                trade_path = os.path.join(OUTPUT_DIR, f"trades_{label}.csv")
                trades_df.to_csv(trade_path, index=False)

                t_elapsed = time.time() - t_sc
                log(f"    n_valid={stats_overall['n_valid']}, pf={stats_overall['pf']}, "
                    f"win={stats_overall['win_rate']:.3f}, fib_lock={stats_overall['n_fib_lock']} ({t_elapsed:.1f}s)",
                    log_lines)

    # 6. 결과 저장
    log(f"\n[6/6] 결과 저장", log_lines)
    df_summary = pd.DataFrame(all_results)
    summary_path = os.path.join(OUTPUT_DIR, "all_scenarios_v34_fib.csv")
    df_summary.to_csv(summary_path, index=False, encoding='utf-8-sig')
    log(f"  ✓ 요약: {summary_path} ({len(df_summary)}행 = 27 × 5장세[overall+4])", log_lines)

    # 알파 후보 (PF >= 1.3 + n_valid >= 30)
    df_alpha = df_summary[(df_summary['pf'] >= 1.3) & (df_summary['n_valid'] >= 30)]
    log(f"\n[알파 후보 (PF≥1.3 + n≥30)]: {len(df_alpha)}건", log_lines)
    if len(df_alpha) > 0:
        log(df_alpha.to_string(index=False), log_lines)
    else:
        log("  (없음)", log_lines)

    t_total = time.time() - t_start
    log(f"\n[총 소요: {t_total:.1f}초 = {t_total/60:.1f}분]", log_lines)

    # 로그 저장
    with open(LOG_PATH, 'w', encoding='utf-8') as f:
        f.write('\n'.join(log_lines))

    return df_summary


if __name__ == "__main__":
    main()
