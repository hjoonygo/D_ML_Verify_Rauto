# [파일명] Predict_ML_v2.py
# 코드길이: 약 200줄, 내부버전명: v2.0 (v3.4_fib), 로직 축약/생략 없이 전체 출력
#
# [목적] PautoV75 3-class 추론기 v2 — 결정 사항 반영
#
# [변경 사항 vs v7.5 원본]
#  - binary 추론 → 3-class 추론 (stay/long/short)
#  - 임계 prob_long ≥ 0.35 → LONG / prob_short ≥ 0.35 → SHORT
#  - 양방향 진입 활성화 (Regime 필터는 그대로)
#  - 학습 모델 파일명: PautoV75_XGB_3class_v2.json (Pipeline_v2와 정합)
#
# [Regime 필터 룰 (원본 유지)]
#  - LONG: prob_long ≥ 0.35 AND regime ∈ {BULLISH_EXPANSION, CHOPPY}
#  - SHORT: prob_short ≥ 0.35 AND regime ∈ {BEARISH_EXPANSION, CHOPPY}
#  - 둘 다 미달 OR 역추세 → WAIT
#
# [변수 파이프라인]
# 📥 IN:
#   - df (DataFrame): 누적 1m봉 윈도우 (OHLCV + oi_*)
#   - current_regime (str): Regime_Master_v2 출력
#   - params (dict): {'ml_long_threshold': 0.35, 'ml_short_threshold': 0.35}
# 🛠️ STATE:
#   - 마감된 캔들만 사용 (closed_df = df[:-1])
#   - 9 feature 실시간 엔지니어링 (학습기와 100% 동일 공식)
# 📤 OUT:
#   - signal (dict): {'action': 'OPEN_LONG'/'OPEN_SHORT'/'WAIT', 'reason': str,
#                     'prob_long': float, 'prob_short': float, 'prob_stay': float}
#
# [함수 목록]
#   Predict_ML_v2.__init__() -> None
#     IN: 없음
#     OUT: model 로드 (PautoV75_XGB_3class_v2.json)
#
#   Predict_ML_v2.get_signal(df, current_regime, params) -> dict
#     IN: df, regime, params
#     OUT: signal dict

import os
import pandas as pd
import numpy as np
import xgboost as xgb


