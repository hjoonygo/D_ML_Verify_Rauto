# [파일명] mock_candles.py
# 코드길이: 약 80줄 / 내부버전: mock_candles_v1 / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] 신호봇 검증용 합성 데이터(실데이터 없이 로직 검증). 7h OHLC를 추세 상승→하락→횡보 +
#        진동(피벗 생성)으로 만들어 롱/숏 진입·trend_flip·SL이 모두 나오게 한다. oi_zscore 배열은
#        일부 [0,1) 무덤구간에 들어가 게이트를 작동시킨다. 1m 미니스트림은 7h 리샘플 검증용.
# [In] n(봉수)  [Out] (df7h, oi_arr) / (m1_bars, expected_7h)
# ── 함수 ── make_7h_series(n) / make_1m_stream()
# ─────────────────────────────────────────────────────────────────────────
import numpy as np
import pandas as pd


def make_7h_series(n=84, seed=0):
    rng = np.random.RandomState(seed)
    i = np.arange(n)
    # 추세: 상승(0~28) → 하락(28~56) → 횡보(56~)
    trend = np.zeros(n)
    trend[:28] = 0.85 * i[:28]
    trend[28:56] = trend[27] - 0.85 * (i[28:56] - 27)
    trend[56:] = trend[55] + 0.0 * (i[56:] - 55)
    osc = 3.0 * np.sin(i / 2.6)                      # 진동 → 피벗 생성
    noise = rng.randn(n) * 0.35
    close = 100.0 + trend + osc + noise
    open_ = np.empty(n); open_[0] = close[0]; open_[1:] = close[:-1]
    wick = 0.9 + np.abs(rng.randn(n)) * 0.7
    high = np.maximum(open_, close) + wick
    low = np.minimum(open_, close) - wick
    idx = pd.date_range('2024-01-01', periods=n, freq='420min')
    df = pd.DataFrame({'open': open_, 'high': high, 'low': low, 'close': close}, index=idx)
    # oi_zscore: 일부 [0,1) 무덤
    oi = 0.5 + 1.2 * np.sin(i / 4.0) + rng.randn(n) * 0.15
    return df, oi


def make_1m_stream():
    # 2개 7h 버킷(420분)에 걸친 1m 봉 + 기대 7h OHLC
    base = pd.Timestamp('2024-03-01 00:00:00')
    bars = []
    # 버킷1: 0~419분
    p = [101, 103, 99, 102]   # 임의 가격 흐름
    for m in range(420):
        ts = base + pd.Timedelta(minutes=m)
        # 단순: open=first, 중간 고저, close=last 가 명확하도록 구성
        c = 100 + np.sin(m / 30.0) * 2
        o = c; h = c + 0.5; l = c - 0.5
        bars.append((ts, o, h, l, c))
    # 버킷2: 420~839분
    for m in range(420, 840):
        ts = base + pd.Timedelta(minutes=m)
        c = 105 + np.cos(m / 25.0) * 1.5
        o = c; h = c + 0.4; l = c - 0.4
        bars.append((ts, o, h, l, c))
    # 기대 7h OHLC(버킷1): open=첫봉 open, high=max, low=min, close=마지막봉 close
    b1 = [b for b in bars if b[0] < base + pd.Timedelta(minutes=420)]
    exp1 = {'open': b1[0][1], 'high': max(b[2] for b in b1),
            'low': min(b[3] for b in b1), 'close': b1[-1][4]}
    return bars, exp1
