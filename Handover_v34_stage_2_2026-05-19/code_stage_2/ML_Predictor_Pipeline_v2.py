# [파일명] ML_Predictor_Pipeline_v2.py
# 코드길이: 약 220줄, 내부버전명: v2.0 (v3.4_fib), 로직 축약/생략 없이 전체 출력
#
# [목적] PautoV75 학습기 v2 — 3-class triple barrier + 정정 ⓟ-6/11/12
#
# [정정 사항]
#  - ⓟ-6 (라벨 단방향): binary long_success → 3-class {0=stay, 1=long, 2=short}
#  - ⓟ-11 (rolling 방향): shift(-1).rolling(10) → 진짜 미래 N봉 max/min
#  - ⓟ-12 (ATR 3항): max(h-l, |h-c_prev|) → max(h-l, |h-c_prev|, |l-c_prev|) — 표준 ATR
#  - ⓟ-9 (학습=백테스트): 학습 인자 명시 권장 (이전 v7.6에서 정정됨, 유지)
#
# [변수 파이프라인]
# 📥 IN: Merged_Data.csv (사용자 PC D:\ML\Verify\)
# 🛠️ STATE: 9 features + 3-class triple barrier 라벨링 + XGBoost 학습
# 📤 OUT:
#   - PautoV75_XGB_3class_v2.json (모델 가중치)
#   - PautoV75_XGB_3class_v2_meta.json (메타)
#
# [함수 목록 + In/Out]
#   calculate_internal_features(df) -> df+9컬럼
#     IN: DataFrame (timestamp idx, OHLCV, oi_sum 등)
#     OUT: 9 feature 컬럼 추가된 DataFrame
#
#   apply_triple_barrier_v2(df, N=10) -> df+target
#     IN: DataFrame + 미래 N봉 (기본 10)
#     OUT: target 컬럼 (0/1/2) 추가
#
#   train_xgboost_3class(train_start, train_end, future_n=10) -> None
#     IN: 학습 기간 + 미래 N봉
#     OUT: 모델 + 메타 저장

import pandas as pd
import numpy as np
import xgboost as xgb
import os
import json
import sys

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(WORK_DIR, "..", "Merged_Data.csv")
MODEL_PATH = os.path.join(WORK_DIR, "PautoV75_XGB_3class_v2.json")
META_PATH = os.path.join(WORK_DIR, "PautoV75_XGB_3class_v2_meta.json")


def calculate_internal_features(df):
    """
    9개 feature 계산. ⓟ-12 ATR 3항 정정 적용.
    IN: df (OHLCV + oi_sum/oi_value/open_interest 중 하나)
    OUT: df + 9 feature 컬럼
    """
    delta_px = df['close'].diff()
    gain = (delta_px.where(delta_px > 0, 0)).rolling(window=14).mean()
    loss = (-delta_px.where(delta_px < 0, 0)).rolling(window=14).mean()
    df['rsi_14'] = 100 - (100 / (1 + gain / loss))

    df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
    df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['ema_dist'] = (df['ema_20'] - df['ema_50']) / df['ema_50'] * 100

    # ⓟ-12 정정: ATR 3항 (표준 Wilder ATR)
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())   # ★ 추가
    true_range = np.max(pd.concat([high_low, high_close, low_close], axis=1), axis=1)
    df['atr_14'] = true_range.rolling(14).mean()

    df['fvg_bull'] = (df['low'] > df['high'].shift(2)).astype(int)
    df['fvg_bear'] = (df['high'] < df['low'].shift(2)).astype(int)

    # OI 컬럼 자동 인식
    if 'open_interest' in df.columns:
        oi_col = 'open_interest'
    elif 'oi_sum' in df.columns:
        oi_col = 'oi_sum'
    elif 'oi_value' in df.columns:
        oi_col = 'oi_value'
    else:
        raise KeyError("OI 컬럼 없음 - open_interest/oi_sum/oi_value 중 하나 필요")
    df['oi_delta'] = df[oi_col].pct_change(periods=3).fillna(0) * 100
    df['rvol_20'] = df['volume'] / (df['volume'].rolling(window=20).mean() + 1e-8)
    df['vol_accel'] = df['volume'].pct_change().fillna(0).replace([np.inf, -np.inf], 0)

    buy_pressure = (df['close'] - df['low']) / (df['high'] - df['low'] + 1e-8)
    df['order_delta'] = df['volume'] * (buy_pressure * 2 - 1)
    df['delta_sign'] = np.sign(df['order_delta'])
    df['delta_streak'] = df.groupby((df['delta_sign'] != df['delta_sign'].shift()).cumsum())['delta_sign'].cumsum()

    return df.dropna()


