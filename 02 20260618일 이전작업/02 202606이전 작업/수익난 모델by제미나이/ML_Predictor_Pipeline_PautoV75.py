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

    df['oi_delta'] = df['open_interest'].pct_change(periods=3).fillna(0) * 100
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

def train_xgboost_model():
    if not os.path.exists(DATA_PATH): 
        print(f"데이터 파일이 없습니다: {DATA_PATH}")
        return
    df = pd.read_csv(DATA_PATH)
    df = calculate_internal_features(df)
    df = apply_triple_barrier(df).dropna()

    features = ['rsi_14', 'ema_dist', 'atr_14', 'fvg_bull', 'fvg_bear', 'oi_delta', 'rvol_20', 'vol_accel', 'delta_streak']
    X, y = df[features], df['target']

    model = xgb.XGBClassifier(n_estimators=150, max_depth=6, learning_rate=0.03, colsample_bytree=0.8, random_state=42)
    model.fit(X, y)
    model.save_model(MODEL_PATH)
    print(f"AI Model Training Complete. 가중치 저장 완료: {MODEL_PATH}")

if __name__ == "__main__":
    train_xgboost_model()