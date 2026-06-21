# [파일명] mock_candles.py
# 코드길이: 약 95줄 / 내부버전: mock_candles_v2 / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] Stg10 검증용 합성 데이터(실데이터 없이 로직검증).
#   make_7h_series : 7h OHLC+거래량 + oi_zscore(일부 [0,1) 무덤) — 신호·POC·게이트 검증
#   make_4h_series : 4H OHLC(상승→하락→횡보) — feat_struct 검증
#   make_1m_stream : 1m 봉(여러 7h·4H 버킷) — 이중 리샘플 검증
# ─────────────────────────────────────────────────────────────────────────
import numpy as np
import pandas as pd


def make_7h_series(n=84, seed=0):
    rng = np.random.RandomState(seed)
    i = np.arange(n)
    trend = np.zeros(n)
    trend[:28] = 0.85 * i[:28]
    trend[28:56] = trend[27] - 0.85 * (i[28:56] - 27)
    trend[56:] = trend[55]
    osc = 3.0 * np.sin(i / 2.6)
    noise = rng.randn(n) * 0.35
    close = 100.0 + trend + osc + noise
    open_ = np.empty(n); open_[0] = close[0]; open_[1:] = close[:-1]
    wick = 0.9 + np.abs(rng.randn(n)) * 0.7
    high = np.maximum(open_, close) + wick
    low = np.minimum(open_, close) - wick
    vol = 500 + np.abs(rng.randn(n)) * 800           # 거래량(POC용)
    idx = pd.date_range('2024-01-01', periods=n, freq='420min')
    df = pd.DataFrame({'open': open_, 'high': high, 'low': low, 'close': close, 'volume': vol}, index=idx)
    oi = 0.5 + 1.2 * np.sin(i / 4.0) + rng.randn(n) * 0.15
    return df, oi


def make_4h_series(n=140, seed=3):
    rng = np.random.RandomState(seed)
    t = np.arange(n)
    seg = n // 3
    c = np.concatenate([100 + t[:seg] * 1.2,
                        100 + seg * 1.2 - (t[seg:2 * seg] - seg) * 1.2,
                        100 + np.sin(t[2 * seg:] / 2.0) * 2.5])
    c = c + rng.randn(n) * 0.4
    o = np.empty(n); o[0] = c[0]; o[1:] = c[:-1]
    df = pd.DataFrame({'open': o, 'high': c + 1.2, 'low': c - 1.2, 'close': c},
                      index=pd.date_range('2024-01-01', periods=n, freq='4h'))
    return df


def make_1m_stream():
    base = pd.Timestamp('2024-03-01 00:00:00')
    bars = []
    for m in range(1000):                              # ≈2.4개 7h 버킷, ≈4개 4H 버킷
        ts = base + pd.Timedelta(minutes=m)
        c = 100 + np.sin(m / 60.0) * 3 + m * 0.002
        o = c; h = c + 0.5; l = c - 0.5; v = 10 + (m % 7)
        bars.append((ts, o, h, l, c, v))
    return bars