def apply_triple_barrier_v2(df, future_n=10):
    """
    ⓟ-6 + ⓟ-11 정정: 3-class triple barrier + 진짜 미래 N봉.

    각 시점 t에서:
      pt_dist = ATR(t) * 1.5
      sl_dist = ATR(t) * 1.0
      미래 N봉 [t+1, t+N]의 high/low 검사:
        - 미래 high 중 어느 것이 close+pt_dist 도달 + 미래 low 모두 close-sl_dist 위 → long 성공 (target=1)
        - 미래 low 중 어느 것이 close-pt_dist 도달 + 미래 high 모두 close+sl_dist 아래 → short 성공 (target=2)
        - 둘 다 아님 → stay (target=0)

    IN: df (calculate_internal_features 통과)
    OUT: df + target 컬럼 (0/1/2)
    """
    pt_dist = df['atr_14'] * 1.5
    sl_dist = df['atr_14'] * 1.0

    n = len(df)
    close = df['close'].values
    high = df['high'].values
    low = df['low'].values
    pt = pt_dist.values
    sl = sl_dist.values

    target = np.zeros(n, dtype=np.int64)  # 기본 stay=0

    # ⓟ-11 정정: 진짜 미래 N봉 max/min 계산 (vectorized)
    # future_high[t] = max(high[t+1], high[t+2], ..., high[t+N])
    # future_low[t]  = min(low[t+1], low[t+2], ..., low[t+N])
    for t in range(n - future_n):
        slice_high = high[t+1 : t+1+future_n]
        slice_low = low[t+1 : t+1+future_n]

        c = close[t]
        ptd = pt[t]
        sld = sl[t]
        if np.isnan(ptd) or np.isnan(sld):
            continue

        max_h = slice_high.max()
        min_l = slice_low.min()

        long_success = (max_h >= c + ptd) and (min_l > c - sld)
        short_success = (min_l <= c - ptd) and (max_h < c + sld)

        # 둘 다 성공 (드물지만 가능) — 더 빨리 도달한 쪽 선택
        if long_success and short_success:
            # 진짜 first-hit 결정: t+1부터 순서대로 검사
            for k in range(future_n):
                h_k = slice_high[k]
                l_k = slice_low[k]
                hit_long = h_k >= c + ptd
                hit_short = l_k <= c - ptd
                if hit_long and hit_short:
                    target[t] = 1  # 동률은 long 우선 (관례)
                    break
                elif hit_long:
                    target[t] = 1
                    break
                elif hit_short:
                    target[t] = 2
                    break
        elif long_success:
            target[t] = 1
        elif short_success:
            target[t] = 2

    df['target'] = target
    return df


