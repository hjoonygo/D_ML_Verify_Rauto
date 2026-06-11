# [파일명] Regime_Master_v2.py
# 코드길이: 약 175줄, 내부버전명: v2.0 (v3.4_fib), 로직 축약/생략 없이 전체 출력
#
# [목적] V7.5 Regime_Master + S1 버그 정정 + 2h봉 분기 추가
#
# [변경 사항 vs V7.5 원본]
#  - S1 버그 정정: window 호출 시 100봉 미만이면 항상 CHOPPY 출력 → window 120봉 권장
#  - 2h봉 입력 분기 추가 (get_regime_2h 메서드)
#  - 결정 사항: 2h봉 반전 신호 → tbm_simulator_v6가 호출
#
# [Regime 분류 룰 (V7.5 원본 유지)]
#  - BULLISH_EXPANSION: close > EMA20 > EMA50 > EMA100 (완벽 정배열)
#  - BEARISH_EXPANSION: close < EMA20 < EMA50 < EMA100 (완벽 역배열)
#  - 그 외 = CHOPPY
#
# [변수 파이프라인]
# 📥 IN:
#   - df (DataFrame): 1m봉 또는 2h봉 OHLC (최소 120봉)
# 📤 OUT:
#   - regime (str): "BULLISH_EXPANSION" / "BEARISH_EXPANSION" / "CHOPPY"
#
# [함수 목록]
#   Regime_Master_v2.__init__()
#   Regime_Master_v2.get_regime(df, params) -> str
#     IN: 1m봉 df (최소 120봉)
#     OUT: regime
#   Regime_Master_v2.get_regime_2h(df_2h, params) -> str
#     IN: 2h봉 df (최소 120봉)
#     OUT: regime
#   Regime_Master_v2.detect_reversal(prev_regime, current_regime) -> str/None
#     IN: 이전/현재 regime
#     OUT: 'long_to_short_reversal' / 'short_to_long_reversal' / None

import pandas as pd
import numpy as np


# 클래스 외부 워밍업 상수
MIN_WARMUP_BARS = 120


class Regime_Master_v2:
    """
    V7.5 장세 판독기 v2.
    S1 버그 정정: window 120봉 이상 필요.
    """

    def __init__(self):
        self.min_warmup = MIN_WARMUP_BARS

    def get_regime(self, df: pd.DataFrame, params: dict = None) -> str:
        """
        1m봉 입력으로 현재 장세 판독.

        IN:
          df: 1m봉 OHLC (DataFrame). 최소 120봉 권장
          params: optional, 미사용 (호환성)
        OUT:
          str: "BULLISH_EXPANSION" / "BEARISH_EXPANSION" / "CHOPPY"
        """
        if len(df) < self.min_warmup:
            return "CHOPPY"

        return self._classify(df, span_20=20, span_50=50, span_100=100, atr_window=14, atr_min_pct=0.02)

    def get_regime_2h(self, df_2h: pd.DataFrame, params: dict = None) -> str:
        """
        2h봉 입력으로 상위 TF 장세 판독.
        반전 신호 감지에 사용.

        IN:
          df_2h: 2h봉 OHLC (DataFrame). 최소 120봉 권장 = 240시간 = 10일
        OUT:
          str: regime
        """
        if len(df_2h) < self.min_warmup:
            return "CHOPPY"

        # 2h봉이라 EMA 기간은 더 짧게 적용 (2h * 20 = 40h, 50 = 100h, 100 = 200h)
        # ATR 최소 변동성도 2h봉 기준으로 적절히 (1분봉 0.02% → 2h봉 0.5%)
        return self._classify(df_2h, span_20=20, span_50=50, span_100=100, atr_window=14, atr_min_pct=0.5)

    def _classify(self, df: pd.DataFrame, span_20=20, span_50=50, span_100=100,
                  atr_window=14, atr_min_pct=0.02) -> str:
        """
        공통 분류 로직.

        IN:
          df: OHLC DataFrame
          span_20/50/100: EMA span
          atr_window: ATR rolling window
          atr_min_pct: 변동성 최소 임계 (% of close)
        OUT:
          regime str
        """
        # 1. 미래 참조 방어
        closed_df = df.iloc[:-1].copy()

        close_price = float(closed_df['close'].iloc[-1])

        # 2. EMA 정/역배열
        ema_20 = closed_df['close'].ewm(span=span_20, adjust=False).mean()
        ema_50 = closed_df['close'].ewm(span=span_50, adjust=False).mean()
        ema_100 = closed_df['close'].ewm(span=span_100, adjust=False).mean()

        last_ema20 = float(ema_20.iloc[-1])
        last_ema50 = float(ema_50.iloc[-1])
        last_ema100 = float(ema_100.iloc[-1])

        # 3. ATR 변동성 (3항 ATR)
        high_low = closed_df['high'] - closed_df['low']
        high_close = np.abs(closed_df['high'] - closed_df['close'].shift())
        low_close = np.abs(closed_df['low'] - closed_df['close'].shift())
        true_range = np.max(pd.concat([high_low, high_close, low_close], axis=1), axis=1)
        atr_14 = float(true_range.rolling(atr_window).mean().iloc[-1])

        # 변동성 필터: ATR_pct 너무 작으면 CHOPPY
        if not np.isfinite(atr_14) or atr_14 <= 0:
            return "CHOPPY"

        atr_pct = (atr_14 / close_price) * 100
        if atr_pct < atr_min_pct:
            return "CHOPPY"

        # 4. 정/역배열 판단
        is_bullish = (close_price > last_ema20) and (last_ema20 > last_ema50) and (last_ema50 > last_ema100)
        is_bearish = (close_price < last_ema20) and (last_ema20 < last_ema50) and (last_ema50 < last_ema100)

        if is_bullish:
            return "BULLISH_EXPANSION"
        elif is_bearish:
            return "BEARISH_EXPANSION"
        else:
            return "CHOPPY"

    def detect_reversal(self, prev_regime: str, current_regime: str) -> str:
        """
        2h봉 사이의 reversal 감지.

        IN:
          prev_regime: 직전 2h봉의 regime
          current_regime: 현재 2h봉의 regime
        OUT:
          'long_to_short_reversal': BULLISH → BEARISH or CHOPPY (상승 추세 무너짐)
          'short_to_long_reversal': BEARISH → BULLISH or CHOPPY (하락 추세 무너짐)
          None: 반전 없음 (같은 regime 또는 CHOPPY 연속)
        """
        if prev_regime == "BULLISH_EXPANSION" and current_regime in ["BEARISH_EXPANSION", "CHOPPY"]:
            return 'long_to_short_reversal'
        elif prev_regime == "BEARISH_EXPANSION" and current_regime in ["BULLISH_EXPANSION", "CHOPPY"]:
            return 'short_to_long_reversal'
        else:
            return None
