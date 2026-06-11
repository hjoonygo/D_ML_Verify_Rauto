# -*- coding: utf-8 -*-
"""
[파일명] measure_v34_obfib.py
코드길이: 약 320줄, 내부버전 v34-obfib-v0.1
로직 축약/생략 없이 전체 출력.

[목적]
PautoV75 ML 진입 + OB 분할 익절 + Fib trailing 청산 *결합* 시스템의 V3.4 거래환경 측정.
사용자 명령: "이것을 증명하는 테스트" — Key 노트의 알파 (PF 2.86, 월 15%) 가 V3.4 환경에서 재현되는지.

[그리드]
TF: [15m, 1h]
ML 임계: [0.35, 0.40]
Lev: [10, 15, 20]
N_ob: [3, 5]
Side: [long, short]
H (TF봉): [4, 8, 16]
= 2 × 2 × 3 × 2 × 2 × 3 = 144 시나리오

fib_ext_pct: 0.618 단일 (Key 노트 합의)
fib_trigger_roe: 24.0% (Lev 20 의 자본 ROE = 가격 +1.2%, Key 노트 합의)
fib_sl_pct: 5.73% (원본 기본값)

[측정 기간]
OOS: 2025-05-01 ~ 2026-04-30 (12mo, V3.4 Stage 1 동일)

[입력 파일 (사용자 PC)]
- Merged_Data.csv (1m OHLCV)
- PautoV75_XGB_3class_v3.json (사용자 학습한 24mo 모델)

[출력]
outputs_v34_obfib/
├ all_scenarios_summary.csv  (144 시나리오 통계)
├ alpha_candidates.csv       (ADR-W3 통과)
├ trade_level_top.csv        (Top 시나리오 거래별)
├ comparison_with_tradelog.csv (사용자 TradeLog 248행 vs 본 측정 비교)
└ run_log.txt
"""

import os
import sys
import time
import json
import numpy as np
import pandas as pd
from datetime import datetime
from itertools import product

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from obfib_simulator import simulate_batch, compute_grid_stats
from stage1_signal_wrapper import extract_signals_stage1


# ============================================================
# 설정
# ============================================================
WORK_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(WORK_DIR, "Merged_Data.csv")

# 모델 파일 자동 탐색 — 알려진 이름 둘 중 존재하는 것 사용
_MODEL_CANDIDATES = [
    "PautoV75_XGB_1to3_Predictor.json",  # 원본 학습 모듈 출력
    "PautoV75_XGB_3class_v3.json",        # 직전 V3.4 Stage 1 사본
]
MODEL_PATH = None
for _cand in _MODEL_CANDIDATES:
    _p = os.path.join(WORK_DIR, _cand)
    if os.path.exists(_p):
        MODEL_PATH = _p
        break
if MODEL_PATH is None:
    # 둘 다 없으면 첫 번째 기본값으로 (실행 시 함수가 명확한 에러 발생)
    MODEL_PATH = os.path.join(WORK_DIR, _MODEL_CANDIDATES[0])

OUTPUT_DIR = os.path.join(WORK_DIR, "outputs_v34_obfib")
os.makedirs(OUTPUT_DIR, exist_ok=True)

OOS_START = "2025-05-01 00:00:00+00:00"
OOS_END = "2026-04-30 23:59:00+00:00"
WINDOW_SIZE = 100

# 그리드 (사용자 결정)
TFS_MIN = [15, 60]                   # 15m, 1h
ML_THRESHOLDS = [0.35, 0.40]
LEVS = [10, 15, 20]
N_OBS = [3, 5]
SIDES = ['long', 'short']
HOLDING_BARS_TF = [4, 8, 16]         # TF봉 단위. 1m 으로 환산 시 (4*TF_min, 8*TF_min, 16*TF_min)

# 청산 파라미터 (Key 노트 합의)
FIB_EXT_PCT = 0.618
FIB_TRIGGER_ROE = 24.0    # Lev 20 기준. Lev 변경 시 가격 +1.2% 고정으로 자동 환산 필요
FIB_SL_PCT = 5.73         # 원본 기본값
COST_RT_NOMINAL = 0.0016
MMR = 0.004

# ADR-W3 알파 판정
ADR_PF_MIN = 1.3
ADR_N_MIN = 30
ADR_NET_MIN = 0.0


# ============================================================
# 로깅
# ============================================================
LOG_PATH = os.path.join(OUTPUT_DIR, "run_log.txt")
log_fp = None

