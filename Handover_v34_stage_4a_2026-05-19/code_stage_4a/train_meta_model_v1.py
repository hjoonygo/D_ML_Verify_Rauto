# -*- coding: utf-8 -*-
"""
[파일명] train_meta_model_v1.py
코드길이: 약 390줄, 내부버전명: v2.1_sample_weight_normalized
검증: measure_v34_stage_4a.py가 생성한 features 캐시 입력 형식 + sample_weight 정규화

[v2.0 → v2.1 변경]
  - sample_weight = |net_return| 원본은 max/min ratio 2254배 → XGBoost 학습 실패 (AUC=0.5)
  - 수정: log1p(x*100) / median 정규화 → median=1 기준 0.1~5 범위로 압축
  - 사용자 결정 B:d (|net_return| weight)의 *변형* — 학술 표준 log scale 적용

[목적] Stage 4A Phase 1 — M2 메타 모델 학습 (4 시나리오)
  base_no_meta는 학습 안 함 (measure에서 M2 없이 시뮬만)

[입력 (IN) — outputs_stage_4a/ 폴더 안]
  - trades_train_phase_4a.csv     (Train 시뮬, M2 학습용 라벨)
  - trades_s0_v10_baseline_sl180.csv (OOS trades, 인수인계 zip 또는 D:\\ML\\Verify\\)
  - signal_features_train_4a.pkl  (Train 신호 features+probs)
  - signal_features_oos_4a.pkl    (OOS 신호 features+probs)
  - regime_master_at_entry.pkl    (Regime_Master lookup)

[출력 (OUT) — outputs_stage_4a/ 폴더 안 (통합)]
  - M2_meta_simple.json + _meta.json
  - M2_meta_purged.json + _meta.json
  - M2_meta_regime.json + _meta.json
  - M2_meta_oos_only.json + _meta.json
  - m2_training_log.txt

[알고리즘]
  - XGBoost binary:logistic (사용자 결정 e)
  - sample_weight = |net_return| (사용자 결정 B:d)
  - feature 정규화 없음 (사용자 결정 f)
  - PurgedKFold 3-fold + embargo 1% (López de Prado Ch.7.4)

[시나리오별 특성]
  meta_simple:   PurgedKFold X, Train+OOS 통합 학습
  meta_purged:   PurgedKFold O, Train+OOS 통합 학습
  meta_regime:   meta_purged + regime_v33 + Regime_Master one-hot
  meta_oos_only: PurgedKFold O, OOS만 학습 (A:b 위험 검증)
"""
import os
import sys
import json
import pickle
import time
import numpy as np
import pandas as pd
import xgboost as xgb
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(WORK_DIR, "outputs_stage_4a")


def find_file(filename):
    candidates = [
        os.path.join(OUTPUT_DIR, filename),
        os.path.join(WORK_DIR, filename),
        os.path.join(WORK_DIR, "..", filename),
        os.path.join(WORK_DIR, "..", "..", filename),
    ]
    grandparent = os.path.abspath(os.path.join(WORK_DIR, "..", ".."))
    if os.path.isdir(grandparent):
        try:
            for entry in os.listdir(grandparent):
                subpath = os.path.join(grandparent, entry)
                if os.path.isdir(subpath):
                    candidates.append(os.path.join(subpath, filename))
                    try:
                        for entry2 in os.listdir(subpath):
                            sub2 = os.path.join(subpath, entry2)
                            if os.path.isdir(sub2):
                                candidates.append(os.path.join(sub2, filename))
                    except (PermissionError, OSError):
                        pass
        except (PermissionError, OSError):
            pass
    for path in candidates:
        if os.path.exists(path):
            return os.path.abspath(path)
    return None


def load_trades_data(train_path, oos_path):
    """Train + OOS trades 통합."""
    train_df = pd.read_csv(train_path, parse_dates=['entry_t', 'exit_t'])
    train_df['source'] = 'train'
    oos_df = pd.read_csv(oos_path, parse_dates=['entry_t', 'exit_t'])
    oos_df['source'] = 'oos'
    df = pd.concat([train_df, oos_df], axis=0, ignore_index=True)

    valid_exits = ['initial_sl', 'step1_sl', 'step2_sl', 'step3_sl',
                   'timeout_4h', 'timeout_16h', 'timeout_18h',
                   'timeout_step_active', 'reversal_2h']
    is_valid = df['exit_reason'].apply(
        lambda r: isinstance(r, str) and (
            r in valid_exits or r.startswith('timeout_')
        )
    )
    df_valid = df[is_valid].copy()

    n_tr = (df_valid['source'] == 'train').sum()
    n_oos = (df_valid['source'] == 'oos').sum()
    print(f"  Train valid: {n_tr}건, OOS valid: {n_oos}건, 통합: {len(df_valid)}건")
    if n_oos < 200:
        print(f"  ⚠️ OOS {n_oos}건 — meta_oos_only 신뢰도 주의")
    return df_valid


