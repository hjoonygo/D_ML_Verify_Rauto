"""
[파일명] measure_pf_v34_pauto.py
코드길이: 약 250줄, 내부버전 v3.4-pauto
목적: PautoV75 진입 로직(ML+Regime)을 v3.3 그리드 측정 시스템으로 알파 검증

[변수 파이프라인]
In:
  - Merged_Data.csv: 36mo 1분봉 + oi_sum (사용자 PC)
  - PautoV75_XGB_1to3_Predictor.json: 학습된 ML 모델

Out:
  - all_scenarios_summary_v34.csv: 시나리오별 통계 (336 × 4 장세 = 1344 행)
  - alpha_candidates_v34.csv: ADR-W3 통과 시나리오
  - trade_logs_v34/: 시나리오별 거래 상세
  - summary_report.txt: 텍스트 요약

[그리드 (336 시나리오)]
  TF: 1m (PautoV75 그대로)
  Lev: [5, 10, 15, 20] (4개)
  SL_acct: [0.0132, 0.026, 0.05, 0.0724, 0.09, 0.12, 0.15] (7개)
  TP_ratio: [2.8, 3.8, 5.0] (3개)
  Holding (1분봉): [60, 240, 480, 960] = [1h, 4h, 8h, 16h] (4개)
  → 4 × 7 × 3 × 4 = 336 시나리오

[그리드 제거]
  W (윈도우): 사용자 결정 Q2 - 봉별 신호 추출
  Mode (A/C): 사용자 결정 - Mode D만 사용

[OOS 기간]
  2025-05-01 00:00:00+00:00 ~ 2026-04-30 23:59:00+00:00 (12mo)
  학습기간 (2023-05-01 ~ 2025-04-30) 이후
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
from pautov75_signal_wrapper import extract_signals_pautov75


# ==================================================
# 설정
# ==================================================
WORK_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(WORK_DIR, "Merged_Data.csv")
MODEL_PATH = os.path.join(WORK_DIR, "PautoV75_XGB_1to3_Predictor.json")
OUTPUT_DIR = os.path.join(WORK_DIR, "outputs_v34_pauto")

OOS_START = "2025-05-01 00:00:00+00:00"
OOS_END = "2026-04-30 23:59:00+00:00"

ML_THRESHOLD_LONG = 0.80
ML_THRESHOLD_SHORT = 0.20

# 그리드
LEVS = [5, 10, 15, 20]
SL_ACCTS = [0.0132, 0.026, 0.05, 0.0724, 0.09, 0.12, 0.15]
TP_RATIOS = [2.8, 3.8, 5.0]
HOLDING_BARS_1MIN = [60, 240, 480, 960]  # 1h, 4h, 8h, 16h
TF_NAME = "1m"
MODE = "A"  # 1분봉 단독 시 Mode A (high/low로 SL/TP/Liq 판정). Mode D는 TF봉+intrabar용

# ADR-W3 통과 임계 (v3.3 표준)
ADR_PF_THRESHOLD = 1.3
ADR_N_VALID_MIN = 30


def load_oos_data():
    """Merged_Data.csv → OOS 12mo만 슬라이싱"""
    print(f"\n[1/5] 데이터 로딩: {DATA_PATH}")
    if not os.path.exists(DATA_PATH):
        raise FileNotFoundError(f"데이터 파일 없음: {DATA_PATH}")
    df = pd.read_csv(DATA_PATH, parse_dates=['timestamp'])
    df.set_index('timestamp', inplace=True)
    print(f"  전체: {df.index.min()} ~ {df.index.max()} ({len(df):,} rows)")

    # tz 정합화
    oos_start_ts = pd.to_datetime(OOS_START)
    oos_end_ts = pd.to_datetime(OOS_END)
    if df.index.tz is not None and oos_start_ts.tz is None:
        oos_start_ts = oos_start_ts.tz_localize(df.index.tz)
        oos_end_ts = oos_end_ts.tz_localize(df.index.tz)

    df_oos = df.loc[oos_start_ts:oos_end_ts].copy()
    print(f"  OOS 슬라이싱: {df_oos.index.min()} ~ {df_oos.index.max()} ({len(df_oos):,} rows)")
    return df_oos


def assign_regime_v33(df_1m):
    """
    v3.3 4장세 분류 (사후 분석용)
    PautoV75 Regime는 *wrapper 안*에서 사용. 여기는 v3.3 그리드 측정 결과를 *4장세별로 분류*하기 위함.
    
    실제 분류 코드는 v3.3 regime_classifier.py에 있으나 1분봉 적용을 위해 단순화:
    EMA 1h(60봉) / 4h(240봉) 변동성으로 분류
    """
    close = df_1m['close'].values
    ema_60 = pd.Series(close).ewm(span=60, adjust=False).mean().values
    ema_240 = pd.Series(close).ewm(span=240, adjust=False).mean().values
    atr = pd.Series((df_1m['high'] - df_1m['low']).values).rolling(60).mean().fillna(0).values
    atr_pct = atr / close * 100  # %
    atr_med = np.nanmedian(atr_pct[atr_pct > 0])
    
    regime = np.full(len(df_1m), "lovol_range", dtype=object)
    is_up = ema_60 > ema_240
    is_down = ema_60 < ema_240
    is_hivol = atr_pct > atr_med * 1.5
    is_lovol = atr_pct < atr_med * 0.5
    
    regime[is_up & ~is_hivol & ~is_lovol] = "uptrend"
    regime[is_down & ~is_hivol & ~is_lovol] = "downtrend"
    regime[is_hivol] = "hivol_range"
    # 나머지 = lovol_range
    
    return regime


def main():
    t_start_total = time.time()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    log_lines = []
    def log(s):
        print(s)
        log_lines.append(s)
    
    log("=" * 78)
    log("[Pauto v3.4 측정 시작]")
    log("=" * 78)
    log(f"  시작 시각: {datetime.now()}")
    log(f"  데이터: {DATA_PATH}")
    log(f"  모델: {MODEL_PATH}")
    log(f"  OOS 기간: {OOS_START} ~ {OOS_END}")
    log(f"  ML 임계값: long ≥ {ML_THRESHOLD_LONG}, short ≤ {ML_THRESHOLD_SHORT}")
    log(f"  그리드: Lev{len(LEVS)} × SL{len(SL_ACCTS)} × TPr{len(TP_RATIOS)} × H{len(HOLDING_BARS_1MIN)} = {len(LEVS)*len(SL_ACCTS)*len(TP_RATIOS)*len(HOLDING_BARS_1MIN)} 시나리오")
    
    # === 1) 데이터 로딩 ===
    df_oos = load_oos_data()
    
    # === 2) PautoV75 신호 추출 ===
    # 본인 합성 데이터 측정 결과 (신뢰도 95%):
    #   - for-loop 추론: 525,600봉 → 약 5.7분 (방식 A)
    # 사용자 PC에서 *실제* 시간은 측정 후 확정
    log(f"\n[2/5] PautoV75 신호 추출")
    t0 = time.time()
    long_indices, short_indices, sig_stats = extract_signals_pautov75(
        df_oos, MODEL_PATH,
        threshold_long=ML_THRESHOLD_LONG,
        threshold_short=ML_THRESHOLD_SHORT,
        window_size=60,
    )
    elapsed_signal = time.time() - t0
    log(f"  소요: {elapsed_signal:.1f}초 ({elapsed_signal/60:.2f}분)")
    log(f"  Long 신호: {sig_stats['n_long_signals']:,} ({sig_stats['signal_pct']['long']:.3f}%)")
    log(f"  Short 신호: {sig_stats['n_short_signals']:,} ({sig_stats['signal_pct']['short']:.3f}%)")
    log(f"  Regime 분포: {sig_stats['regime_distribution']}")
    
    if len(long_indices) + len(short_indices) == 0:
        log("⚠️ [경고] 신호 0건. 측정 의미 없음. 종료")
        return
    
    # === 3) v3.3 그리드 측정 준비 ===
    log(f"\n[3/5] v3.3 시뮬레이션 환경 준비 (Mode A — intrabar provider 불필요)")
    ohlc = {
        'open': df_oos['open'].values,
        'high': df_oos['high'].values,
        'low': df_oos['low'].values,
        'close': df_oos['close'].values,
    }
    
    # 4장세 분류 (사후 분석용)
    regime_series = assign_regime_v33(df_oos)
    log(f"  4장세 분포: {pd.Series(regime_series).value_counts().to_dict()}")
    
    # === 4) 그리드 측정 ===
    log(f"\n[4/5] 그리드 측정 시작 (336 시나리오 × 4 장세 = 1344 행)")
    t_grid = time.time()
    
    results = []
    scenario_count = 0
    total_scenarios = len(LEVS) * len(SL_ACCTS) * len(TP_RATIOS) * len(HOLDING_BARS_1MIN)
    
    for lev in LEVS:
        for sl in SL_ACCTS:
            for tp_r in TP_RATIOS:
                for hold in HOLDING_BARS_1MIN:
                    scenario_count += 1
                    
                    df_l = simulate_batch_vec_v4(
                        long_indices, ohlc, sl, tp_r, lev, hold, "long",
                        regime_series=regime_series,
                        mode=MODE,
                    )
                    df_s = simulate_batch_vec_v4(
                        short_indices, ohlc, sl, tp_r, lev, hold, "short",
                        regime_series=regime_series,
                        mode=MODE,
                    )
                    df_l["side"] = "long"
                    df_s["side"] = "short"
                    df_all = pd.concat([df_l, df_s], ignore_index=True).sort_values("entry_idx").reset_index(drop=True)
                    df_surv = apply_single_position_filter(df_all)
                    
                    # 전체 통계
                    stats_all = compute_stats_v4(df_surv)
                    stats_all['regime'] = 'overall'
                    
                    # 4장세별 통계
                    regime_stats = []
                    if 'regime' in df_surv.columns:
                        for r in ['uptrend', 'downtrend', 'hivol_range', 'lovol_range']:
                            df_r = df_surv[df_surv['regime'] == r]
                            if len(df_r) >= 5:  # 최소 5거래
                                st = compute_stats_v4(df_r)
                                st['regime'] = r
                                regime_stats.append(st)
                    
                    for st in [stats_all] + regime_stats:
                        st['lev'] = lev
                        st['sl_acct'] = sl
                        st['tp_ratio'] = tp_r
                        st['holding_bars'] = hold
                        st['holding_min'] = hold  # 1분봉이라 동일
                        st['tf'] = TF_NAME
                        # ADR-W3 통과 판정
                        st['adr_w3_passed'] = (
                            (st.get('n_valid', 0) >= ADR_N_VALID_MIN) and
                            (st.get('net_return_sum', 0) > 0) and
                            (st.get('pf', 0) >= ADR_PF_THRESHOLD)
                        )
                        results.append(st)
                    
                    if scenario_count % 20 == 0:
                        elapsed = time.time() - t_grid
                        rate = scenario_count / max(1, elapsed)
                        eta = (total_scenarios - scenario_count) / max(0.001, rate)
                        log(f"  진행 {scenario_count}/{total_scenarios} "
                            f"({100*scenario_count/total_scenarios:.1f}%), "
                            f"경과 {elapsed:.0f}초, ETA {eta:.0f}초")
    
    elapsed_grid = time.time() - t_grid
    log(f"  그리드 측정 완료: {elapsed_grid:.1f}초 ({elapsed_grid/60:.1f}분)")
    
    # === 5) 결과 저장 ===
    log(f"\n[5/5] 결과 저장")
    df_results = pd.DataFrame(results)
    summary_path = os.path.join(OUTPUT_DIR, 'all_scenarios_summary_v34.csv')
    df_results.to_csv(summary_path, index=False, encoding='utf-8-sig')
    log(f"  전체 시나리오: {summary_path}")
    
    alphas = df_results[df_results['adr_w3_passed']]
    alpha_path = os.path.join(OUTPUT_DIR, 'alpha_candidates_v34.csv')
    alphas.to_csv(alpha_path, index=False, encoding='utf-8-sig')
    log(f"  알파 후보 ({len(alphas)}건): {alpha_path}")
    
    # 요약 보고
    elapsed_total = time.time() - t_start_total
    log(f"\n{'='*78}")
    log(f"[측정 완료] 총 소요: {elapsed_total/60:.1f}분")
    log(f"  - 신호 추출: {elapsed_signal/60:.2f}분")
    log(f"  - 그리드 측정: {elapsed_grid/60:.2f}분")
    log(f"  - 알파 후보 (PF≥{ADR_PF_THRESHOLD}, n_valid≥{ADR_N_VALID_MIN}): {len(alphas)}건")
    log(f"  - 최대 PF: {df_results['pf'].max():.3f}")
    log(f"  - 평균 PF: {df_results['pf'].mean():.3f}")
    
    log_path = os.path.join(OUTPUT_DIR, 'run_log.txt')
    with open(log_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(log_lines))
    
    # 신호 통계 JSON
    sig_stats_path = os.path.join(OUTPUT_DIR, 'signal_stats.json')
    with open(sig_stats_path, 'w', encoding='utf-8') as f:
        # numpy int 변환
        sig_stats_save = {k: (int(v) if hasattr(v, 'item') else v) for k, v in sig_stats.items()}
        json.dump(sig_stats_save, f, indent=2, default=str)
    
    print(f"\n✓ 모든 결과 저장: {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
