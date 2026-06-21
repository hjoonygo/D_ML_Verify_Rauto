# ==============================================================================
# [파일명] oos_regression_V80k_Verify_3.py
# [코드길이] 약 200줄 / 내부버전 V80k_Verify_3_S3 / 로직축약·생략 없이 전체 출력
# [모듈 종류] 회귀 검증 (학습된 TBM v3 모델을 OOS 30%에 추론 → 골든 메트릭 비교)
# ==============================================================================
# [목적]
#   train_tbm_v2()로 학습한 신규 v3 모델이 V8.0.k 원본 v2와 동등 성능인지 검증.
#   OOS 30% 데이터에서 conf 분포를 Takeaway 3.3.3 골든 값과 비교.
#
# [📥 IN]
#   csv_path        : 21mo CSV (Merged_21mo.csv)
#   models_dir      : v3 모델 폴더 (train_tbm_v2 출력)
#   regime_model_path: Regime 70% 학습 모델 (D1 누설 차단판)
#
# [📤 OUT - JSON]
#   {
#     'oos_conf_distribution': {
#         'BULL': {'conf_07_pct', 'conf_06_pct', 'conf_05_pct'},
#         'BEAR': {...}, 'CHOP': {...}
#     },
#     'golden_comparison': {
#         'BULL': {'actual': 22.7%, 'golden': 22.7%, 'pass': True}, ...
#     },
#     'overall_pass': bool,
#     'tbm_action_distribution': {LONG/SHORT/NO_PROFIT 비율}
#   }
#
# [출처]
#   Takeaway 3.3.3 명시: OOS conf>=0.7 비율 BULL 22.7%, BEAR 29.5%, CHOP 68.8%
#   허용 ±5%p (절대 기준)
# ==============================================================================
import os
import sys
import json
import argparse
import numpy as np
import pandas as pd
import xgboost as xgb


GOLDEN_OOS = {
    'BULL': {'conf_07_pct': 22.7, 'conf_06_pct': None, 'conf_05_pct': None},
    'BEAR': {'conf_07_pct': 29.5, 'conf_06_pct': None, 'conf_05_pct': None},
    'CHOP': {'conf_07_pct': 68.8, 'conf_06_pct': None, 'conf_05_pct': None},
}
TOLERANCE_PCT = 5.0  # ±5%p