def build_m2_dataset(df_valid, scenario, train_features_cache, oos_features_cache,
                     rm_lookup, df_1m_index):
    """M2 학습 데이터셋 생성.

    IN: df_valid (trades), scenario, features 캐시 2개, rm_lookup (Regime_Master),
        df_1m_index (timestamp ↔ idx 매핑용, optional)
    OUT: (X, y, w, times, feature_names)
    """
    if scenario == 'meta_oos_only':
        df_use = df_valid[df_valid['source'] == 'oos'].copy()
        print(f"  meta_oos_only: OOS {len(df_use)}건만")
        if len(df_use) < 30:
            raise ValueError(f"OOS 데이터 너무 적음: {len(df_use)}")
    else:
        df_use = df_valid.copy()

    rows = []
    skipped = {'no_features': 0}

    for _, trade in df_use.iterrows():
        entry_t = pd.Timestamp(trade['entry_t'])
        source = trade.get('source', 'oos')

        # features cache lookup
        # trades csv의 'entry_signal_idx_1m' 컬럼이 있으면 idx 기반, 없으면 timestamp 매칭 시도
        idx = trade.get('entry_signal_idx_1m', None)
        feats = None
        if idx is not None and not pd.isna(idx):
            idx = int(idx)
            if source == 'train' and idx in train_features_cache:
                feats = train_features_cache[idx]
            elif source == 'oos' and idx in oos_features_cache:
                feats = oos_features_cache[idx]

        if feats is None:
            skipped['no_features'] += 1
            continue

        row = {
            'rsi_14': feats['rsi_14'], 'ema_dist': feats['ema_dist'],
            'atr_14': feats['atr_14'], 'fvg_bull': feats['fvg_bull'],
            'fvg_bear': feats['fvg_bear'], 'oi_delta': feats['oi_delta'],
            'rvol_20': feats['rvol_20'], 'vol_accel': feats['vol_accel'],
            'delta_streak': feats['delta_streak'],
            'prob_long': feats['prob_long'], 'prob_short': feats['prob_short'],
            'prob_stay': feats['prob_stay'],
            'side_long': 1 if trade['side'] == 'long' else 0,
            'side_short': 1 if trade['side'] == 'short' else 0,
            'entry_t': entry_t, 'exit_t': pd.Timestamp(trade['exit_t']),
            'net_return': float(trade['net_return']),
            'label': 1 if float(trade['net_return']) > 0 else 0,
            'source': source,
        }

        if scenario == 'meta_regime':
            reg_v33 = str(trade.get('regime_at_entry', 'lovol_range'))
            for r in ['uptrend', 'downtrend', 'hivol_range', 'lovol_range']:
                row[f'regime_v33_{r}'] = 1 if reg_v33 == r else 0
            rm = 'CHOPPY'
            if rm_lookup:
                for delta_min in range(0, 121, 15):
                    cand = entry_t - pd.Timedelta(minutes=delta_min)
                    if cand in rm_lookup:
                        rm = rm_lookup[cand]
                        break
            for r in ['BULLISH_EXPANSION', 'BEARISH_EXPANSION', 'CHOPPY']:
                row[f'regime_master_{r}'] = 1 if rm == r else 0

        rows.append(row)

    print(f"  데이터셋: 사용 {len(rows)}건, 스킵 {skipped['no_features']}(no_features)")
    if len(rows) == 0:
        raise ValueError(f"{scenario} 데이터셋 비어있음")

    dataset = pd.DataFrame(rows)

    base_features = ['rsi_14', 'ema_dist', 'atr_14', 'fvg_bull', 'fvg_bear',
                     'oi_delta', 'rvol_20', 'vol_accel', 'delta_streak',
                     'prob_long', 'prob_short', 'prob_stay',
                     'side_long', 'side_short']

    if scenario == 'meta_regime':
        regime_features = [
            'regime_v33_uptrend', 'regime_v33_downtrend',
            'regime_v33_hivol_range', 'regime_v33_lovol_range',
            'regime_master_BULLISH_EXPANSION',
            'regime_master_BEARISH_EXPANSION', 'regime_master_CHOPPY',
        ]
        feature_names = base_features + regime_features
    else:
        feature_names = base_features

    X = dataset[feature_names].copy()
    y = dataset['label'].values.astype(int)

    # ★ sample_weight (사용자 결정 B:d) + 정규화 (a 선택)
    # 원본 |net_return| 분포: min~0.000022, max~0.050335, ratio~2254배
    # → XGBoost 학습 실패 (AUC=0.5).
    # 정규화 3단계:
    #   1) log1p(x*100): 큰 값 압축
    #   2) median 정규화: median=1 기준
    #   3) 하한 0.05 clip: 극소값 보호 → 최종 max/min ratio < 100배 (학습 안전)
    w_raw = np.abs(dataset['net_return'].values)
    w_raw = np.maximum(w_raw, 1e-6)
    w = np.log1p(w_raw * 100)
    median_w = np.median(w)
    if median_w > 0:
        w = w / median_w
    w = np.clip(w, 0.07, None)  # 하한 clip — XGBoost 학습 안전 범위 (ratio < 75배)
    print(f"  sample_weight: raw ratio={w_raw.max()/w_raw.min():.0f}배 "
          f"→ normalized min/median/max={w.min():.3f}/{np.median(w):.3f}/{w.max():.3f} "
          f"(ratio={w.max()/w.min():.1f}배)")

    times = dataset[['entry_t', 'exit_t']].reset_index(drop=True)
    return X, y, w, times, feature_names


