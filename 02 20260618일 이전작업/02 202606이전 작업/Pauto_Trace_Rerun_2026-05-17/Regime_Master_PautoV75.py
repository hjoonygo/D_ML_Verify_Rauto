# ==============================================================================
# 파일명: Regime_Master_PautoV75.py
# 역할: Pauto V7.5 장세 판독기 (Market Regime Switching)
# 
# [변수 파이프라인 (Data I/O Pipeline)]
# 📥 [IN] 
#   - df (DataFrame): Historical_DataEngine에서 공급되는 실시간 누적 1분봉 윈도우
#   - params (dict): 엔진 마스터 설정값
# 
# 🛠️ [STATE] 
#   - 미래 참조 방어를 위해 마감된 캔들만 사용.
#   - 다중 이동평균선(EMA 20, 50, 100)의 정배열/역배열 구조 분석.
#   - 변동성(ATR)을 측정하여 거래량이 말라버린 극심한 횡보 구간 필터링.
# 
# 📤 [OUT] 
#   - current_regime (str): "BULLISH_EXPANSION", "BEARISH_EXPANSION", "CHOPPY" 중 하나 반환
# ==============================================================================

import pandas as pd
import numpy as np

class Regime_Master_PautoV75:
    def __init__(self):
        pass

    def get_regime(self, df: pd.DataFrame, params: dict) -> str:
        # 데이터 워밍업 체크 (최소 100캔들 필요)
        if len(df) < 100:
            return "CHOPPY"

        # 1. 미래 참조 방어 (실시간 변동 중인 현재 캔들은 버리고 확정 마감된 캔들만 사용)
        closed_df = df.iloc[:-1].copy()
        
        close_price = closed_df['close'].iloc[-1]

        # 2. 다중 이동평균선(EMA) 배열 계산
        ema_20 = closed_df['close'].ewm(span=20, adjust=False).mean()
        ema_50 = closed_df['close'].ewm(span=50, adjust=False).mean()
        ema_100 = closed_df['close'].ewm(span=100, adjust=False).mean()

        last_ema20 = ema_20.iloc[-1]
        last_ema50 = ema_50.iloc[-1]
        last_ema100 = ema_100.iloc[-1]

        # 3. 변동성 (ATR) 계산 - 비정상적인 횡보장 필터링
        high_low = closed_df['high'] - closed_df['low']
        high_close = np.abs(closed_df['high'] - closed_df['close'].shift())
        low_close = np.abs(closed_df['low'] - closed_df['close'].shift())
        
        true_range = np.max(pd.concat([high_low, high_close, low_close], axis=1), axis=1)
        atr_14 = true_range.rolling(14).mean().iloc[-1]

        # 변동성 비율(ATR %) 검사
        # 0.02% 이하의 변동성이면 방향성이 없는 무의미한 휩쏘(횡보) 장세로 규정
        atr_pct = (atr_14 / close_price) * 100
        if atr_pct < 0.02:
            return "CHOPPY"

        # 4. 장세 판독 로직 (배열 및 이격도)
        # 상승장(Bullish): 주가 > 20선 > 50선 > 100선 (완벽한 정배열)
        is_bullish_aligned = (close_price > last_ema20) and (last_ema20 > last_ema50) and (last_ema50 > last_ema100)
        
        # 하락장(Bearish): 주가 < 20선 < 50선 < 100선 (완벽한 역배열)
        is_bearish_aligned = (close_price < last_ema20) and (last_ema20 < last_ema50) and (last_ema50 < last_ema100)

        if is_bullish_aligned:
            return "BULLISH_EXPANSION"
        elif is_bearish_aligned:
            return "BEARISH_EXPANSION"
        else:
            return "CHOPPY"