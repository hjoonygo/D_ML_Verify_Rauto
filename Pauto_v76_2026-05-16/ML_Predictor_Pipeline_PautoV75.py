# ==============================================================================
# 모듈 (역할): AI 학습기 (ML_Predictor_Pipeline_PautoV75)
# 📥 입력 (IN): Merged_Data.csv (통합 마스터 데이터)
# 🛠️ 내부 처리 로직 (STATE): 9대 오더플로우 피처 생성, 손익비 기반 트리플 배리어 라벨링, XGBoost 훈련
# 📤 출력 (OUT): PautoV75_XGB_1to3_Predictor.json (AI 가중치 뇌 파일)
# ==============================================================================
import pandas as pd
import numpy as np
import xgboost as xgb
import os

# [핵심 수정]: 하드코딩된 C:\PASTBACKTEST 경로를 현재 실행 파일 위치로 동적 변경
WORK_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(WORK_DIR, "Merged_Data.csv")
MODEL_PATH = os.path.join(WORK_DIR, "PautoV75_XGB_1to3_Predictor.json")

def calculate_internal_features(df):
    delta_px = df['close'].diff()
    gain = (delta_px.where(delta_px > 0, 0)).rolling(window=14).mean()
    loss = (-delta_px.where(delta_px < 0, 0)).rolling(window=14).mean()
    df['rsi_14'] = 100 - (100 / (1 + gain / loss))

    df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
    df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['ema_dist'] = (df['ema_20'] - df['ema_50']) / df['ema_50'] * 100

    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    df['atr_14'] = np.max(pd.concat([high_low, high_close], axis=1), axis=1).rolling(14).mean()

    df['fvg_bull'] = (df['low'] > df['high'].shift(2)).astype(int)
    df['fvg_bear'] = (df['high'] < df['low'].shift(2)).astype(int)

    # [v7.6 정정] OI 컬럼명 자동 인식 (사용자 데이터 호환)
    # 우선순위: open_interest (PautoV75 원본) > oi_sum (BTC 수량) > oi_value (USD 환산)
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

def apply_triple_barrier(df):
    pt_dist = df['atr_14'] * 1.5
    sl_dist = df['atr_14'] * 1.0
    future_high = df['high'].shift(-1).rolling(10).max()
    future_low = df['low'].shift(-1).rolling(10).min()
    long_success = (future_high >= df['close'] + pt_dist) & (future_low > df['close'] - sl_dist)
    df['target'] = long_success.astype(int)
    return df