def purged_kfold_split(times, n_splits=3, embargo_pct=0.01):
    """López de Prado Ch.7.4 PurgedKFold."""
    n = len(times)
    sorted_order = times['entry_t'].argsort().values
    sorted_times = times.iloc[sorted_order].reset_index(drop=True)
    fold_size = n // n_splits
    embargo_size = max(1, int(n * embargo_pct))

    for k in range(n_splits):
        test_start = k * fold_size
        test_end = (k + 1) * fold_size if k < n_splits - 1 else n
        test_idx = np.arange(test_start, test_end)

        test_t0 = sorted_times.iloc[test_start]['entry_t']
        test_t1 = sorted_times.iloc[test_end - 1]['exit_t']

        train_cand = [i for i in range(n) if i not in test_idx]
        purged = []
        for i in train_cand:
            t_e = sorted_times.iloc[i]['entry_t']
            t_x = sorted_times.iloc[i]['exit_t']
            if (t_x >= test_t0) and (t_e <= test_t1):
                continue
            purged.append(i)
        embargo_end = min(test_end + embargo_size, n)
        purged = [i for i in purged if not (test_end <= i < embargo_end)]

        yield sorted_order[purged], sorted_order[test_idx]


def train_m2(X, y, w, times, scenario, use_purged_cv=True, n_splits=3):
    """M2 XGBoost binary 학습 + CV."""
    from sklearn.metrics import roc_auc_score, f1_score
    cv_results = []

    if use_purged_cv and len(X) > n_splits * 5:
        for fi, (tr_idx, te_idx) in enumerate(purged_kfold_split(times, n_splits=n_splits)):
            X_tr, X_te = X.iloc[tr_idx], X.iloc[te_idx]
            y_tr, y_te = y[tr_idx], y[te_idx]
            w_tr = w[tr_idx]

            if len(X_tr) < 10 or len(X_te) < 5 or len(np.unique(y_tr)) < 2:
                print(f"    fold {fi+1}: skip (tr={len(X_tr)}, te={len(X_te)})")
                continue

            m = xgb.XGBClassifier(
                n_estimators=100, max_depth=4, learning_rate=0.05,
                colsample_bytree=0.8, random_state=42,
                objective='binary:logistic', eval_metric='logloss',
            )
            m.fit(X_tr, y_tr, sample_weight=w_tr)
            y_proba = m.predict_proba(X_te)[:, 1]
            y_pred = (y_proba >= 0.5).astype(int)

            try:
                auc = roc_auc_score(y_te, y_proba) if len(np.unique(y_te)) > 1 else 0.5
            except Exception:
                auc = 0.5
            f1 = f1_score(y_te, y_pred, zero_division=0)
            cv_results.append({'fold': fi+1, 'n_train': len(X_tr), 'n_test': len(X_te),
                              'auc': float(auc), 'f1': float(f1)})
            print(f"    fold {fi+1}: tr={len(X_tr)} te={len(X_te)} AUC={auc:.3f} F1={f1:.3f}")

    # 최종 모델
    model = xgb.XGBClassifier(
        n_estimators=100, max_depth=4, learning_rate=0.05,
        colsample_bytree=0.8, random_state=42,
        objective='binary:logistic', eval_metric='logloss',
    )
    model.fit(X, y, sample_weight=w)
    print(f"    최종 학습 완료 (n={len(X)})")

    cv_scores = {
        'folds': cv_results,
        'mean_auc': float(np.mean([r['auc'] for r in cv_results])) if cv_results else None,
        'mean_f1': float(np.mean([r['f1'] for r in cv_results])) if cv_results else None,
    }
    return model, cv_scores


