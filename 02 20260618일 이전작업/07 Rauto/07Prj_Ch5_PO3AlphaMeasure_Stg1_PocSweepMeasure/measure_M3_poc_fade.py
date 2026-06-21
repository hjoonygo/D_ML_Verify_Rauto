# -*- coding: utf-8 -*-
# [파일명] measure_M3_poc_fade.py
# 코드길이: 약 170줄 | 내부버전: M3_poc_fade_v1
# [목적] H1 정직화 — POC 평균회귀를 '실제 거래'로 시뮬해 왕복비용(0.14%) 차감 후에도 돈이 되는지 측정.
#        (봇 아님·엔진 무수정. measure_M1 회귀'확률'을 거래'수익'으로 정직화.)
# [거래룰] 진입: dist 0.5~2 ATR 이탈봉, open[i+1]. above→숏(POC로 하락) / below→롱(POC로 상승).
#          청산: TP=POC±0.1ATR 도달 / SL=진입가±sl_mult·ATR / 시간컷=H봉 후 close.
#          동봉 TP·SL 동시터치는 SL 우선(보수). 비용=왕복 2×0.07%=0.14%(슬립 포함).
# [lookahead 차단] POC=close[i-1440:i] 과거만. 진입=open[i+1]. 미래슬라이스는 청산판정 윈도우뿐. shift(-) 미사용.
import os, sys, time
import numpy as np
import pandas as pd
import po3_common as pc

WINDOW = 1440
BIN_PCT = 0.0005
EPS_ATR = 0.1
DIST_LO, DIST_HI = 0.5, 2.0        # 진입 버킷(기계적 <=0.5 / 추세 >=2 제외)
SL_MULTS = [1.0, 1.5]
HS = [30, 60, 120]
SAMPLE = 5
COST_RT = 2 * pc.COST_ONEWAY       # 왕복 0.0014


def poc_of(prices, vols, mid):
    binw = mid * BIN_PCT
    lo, hi = prices.min(), prices.max()
    if hi <= lo or binw <= 0:
        return prices[-1]
    nb = min(max(int((hi - lo) / binw) + 1, 1), 4000)
    edges = np.linspace(lo, hi, nb + 1)
    idx = np.clip(np.searchsorted(edges, prices, side="right") - 1, 0, nb - 1)
    vsum = np.bincount(idx, weights=vols, minlength=nb)
    k = int(vsum.argmax())
    return (edges[k] + edges[k + 1]) / 2.0


def run(df, sample=SAMPLE):
    o = df["open"].to_numpy(float); h = df["high"].to_numpy(float)
    l = df["low"].to_numpy(float); c = df["close"].to_numpy(float)
    v = df["volume"].to_numpy(float)
    atr = pc.atr_1m(df, 14)
    yr = df["year"].to_numpy()
    smc8 = df["label_smc_8"].to_numpy(object); fs8 = df["feat_struct_8"].to_numpy(object)
    ts = df["timestamp"]
    N = len(df); Hmax = max(HS); end = N - Hmax - 1
    BIG = 10**9
    recs = []
    for i in range(WINDOW, end, sample):
        ai = atr[i]
        if not np.isfinite(ai) or ai <= 0:
            continue
        poc = poc_of(c[i - WINDOW:i], v[i - WINDOW:i], c[i])
        dist = (c[i] - poc) / ai
        if not np.isfinite(dist):
            continue
        ad = abs(dist)
        if not (DIST_LO <= ad < DIST_HI):
            continue
        short = dist > 0
        P0 = o[i + 1]
        if not np.isfinite(P0) or P0 <= 0:
            continue
        bkt = "0.5-1" if ad < 1.0 else "1-2"
        fh = h[i + 1:i + 1 + Hmax]; fl = l[i + 1:i + 1 + Hmax]
        atr_pct = ai / c[i]
        for sl in SL_MULTS:
            if short:
                tp_px = poc + EPS_ATR * ai
                sl_px = P0 + sl * ai
            else:
                tp_px = poc - EPS_ATR * ai
                sl_px = P0 - sl * ai
            for H in HS:
                fhH = fh[:H]; flH = fl[:H]
                if short:
                    tph = np.where(flH <= tp_px)[0]
                    slh = np.where(fhH >= sl_px)[0]
                else:
                    tph = np.where(fhH >= tp_px)[0]
                    slh = np.where(flH <= sl_px)[0]
                tdt = tph[0] if len(tph) else BIG
                sdt = slh[0] if len(slh) else BIG
                if tdt == BIG and sdt == BIG:
                    exit_px = c[i + H]; outc = "timecut"
                elif sdt <= tdt:                 # 동봉 동시터치 → SL 우선(보수)
                    exit_px = sl_px; outc = "sl"
                else:
                    exit_px = tp_px; outc = "tp"
                gross = (P0 - exit_px) / P0 if short else (exit_px - P0) / P0
                net = gross - COST_RT
                recs.append((ts.iat[i], smc8[i], fs8[i], "short" if short else "long",
                             bkt, sl, H, outc, round(net, 6), round(gross, 6),
                             round(atr_pct, 6), int(yr[i])))
    cols = ["ts", "regime", "regime_feat", "dir", "dist_bucket", "sl_mult", "H",
            "outcome", "ret_net", "ret_gross", "atr_pct", "year"]
    return pd.DataFrame.from_records(recs, columns=cols)


def pf(x):
    g = x[x > 0].sum(); b = -x[x < 0].sum()
    return round(g / b, 3) if b > 0 else np.inf


def main():
    t0 = time.time()
    nrows = 60000 if "--quick" in sys.argv else None
    if nrows:
        print("[QUICK] 앞 60,000행")
    df = pc.load_1m(nrows=nrows)
    print(f"[M3] 데이터 {len(df):,}행 | {df['timestamp'].min()} ~ {df['timestamp'].max()}")
    out = run(df)
    od = pc.ensure_out()
    fp = os.path.join(od, "measure_M3_poc_fade.csv")
    out.to_csv(fp, index=False, encoding="utf-8-sig")
    print(f"[M3] 거래행 {len(out):,} | 저장 {fp} | {time.time()-t0:.1f}s")
    if not len(out):
        return
    print(f"\n[1m ATR 크기] 평균 atr_pct = {out['atr_pct'].mean()*100:.4f}% (왕복비용 0.14%와 비교)")
    g = out.groupby(["dist_bucket", "sl_mult", "H"])
    summ = g.agg(n=("ret_net", "size"),
                 win=("ret_net", lambda x: round((x > 0).mean(), 3)),
                 net_mean_bp=("ret_net", lambda x: round(x.mean() * 1e4, 2)),
                 gross_mean_bp=("ret_gross", lambda x: round(x.mean() * 1e4, 2)),
                 net_pf=("ret_net", pf)).reset_index()
    print("\n[정직화 핵심표 — 버킷×sl_mult×H | net=비용후, 단위 bp(0.01%)]")
    print(summ.to_string(index=False))
    print("\n[outcome 비율]")
    print((out["outcome"].value_counts(normalize=True).round(3)).to_string())
    print(f"\n[전체 비용후] net 평균 {out['ret_net'].mean()*1e4:.2f}bp | 승률 {(out['ret_net']>0).mean():.3f} | PF {pf(out['ret_net'])}")


if __name__ == "__main__":
    main()
