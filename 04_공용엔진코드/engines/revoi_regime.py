# -*- coding: utf-8 -*-
# [revoi_regime.py] REVoi 레짐 오버레이 헬퍼 — 진입게이트 + 레짐적응 스텝 (세션 260626_02_Rauto2_Sys).
#   ★봇 알파 도메인(§25 신호/진입/청산): trend_gate(추세역행 진입 차단) · regime_step(저변동 봉 fib스텝 타이트).
#   ★전부 진입시점 '과거만'(룩어헤드0). 자기완결(parquet 의존 없음 — 라이브/워밍업서도 동작). 검증엔진 무수정.
import numpy as np
import pandas as pd
import trendstack_signal_engine as TS


def _dfx(d1m, rev_tf):
    return TS.resample_tf(d1m[["open", "high", "low", "close"]], rev_tf)


def trend_gate(side, d1m, rev_tf, lo=-10.0, hi=12.0):
    """추세역행 진입 차단: 지속하락(30일<lo%)서 롱·지속상승(>hi%)서 숏 신호를 0으로(역추세가 강추세와 싸우지않기).
       side = rev_side 출력(rev_tf 봉별). 반환 = 마스킹된 side(같은 길이)."""
    dfx = _dfx(d1m, rev_tf)
    c = dfx["close"]
    bars = max(1, int(round(30 * 1440 / rev_tf)))         # 30일치 rev_tf 봉수
    r30 = ((c / c.shift(bars) - 1.0) * 100.0).fillna(0.0).values
    s = np.array(side, dtype=int).copy()
    n = min(len(s), len(r30))
    block = np.zeros(len(s), dtype=bool)
    block[:n] = ((r30[:n] < lo) & (s[:n] == 1)) | ((r30[:n] > hi) & (s[:n] == -1))
    s[block] = 0
    return s


def regime_step(d1m, rev_tf, factor):
    """저변동(횡보) 봉서 피보 스텝 ×factor(스톱 타이트). factor<=1이면 None(off).
       자기완결: rev_tf 봉 ATR(rolling) <= 과거 롤링 Q20면 불리레짐. 반환 fib_scale 배열(dfx 길이) 또는 None."""
    if factor is None or factor <= 1.0:
        return None
    dfx = _dfx(d1m, rev_tf)
    tr = ((dfx["high"] - dfx["low"]) / dfx["close"])
    atr = tr.rolling(14, min_periods=5).mean()
    q20 = atr.rolling(720, min_periods=120).quantile(0.2)   # 과거 롤링 Q20(룩어헤드0)
    adverse = (atr <= q20).fillna(False).values
    return np.where(adverse, float(factor), 1.0).astype(float)
