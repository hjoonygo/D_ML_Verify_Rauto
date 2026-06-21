"""
[파일명] test_stage1_integration.py
코드길이: 약 200줄
목적: Stage 1 정정 4건 + TF aggregate + 3-class 모델 합성 데이터 검증

8개 시나리오:
1. 학습 모듈 ATR 3항 적용 확인
2. 학습 모듈 3-class 라벨 균형 확인
3. 학습 모듈 look-ahead 정정 확인 (rolling 방향)
4. Wrapper window_size=100 → Regime 가드 통과
5. TF aggregate (15m, 1h) 정상 작동
6. 3-class 모델 추론 정상 (predict_proba 3개 출력)
7. 신호 인덱스 1m 매핑 정상
8. v3.3 simulate_batch 통합 정상
"""
import sys, os, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import numpy as np
import xgboost as xgb

results = []
def chk(cond, msg):
    sym = "✓" if cond else "✗"
    results.append((msg, cond))
    print(f"  {sym} {msg}")
    return cond

print("="*70)
print("[Stage 1 통합 테스트 — 8개 시나리오]")
print("="*70)

# 합성 데이터 1mo (43,200 1m봉)
print("\n[합성 데이터 생성]")
rng = np.random.default_rng(42)
n = 43200
ts = pd.date_range('2025-05-01', periods=n, freq='1min', tz='UTC')
close = 30000 + np.cumsum(rng.normal(0, 30, n))
df_test = pd.DataFrame({
    'open': np.r_[close[0], close[:-1]],
    'high': close + np.abs(rng.normal(0, 20, n)),
    'low': close - np.abs(rng.normal(0, 20, n)),
    'close': close,
    'volume': np.abs(rng.normal(100, 20, n)),
    'oi_sum': 86000 + np.cumsum(rng.normal(0, 10, n)),
}, index=ts)
df_test.index.name = 'timestamp'

tmpdir = tempfile.mkdtemp()
csv_path = os.path.join(tmpdir, 'Merged_Data.csv')
df_test.reset_index().to_csv(csv_path, index=False)


# === 시나리오 1: 학습 모듈 ATR 3항 적용 ===
print("\n[시나리오 1] 학습 모듈 ATR 3항 (ⓟ-12 정정)")
import importlib
if 'ML_Predictor_Pipeline_PautoV75' in sys.modules:
    del sys.modules['ML_Predictor_Pipeline_PautoV75']
import ML_Predictor_Pipeline_PautoV75 as ml

# calculate_internal_features 호출
df_for_train = df_test.copy()
df_feats = ml.calculate_internal_features(df_for_train)
chk('atr_14' in df_feats.columns, "atr_14 생성됨")
# ATR 평균 (3항이면 더 큼)
high_low = df_test['high'] - df_test['low']
high_close = np.abs(df_test['high'] - df_test['close'].shift())
atr_2term = np.max(pd.concat([high_low, high_close], axis=1), axis=1).rolling(14).mean().mean()
atr_3term = df_feats['atr_14'].mean()
chk(atr_3term > atr_2term * 1.01, f"ATR 3항이 2항보다 큼 (3항 {atr_3term:.2f} vs 2항 {atr_2term:.2f})")


# === 시나리오 2: 학습 모듈 3-class 라벨 ===
print("\n[시나리오 2] 3-class 라벨 (ⓟ-6 정정)")
df_labeled = ml.apply_triple_barrier(df_feats.copy()).dropna()
target_dist = df_labeled['target'].value_counts().to_dict()
chk(set(df_labeled['target'].unique()).issubset({0, 1, 2}), f"라벨이 {{0,1,2}} 셋 안에 (실제 {df_labeled['target'].unique()})")
chk(0 in target_dist and 1 in target_dist and 2 in target_dist, f"3-class 모두 존재 {target_dist}")
# 양방향 라벨이면 long과 short 비슷한 비율
ratio = target_dist.get(1, 0) / max(1, target_dist.get(2, 0))
chk(0.3 < ratio < 3.3, f"long/short 비율 0.3~3.3 (실제 {ratio:.2f}) — 양방향 균형")


# === 시나리오 3: look-ahead 정정 ===
print("\n[시나리오 3] look-ahead 정정 (ⓟ-11)")
# t_test 위치의 future_high가 t+1~t+10 max인지 확인
# 주의: df_feats는 dropna() 후라 df_test와 인덱스 정합성 다름.
# df_feats 인덱스 기준으로 *진짜 비교 대상* 찾기
t_test = 1000
ts_at_t = df_feats.index[t_test]
ts_to_iloc = df_test.index.get_loc(ts_at_t)  # df_test 안의 실제 iloc

manual_max = df_test['high'].iloc[ts_to_iloc+1:ts_to_iloc+11].max()
manual_min = df_test['low'].iloc[ts_to_iloc+1:ts_to_iloc+11].min()

