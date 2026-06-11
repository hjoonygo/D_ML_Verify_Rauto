"""
[파일명] diagnose_prob_distribution.py
코드길이: 약 130줄, 내부버전 v3.4-stage1-diag
목적: Stage 1 측정 신호 0건 원인 진단 — 진짜 prob 분포 측정
       임계 0.50이 너무 높은지 사용자 PC 진짜 데이터로 확인

[실행]
python diagnose_prob_distribution.py

[출력]
- long_prob / short_prob / stay_prob 분포 buckets
- 임계 [0.30, 0.35, 0.40, 0.45, 0.50]별 신호 빈도 추정
- 권장 임계 (long/short 각 5% 이상 발생하는 임계)

[샘플링]
OOS 12mo 525,540봉 중 무작위 5,000봉만 추론 (30초)
TF aggregate 후 15m 봉 → 5000개. 전체 측정의 1/7 표본

[변수 In/Out]
In: Merged_Data.csv, PautoV75_XGB_3class_v3.json
Out: console 출력 + diag_result.csv
"""

import os
import sys
import numpy as np
import pandas as pd
import xgboost as xgb

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stage1_signal_wrapper import aggregate_to_tf, calculate_features_3term, FEATURE_ORDER
from Regime_Master_PautoV75 import Regime_Master_PautoV75


WORK_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(WORK_DIR, "Merged_Data.csv")
MODEL_PATH = os.path.join(WORK_DIR, "PautoV75_XGB_3class_v3.json")

OOS_START = "2025-05-01 00:00:00+00:00"
OOS_END = "2026-04-30 23:59:00+00:00"

TF_MINUTES = 15        # 진단용 한 TF만
WINDOW_SIZE = 100
N_SAMPLE = 5000        # 샘플링할 TF봉 수 (15m 기준 = 약 52일 표본)


