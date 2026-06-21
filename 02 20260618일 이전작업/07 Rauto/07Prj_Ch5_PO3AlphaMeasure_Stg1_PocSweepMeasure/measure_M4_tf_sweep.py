# -*- coding: utf-8 -*-
# [파일명] measure_M4_tf_sweep.py
# 코드길이: 약 180줄 | 내부버전: M4_tf_sweep_v1
# [목적] H1 정직화 2탄 — POC 페이드를 16개 상위 타임프레임에서 측정. 봉이 커지면 목표이익(0.5~2ATR)이
#        왕복비용 14bp를 넘는지, 그 TF에서 회귀 엣지가 비용후에도 살아남는지(net>0) 탐색.
#        (봇 아님·엔진 무수정. 측정 스크립트.)
# [TF] 5/15/30분 · 1~10시간 · 12/16/24시간 (분 단위로 리샘플).
# [거래룰] M3와 동일: 진입 dist 0.5~2 ATR, open[i+1] / TP=POC±0.1ATR / SL=진입가±{1.0,1.5}ATR /
#          시간컷 H∈{5,10,20} TF봉 / 비용 왕복 0.14%. 동봉 TP·SL 동시 → SL우선(보수).
# [TF별 기준] POC 윈도우=100 TF봉 고정(전 TF 동일 표본) · ATR=TF봉 Wilder14 · 진입=다음 TF봉 시가.
# [lookahead 차단] 리샘플 label=right/closed=right(봉 닫힘 후). POC=과거 TF봉만. 미래슬라이스=청산판정뿐. shift(-) 미사용.
import os, sys, time
import numpy as np
import pandas as pd
import po3_common as pc

TFS_MIN = [5, 15, 30, 60, 120, 180, 240, 300, 360, 420, 480, 540, 600, 720, 960, 1440]
LOOKBACK = 100
BIN_PCT = 0.0005
EPS_ATR = 0.1
DIST_LO, DIST_HI = 0.5, 2.0
SL_MULTS = [1.0, 1.5]
HS = [5, 10, 20]
COST_RT = 2 * pc.COST_ONEWAY


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


def atr_arr(h, l, c, n=14):
    pcv = np.empty_like(c); pcv[0] = c[0]; pcv[1:] = c[:-1]
    tr = np.maximum.reduce([h - l, np.abs(h - pcv), np.abs(l - pcv)])
    return pd.Series(tr).ewm(alpha=1.0 / n, adjust=False).mean().to_numpy()


def run_tf(d, m):
    o = d["open"].to_numpy(float); h = d["high"].to_numpy(float)
    l = d["low"].to_numpy(float); c = d["close"].to_numpy(float)
    v = d["volume"].to_numpy(float)
    atr = atr_arr(h, l, c, 14)
    smc8 = d["label_smc_8"].to_numpy(object); fs8 = d["feat_struct_8"].to_numpy(object)
    yr = d["year"].to_numpy(); ts = d.index
    N = len(d); Hmax = max(HS); end = N - Hmax - 1; BIG = 10**9
    recs = []
    for i in range(LOOKBACK, end):
        ai = atr[i]
        if not np.isfinite(ai) or ai <= 0:
            continue
        poc = poc_of(c[i - LOOKBACK:i], v[i - LOOKBACK:i], c[i])
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
                tp_px = poc + EPS_ATR * ai; sl_px = P0 + sl * ai
            else:
                tp_px = poc - EPS_ATR * ai; sl_px = P0 - sl * ai
            for H in HS:
                fhH = fh[:H]; flH = fl[:H]
                if short:
                    tph = np.where(flH <= tp_px)[0]; slh = np.where(fhH >= sl_px)[0]
                else:
                    tph = np.where(fhH >= tp_px)[0]; slh = np.where(flH <= sl_px)[0]
                tdt = tph[0] if len(tph) else BIG
                sdt = slh[0] if len(slh) else BIG
                if tdt == BIG and sdt == BIG:
                    exit_px = c[i + H]; outc = "timecut"
                elif sdt <= tdt:
                    exit_px = sl_px; outc = "sl"
                else:
                    exit_px = tp_px; outc = "tp"
                gross = (P0 - exit_px) / P0 if short else (exit_px - P0) / P0
                recs.append((m, ts[i], smc8[i], fs8[i], "short" if short else "long",
                             bkt, sl, H, outc, round(gross - COST_RT, 6), round(gross, 6),
                             round(atr_pct, 6), int(yr[i])))
    return recs


def pf(x):
    g = x[x > 0].sum(); b = -x[x < 0].sum()
    return round(g / b, 3) if b > 0 else np.inf


def main():
    t0 = time.time()
    nrows = 200000 if "--quick" in sys.argv else None
    if nrows:
        print("[QUICK] 앞 200,000행")
    base = pc.load_1m(nrows=nrows).set_index("timestamp")
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum",
           "label_smc_8": "last", "feat_struct_8": "last", "year": "last"}
    all_recs = []
    print(f"[M4] 1분봉 {len(base):,}행 → 16 TF 리샘플 측정")
    for m in TFS_MIN:
        d = base.resample(f"{m}min", label="right", closed="right").agg(agg).dropna(subset=["close"])
        recs = run_tf(d, m)
        all_recs.extend(recs)
        print(f"  TF {m:>4}분: 봉 {len(d):>7,} | 거래행 {len(recs):>7,}")
    cols = ["tf_min", "ts", "regime", "regime_feat", "dir", "dist_bucket", "sl_mult", "H",
            "outcome", "ret_net", "ret_gross", "atr_pct", "year"]
    out = pd.DataFrame.from_records(all_recs, columns=cols)
    od = pc.ensure_out()
    fp = os.path.join(od, "measure_M4_tf_sweep.csv")
    out.to_csv(fp, index=False, encoding="utf-8-sig")
    print(f"\n[M4] 총 거래행 {len(out):,} | 저장 {fp} | {time.time()-t0:.1f}s")
    # TF별 정직화 요약
    rows = []
    for m in TFS_MIN:
        s = out[out.tf_min == m]
        if not len(s):
            continue
        bestc = s.groupby(["dist_bucket", "sl_mult", "H"])["ret_net"].mean()
        bk = bestc.idxmax(); bnet = bestc.max()
        bs = s[(s.dist_bucket == bk[0]) & (s.sl_mult == bk[1]) & (s.H == bk[2])]
        rows.append((m, len(s) // (len(SL_MULTS) * len(HS)), round(s.atr_pct.mean() * 100, 4),
                     round(s.ret_net.mean() * 1e4, 2), round(bnet * 1e4, 2),
                     f"{bk[0]}/sl{bk[1]}/H{bk[2]}", round((bs.ret_net > 0).mean(), 3),
                     pf(bs.ret_net.to_numpy())))
    summ = pd.DataFrame(rows, columns=["tf_min", "n_entry", "atr_pct%", "net_all_bp",
                                       "best_net_bp", "best_combo", "best_win", "best_pf"])
    print("\n[정직화 TF 스윕 — net=비용후 bp(0.01%). best=TF별 최우호 조합]")
    print(summ.to_string(index=False))
    winners = summ[summ.best_net_bp > 0]
    print(f"\n[★net>0 TF] {len(winners)}개: " +
          (", ".join(f"{int(r.tf_min)}분({r.best_net_bp}bp)" for _, r in winners.iterrows()) if len(winners) else "없음"))


if __name__ == "__main__":
    main()
