# -*- coding: utf-8 -*-
# [파일명] measure_M1_poc_revert.py
# 코드길이: 약 150줄 | 내부버전: M1_poc_revert_v1
# [가설 H1] POC 자석: close가 POC(거래량 최대 가격대)에서 d(ATR) 멀어지면 H봉 안에 POC로 회귀하는가.
# [정의] POC = 직전 WINDOW봉(24h) 거래량프로파일 최대 빈 중심. dist=(close-POC)/ATR_1m.
#        회귀 = i+1..i+H 안에 POC ±EPS_ATR*ATR 도달(above→하락도달 / below→상승도달).
# [lookahead 차단] POC는 close[i-WINDOW:i] 과거만. 신호=close[i], 측정=i+1부터. shift(-) 미사용.
# [함수 In/Out]
#   poc_of(prices,vols,mid) -> float : 거래량프로파일 POC 가격
#   run(df, sample) -> DataFrame     : 이벤트×H 행 (ts,regime..,dir,dist_bucket,H,reverted,bars,mfe,mae,year)
import os, sys, time
import numpy as np
import pandas as pd
import po3_common as pc

WINDOW = 1440        # 24h 롤링 거래량프로파일(1분봉)
BIN_PCT = 0.0005     # 가격빈 폭 = 가격의 0.05%
EPS_ATR = 0.1        # POC 도달 허용 ±0.1 ATR
HS = [30, 60, 120]   # forward 봉수 비교
SAMPLE = 5           # 5분 샘플(매 5봉 평가) — 1차. 생존 시 전수(SAMPLE=1) 재측정.
BUCKETS = [(0.0, 0.5, "<=0.5"), (0.5, 1.0, "0.5-1"),
           (1.0, 2.0, "1-2"), (2.0, 1e18, ">=2")]


def bucket_of(ad):
    for lo, hi, name in BUCKETS:
        if lo <= ad < hi:
            return name
    return ">=2"


def poc_of(prices, vols, mid):
    binw = mid * BIN_PCT
    lo, hi = prices.min(), prices.max()
    if hi <= lo or binw <= 0:
        return prices[-1]
    nb = int((hi - lo) / binw) + 1
    nb = min(max(nb, 1), 4000)
    edges = np.linspace(lo, hi, nb + 1)
    idx = np.clip(np.searchsorted(edges, prices, side="right") - 1, 0, nb - 1)
    vsum = np.bincount(idx, weights=vols, minlength=nb)
    k = int(vsum.argmax())
    return (edges[k] + edges[k + 1]) / 2.0


def run(df, sample=SAMPLE):
    o = df["open"].to_numpy(float)
    h = df["high"].to_numpy(float)
    l = df["low"].to_numpy(float)
    c = df["close"].to_numpy(float)
    v = df["volume"].to_numpy(float)
    atr = pc.atr_1m(df, 14)
    yr = df["year"].to_numpy()
    smc8 = df["label_smc_8"].to_numpy(object)
    smc5 = df["label_smc_5"].to_numpy(object)
    smc12 = df["label_smc_12"].to_numpy(object)
    fs8 = df["feat_struct_8"].to_numpy(object)
    N = len(df)
    Hmax = max(HS)
    start = WINDOW
    end = N - Hmax - 1
    recs = []
    for i in range(start, end, sample):
        ai = atr[i]
        if not np.isfinite(ai) or ai <= 0:
            continue
        poc = poc_of(c[i - WINDOW:i], v[i - WINDOW:i], c[i])
        dist = (c[i] - poc) / ai
        if not np.isfinite(dist):
            continue
        above = dist > 0
        ad = abs(dist)
        bkt = bucket_of(ad)
        eps = EPS_ATR * ai
        ci = c[i]
        fl_all = l[i + 1:i + 1 + Hmax]
        fh_all = h[i + 1:i + 1 + Hmax]
        for H in HS:
            fl = fl_all[:H]
            fh = fh_all[:H]
            if above:                       # POC 아래 → 하락 도달이 회귀
                hit = fl <= (poc + eps)
                rev = bool(hit.any())
                bars = int(np.argmax(hit) + 1) if rev else -1
                mfe = (ci - fl.min()) / ai   # POC 방향(하락) 최대 유리
                mae = (fh.max() - ci) / ai   # 반대(상승) 최대 불리
            else:                            # POC 위 → 상승 도달이 회귀
                hit = fh >= (poc - eps)
                rev = bool(hit.any())
                bars = int(np.argmax(hit) + 1) if rev else -1
                mfe = (fh.max() - ci) / ai
                mae = (ci - fl.min()) / ai
            recs.append((df["timestamp"].iat[i], smc8[i], fs8[i], smc5[i], smc12[i],
                         "above" if above else "below", bkt, H,
                         int(rev), bars, round(mfe, 4), round(mae, 4), int(yr[i])))
    cols = ["ts", "regime", "regime_feat", "regime_smc5", "regime_smc12",
            "dir", "dist_bucket", "H", "reverted", "bars_to_poc", "mfe_atr", "mae_atr", "year"]
    return pd.DataFrame.from_records(recs, columns=cols)


def main():
    t0 = time.time()
    nrows = None
    sample = SAMPLE
    if "--quick" in sys.argv:
        nrows = 60000      # 사전실행: 앞 ~41일
        print("[QUICK] 앞 60,000행 사전실행")
    df = pc.load_1m(nrows=nrows)
    print(f"[M1] 데이터 {len(df):,}행 | {df['timestamp'].min()} ~ {df['timestamp'].max()}")
    out = run(df, sample)
    od = pc.ensure_out()
    fp = os.path.join(od, "measure_M1_poc_revert.csv")
    out.to_csv(fp, index=False, encoding="utf-8-sig")
    print(f"[M1] 이벤트행 {len(out):,} | 저장 {fp} | {time.time()-t0:.1f}s")
    # 빠른 미리보기(전체 회귀율 by bucket×H)
    if len(out):
        pv = out.groupby(["dist_bucket", "H"])["reverted"].mean().round(3)
        print(pv.to_string())


if __name__ == "__main__":
    main()