def main():
    print("=" * 70)
    print("[Stage 1 진단 — prob 분포 측정]")
    print("=" * 70)
    
    # 모델 + 데이터
    if not os.path.exists(MODEL_PATH):
        print(f"❌ 모델 없음: {MODEL_PATH}")
        return
    if not os.path.exists(DATA_PATH):
        print(f"❌ 데이터 없음: {DATA_PATH}")
        return
    
    model = xgb.XGBClassifier()
    model.load_model(MODEL_PATH)
    
    df = pd.read_csv(DATA_PATH, parse_dates=['timestamp'])
    df.set_index('timestamp', inplace=True)
    
    oos_start = pd.to_datetime(OOS_START)
    oos_end = pd.to_datetime(OOS_END)
    if df.index.tz is not None and oos_start.tz is None:
        oos_start = oos_start.tz_localize(df.index.tz)
        oos_end = oos_end.tz_localize(df.index.tz)
    df_oos = df.loc[oos_start:oos_end].copy()
    print(f"OOS 데이터: {len(df_oos):,} 1m봉")
    
    # TF aggregate
    df_tf = aggregate_to_tf(df_oos, TF_MINUTES)
    n_tf = len(df_tf)
    print(f"TF {TF_MINUTES}m: {n_tf:,}봉")
    
    # 샘플링 (균일 간격)
    if n_tf > N_SAMPLE:
        step = n_tf // N_SAMPLE
        sample_indices = list(range(WINDOW_SIZE, n_tf, step))[:N_SAMPLE]
    else:
        sample_indices = list(range(WINDOW_SIZE, n_tf))
    print(f"샘플 봉: {len(sample_indices):,}개 (균일 간격)")
    
    # Regime
    regime_inst = Regime_Master_PautoV75()
    params = {'ml_long_threshold': 0.5, 'ml_short_threshold': 0.5}
    
    # 추론
    stay_probs = []
    long_probs = []
    short_probs = []
    regimes = []
    skipped = 0
    
    print(f"\n[추론 진행 — 약 30초]")
    for i, t in enumerate(sample_indices):
        window = df_tf.iloc[t - WINDOW_SIZE + 1 : t + 1].copy()
        
        try:
            regime = regime_inst.get_regime(window, params)
        except:
            regime = "CHOPPY"
        
        closed_df = window.iloc[:-1]
        feats = calculate_features_3term(closed_df)
        if feats is None:
            skipped += 1
            continue
        
        feat_array = np.array([[feats[k] for k in FEATURE_ORDER]])
        proba = model.predict_proba(feat_array)[0]
        stay_probs.append(proba[0])
        long_probs.append(proba[1])
        short_probs.append(proba[2])
        regimes.append(regime)
        
        if (i + 1) % 1000 == 0:
            print(f"  진행 {i+1}/{len(sample_indices)}")
    
    print(f"\n샘플 완료. 유효 {len(long_probs):,}개, skip {skipped}")
    
    stay_arr = np.array(stay_probs)
    long_arr = np.array(long_probs)
    short_arr = np.array(short_probs)
    
    # === 분포 분석 ===
    print(f"\n[stay_prob 분포]")
    print(f"  평균 {stay_arr.mean():.4f}, 중앙 {np.median(stay_arr):.4f}, max {stay_arr.max():.4f}")
    
    print(f"\n[long_prob 분포]")
    print(f"  평균 {long_arr.mean():.4f}, 중앙 {np.median(long_arr):.4f}, max {long_arr.max():.4f}")
    print(f"  90% 분위: {np.percentile(long_arr, 90):.4f}")
    print(f"  95% 분위: {np.percentile(long_arr, 95):.4f}")
    print(f"  99% 분위: {np.percentile(long_arr, 99):.4f}")
    
    print(f"\n[short_prob 분포]")
    print(f"  평균 {short_arr.mean():.4f}, 중앙 {np.median(short_arr):.4f}, max {short_arr.max():.4f}")
    print(f"  90% 분위: {np.percentile(short_arr, 90):.4f}")
    print(f"  95% 분위: {np.percentile(short_arr, 95):.4f}")
    print(f"  99% 분위: {np.percentile(short_arr, 99):.4f}")
    
    # 임계별 발생 빈도
    print(f"\n[임계별 신호 빈도 추정] (샘플 {len(long_arr):,} 봉 기준)")
    print(f"{'임계':>6s} | {'Long ≥':>8s} | {'Long%':>6s} | {'Short ≥':>8s} | {'Short%':>6s} | OOS 12mo 추정 신호")
    print("-" * 80)
    
    sample_to_oos_ratio = (n_tf - WINDOW_SIZE) / max(1, len(long_arr))
    
    for thresh in [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60]:
        n_long = (long_arr >= thresh).sum()
        n_short = (short_arr >= thresh).sum()
        pct_long = 100 * n_long / len(long_arr)
        pct_short = 100 * n_short / len(long_arr)
        est_long_full = int(n_long * sample_to_oos_ratio)
        est_short_full = int(n_short * sample_to_oos_ratio)
        marker = " ★" if (pct_long > 1.0 and pct_short > 1.0) else ""
        print(f"{thresh:>6.2f} | {n_long:>8,} | {pct_long:>5.2f}% | {n_short:>8,} | {pct_short:>5.2f}% | L≈{est_long_full:,} S≈{est_short_full:,}{marker}")
    
    # 권장 임계
    print(f"\n[권장 임계 (long/short 각 1%+ 발생)]")
    recommended = None
    for thresh in [0.60, 0.55, 0.50, 0.45, 0.40, 0.35, 0.30]:
        pct_long = 100 * (long_arr >= thresh).sum() / len(long_arr)
        pct_short = 100 * (short_arr >= thresh).sum() / len(long_arr)
        if pct_long >= 1.0 and pct_short >= 1.0:
            recommended = thresh
            break
    
    if recommended:
        print(f"  ★ 권장: {recommended} (long/short 각 1%+ 발생)")
        oos_long_est = int((long_arr >= recommended).sum() * sample_to_oos_ratio)
        oos_short_est = int((short_arr >= recommended).sum() * sample_to_oos_ratio)
        print(f"  OOS 12mo 추정 신호: Long ≈ {oos_long_est:,}, Short ≈ {oos_short_est:,}")
    else:
        print(f"  ⚠️ 임계 0.30에서도 1% 미달 — 모델 자체 문제 가능")
        max_at_030 = max(100*(long_arr >= 0.30).sum() / len(long_arr), 100*(short_arr >= 0.30).sum() / len(long_arr))
        print(f"    임계 0.30 시 max(long%,short%) = {max_at_030:.2f}%")
    
    # 결과 csv
    diag = pd.DataFrame({
        'stay_prob': stay_arr, 'long_prob': long_arr, 'short_prob': short_arr,
        'regime': regimes,
    })
    diag_path = os.path.join(WORK_DIR, 'diag_result.csv')
    diag.to_csv(diag_path, index=False, encoding='utf-8-sig')
    print(f"\n[저장] {diag_path}")
    print(f"\n사용자 작업: 권장 임계를 본인에게 보고 → 본인이 measure_stage1.py 재측정 안내")


if __name__ == "__main__":
    main()