def train_xgboost_3class(train_start=None, train_end=None, future_n=10):
    """
    3-class XGBoost 학습. ⓟ-9 학습기간 인자 필수 권장.

    IN:
      train_start: '%Y-%m-%d' or None
      train_end: '%Y-%m-%d' or None
      future_n: 미래 N봉 (기본 10)
    OUT:
      MODEL_PATH 저장 + META_PATH 저장
    """
    if not os.path.exists(DATA_PATH):
        print(f"[ERROR] 데이터 파일 없음: {DATA_PATH}")
        return False

    df = pd.read_csv(DATA_PATH, parse_dates=['timestamp'])
    df.set_index('timestamp', inplace=True)

    full_start, full_end = df.index.min(), df.index.max()
    actual_start = pd.to_datetime(train_start) if train_start else full_start
    actual_end = pd.to_datetime(train_end) if train_end else full_end

    # tz 정합화
    data_is_tz = full_start.tz is not None
    arg_start_tz = actual_start.tz is not None if isinstance(actual_start, pd.Timestamp) else False
    arg_end_tz = actual_end.tz is not None if isinstance(actual_end, pd.Timestamp) else False

    if data_is_tz != arg_start_tz:
        if data_is_tz and not arg_start_tz:
            actual_start = actual_start.tz_localize(full_start.tz)
        else:
            actual_start = actual_start.tz_localize(None)
    if data_is_tz != arg_end_tz:
        if data_is_tz and not arg_end_tz:
            actual_end = actual_end.tz_localize(full_start.tz)
        else:
            actual_end = actual_end.tz_localize(None)

    print(f"[tz 정합화] 데이터 tz: {full_start.tz}, 학습 인자: {actual_start.tz}")

    if actual_start > full_end or actual_end < full_start:
        print(f"⚠️ 학습기간 범위 밖. 데이터: {full_start} ~ {full_end}")
        return False

    df_train = df.loc[actual_start:actual_end].copy()
    n_total = len(df)
    n_train = len(df_train)

    print(f"\n[학습기간 분리]")
    print(f"  전체: {full_start} ~ {full_end} ({n_total:,} rows)")
    print(f"  학습: {df_train.index.min()} ~ {df_train.index.max()} ({n_train:,} rows, {100*n_train/n_total:.1f}%)")
    print(f"  OOS: {n_total - n_train:,} rows ({100*(n_total-n_train)/n_total:.1f}%)")

    df_train = calculate_internal_features(df_train)
    df_train = apply_triple_barrier_v2(df_train, future_n=future_n).dropna()

    features = ['rsi_14', 'ema_dist', 'atr_14', 'fvg_bull', 'fvg_bear',
                'oi_delta', 'rvol_20', 'vol_accel', 'delta_streak']
    X = df_train[features]
    y = df_train['target']

    print(f"  Feature 완료: {len(df_train):,} rows")
    target_counts = y.value_counts().to_dict()
    print(f"  Target 3-class 분포: {target_counts}")
    for k in [0, 1, 2]:
        cnt = target_counts.get(k, 0)
        name = {0: 'stay', 1: 'long', 2: 'short'}[k]
        pct = 100 * cnt / len(y) if len(y) > 0 else 0
        print(f"    {name}: {cnt:,} ({pct:.2f}%)")

    # XGBoost 3-class
    model = xgb.XGBClassifier(
        n_estimators=150, max_depth=6, learning_rate=0.03,
        colsample_bytree=0.8, random_state=42,
        objective='multi:softprob', num_class=3,
    )
    model.fit(X, y)
    model.save_model(MODEL_PATH)

    meta = {
        'version': 'v2.0_v34_fib',
        'train_start': str(df_train.index.min()),
        'train_end': str(df_train.index.max()),
        'train_rows': int(n_train),
        'features': features,
        'future_n': future_n,
        'n_estimators': 150, 'max_depth': 6, 'learning_rate': 0.03,
        'objective': 'multi:softprob', 'num_class': 3,
        'target_distribution': {str(k): int(v) for k, v in target_counts.items()},
        'corrections': ['p-6 (binary->3class)', 'p-11 (rolling direction)', 'p-12 (ATR 3-term)'],
        'created_at': pd.Timestamp.now().isoformat(),
    }
    with open(META_PATH, 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=2)

    print(f"\n✅ 3-class XGBoost 학습 완료.")
    print(f"   모델: {MODEL_PATH}")
    print(f"   메타: {META_PATH}")
    return True


if __name__ == "__main__":
    args = sys.argv[1:]
    train_start = None
    train_end = None

    if len(args) == 2:
        train_start, train_end = args
    elif len(args) == 4:
        train_start = f"{args[0]} {args[1]}"
        train_end = f"{args[2]} {args[3]}"
        print(f"[자동 조립] '{train_start}', '{train_end}'")
    elif len(args) == 0:
        print("⚠️ 학습 기간 인자 *반드시 권장*. ⓟ-9 IS 결과 위험.")
        print("   사용법: python ML_Predictor_Pipeline_v2.py 2023-05-01 2025-04-30")
        sys.exit(1)
    else:
        print(f"⚠️ 인자 개수 비정상 ({len(args)}). 사용법:")
        print("   python ML_Predictor_Pipeline_v2.py 2023-05-01 2025-04-30")
        sys.exit(1)

    train_xgboost_3class(train_start, train_end)