def train_xgboost_model(train_start: str = None, train_end: str = None):
    """
    [v7.6 점프 ⓟ-9 정정] 학습 기간 인자 추가
    
    In:
      train_start: '%Y-%m-%d' 형식. None이면 데이터 처음부터
      train_end: '%Y-%m-%d' 형식. None이면 데이터 끝까지
    Out:
      MODEL_PATH에 모델 저장 + meta JSON 함께 저장 (재현성)
    """
    if not os.path.exists(DATA_PATH): 
        print(f"데이터 파일이 없습니다: {DATA_PATH}")
        return
    df = pd.read_csv(DATA_PATH, parse_dates=['timestamp'])
    df.set_index('timestamp', inplace=True)
    
    # [v7.6 정정] 학습 기간 슬라이싱 (Look-ahead bias 방지)
    full_start, full_end = df.index.min(), df.index.max()
    actual_start = pd.to_datetime(train_start) if train_start else full_start
    actual_end = pd.to_datetime(train_end) if train_end else full_end
    
    # [v7.6 추가 정정] timezone 정합화 — 데이터와 인자의 tz가 다르면 자동 통일
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
    
    print(f"[v7.6 tz 정합화] 데이터 tz: {full_start.tz}, 학습 인자 정합화 후: {actual_start.tz}")
    
    if actual_start > full_end or actual_end < full_start:
        print(f"⚠️ [경고] 학습기간이 데이터 범위 밖. 데이터: {full_start} ~ {full_end}, 요청: {actual_start} ~ {actual_end}")
        return
    
    df_train = df.loc[actual_start:actual_end].copy()
    n_total = len(df)
    n_train = len(df_train)
    
    print(f"[v7.6 학습기간 분리]")
    print(f"  전체 데이터: {full_start} ~ {full_end} ({n_total:,} rows)")
    print(f"  학습 사용:   {df_train.index.min()} ~ {df_train.index.max()} ({n_train:,} rows, {100*n_train/n_total:.1f}%)")
    print(f"  OOS 잔여:    {n_total - n_train:,} rows ({100*(n_total-n_train)/n_total:.1f}%)")
    
    df_train = calculate_internal_features(df_train)
    df_train = apply_triple_barrier(df_train).dropna()
    
    features = ['rsi_14', 'ema_dist', 'atr_14', 'fvg_bull', 'fvg_bear', 'oi_delta', 'rvol_20', 'vol_accel', 'delta_streak']
    X, y = df_train[features], df_train['target']
    
    print(f"  Feature engineering 후: {len(df_train):,} rows")
    print(f"  Target (long 성공) 분포: {y.value_counts().to_dict()}")
    
    model = xgb.XGBClassifier(n_estimators=150, max_depth=6, learning_rate=0.03, colsample_bytree=0.8, random_state=42)
    model.fit(X, y)
    model.save_model(MODEL_PATH)
    
    # [v7.6 신규] 학습 메타정보 별도 JSON 기록 (재현성 + OOS 검증 보호)
    import json
    meta = {
        'train_start': str(df_train.index.min()),
        'train_end': str(df_train.index.max()),
        'train_rows': int(n_train),
        'features': features,
        'n_estimators': 150, 'max_depth': 6, 'learning_rate': 0.03,
        'created_at': pd.Timestamp.now().isoformat()
    }
    meta_path = MODEL_PATH.replace('.json', '_meta.json')
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=2)
    
    print(f"✅ AI Model Training Complete.")
    print(f"   모델 저장: {MODEL_PATH}")
    print(f"   메타 저장: {meta_path}")

if __name__ == "__main__":
    import sys
    # 명령행 인자: python ML_Predictor_Pipeline_PautoV75.py [train_start] [train_end]
    # 권장 형식 1: python ML_Predictor_Pipeline_PautoV75.py 2023-05-01 2026-04-30
    # 권장 형식 2 (공백 포함 시 따옴표): python ML_Predictor_Pipeline_PautoV75.py "2023-05-01 00:00:00" "2026-04-30 23:59:00"
    
    # [v7.6 정정] 공백 인자 자동 조립 (사용자가 따옴표 빼먹어도 동작)
    args = sys.argv[1:]
    train_start = None
    train_end = None
    
    if len(args) == 2:
        train_start, train_end = args
    elif len(args) == 4:
        # 사용자가 공백 포함 datetime을 따옴표 없이 입력한 경우
        # 예: ... 2023-05-01 00:00:00+00:00 2026-04-30 23:59:00+00:00
        train_start = f"{args[0]} {args[1]}"
        train_end = f"{args[2]} {args[3]}"
        print(f"[자동 조립] 공백 인자 감지 — 학습 시작: '{train_start}', 학습 종료: '{train_end}'")
    elif len(args) == 0:
        print("⚠️ [경고] 학습 기간 인자 없음 — 전체 데이터로 학습 (점프 ⓟ-9 IS 결과)")
        print("   권장: python ML_Predictor_Pipeline_PautoV75.py 2023-05-01 2026-04-30")
    else:
        print(f"⚠️ [경고] 인자 개수 비정상 ({len(args)}개). 사용법:")
        print("   python ML_Predictor_Pipeline_PautoV75.py <train_start> <train_end>")
        print("   예: python ML_Predictor_Pipeline_PautoV75.py 2023-05-01 2026-04-30")
        print('   공백 포함 시: python ML_Predictor_Pipeline_PautoV75.py "2023-05-01 00:00:00" "2026-04-30 23:59:00"')
        sys.exit(1)
    
    train_xgboost_model(train_start, train_end)