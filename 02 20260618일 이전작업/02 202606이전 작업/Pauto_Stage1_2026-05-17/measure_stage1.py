"""
[파일명] measure_stage1.py
코드길이: 약 280줄, 내부버전 v3.4-stage1
목적: Stage 1 270 시나리오 측정 (15m + 1h × 정정 4건 모델)

[그리드]
TF: 15m, 1h
Lev: [10, 15, 20]
SL_acct: [0.0132, 0.026, 0.060, 0.090, 0.150]
TP_ratio: [2.8, 3.8, 5.0]
Holding (TF봉): [4, 8, 16]
= 2 × 3 × 5 × 3 × 3 = 270 시나리오

OOS: 2025-05-01 ~ 2026-04-30

[변경 핵심 - v3.4와 차이]
- 모델: 3-class XGBoost (multi:softprob)
- window_size: 100 (Regime 가드 통과)
- Holding 단위: TF봉 단위 ([4, 8, 16]봉)
- TF: 15m + 1h (v3.4의 1m 단독에서 변경)
"""

import os
import sys
import time
import json
import numpy as np
import pandas as pd
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tbm_simulator_v4 import simulate_batch_vec_v4, compute_stats_v4
from single_pos_filter import apply_single_position_filter
from stage1_signal_wrapper import extract_signals_stage1, aggregate_to_tf


# ==========================================
# 설정
# ==========================================
WORK_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(WORK_DIR, "Merged_Data.csv")
MODEL_PATH = os.path.join(WORK_DIR, "PautoV75_XGB_3class_v3.json")
OUTPUT_DIR = os.path.join(WORK_DIR, "outputs_stage1")

OOS_START = "2025-05-01 00:00:00+00:00"
OOS_END = "2026-04-30 23:59:00+00:00"

ML_THRESHOLD_LONG = 0.50    # 기본값. CLI 인자로 변경 가능
ML_THRESHOLD_SHORT = 0.50
WINDOW_SIZE = 100

# 그리드
TFS_MIN = [15, 60]      # 15m, 1h
LEVS = [10, 15, 20]
SL_ACCTS = [0.0132, 0.026, 0.060, 0.090, 0.150]
TP_RATIOS = [2.8, 3.8, 5.0]
HOLDING_BARS_TF = [4, 8, 16]  # TF봉 단위

# ADR-W3
ADR_PF_THRESHOLD = 1.3
ADR_N_VALID_MIN = 30


def assign_regime_v33(df_1m: pd.DataFrame) -> np.ndarray:
    """v3.3 4장세 사후 분류 (uptrend/downtrend/hivol_range/lovol_range)"""
    close = df_1m['close'].values
    ema_60 = pd.Series(close).ewm(span=60, adjust=False).mean().values
    ema_240 = pd.Series(close).ewm(span=240, adjust=False).mean().values
    atr = pd.Series((df_1m['high'] - df_1m['low']).values).rolling(60).mean().fillna(0).values
    atr_pct = atr / np.where(close > 0, close, 1) * 100
    atr_med = np.nanmedian(atr_pct[atr_pct > 0]) if (atr_pct > 0).any() else 0
    
    regime = np.full(len(df_1m), "lovol_range", dtype=object)
    is_up = ema_60 > ema_240
    is_down = ema_60 < ema_240
    is_hivol = atr_pct > atr_med * 1.5
    
    regime[is_up & ~is_hivol] = "uptrend"
    regime[is_down & ~is_hivol] = "downtrend"
    regime[is_hivol] = "hivol_range"
    return regime


def load_oos_data():
    print(f"\n[데이터 로딩] {DATA_PATH}")
    df = pd.read_csv(DATA_PATH, parse_dates=['timestamp'])
    df.set_index('timestamp', inplace=True)
    print(f"  전체: {df.index.min()} ~ {df.index.max()} ({len(df):,} rows)")
    
    oos_start_ts = pd.to_datetime(OOS_START)
    oos_end_ts = pd.to_datetime(OOS_END)
    if df.index.tz is not None and oos_start_ts.tz is None:
        oos_start_ts = oos_start_ts.tz_localize(df.index.tz)
        oos_end_ts = oos_end_ts.tz_localize(df.index.tz)
    
    df_oos = df.loc[oos_start_ts:oos_end_ts].copy()
    print(f"  OOS: {df_oos.index.min()} ~ {df_oos.index.max()} ({len(df_oos):,} rows)")
    return df_oos