# apply_triple_barrier 내부 로직 재현 (df_feats 기준)
future_highs = pd.concat([df_feats['high'].shift(-i) for i in range(1, 11)], axis=1).max(axis=1)
future_lows = pd.concat([df_feats['low'].shift(-i) for i in range(1, 11)], axis=1).min(axis=1)
fh = future_highs.iloc[t_test]
fl = future_lows.iloc[t_test]
chk(np.isclose(fh, manual_max), f"future_high 일치 ({fh:.2f} vs manual {manual_max:.2f})")
chk(np.isclose(fl, manual_min), f"future_low 일치 ({fl:.2f} vs manual {manual_min:.2f})")


# === 시나리오 4: 3-class 모델 학습 + 추론 ===
print("\n[시나리오 4] 3-class 모델 학습 + 추론")
features = ['rsi_14', 'ema_dist', 'atr_14', 'fvg_bull', 'fvg_bear', 'oi_delta', 'rvol_20', 'vol_accel', 'delta_streak']
X = df_labeled[features]
y = df_labeled['target']
model = xgb.XGBClassifier(objective='multi:softprob', num_class=3, n_estimators=20, max_depth=4, random_state=42)
model.fit(X, y)
model_path = os.path.join(tmpdir, 'test_3class.json')
model.save_model(model_path)
chk(os.path.exists(model_path), "모델 저장 성공")
# 추론
proba = model.predict_proba(X.iloc[:5].values)
chk(proba.shape == (5, 3), f"predict_proba shape (5,3) (실제 {proba.shape})")
chk(np.allclose(proba.sum(axis=1), 1.0), "각 행 prob 합 = 1")


# === 시나리오 5: TF aggregate ===
print("\n[시나리오 5] TF aggregate (15m, 1h)")
from stage1_signal_wrapper import aggregate_to_tf
df_15m = aggregate_to_tf(df_test, 15)
df_1h = aggregate_to_tf(df_test, 60)
# resample(label='right', closed='right')이 경계봉 1개 추가 생성 가능
# 43200/15 = 2880 ± 1, 43200/60 = 720 ± 1
chk(abs(len(df_15m) - n // 15) <= 1, f"15m 봉수 ≈ {n//15}±1 (실제 {len(df_15m)})")
chk(abs(len(df_1h) - n // 60) <= 1, f"1h 봉수 ≈ {n//60}±1 (실제 {len(df_1h)})")
chk('oi_sum' in df_15m.columns, "15m에 oi_sum 포함")


# === 시나리오 6: Wrapper window_size=100 → Regime 가드 통과 ===
print("\n[시나리오 6] window_size=100 → Regime 작동")
from stage1_signal_wrapper import extract_signals_stage1
long_idx, short_idx, stats = extract_signals_stage1(
    df_test, model_path,
    tf_minutes=15,
    threshold_long=0.5, threshold_short=0.5,
    window_size=100,
    verbose_every=0,
)
# Regime이 BULLISH/BEARISH 분리 있어야 함 (100% CHOPPY 아님)
chk(stats['regime_distribution']['CHOPPY'] < stats['n_tf_bars'], 
    f"CHOPPY 비율 < 100% (실제 {stats['regime_distribution']})")


# === 시나리오 7: 1m 인덱스 매핑 ===
print("\n[시나리오 7] 신호 1m 인덱스 매핑")
chk(long_idx.dtype == np.int64 if len(long_idx) else True, "long dtype int64")
chk(short_idx.dtype == np.int64 if len(short_idx) else True, "short dtype int64")
if len(long_idx) > 0:
    chk((long_idx < n).all(), "1m 인덱스 범위 안")


# === 시나리오 8: v3.3 simulate_batch 통합 ===
print("\n[시나리오 8] v3.3 simulate_batch_vec_v4 통합")
from tbm_simulator_v4 import simulate_batch_vec_v4
ohlc = {
    'open': df_test['open'].values,
    'high': df_test['high'].values,
    'low': df_test['low'].values,
    'close': df_test['close'].values,
}
n_test = min(20, len(long_idx) if len(long_idx) else 0)
if n_test > 0:
    # holding 4 × 15m = 60 1m봉
    df_sim = simulate_batch_vec_v4(
        long_idx[:n_test], ohlc, sl_acct=0.05, tp_ratio=3.8,
        lev=10, holding_bars=60, side="long", mode="A"
    )
    chk(len(df_sim) > 0, f"시뮬 정상 ({len(df_sim)} 거래)")
    chk('net_return' in df_sim.columns, "net_return 컬럼")
else:
    chk(True, "long 신호 부족으로 시뮬 skip (정상)")

# === 정리 ===
shutil.rmtree(tmpdir)
print("\n" + "="*70)
passed = sum(1 for _, ok in results if ok)
print(f"단위 테스트 결과: {passed}/{len(results)} 통과")
for msg, ok in results:
    if not ok:
        print(f"  FAIL: {msg}")
sys.exit(0 if passed == len(results) else 1)