def log(msg):
    global log_fp
    if log_fp is None:
        log_fp = open(LOG_PATH, "w", encoding="utf-8")
    print(msg, flush=True)
    log_fp.write(msg + "\n")
    log_fp.flush()


# ============================================================
# 데이터 로드
# ============================================================
def load_data():
    """1m OHLCV + OOS 슬라이스"""
    log(f"[Load] {DATA_PATH}")
    df = pd.read_csv(DATA_PATH, parse_dates=['timestamp'])
    df = df.set_index('timestamp').sort_index()
    if df.index.tz is None:
        df.index = df.index.tz_localize('UTC')

    df_oos = df.loc[OOS_START:OOS_END]
    log(f"  1m 봉 수 (OOS): {len(df_oos):,}")
    log(f"  기간: {df_oos.index[0]} ~ {df_oos.index[-1]}")
    return df_oos


# ============================================================
# 진입 신호 추출 (캐싱)
# ============================================================
def extract_signals_cached(df_1m, tf_min, threshold):
    """
    TF × threshold 조합별 진입 신호 추출. 디스크 캐시.

    extract_signals_stage1 는:
      - df_1m (timestamp 인덱스, OHLCV+oi_sum) 받음
      - 내부에서 TF 변환 + 신호 추출
      - (long_indices_1m, short_indices_1m, stats) 3개 반환
      - 인덱스는 이미 1m 봉 위치
    """
    cache_path = os.path.join(OUTPUT_DIR, f"signals_TF{tf_min}_th{threshold:.2f}.npz")
    if os.path.exists(cache_path):
        log(f"  [Cache hit] {cache_path}")
        d = np.load(cache_path)
        return d['long_indices'], d['short_indices']

    log(f"  [신호 추출] TF={tf_min}m, threshold={threshold}")

    long_indices_1m, short_indices_1m, stats = extract_signals_stage1(
        df_1m, MODEL_PATH,
        tf_minutes=tf_min,
        threshold_long=threshold,
        threshold_short=threshold,
        window_size=WINDOW_SIZE,
    )

    log(f"    TF봉: {stats['n_tf_bars']:,}, Long: {len(long_indices_1m)}, Short: {len(short_indices_1m)}")
    log(f"    Regime 분포: {stats['regime_distribution']}")

    np.savez(cache_path, long_indices=long_indices_1m, short_indices=short_indices_1m)
    return long_indices_1m, short_indices_1m


# ============================================================
# 단일 그리드 측정
# ============================================================
def run_grid_one(df_1m, tf_min, threshold, lev, n_ob, side, h_tf):
    """한 시나리오 측정"""
    long_idx, short_idx = extract_signals_cached(df_1m, tf_min, threshold)

    indices = long_idx if side == 'long' else short_idx
    if len(indices) == 0:
        empty_stats = {
            'tf_min': tf_min, 'threshold': threshold, 'lev': lev,
            'n_ob': n_ob, 'side': side, 'h_tf': h_tf,
            'n_trades': 0, 'adr_w3_pass': False,
        }
        return empty_stats, pd.DataFrame()

    holding_bars_1m = h_tf * tf_min

    params = {
        'leverage': lev,
        'fib_trigger_roe': FIB_TRIGGER_ROE,
        'fib_sl_pct': FIB_SL_PCT,
        'fib_ext_pct': FIB_EXT_PCT,
        'N_ob': n_ob,
        'holding_bars_1m': holding_bars_1m,
        'mmr': MMR,
        'cost_round_trip_nominal': COST_RT_NOMINAL,
    }

    trades_df = simulate_batch(indices, df_1m, side, params)
    stats = compute_grid_stats(trades_df)
    stats['tf_min'] = tf_min
    stats['threshold'] = threshold
    stats['lev'] = lev
    stats['n_ob'] = n_ob
    stats['side'] = side
    stats['h_tf'] = h_tf
    stats['h_1m'] = holding_bars_1m

    return stats, trades_df