def save_m2(model, scenario, feature_names, cv_scores, meta_info):
    """outputs_stage_4a/ 통합 폴더 안에 저장."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    model_path = os.path.join(OUTPUT_DIR, f"M2_{scenario}.json")
    meta_path = os.path.join(OUTPUT_DIR, f"M2_{scenario}_meta.json")

    model.save_model(model_path)

    meta = {
        'scenario': scenario,
        'features': feature_names, 'n_features': len(feature_names),
        'cv_scores': cv_scores,
        'n_train_total': int(meta_info['n_train_total']),
        'positive_rate': float(meta_info['positive_rate']),
        'mean_sample_weight': float(meta_info['mean_sample_weight']),
        'created_at': datetime.utcnow().isoformat(),
        'sample_weight_method': 'abs_net_return',
        'm2_threshold': 0.5,
    }
    if scenario == 'meta_oos_only':
        meta['warning'] = 'small_sample_size'
        meta['reliability_note'] = (
            f"OOS {meta_info['n_train_total']}건만 학습. 300건+ 학술 권장 미달."
        )

    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=2, default=str, ensure_ascii=False)
    print(f"    저장: {os.path.basename(model_path)}, {os.path.basename(meta_path)}")


def main():
    log_lines = []
    def log(m):
        print(m)
        log_lines.append(str(m))

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    log(f"\n{'='*72}")
    log(f"[Stage 4A M2 학습] {datetime.now()}")
    log(f"내부버전: v2.0_uses_features_cache")
    log(f"출력: {OUTPUT_DIR}")
    log(f"{'='*72}")

    train_trades = find_file('trades_train_phase_4a.csv')
    oos_trades = find_file('trades_s0_v10_baseline_sl180.csv')
    train_feats_path = find_file('signal_features_train_4a.pkl')
    oos_feats_path = find_file('signal_features_oos_4a.pkl')
    rm_lookup_path = find_file('regime_master_at_entry.pkl')

    log(f"\n[입력]")
    log(f"  train_trades: {train_trades}")
    log(f"  oos_trades:   {oos_trades}")
    log(f"  train_feats:  {train_feats_path}")
    log(f"  oos_feats:    {oos_feats_path}")
    log(f"  rm_lookup:    {rm_lookup_path}")

    missing = []
    if not train_trades: missing.append('trades_train_phase_4a.csv')
    if not oos_trades: missing.append('trades_s0_v10_baseline_sl180.csv')
    if not train_feats_path: missing.append('signal_features_train_4a.pkl')
    if not oos_feats_path: missing.append('signal_features_oos_4a.pkl')

    if missing:
        log(f"\n❌ 누락: {missing}")
        return False

    df_valid = load_trades_data(train_trades, oos_trades)

    with open(train_feats_path, 'rb') as f:
        train_features_cache = pickle.load(f)
    with open(oos_feats_path, 'rb') as f:
        oos_features_cache = pickle.load(f)
    log(f"  features cache: train {len(train_features_cache)}, oos {len(oos_features_cache)}")

    rm_lookup = None
    if rm_lookup_path:
        with open(rm_lookup_path, 'rb') as f:
            rm_lookup = pickle.load(f)
        log(f"  rm_lookup: {len(rm_lookup)}")

    scenarios = [
        ('meta_simple', False, 3),
        ('meta_purged', True, 3),
        ('meta_regime', True, 3),
        ('meta_oos_only', True, 3),
    ]

    for s_name, use_cv, n_splits in scenarios:
        log(f"\n---- {s_name} ----")
        try:
            X, y, w, times, feat_names = build_m2_dataset(
                df_valid, s_name, train_features_cache, oos_features_cache,
                rm_lookup, None,
            )
            log(f"  n={len(X)}, features={len(feat_names)}, pos_rate={y.mean():.3f}")

            model, cv_scores = train_m2(X, y, w, times, s_name,
                                         use_purged_cv=use_cv, n_splits=n_splits)

            meta_info = {
                'n_train_total': len(X),
                'positive_rate': y.mean(),
                'mean_sample_weight': w.mean(),
            }
            save_m2(model, s_name, feat_names, cv_scores, meta_info)
        except Exception as e:
            log(f"  ❌ {s_name} 실패: {e}")
            import traceback
            log(traceback.format_exc())

    log_path = os.path.join(OUTPUT_DIR, "m2_training_log.txt")
    with open(log_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(log_lines))
    log(f"\n[M2 학습 완료]")
    return True


if __name__ == "__main__":
    main()
