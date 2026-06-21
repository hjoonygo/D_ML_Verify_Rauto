# ==============================================================================
# 파일명: Predict_ML_PautoV75.py
# 역할: Pauto V7.5 오프라인 백테스터 전용 기관급 딥-패턴 타점 포착 모듈
# 
# [변수 파이프라인 (Data I/O Pipeline)]
# 📥 [IN] 
#   - df (DataFrame): Backtest_Engine_PautoV75에서 수신한 누적 1분봉 데이터 (윈도우)
#   - current_regime (str): Regime_Master_PautoV75가 판독한 현재 장세 상태
#   - params (dict): 엔진 마스터 설정값
# 
# 🛠️ [CREATE] 
#   - closed_df: 미래 참조 방지를 위한 직전 확정 캔들
#   - 9대 딥-피처: RSI, EMA이격, ATR, FVG, OI델타, RVOL, 거래량가속도, 매수매도연속성
#   - pred_prob: 딥-패턴 AI 모델이 예측한 손익비 높은 진짜 롱 타점 확률
# 
# 📤 [OUT] 
#   - signal (dict): 엔진으로 반환하는 타점 지침 (액션 및 사유)
# ==============================================================================

import os
import pandas as pd
import numpy as np
import xgboost as xgb

class Predict_ML_PautoV75:
    """
    [Pauto V7.5 기관급 딥-패턴 타점 예측 모듈]
    학습 파이프라인과 100% 동일한 규격으로 오더플로우(자금 흐름) 및 볼륨 가속도 피처를 생성하여
    '가짜 돌파'를 걸러내고 폭발적인 '진짜 돌파' 타점만 저격합니다.
    """
    def __init__(self):
        # [수정 완료]: 하드코딩된 경로 제거 및 현재 실행 파일 위치 동적 감지
        self.work_dir = os.path.dirname(os.path.abspath(__file__))
        self.model_path = os.path.join(self.work_dir, "PautoV75_XGB_1to3_Predictor.json")
        self.model = None
        self.model_loaded = False
        
        # 모델 메모리 로드 (최초 1회)
        if os.path.exists(self.model_path):
            try:
                self.model = xgb.Booster()
                self.model.load_model(self.model_path)
                self.model_loaded = True
            except Exception as e:
                print(f"[경고] AI 모델 로딩 실패: {e}")

    def get_signal(self, df: pd.DataFrame, current_regime: str, params: dict) -> dict:
        # 데이터가 충분하지 않거나 모델이 없으면 관망
        if len(df) < 50 or not self.model_loaded:
            return {'action': 'WAIT', 'reason': '데이터 워밍업 또는 모델 부재'}

        # 1. 미래 참조 방어 (실시간으로 변하는 현재 캔들은 버리고 마감된 캔들만 사용)
        closed_df = df.iloc[:-1].copy()

        # -------------------------------------------------------------
        # 2. 딥-피처 실시간 엔지니어링 (학습 모듈과 100% 동기화)
        # -------------------------------------------------------------
        
        # [기본 모멘텀 및 SMC]
        delta_px = closed_df['close'].diff()
        gain = (delta_px.where(delta_px > 0, 0)).rolling(window=14).mean()
        loss = (-delta_px.where(delta_px < 0, 0)).rolling(window=14).mean()
        rsi_14 = 100 - (100 / (1 + gain / loss))

        ema_20 = closed_df['close'].ewm(span=20, adjust=False).mean()
        ema_50 = closed_df['close'].ewm(span=50, adjust=False).mean()
        ema_dist = (ema_20 - ema_50) / ema_50 * 100

        high_low = closed_df['high'] - closed_df['low']
        high_close = np.abs(closed_df['high'] - closed_df['close'].shift())
        low_close = np.abs(closed_df['low'] - closed_df['close'].shift())
        true_range = np.max(pd.concat([high_low, high_close, low_close], axis=1), axis=1)
        atr_14 = true_range.rolling(14).mean()

        fvg_bull = (closed_df['low'] > closed_df['high'].shift(2)).astype(int)
        fvg_bear = (closed_df['high'] < closed_df['low'].shift(2)).astype(int)

        # [오더플로우 및 자금 흐름]
        # [v7.6 정정] OI 컬럼 자동 인식 (학습 모듈과 동일 우선순위)
        if 'open_interest' in closed_df.columns:
            oi_col = 'open_interest'
        elif 'oi_sum' in closed_df.columns:
            oi_col = 'oi_sum'
        elif 'oi_value' in closed_df.columns:
            oi_col = 'oi_value'
        else:
            oi_col = None
        
        if oi_col:
            oi_delta = closed_df[oi_col].pct_change(periods=3).fillna(0) * 100
        else:
            oi_delta = pd.Series(0.0, index=closed_df.index)

        rvol_20 = closed_df['volume'] / (closed_df['volume'].rolling(window=20).mean() + 1e-8)
        vol_accel = closed_df['volume'].pct_change().fillna(0).replace([np.inf, -np.inf], 0)

        buy_pressure = (closed_df['close'] - closed_df['low']) / (closed_df['high'] - closed_df['low'] + 1e-8)
        order_delta = closed_df['volume'] * (buy_pressure * 2 - 1)
        delta_sign = np.sign(order_delta)
        delta_streak = delta_sign.groupby((delta_sign != delta_sign.shift()).cumsum()).cumsum()

        # 직전 마감 캔들의 특성값 추출 (결측치 발생 방지)
        try:
            features_dict = {
                'rsi_14': float(rsi_14.iloc[-1]),
                'ema_dist': float(ema_dist.iloc[-1]),
                'atr_14': float(atr_14.iloc[-1]),
                'fvg_bull': int(fvg_bull.iloc[-1]),
                'fvg_bear': int(fvg_bear.iloc[-1]),
                'oi_delta': float(oi_delta.iloc[-1]),
                'rvol_20': float(rvol_20.iloc[-1]),
                'vol_accel': float(vol_accel.iloc[-1]),
                'delta_streak': float(delta_streak.iloc[-1])
            }
        except:
            return {'action': 'WAIT', 'reason': '피처 연산 대기 (초기 캔들)'}
        
        if pd.isna(list(features_dict.values())).any():
            return {'action': 'WAIT', 'reason': '결측치 발생'}

        # -------------------------------------------------------------
        # 3. XGBoost 확률 인퍼런스 (추론)
        # -------------------------------------------------------------
        feature_names = ['rsi_14', 'ema_dist', 'atr_14', 'fvg_bull', 'fvg_bear', 
                         'oi_delta', 'rvol_20', 'vol_accel', 'delta_streak']
        feature_values = [features_dict[f] for f in feature_names]
        
        X_infer = xgb.DMatrix(np.array([feature_values]), feature_names=feature_names)
        pred_prob = float(self.model.predict(X_infer)[0])

        # 임계값 세팅
        long_threshold = params.get('ml_long_threshold', 0.70)
        short_threshold = params.get('ml_short_threshold', 0.30)

        # -------------------------------------------------------------
        # 4. 장세와 AI의 융합 딥-타격
        # -------------------------------------------------------------
        reason_txt = f"AI {pred_prob*100:.1f}% | OI델타 {features_dict['oi_delta']:.2f}% | 가속도 {features_dict['vol_accel']:.1f} | 델타연속 {features_dict['delta_streak']:.0f}"
        
        if pred_prob >= long_threshold and current_regime in ["BULLISH_EXPANSION", "CHOPPY"]:
            return {'action': 'OPEN_LONG', 'reason': f"LONG: {reason_txt} | 장세: {current_regime}"}
            
        elif pred_prob <= short_threshold and current_regime in ["BEARISH_EXPANSION", "CHOPPY"]:
            return {'action': 'OPEN_SHORT', 'reason': f"SHORT: {reason_txt} | 장세: {current_regime}"}
            
        else:
            return {'action': 'WAIT', 'reason': f"관망: AI 미달 또는 역추세 ({pred_prob*100:.1f}%)"}