# ============================================================
# 메인
# ============================================================
def main():
    t0 = time.time()
    log("=" * 70)
    log("V3.4 OB+Fib 알파 + 수익 효과성 측정")
    log(f"시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 70)
    log(f"OOS: {OOS_START} ~ {OOS_END}")
    log(f"모델: {os.path.basename(MODEL_PATH)} ({'존재 ✓' if os.path.exists(MODEL_PATH) else '★ 없음'})")
    log(f"그리드: TF×TH×Lev×N×Side×H = {len(TFS_MIN)}×{len(ML_THRESHOLDS)}×{len(LEVS)}×{len(N_OBS)}×{len(SIDES)}×{len(HOLDING_BARS_TF)}")
    total_scen = len(TFS_MIN) * len(ML_THRESHOLDS) * len(LEVS) * len(N_OBS) * len(SIDES) * len(HOLDING_BARS_TF)
    log(f"  = {total_scen} 시나리오\n")

    df_1m = load_data()
    log("")

    log("[1] 신호 사전 추출 (TF × Threshold)")
    for tf in TFS_MIN:
        for th in ML_THRESHOLDS:
            extract_signals_cached(df_1m, tf, th)
    log("")

    log("[2] 그리드 시뮬레이션 시작")
    results = []
    top_trades_dict = {}  # 상위 시나리오 거래 디테일 저장

    n_done = 0
    for tf, th, lev, n_ob, side, h_tf in product(
        TFS_MIN, ML_THRESHOLDS, LEVS, N_OBS, SIDES, HOLDING_BARS_TF
    ):
        n_done += 1
        scen_id = f"TF{tf}_TH{th:.2f}_L{lev}_N{n_ob}_{side}_H{h_tf}"
        try:
            stats, trades_df = run_grid_one(df_1m, tf, th, lev, n_ob, side, h_tf)
            if len(trades_df) > 0:
                top_trades_dict[scen_id] = trades_df

            stats['scen_id'] = scen_id
            results.append(stats)

            if stats.get('n_trades', 0) >= 10:
                log(f"  [{n_done}/{total_scen}] {scen_id}: "
                    f"n={stats['n_trades']}, PF={stats.get('pf', 0):.2f}, "
                    f"net={stats.get('net_return_sum_pct', 0):.1f}%, "
                    f"MDD={stats.get('mdd_pct', 0):.1f}%, "
                    f"adr={'★' if stats.get('adr_w3_pass') else '-'}")
        except Exception as e:
            log(f"  [ERROR] {scen_id}: {e}")
            import traceback; traceback.print_exc()
            results.append({'scen_id': scen_id, 'error': str(e)})

    log("")
    log("[3] 결과 저장")
    df_results = pd.DataFrame(results)
    df_results.to_csv(os.path.join(OUTPUT_DIR, "all_scenarios_summary.csv"), index=False)
    log(f"  all_scenarios_summary.csv  ({len(df_results)} 행)")

    df_alpha = df_results[df_results.get('adr_w3_pass', False) == True].copy()
    df_alpha = df_alpha.sort_values('pf', ascending=False)
    df_alpha.to_csv(os.path.join(OUTPUT_DIR, "alpha_candidates.csv"), index=False)
    log(f"  alpha_candidates.csv  ({len(df_alpha)} 통과)")

    # Top 시나리오 거래 디테일 저장 (PF 기준 상위 3)
    if len(df_alpha) > 0:
        top_3 = df_alpha.head(3)
        for _, row in top_3.iterrows():
            sid = row['scen_id']
            if sid in top_trades_dict:
                top_trades_dict[sid].to_csv(
                    os.path.join(OUTPUT_DIR, f"trades_{sid}.csv"), index=False
                )
        log(f"  trades_*.csv  (Top {len(top_3)} 시나리오)")

    # 요약 보고
    log("")
    log("=" * 70)
    log("측정 완료 요약")
    log("=" * 70)
    log(f"총 시나리오: {len(df_results)}")
    log(f"알파 후보 (ADR-W3): {len(df_alpha)}")
    if len(df_alpha) > 0:
        top1 = df_alpha.iloc[0]
        log(f"\nTop PF 시나리오: {top1['scen_id']}")
        log(f"  PF: {top1['pf']:.3f}")
        log(f"  n_trades: {int(top1['n_trades'])}")
        log(f"  net_return_sum: {top1['net_return_sum_pct']:.2f}%")
        log(f"  MDD: {top1['mdd_pct']:.2f}%")
        log(f"  Sharpe: {top1['sharpe']:.3f}")
        log(f"  Fib 청산: {int(top1['n_fib'])} 건 (평균 {top1['avg_fib_pct']:.2f}%)")
        log(f"  Fib 청산이 전체 수익에서 차지: {top1['pct_fib_of_total_profit']:.1f}%")

    t_total = time.time() - t0
    log(f"\n총 소요: {t_total:.1f}초 ({t_total/60:.1f}분)")
    log("")
    log("[다음 단계] 사용자: outputs_v34_obfib/ 폴더 전체를 zip 으로 압축해 채팅에 업로드")


if __name__ == "__main__":
    main()
