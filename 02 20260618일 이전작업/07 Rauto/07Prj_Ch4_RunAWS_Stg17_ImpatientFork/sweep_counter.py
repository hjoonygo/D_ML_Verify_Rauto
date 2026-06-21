# -*- coding: utf-8 -*-
# [sweep_counter.py] 성급왕 역회귀(OPVnN n) 사이징 스윕 — full-sample + CPCV 표준6. (1회용)
#   n만 바꿔 재계산(거래·진입청산 불변, 역회귀 거래 노출만 변동). 과최적합 방지 위해 CPCV p25/최악 병기.
import os, sys
from itertools import combinations
import numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "bots"))
import trendstack_signal_engine as E, trendstack_poc as P, trendstack_regime as RG
DATA = r"D:\ML\Verify\Merged_Data.csv"
df = pd.read_csv(DATA, usecols=lambda c: c in ("timestamp", "open", "high", "low", "close", "volume", "oi_zscore_24h"))
df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert(None); df = df.set_index("timestamp")
ohlc = df[["open", "high", "low", "close"]]; df7 = E.resample_tf(ohlc, E.TF_MIN)
vol7 = df["volume"].resample(f"{E.TF_MIN}min", label="left", closed="left").sum().reindex(df7.index).fillna(0.0)
oi7 = df["oi_zscore_24h"].resample(f"{E.TF_MIN}min", label="left", closed="left").last().reindex(df7.index).values
sig = E.compute_signals(df7); Trend = sig["Trend"]; phc = sig["ph_conf"]; plc = sig["pl_conf"]; er = sig["er"]
H = df7["high"].values; L = df7["low"].values; Cl = df7["close"].values; idx = df7.index; mid = (H + L) / 2.0
atr7 = E.compute_atr(H, L, Cl, E.ATR_PERIOD); poc7 = P.compute_poc(H, L, mid, vol7.values, 60, 50)
df4 = E.resample_tf(ohlc, 240)
try:
    _, fs = RG.feat_struct_of(df4, 8); fs.index = df4.index
except Exception:
    fs = pd.Series("range", index=df4.index)
eh = ((idx - pd.Timestamp("1970-01-01")) / pd.Timedelta(hours=1)).values.astype("float64")
COST = E.COST; SLP = E.SL_PCT; F8 = E.FUND_8H; DZ_LO, DZ_HI = E.DZ_LO, E.DZ_HI; GER = 0.45; fib = E.FIB
SLIP = 0.0005; BASE = 7.0864; LEV = 22.0; SH = 0.0; K = 1.0


def nf(a, b): return int(np.floor(eh[b] / 8.0) - np.floor(eh[a] / 8.0))


# 역회귀 판정: |dev|>=0.25 & side==-rdir (rdir=-sign(dev))
def replay():
    pos = 0; ep = np.nan; ei = -1; sl = np.nan; pb = 0; lastPH = np.nan; lastPL = np.nan; out = []
    for i in range(len(df7)):
        if i < (E.LEFT + E.RIGHT + 1): continue
        nph = i in phc; npl = i in plc
        if nph: lastPH = phc[i][1]
        if npl: lastPL = plc[i][1]
        if pos != 0:
            flip = (pos == 1 and Trend[i] == -1) or (pos == -1 and Trend[i] == 1)
            slbr = (i > ei and not np.isnan(sl)) and ((pos == 1 and L[i] <= sl) or (pos == -1 and H[i] >= sl))
            ex = ("sl", sl * (1 - pos * SLIP)) if slbr else (("flip", Cl[i]) if flip else None)
            if ex:
                R = pos * (ex[1] - ep) / ep - COST - F8 * nf(ei, i)
                dev, rdir = P.dev_rdir(ep, poc7[ei], atr7[ei]) if (atr7[ei] > 0 and not np.isnan(poc7[ei])) else (np.nan, 0)
                feat = str(fs.asof(idx[ei])); cut = SH if (feat == "uptrend" and pos == -1) else 1.0
                counter = (dev is not None and not np.isnan(dev) and abs(dev) >= 0.25 and pos == -rdir)
                out.append(dict(R=R, fund=F8 * nf(ei, i), base=BASE * cut * K, counter=bool(counter)))
                pos = 0; sl = np.nan; pb = 0; continue
            if pos == 1 and npl and not np.isnan(lastPH):
                pb += 1; r = fib[0] if pb == 1 else fib[1] if pb == 2 else fib[2]
                cand = lastPH - r * (lastPH - plc[i][1]); sl = cand if np.isnan(sl) else max(sl, cand)
            if pos == -1 and nph and not np.isnan(lastPL):
                pb += 1; r = fib[0] if pb == 1 else fib[1] if pb == 2 else fib[2]
                cand = lastPL + r * (phc[i][1] - lastPL); sl = cand if np.isnan(sl) else min(sl, cand)
        if pos == 0:
            le = Trend[i] == 1 and not np.isnan(lastPH) and not np.isnan(lastPL)
            se = Trend[i] == -1 and not np.isnan(lastPH) and not np.isnan(lastPL)
            z = oi7[i]
            if not np.isnan(z) and (DZ_LO <= z < DZ_HI) and (er[i] >= GER): le = False; se = False
            if le or se:
                d = 1 if le else -1; ep = Cl[i]; pos = d; ei = i; pb = 0; sl = ep * (1 - d * SLP / 100)
    return out


def cpcv(r, ng=6):
    r = np.asarray(r, float); g = np.array_split(np.arange(len(r)), ng); rr = []
    for lv in combinations(range(ng), 2):
        ix = np.concatenate([x for j, x in enumerate(g) if j not in lv]); rr.append(np.prod(1 + r[ix]) - 1)
    rr = np.array(rr); return np.percentile(rr, 25), rr.min()


def metr(recs, n_counter, C):
    r = np.array([(t["R"] + 0.0004 - C) * (t["base"] * (n_counter if t["counter"] else 1.0) / 100.0 * LEV) for t in recs])
    eq = 10000 * np.cumprod(1 + r); pk = np.maximum.accumulate(eq); mdd = (eq / pk - 1).min() * 100
    full = (eq[-1] / 1e4 - 1) * 100; p25, mn = cpcv(r)
    return full, mdd, p25 * 100, mn * 100


trd = replay()
nc = sum(1 for t in trd if t["counter"])
print(f"총 {len(trd)}거래 | 역회귀 {nc}건 / 비역회귀 {len(trd)-nc}건")
for C in (0.0004, 0.0008):
    print(f"\n[비용 {C*1e4:.0f}bp] 역회귀n  전표본%   MDD%   CPCV_p25%   최악경로%   판정")
    for n in (0.0, 0.2, 0.3, 0.4, 0.6, 0.8, 1.0):
        full, mdd, p25, mn = metr(trd, n, C)
        tag = " <현재" if abs(n - 0.6) < 1e-9 else (" <컷" if n == 0 else "")
        ok = "PASS" if (p25 > 0 and mn > 0) else "FAIL"
        print(f"          {n:<4.1f}  {full:>8.0f} {mdd:>6.1f} {p25:>10.0f} {mn:>10.0f}  {ok}{tag}")