def main():
    t_start = time.time()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    log_lines = []
    def log(s):
        print(s)
        log_lines.append(s)
    
    log("=" * 78)
    log("[Pauto Stage 1 측정 시작]")
    log("=" * 78)
    log(f"  시작: {datetime.now()}")
    log(f"  모델: {MODEL_PATH}")
    log(f"  OOS: {OOS_START} ~ {OOS_END}")
    log(f"  ML 임계: long ≥ {ML_THRESHOLD_LONG}, short ≥ {ML_THRESHOLD_SHORT}")
    log(f"  window_size: {WINDOW_SIZE} (Regime 가드 통과)")
    log(f"  그리드: TF{len(TFS_MIN)} × Lev{len(LEVS)} × SL{len(SL_ACCTS)} × TPr{len(TP_RATIOS)} × H{len(HOLDING_BARS_TF)}")
    total_scen = len(TFS_MIN) * len(LEVS) * len(SL_ACCTS) * len(TP_RATIOS) * len(HOLDING_BARS_TF)
    log(f"  총 {total_scen} 시나리오")
    
    # 데이터
    df_oos = load_oos_data()
    
    # 4장세 사후 분류 (1m 기준)
    log(f"\n[4장세 사후 분류 (1m 기준)]")
    regime_series = assign_regime_v33(df_oos)
    log(f"  분포: {pd.Series(regime_series).value_counts().to_dict()}")
    
    # OHLC 1m (시뮬에 사용)
    ohlc = {
        'open': df_oos['open'].values,
        'high': df_oos['high'].values,
        'low': df_oos['low'].values,
        'close': df_oos['close'].values,
    }
    
    all_results = []
    scenario_count = 0
    
    # TF별 신호 추출 + 그리드 측정
    for tf_min in TFS_MIN:
        log(f"\n{'='*78}")
        log(f"[TF {tf_min}m 처리]")
        log(f"{'='*78}")
        
        t_sig = time.time()
        long_idx, short_idx, sig_stats = extract_signals_stage1(
            df_oos, MODEL_PATH,
            tf_minutes=tf_min,
            threshold_long=ML_THRESHOLD_LONG,
            threshold_short=ML_THRESHOLD_SHORT,
            window_size=WINDOW_SIZE,
        )
        log(f"  신호 추출 소요: {time.time()-t_sig:.1f}초")
        log(f"  Long {len(long_idx):,} / Short {len(short_idx):,}")
        log(f"  Regime: {sig_stats['regime_distribution']}")
        
        # 신호 0이면 건너뜀
        if len(long_idx) + len(short_idx) == 0:
            log(f"  ⚠️ TF {tf_min}m 신호 0건. 건너뜀")
            continue
        
        # holding bars (TF봉 → 1m봉)
        # TF 15m × 4봉 = 60 1m봉, 15m × 8봉 = 120 1m봉, 15m × 16봉 = 240 1m봉
        # TF 1h × 4봉 = 240 1m봉, 1h × 8봉 = 480 1m봉, 1h × 16봉 = 960 1m봉
        hold_bars_1m_list = [h * tf_min for h in HOLDING_BARS_TF]
        
        # 그리드 측정
        log(f"\n[TF {tf_min}m 그리드 측정]")
        t_grid = time.time()
        for lev in LEVS:
            for sl in SL_ACCTS:
                for tp_r in TP_RATIOS:
                    for i_h, hold_1m in enumerate(hold_bars_1m_list):
                        scenario_count += 1
                        
                        df_l = simulate_batch_vec_v4(
                            long_idx, ohlc, sl, tp_r, lev, hold_1m, "long",
                            regime_series=regime_series, mode="A",
                        )
                        df_s = simulate_batch_vec_v4(
                            short_idx, ohlc, sl, tp_r, lev, hold_1m, "short",
                            regime_series=regime_series, mode="A",
                        )
                        df_l["side"] = "long"
                        df_s["side"] = "short"
                        df_all = pd.concat([df_l, df_s], ignore_index=True).sort_values("entry_idx").reset_index(drop=True)
                        df_surv = apply_single_position_filter(df_all)
                        
                        # 전체 + 4장세별 통계
                        stats_all = compute_stats_v4(df_surv)
                        stats_all['regime'] = 'overall'
                        stats_list = [stats_all]
                        
                        if 'regime' in df_surv.columns:
                            for r in ['uptrend', 'downtrend', 'hivol_range', 'lovol_range']:
                                df_r = df_surv[df_surv['regime'] == r]
                                if len(df_r) >= 5:
                                    st = compute_stats_v4(df_r)
                                    st['regime'] = r
                                    stats_list.append(st)
                        
                        for st in stats_list:
                            st['tf'] = f"{tf_min}m"
                            st['lev'] = lev
                            st['sl_acct'] = sl
                            st['tp_ratio'] = tp_r
                            st['holding_bars_tf'] = HOLDING_BARS_TF[i_h]
                            st['holding_min'] = hold_1m
                            st['adr_w3_passed'] = (
                                (st.get('n_valid', 0) >= ADR_N_VALID_MIN) and
                                (st.get('net_return_sum', 0) > 0) and
                                (st.get('pf', 0) >= ADR_PF_THRESHOLD)
                            )
                            all_results.append(st)
                        
                        if scenario_count % 20 == 0:
                            elapsed = time.time() - t_grid
                            rate = scenario_count / max(1, elapsed)
                            log(f"    진행 {scenario_count}/{total_scen} (TF{tf_min} 부분), 경과 {elapsed:.0f}초")
        
        log(f"  TF {tf_min}m 그리드 소요: {time.time()-t_grid:.1f}초")
    
    # 결과 저장
    log(f"\n{'='*78}")
    log(f"[결과 저장]")
    df_results = pd.DataFrame(all_results)
    summary_path = os.path.join(OUTPUT_DIR, 'all_scenarios_stage1.csv')
    df_results.to_csv(summary_path, index=False, encoding='utf-8-sig')
    log(f"  전체: {summary_path}")
    
    # [점프 23 정정] 빈 결과 방어 — 신호 0건이면 통계 계산 건너뜀
    if len(df_results) == 0 or 'adr_w3_passed' not in df_results.columns:
        log(f"\n⚠️ 측정 결과 0건. 진단 권장:")
        log(f"   python diagnose_prob_distribution.py")
        log(f"   (임계 0.50이 3-class 모델에 너무 높을 가능성)")
        elapsed_total = time.time() - t_start
        log(f"\n[총 소요] {elapsed_total/60:.1f}분")
        log_path = os.path.join(OUTPUT_DIR, 'run_log.txt')
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(log_lines))
        print(f"\n✓ run_log: {log_path}")
        return
    
    alphas = df_results[df_results['adr_w3_passed']]
    alpha_path = os.path.join(OUTPUT_DIR, 'alpha_candidates_stage1.csv')
    alphas.to_csv(alpha_path, index=False, encoding='utf-8-sig')
    log(f"  알파 후보 ({len(alphas)}건): {alpha_path}")
    
    # 통계 요약
    df_o = df_results[df_results['regime'] == 'overall']
    log(f"\n[overall {len(df_o)} 시나리오 요약]")
    log(f"  최대 PF: {df_o['pf'].max():.3f}")
    log(f"  평균 PF: {df_o['pf'].mean():.3f}")
    log(f"  PF ≥ 1.0: {(df_o['pf'] >= 1.0).sum()}건")
    log(f"  PF ≥ 1.3 + n_valid≥30: {len(alphas)}건")
    
    elapsed_total = time.time() - t_start
    log(f"\n[총 소요] {elapsed_total/60:.1f}분")
    
    log_path = os.path.join(OUTPUT_DIR, 'run_log.txt')
    with open(log_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(log_lines))
    print(f"\n✓ 모든 결과: {OUTPUT_DIR}/")


if __name__ == "__main__":
    # CLI 인자: python measure_stage1.py [threshold]
    # 예: python measure_stage1.py 0.40 → long/short 임계 모두 0.40
    if len(sys.argv) >= 2:
        try:
            t = float(sys.argv[1])
            ML_THRESHOLD_LONG = t
            ML_THRESHOLD_SHORT = t
            print(f"[CLI] 임계 변경 → long/short = {t}")
        except ValueError:
            print(f"⚠️ 인자 {sys.argv[1]} 는 숫자가 아님. 기본 0.50 사용")
    main()
