# [파일명] trendstack_poc.py
# 코드길이: 약 55줄 / 내부버전: trendstack_poc_v1 (OPVnNSweep 추출) / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] OPVnN 사이징용 POC(거래량 최빈가)·dev 계산. test_07Prj_Ch2_Stg2_TrendStack_OPVnNSweep.py
#        (업로드 원본)에서 compute_poc를 '한 글자도 안 바꾸고' 추출(원본 L56-68).
# [미래참조] compute_poc는 [i-lb:i) 과거만 사용 → 룩어헤드 없음(원본·실측 확인).
# [In] high/low/mid/vol 배열 + lb(60)·bins(50) [Out] poc 배열 / dev·rdir
# ── 함수 ── compute_poc(원본1:1) / dev_rdir(진입가·POC·ATR → dev, 회귀방향)
# ── 상수 ── POC_LB=60, POC_BINS=50 (원본값)
# ─────────────────────────────────────────────────────────────────────────
import numpy as np

POC_LB = 60
POC_BINS = 50


def compute_poc(high, low, mid, vol, lb, bins):
    # 횡보봇 SidewayDCA compute_poc 로직 복제: [i-lb:i) 과거 거래량분포 최빈가(룩어헤드 없음)
    n = len(mid); poc = np.full(n, np.nan)
    for i in range(lb, n):
        s = i - lb; lo = low[s:i].min(); hi = high[s:i].max()
        if hi <= lo: poc[i] = mid[i - 1]; continue
        edges = np.linspace(lo, hi, bins + 1)
        idxb = np.clip(np.digitize(mid[s:i], edges) - 1, 0, bins - 1)
        hist = np.zeros(bins); np.add.at(hist, idxb, vol[s:i])
        k = int(hist.argmax()); poc[i] = (edges[k] + edges[k + 1]) / 2.0
    return poc



def dev_rdir(entry_price, poc_val, atr_val):
    # dev=(진입가-POC)/ATR, 회귀방향 rdir=-sign(dev). 원본 build_dev/main과 동일식.
    if poc_val is None or np.isnan(poc_val) or atr_val is None or atr_val <= 0:
        return np.nan, 0
    dev = (entry_price - poc_val) / atr_val
    return dev, int(-np.sign(dev))