def regression_test_oos(csv_path, models_dir, regime_model_path,
                        train_split=0.70, log_fn=print):
    """v3 모델로 OOS 30% 추론 → Takeaway 3.3.3 골든 메트릭 비교."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from PautoV80_Regime_ML import compute_features, FEATURE_COLS, _load_csv_auto
    
    log_fn("=" * 78)
    log_fn(f"V80k_Verify_3_S3 — OOS 회귀 검증 (TBM v3 vs Takeaway 3.3.3 골든)")
    log_fn("=" * 78)
    
    # 1. 데이터 + 분할
    df = _load_csv_auto(csv_path)
    n = len(df)
    split_idx = int(n * train_split)
    log_fn(f"  전체 {n:,}봉 / 학습 {split_idx:,} / OOS {n-split_idx:,}")
    
    feat = compute_features(df)
    feat_oos = feat.iloc[split_idx:]
    feat_oos_clean = feat_oos[FEATURE_COLS].dropna()
    X_oos = feat_oos_clean.values
    log_fn(f"  OOS 유효 봉수: {len(X_oos):,}")
    
    # 2. Regime 추론 → 환경별 분리
    regime = xgb.XGBClassifier()
    regime.load_model(regime_model_path)
    rg_proba = regime.predict_proba(X_oos)
    rg_pred = rg_proba.argmax(axis=1)
    
    log_fn(f"  OOS 환경 분포:")
    env_idx = {}
    for r_id, r_name in [(0, 'BULL'), (1, 'BEAR'), (2, 'CHOP')]:
        mask = rg_pred == r_id
        env_idx[r_name] = mask
        log_fn(f"    {r_name}: {mask.sum():>6,} ({mask.sum()/len(X_oos)*100:.2f}%)")
    
    # 3. 환경별 TBM v3 추론 + conf 분포
    oos_conf_dist = {}
    action_count = {'LONG': 0, 'SHORT': 0, 'NO_PROFIT': 0}
    
    for r_name in ['BULL', 'BEAR', 'CHOP']:
        model_path = os.path.join(models_dir, f"PautoV80_TBM_{r_name}_v3.json")
        if not os.path.exists(model_path):
            log_fn(f"  ⚠ {r_name} 모델 없음: {model_path}")
            oos_conf_dist[r_name] = {'skipped': True}
            continue
        
        m = xgb.XGBClassifier()
        m.load_model(model_path)
        
        mask = env_idx[r_name]
        if mask.sum() == 0:
            log_fn(f"  {r_name}: OOS 환경 봉 없음")
            oos_conf_dist[r_name] = {'n': 0}
            continue
        
        X_env = X_oos[mask]
        proba = m.predict_proba(X_env)
        pred = proba.argmax(axis=1)
        conf = proba.max(axis=1)
        
        # conf 분포
        n_env = len(X_env)
        c05 = (conf >= 0.5).sum()
        c06 = (conf >= 0.6).sum()
        c07 = (conf >= 0.7).sum()
        
        oos_conf_dist[r_name] = {
            'n_oos': int(n_env),
            'conf_05_pct': float(c05/n_env*100),
            'conf_06_pct': float(c06/n_env*100),
            'conf_07_pct': float(c07/n_env*100),
            'action_dist': {
                'LONG': int((pred == 0).sum()),
                'SHORT': int((pred == 1).sum()),
                'NO_PROFIT': int((pred == 2).sum()),
            }
        }
        
        action_count['LONG'] += oos_conf_dist[r_name]['action_dist']['LONG']
        action_count['SHORT'] += oos_conf_dist[r_name]['action_dist']['SHORT']
        action_count['NO_PROFIT'] += oos_conf_dist[r_name]['action_dist']['NO_PROFIT']
        
        log_fn(f"\n  [{r_name}] OOS {n_env:,}봉")
        log_fn(f"    conf>=0.5: {c05/n_env*100:5.2f}% | conf>=0.6: {c06/n_env*100:5.2f}% | conf>=0.7: {c07/n_env*100:5.2f}%")
    
    # 4. 골든 메트릭 비교
    log_fn(f"\n[골든 메트릭 비교 — Takeaway 3.3.3]")
    golden_cmp = {}
    pass_count = 0
    fail_count = 0
    
    for r_name in ['BULL', 'BEAR', 'CHOP']:
        if oos_conf_dist.get(r_name, {}).get('skipped') or oos_conf_dist.get(r_name, {}).get('n') == 0:
            golden_cmp[r_name] = {'skipped': True}
            continue
        
        actual = oos_conf_dist[r_name]['conf_07_pct']
        target = GOLDEN_OOS[r_name]['conf_07_pct']
        diff = abs(actual - target)
        passed = diff <= TOLERANCE_PCT
        
        golden_cmp[r_name] = {
            'metric': 'conf_07_pct',
            'actual': actual,
            'golden': target,
            'abs_diff_pct': diff,
            'tolerance': TOLERANCE_PCT,
            'pass': passed,
        }
        
        mark = '✓' if passed else '✗'
        log_fn(f"  {mark} {r_name}: 실측 {actual:5.2f}% | 골든 {target:5.2f}% | 차이 {diff:.2f}%p")
        
        if passed:
            pass_count += 1
        else:
            fail_count += 1
    
    overall_pass = fail_count == 0
    log_fn(f"\n  종합: {pass_count}/{pass_count+fail_count} 통과")
    log_fn(f"  판정: {'★ PASS — OOS 분포 골든과 일치' if overall_pass else '⚠ FAIL — 격차 검토 필요'}")
    
    return {
        'oos_conf_distribution': oos_conf_dist,
        'golden_comparison': golden_cmp,
        'overall_pass': overall_pass,
        'tbm_action_distribution': action_count,
        'split_idx': int(split_idx),
        'oos_n': int(len(X_oos)),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--csv', required=True)
    parser.add_argument('--models-dir', required=True)
    parser.add_argument('--regime-model', required=True)
    parser.add_argument('--output', default='V80k_Verify_3_S3_oos_regression.json')
    args = parser.parse_args()
    
    result = regression_test_oos(args.csv, args.models_dir, args.regime_model)
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\n[저장] {args.output}")
    sys.exit(0 if result['overall_pass'] else 1)
