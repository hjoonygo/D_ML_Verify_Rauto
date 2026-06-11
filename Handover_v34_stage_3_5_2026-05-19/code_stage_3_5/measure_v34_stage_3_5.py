# -*- coding: utf-8 -*-
"""
[파일명] measure_v34_stage_3_5.py
[코드길이] 약 450줄, [내부버전명] v11.0 (stage_3_5_regime_policy)

[목적] Stage 3.5 측정 — regime별 차별 정책 효과 검증
  사용자 결정 정책:
    - uptrend long: 진입 차단
    - hivol_range long: SL 500bp + timeout 16H 또는 18H (둘 다 비교)
    - 그 외 regime: 기존 v10 정책 (SL 150bp 동적 / timeout 4H)

[Grid - 4 시나리오]
  scenario_id              uptrend_long  hivol_long   기타       비고
  ─────────────────────────────────────────────────────────────────────────
  s0_v10_baseline          허용          기본 v10     기본 v10    비교 기준 (v10 그대로)
  s1_uptrend_block_only    차단          기본 v10     기본 v10    uptrend long만 차단
  s2_full_500bp_16H        차단          SL500/16H    기본 v10    16H (짧게)
  s3_full_500bp_18H        차단          SL500/18H    기본 v10    18H (가상 시뮬 sweet spot)

[Lookahead 처리 — 사용자 결정 A안]
  - 4장세 분류에 사용하는 atr_med를 Train 70% 기간 데이터로 고정
  - OOS 시뮬에서는 그 fixed atr_med 사용 (lookahead 차단)

[Fixed]
  - OB TF: 60m
  - 진입 게이트: TP≥48bp, SL≥32bp, RR≥1.5
  - 3단계 스텝업: 100bp/0.5, 161.8bp/0.618, 196.3bp/0.764
  - 대기 진입 2H, Lev 10, Filter off

[Files used]
  tf_aggregator_v2.py
  tbm_simulator_v11.py
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
from tbm_simulator_v11 import (
    compute_atr, batch_simulate_v11,
    HIVOL_LONG_SL_MAX_DEFAULT, HIVOL_LONG_TIMEOUT_DEFAULT,
    SL_MAX_DEFAULT,
)
from pautov75_signal_wrapper_v4 import (
    extract_signals_v4, compute_atr_15m_pct_per_1m, process_signals_with_wait_v4
)
from Regime_Master_v2 import Regime_Master_v2


WORK_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(WORK_DIR, "..", "Merged_Data.csv")
OUTPUT_DIR = os.path.join(WORK_DIR, "outputs_stage_3_5")
LOG_PATH = os.path.join(OUTPUT_DIR, "measure_log.txt")

# Stage 3.5 그리드
STAGE35_GRID = [
    # (scenario_id, enable_regime_policy, hivol_sl, hivol_timeout)
    # s0: v10 그대로 (regime 정책 비활성, sl_max=180bp = Stage 3 최우승)
    ('s0_v10_baseline_sl180', False, 0.0180, 240),
    # s1: uptrend long만 차단, 나머지는 v10 + sl_max=180bp
    # → 코드 구조상 enable_regime_policy=True에서 hivol 정책도 같이 켜짐.
    #    s1은 별도 구현 어려우니 hivol_long 정책도 적용. 다만 비교 목적으로 s0와 차이 측정 가능.
    # → 대안: s1 생략하고 s0 vs s2,s3 비교만
    # 결정: s1을 'uptrend_block + hivol=기본v10' 정책으로 (hivol_sl=180bp, hivol_timeout=240)
    ('s1_uptrend_block_only', True, 0.0180, 240),
    # s2: 전체 정책 + 16H (짧게)
    ('s2_full_500bp_16H', True, 0.0500, 960),
    # s3: 전체 정책 + 18H (sweet spot)
    ('s3_full_500bp_18H', True, 0.0500, 1080),
]

# Fixed
OB_TF = 60
LEV = 10
ROLLING_LOOKBACK = 14 * 1440
TRAIN_RATIO = 0.70
ENABLE_WAIT_ENTRY = True
WAIT_TIMEOUT_MINUTES = 120


def log(msg, log_lines):
    print(msg)
    log_lines.append(msg)


def assign_regime_v33_fixed(df_1m, atr_med_fixed):
    """4장세 사후 분류 — Train 기간 median 고정 사용 (lookahead 차단)
    
    IN: df_1m, atr_med_fixed (학습 기간에서 미리 계산한 ATR_pct median)
    OUT: regime 배열 (1m봉마다)
    """
    close = df_1m['close'].values
    ema_60 = pd.Series(close).ewm(span=60, adjust=False).mean().values
    ema_240 = pd.Series(close).ewm(span=240, adjust=False).mean().values
    atr = pd.Series((df_1m['high'] - df_1m['low']).values).rolling(60).mean().fillna(0).values
    atr_pct = atr / close * 100  # %
    
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
    """Train 기간 ATR_pct median 계산 (lookahead 차단용)"""
    close = df_train_1m['close'].values
    atr = pd.Series((df_train_1m['high'] - df_train_1m['low']).values).rolling(60).mean().fillna(0).values
    atr_pct = atr / close * 100
    valid = atr_pct[atr_pct > 0]
    if len(valid) == 0:
        return 0.1
    return float(np.nanmedian(valid))


def compute_stats_v11(df_trades, label, regime_label='overall'):
    """v11 — regime 정책 신규 컬럼 반영 통계"""
    valid_exits_prefix = ('initial_sl','step1_sl','step2_sl','step3_sl',
                          'timeout_','reversal_2h')
    
    def is_valid_exit(r):
        if not isinstance(r, str):
            return False
        return any(r == e or r.startswith(p if p.endswith('_') else p) for e in [] for p in [])
    
    # 명확하게: timeout_4h, timeout_6h, ..., timeout_step_active 등
    is_valid = df_trades['exit_reason'].apply(
        lambda r: isinstance(r, str) and (
            r in ['initial_sl','step1_sl','step2_sl','step3_sl','reversal_2h','timeout_step_active']
            or r.startswith('timeout_')
        )
    )
    df_valid = df_trades[is_valid].copy()
    n_valid = len(df_valid)
    
    if n_valid == 0:
        return {
            'scenario': label, 'regime': regime_label,
            'n_valid': 0, 'pf': 0, 'win_rate': 0, 'net_sum': 0,
            'avg_return': 0, 'mdd_pct': 0, 'sharpe': 0,
            'n_blocked_regime': 0, 'n_other_exits': 0,
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
    
    sharpe = nets.mean() / nets.std() * np.sqrt(252*24*60/60) if nets.std() > 0 else 0
    
    reasons = df_valid['exit_reason'].value_counts()
    
    # v11 신규: regime 차단된 거래
    n_blocked_regime = (df_trades['exit_reason']=='regime_blocked').sum()
    n_blocked_single = (df_trades['exit_reason']=='blocked_single_pos').sum()
    n_gate_fail = sum(int(df_trades['exit_reason'].value_counts().get(k, 0)) 
                       for k in ['sl_gate_fail','tp_gate_fail','rr_gate_fail'])
    n_wait_cancel = (df_trades['exit_reason'].isin(['wait_cancel_no_signal','wait_cancel_opposite_signal'])).sum()
    n_wait_timeout = (df_trades['exit_reason']=='wait_timeout').sum()
    
    # policy_label 분포 (regime 정책 활성시)
    if 'policy_label' in df_valid.columns:
        policy_counts = df_valid['policy_label'].value_counts().to_dict()
    else:
        policy_counts = {}
    
    # exit_reason 분포 (timeout_* 등 다 포함)
    exit_dist = df_valid['exit_reason'].value_counts().to_dict()
    
    return {
        'scenario': label, 'regime': regime_label,
        'n_valid': n_valid,
        'pf': round(pf, 3) if pf != float('inf') else 999,
        'win_rate': round(win_rate, 4),
        'net_sum': round(nets.sum(), 4),
        'avg_return': round(nets.mean(), 5),
        'mdd_pct': round(mdd * 100, 3),
        'sharpe': round(sharpe, 3),
        # exit_reason 카운트 (주요)
        'n_initial_sl': int(reasons.get('initial_sl', 0)),
        'n_step1_sl': int(reasons.get('step1_sl', 0)),
        'n_step2_sl': int(reasons.get('step2_sl', 0)),
        'n_step3_sl': int(reasons.get('step3_sl', 0)),
        'n_timeout_4h': int(reasons.get('timeout_4h', 0)),
        'n_timeout_16h': int(reasons.get('timeout_16h', 0)),
        'n_timeout_18h': int(reasons.get('timeout_18h', 0)),
        'n_timeout_step_active': int(reasons.get('timeout_step_active', 0)),
        'n_reversal_2h': int(reasons.get('reversal_2h', 0)),
        # 게이트/차단
        'n_blocked_regime': int(n_blocked_regime),
        'n_blocked_single_pos': int(n_blocked_single),
        'n_gate_fail': int(n_gate_fail),
        'n_wait_cancel': int(n_wait_cancel),
        'n_wait_timeout': int(n_wait_timeout),
        # 보조 통계
        'step_activation_rate': round((df_valid['step_active_max']>=1).sum()/n_valid, 4),
        'avg_initial_sl_dist_bp': round(df_valid['initial_sl_dist'].mean()*10000, 1) if 'initial_sl_dist' in df_valid.columns else 0,
        'avg_bars_held_min': round(df_valid['bars_held_1m'].mean(), 1) if 'bars_held_1m' in df_valid.columns else 0,
        'avg_rr_at_entry': round(df_valid['rr_at_entry'].mean(), 3) if 'rr_at_entry' in df_valid.columns and df_valid['rr_at_entry'].notna().any() else 0,
    }


def main():
    t_start = time.time()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    log_lines = []
    
    log("\n" + "="*78, log_lines)
    log(f"[Stage 3.5 측정 시작] {pd.Timestamp.now()}", log_lines)
    log("="*78 + "\n", log_lines)
    log(f"실행 폴더: {WORK_DIR}", log_lines)
    log(f"데이터:    {DATA_PATH}", log_lines)
    log(f"결과 폴더: {OUTPUT_DIR}\n", log_lines)
    
    log(f"그리드: 4 시나리오", log_lines)
    for sc_id, enable, hivol_sl, hivol_to in STAGE35_GRID:
        log(f"  {sc_id}: regime_policy={enable}, hivol_long=(SL {hivol_sl*10000:.0f}bp, timeout {hivol_to}min={hivol_to//60}H)", log_lines)
    
    log(f"\n사용자 정책:", log_lines)
    log(f"  uptrend long: 진입 차단", log_lines)
    log(f"  hivol_range long: SL 500bp + timeout 16H 또는 18H", log_lines)
    log(f"  그 외: 기존 v10 (SL 150bp 동적 / timeout 4H)", log_lines)
    log(f"\nLookahead 처리: Train 70% 기간 atr_med 고정 사용", log_lines)
    log(f"고정: OB TF {OB_TF}m, Lev {LEV}", log_lines)
    
    if not os.path.exists(DATA_PATH):
        log(f"X 데이터 파일 없음: {DATA_PATH}", log_lines)
        return
    
    # 1. 데이터 로드
    log(f"\n[1/7] 데이터 로드", log_lines)
    df = pd.read_csv(DATA_PATH, parse_dates=['timestamp']).set_index('timestamp')
    if df.index.tz is None:
        df.index = df.index.tz_localize('UTC')
    log(f"  전체: {df.index.min()} ~ {df.index.max()} ({len(df):,}봉)", log_lines)
    
    n_train = int(len(df) * TRAIN_RATIO)
    oos_start_idx = n_train
    oos_end_idx = len(df)
    log(f"  Train: idx 0~{oos_start_idx-1} ({oos_start_idx:,}봉, 70%)", log_lines)
    log(f"  OOS:   idx {oos_start_idx}~{oos_end_idx-1} ({oos_end_idx-oos_start_idx:,}봉, 30%)", log_lines)
    
    # 2. Train 기간 atr_med 계산 (lookahead 차단)
    log(f"\n[2/7] Train 70% atr_med 계산 (lookahead 차단용)", log_lines)
    df_train = df.iloc[:oos_start_idx]
    atr_med_fixed = compute_train_atr_med(df_train)
    log(f"  Train atr_med: {atr_med_fixed:.6f} %", log_lines)
    log(f"  이 값을 OOS 4장세 분류에 사용 (Stage 3에서는 OOS 자체 median 사용 = lookahead)", log_lines)
    
    # 3. ATR_pct 계산 (SL 동적 분류용, 진입 시점만 사용 = lookahead 없음)
    log(f"\n[3/7] 1m별 15m ATR_pct 사전 계산", log_lines)
    t_atr = time.time()
    atr_15m_pct_per_1m = compute_atr_15m_pct_per_1m(df)
    log(f"  계산 시간: {time.time()-t_atr:.1f}초", log_lines)
    log(f"  ATR_pct mean: {np.nanmean(atr_15m_pct_per_1m)*100:.4f}%", log_lines)
    
    # 4. ML 신호 (캐시 활용)
    cache_path = os.path.join(WORK_DIR, "signals_cache_stage_3_5.pkl")
    cache_path_s3 = os.path.join(WORK_DIR, "signals_cache_stage_3.pkl")
    cache_to_use = None
    if os.path.exists(cache_path):
        cache_to_use = cache_path
    elif os.path.exists(cache_path_s3):
        cache_to_use = cache_path_s3
        log(f"  Stage 3 캐시 발견, 재사용", log_lines)
    
    if cache_to_use is not None:
        log(f"\n[4/7] ML 신호 캐시 로드: {cache_to_use}", log_lines)
        import pickle
        with open(cache_to_use, 'rb') as f:
            cached = pickle.load(f)
        long_idx = cached['long_idx']
        short_idx = cached['short_idx']
        log(f"  Long {len(long_idx)}, Short {len(short_idx)}", log_lines)
    else:
        log(f"\n[4/7] ML 신호 추출 (filter=off, 1회)", log_lines)
        t_sig = time.time()
        long_idx_raw, short_idx_raw, _ = extract_signals_v4(
            df, atr_15m_pct_per_1m,
            threshold_long=0.35, threshold_short=0.35,
            window_size=120, filter_mode='off',
            rolling_lookback_minutes=ROLLING_LOOKBACK,
            start_idx=oos_start_idx, end_idx=oos_end_idx,
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
    
    # 5. regime 분류 (전체 df, Train fixed median 사용)
    log(f"\n[5/7] 4장세 분류 — Train fixed median 사용 (lookahead 차단)", log_lines)
    regime_per_1m_full = assign_regime_v33_fixed(df, atr_med_fixed)
    log(f"  전체 분포: {pd.Series(regime_per_1m_full).value_counts().to_dict()}", log_lines)
    # OOS만 통계
    regime_oos = regime_per_1m_full[oos_start_idx:oos_end_idx]
    log(f"  OOS 분포: {pd.Series(regime_oos).value_counts().to_dict()}", log_lines)
    
    # 6. TF aggregate
    log(f"\n[6/7] TF aggregate", log_lines)
    df_reset = df.reset_index()
    df_2h = aggregate_ohlcv(df_reset, 120).set_index('timestamp')
    df_ob = aggregate_ohlcv(df_reset, OB_TF).set_index('timestamp')
    atr_ob = compute_atr(df_ob['high'].values, df_ob['low'].values, df_ob['close'].values, period=20)
    log(f"  2h봉: {len(df_2h)}, {OB_TF}m봉: {len(df_ob)}", log_lines)
    
    # 7. 시뮬레이션 4 시나리오
    log(f"\n[7/7] 4 시나리오 시뮬레이션", log_lines)
    all_results = []
    rm = Regime_Master_v2()
    
    for sc_idx, (sc_id, enable_policy, hivol_sl, hivol_to) in enumerate(STAGE35_GRID):
        t_sc = time.time()
        log(f"\n  [{sc_idx+1}/4] {sc_id} (regime_policy={enable_policy})...", log_lines)
        
        trades_df = batch_simulate_v11(
            long_signal_indices_1m=long_idx.tolist(),
            short_signal_indices_1m=short_idx.tolist(),
            df_1m=df, df_ob_tf=df_ob, df_2h=df_2h,
            atr_ob_tf=atr_ob,
            atr_15m_pct_per_1m=atr_15m_pct_per_1m,
            regime_per_1m=regime_per_1m_full,
            sl_max=0.0180,  # 기본 sl_max (다른 regime용, Stage 3 최우승값)
            leverage=LEV, w=5, N=5,
            ob_tf_minutes=OB_TF,
            enable_2h_reversal=True,
            regime_master=rm,
            enable_wait_entry=ENABLE_WAIT_ENTRY,
            wait_timeout_minutes=WAIT_TIMEOUT_MINUTES,
            verbose=False,
            enable_regime_policy=enable_policy,
            hivol_long_sl_max=hivol_sl,
            hivol_long_timeout=hivol_to,
        )
        
        # 진입 시점 regime을 거래 row에 매핑 (이미 simulate에서 기록되지만, 통계용으로)
        trades_df['regime_assigned'] = trades_df['regime_at_entry']
        
        # overall + regime별 + side별 통계
        stats_overall = compute_stats_v11(trades_df, sc_id, 'overall')
        all_results.append(stats_overall)
        
        for reg in ['uptrend', 'downtrend', 'hivol_range', 'lovol_range']:
            sub = trades_df[trades_df['regime_at_entry']==reg]
            if len(sub) > 0:
                sub_stats = compute_stats_v11(sub, sc_id, reg)
                all_results.append(sub_stats)
        
        for s in ['long', 'short']:
            sub_side = trades_df[trades_df['side']==s]
            if len(sub_side) > 0:
                side_stats = compute_stats_v11(sub_side, sc_id, f'side_{s}')
                all_results.append(side_stats)
        
        # regime x side
        for reg in ['uptrend','downtrend','hivol_range','lovol_range']:
            for s in ['long','short']:
                sub_rs = trades_df[(trades_df['regime_at_entry']==reg) & (trades_df['side']==s)]
                if len(sub_rs) > 0:
                    rs_stats = compute_stats_v11(sub_rs, sc_id, f'{reg}_{s}')
                    all_results.append(rs_stats)
        
        # 시나리오별 trades csv
        trade_path = os.path.join(OUTPUT_DIR, f"trades_{sc_id}.csv")
        trades_df.to_csv(trade_path, index=False)
        
        t_elapsed = time.time() - t_sc
        log(f"    n_valid={stats_overall['n_valid']}, "
            f"pf={stats_overall['pf']}, win={stats_overall['win_rate']:.3f}, "
            f"net_sum={stats_overall['net_sum']*100:+.2f}%, "
            f"blocked_regime={stats_overall['n_blocked_regime']}, "
            f"({t_elapsed:.1f}s)", log_lines)
    
    # 결과 저장
    df_summary = pd.DataFrame(all_results)
    summary_path = os.path.join(OUTPUT_DIR, "all_scenarios_stage_3_5.csv")
    df_summary.to_csv(summary_path, index=False, encoding='utf-8-sig')
    log(f"\n  요약: {summary_path}", log_lines)
    
    df_overall = df_summary[df_summary['regime']=='overall']
    log(f"\n[Overall 비교]", log_lines)
    cols_show = ['scenario','n_valid','pf','win_rate','net_sum','mdd_pct','n_blocked_regime']
    log(df_overall[cols_show].to_string(index=False), log_lines)
    
    df_alpha = df_overall[(df_overall['pf']>=1.0) & (df_overall['n_valid']>=30)]
    log(f"\n[알파 후보 (PF>=1.0, n>=30, overall)]: {len(df_alpha)}건", log_lines)
    if len(df_alpha) > 0:
        log(df_alpha[cols_show].to_string(index=False), log_lines)
    
    t_total = time.time() - t_start
    log(f"\n[총 소요: {t_total:.1f}초 = {t_total/60:.1f}분]", log_lines)
    
    with open(LOG_PATH, 'w', encoding='utf-8') as f:
        f.write('\n'.join(log_lines))
    
    return df_summary


if __name__ == "__main__":
    main()