class Predict_ML_v2:
    """
    Pauto V7.5 3-class 추론 모듈 v2.
    학습 파이프라인 ML_Predictor_Pipeline_v2와 100% 동일한 9 feature 사용.
    임계 0.35 적용 (양방향).
    """

    def __init__(self):
        self.work_dir = os.path.dirname(os.path.abspath(__file__))
        self.model_path = os.path.join(self.work_dir, "PautoV75_XGB_3class_v2.json")
        self.model = None
        self.model_loaded = False

        if os.path.exists(self.model_path):
            try:
                self.model = xgb.XGBClassifier()
                self.model.load_model(self.model_path)
                self.model_loaded = True
                print(f"[Predict_ML_v2] 3-class 모델 로드 완료: {self.model_path}")
            except Exception as e:
                print(f"[경고] AI 모델 로딩 실패: {e}")
        else:
            print(f"[경고] 모델 파일 없음: {self.model_path}")

    def get_signal(self, df: pd.DataFrame, current_regime: str, params: dict) -> dict:
        """
        진입 신호 추출.

        IN:
          df: 누적 1m봉 윈도우 (최소 50봉)
          current_regime: BULLISH_EXPANSION / BEARISH_EXPANSION / CHOPPY
          params: {'ml_long_threshold': 0.35, 'ml_short_threshold': 0.35}

        OUT:
          {'action': 'OPEN_LONG' or 'OPEN_SHORT' or 'WAIT',
           'reason': str,
           'prob_long': float, 'prob_short': float, 'prob_stay': float}
        """
        if len(df) < 50 or not self.model_loaded:
            return {
                'action': 'WAIT', 'reason': '데이터 워밍업 또는 모델 부재',
                'prob_long': 0.0, 'prob_short': 0.0, 'prob_stay': 1.0,
            }

        # 1. 미래 참조 방어
        closed_df = df.iloc[:-1].copy()

        # 2. 9 feature 엔지니어링 (ML_Predictor_Pipeline_v2와 100% 동일)
        delta_px = closed_df['close'].diff()
        gain = (delta_px.where(delta_px > 0, 0)).rolling(window=14).mean()
        loss = (-delta_px.where(delta_px < 0, 0)).rolling(window=14).mean()
        rsi_14 = 100 - (100 / (1 + gain / loss))

        ema_20 = closed_df['close'].ewm(span=20, adjust=False).mean()
        ema_50 = closed_df['close'].ewm(span=50, adjust=False).mean()
        ema_dist = (ema_20 - ema_50) / ema_50 * 100

        # ATR 3항 (ⓟ-12)
        high_low = closed_df['high'] - closed_df['low']
        high_close = np.abs(closed_df['high'] - closed_df['close'].shift())
        low_close = np.abs(closed_df['low'] - closed_df['close'].shift())
        true_range = np.max(pd.concat([high_low, high_close, low_close], axis=1), axis=1)
        atr_14 = true_range.rolling(14).mean()

        fvg_bull = (closed_df['low'] > closed_df['high'].shift(2)).astype(int)
        fvg_bear = (closed_df['high'] < closed_df['low'].shift(2)).astype(int)

        # OI 자동 인식
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

        # 직전 마감 봉의 feature 값 추출
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
                'delta_streak': float(delta_streak.iloc[-1]),
            }
        except Exception:
            return {
                'action': 'WAIT', 'reason': '피처 연산 대기 (초기 캔들)',
                'prob_long': 0.0, 'prob_short': 0.0, 'prob_stay': 1.0,
            }

        if pd.isna(list(features_dict.values())).any():
            return {
                'action': 'WAIT', 'reason': '결측치 발생',
                'prob_long': 0.0, 'prob_short': 0.0, 'prob_stay': 1.0,
            }

        # 3. XGBoost 3-class 추론
        feature_names = ['rsi_14', 'ema_dist', 'atr_14', 'fvg_bull', 'fvg_bear',
                         'oi_delta', 'rvol_20', 'vol_accel', 'delta_streak']
        feature_values = np.array([[features_dict[f] for f in feature_names]])

        # predict_proba 반환: shape (1, 3), 컬럼 = [stay, long, short]
        probs = self.model.predict_proba(feature_values)[0]
        prob_stay = float(probs[0])
        prob_long = float(probs[1])
        prob_short = float(probs[2])

        # 4. 임계 + Regime 필터 적용
        long_threshold = params.get('ml_long_threshold', 0.35)
        short_threshold = params.get('ml_short_threshold', 0.35)

        reason_txt = f"prob[stay/long/short]=[{prob_stay:.3f}/{prob_long:.3f}/{prob_short:.3f}] | OI {features_dict['oi_delta']:+.2f}% | 가속도 {features_dict['vol_accel']:+.2f} | 델타연속 {features_dict['delta_streak']:.0f}"

        # LONG 조건: prob_long ≥ 임계 AND regime ∈ {BULLISH, CHOPPY}
        long_signal = (prob_long >= long_threshold) and (current_regime in ["BULLISH_EXPANSION", "CHOPPY"])

        # SHORT 조건: prob_short ≥ 임계 AND regime ∈ {BEARISH, CHOPPY}
        short_signal = (prob_short >= short_threshold) and (current_regime in ["BEARISH_EXPANSION", "CHOPPY"])

        # 둘 다 통과 시 더 큰 prob 선택
        if long_signal and short_signal:
            if prob_long > prob_short:
                return {
                    'action': 'OPEN_LONG',
                    'reason': f"LONG (양방향 우세): {reason_txt} | 장세: {current_regime}",
                    'prob_long': prob_long, 'prob_short': prob_short, 'prob_stay': prob_stay,
                }
            else:
                return {
                    'action': 'OPEN_SHORT',
                    'reason': f"SHORT (양방향 우세): {reason_txt} | 장세: {current_regime}",
                    'prob_long': prob_long, 'prob_short': prob_short, 'prob_stay': prob_stay,
                }
        elif long_signal:
            return {
                'action': 'OPEN_LONG',
                'reason': f"LONG: {reason_txt} | 장세: {current_regime}",
                'prob_long': prob_long, 'prob_short': prob_short, 'prob_stay': prob_stay,
            }
        elif short_signal:
            return {
                'action': 'OPEN_SHORT',
                'reason': f"SHORT: {reason_txt} | 장세: {current_regime}",
                'prob_long': prob_long, 'prob_short': prob_short, 'prob_stay': prob_stay,
            }
        else:
            # 미달 또는 역추세
            reason_detail = []
            if prob_long < long_threshold and prob_short < short_threshold:
                reason_detail.append(f"임계 미달")
            if (prob_long >= long_threshold) and current_regime not in ["BULLISH_EXPANSION", "CHOPPY"]:
                reason_detail.append(f"LONG 역추세 (regime={current_regime})")
            if (prob_short >= short_threshold) and current_regime not in ["BEARISH_EXPANSION", "CHOPPY"]:
                reason_detail.append(f"SHORT 역추세 (regime={current_regime})")
            reason_txt_full = f"WAIT: {', '.join(reason_detail)} | {reason_txt} | 장세: {current_regime}"
            return {
                'action': 'WAIT', 'reason': reason_txt_full,
                'prob_long': prob_long, 'prob_short': prob_short, 'prob_stay': prob_stay,
            }
