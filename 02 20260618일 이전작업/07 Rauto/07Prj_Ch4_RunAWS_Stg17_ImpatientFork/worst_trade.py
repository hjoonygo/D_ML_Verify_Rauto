# -*- coding: utf-8 -*-
# [worst_trade.py] '한 번의 급변에서 단일거래 최악 손실' — 설정별. 슬리피지=그 1분봉 실제 excursion(보수). (1회용)
#   계좌타격(보수) = max(SL손익 - 1분excursion, -buffer) 를 노출로 곱한 1거래 계좌% 손실.
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "bots"))
import trendstack_signal_engine as E, trendstack_poc as P, rauto_paper_engine as PE, trendstack_regime as RG
from rauto_contract import Signal, Action, Side
DATA = r"D:\ML\Verify\Merged_Data.csv"
m = pd.read_csv(DATA, usecols=lambda c: c in ("timestamp", "open", "high", "low", "close"))
m["timestamp"] = pd.to_datetime(m["timestamp"], utc=True).dt.tz_convert(None); m = m.set_index("timestamp").sort_index()
d = pd.read_csv(DATA, usecols=lambda c: c in ("timestamp", "open", "high", "low", "close", "volume", "oi_zscore_24h"))
d["timestamp"] = pd.to_datetime(d["timestamp"], utc=True).dt.tz_convert(None); d = d.set_index("timestamp")
df7 = E.resample_tf(m[["open", "high", "low", "close"]], E.TF_MIN)
vol7 = d["volume"].resample(f"{E.TF_MIN}min", label="left", closed="left").sum().reindex(df7.index).fillna(0.0)
oi7 = d["oi_zscore_24h"].resample(f"{E.TF_MIN}min", label="left", closed="left").last().reindex(df7.index).values
sig = E.compute_signals(df7); Trend = sig["Trend"]; phc = sig["ph_conf"]; plc = sig["pl_conf"]; er = sig["er"]
H = df7["high"].values; L = df7["low"].values; Cl = df7["close"].values; idx = df7.index; mid = (H + L) / 2.0
atr7 = E.compute_atr(H, L, Cl, E.ATR_PERIOD); poc7 = P.compute_poc(H, L, mid, vol7.values, 60, 50)
df4 = E.resample_tf(m[["open", "high", "low", "close"]], 240)
try:
    _, fs = RG.feat_struct_of(df4, 8); fs.index = df4.index
except Exception:
    fs = pd.Series("range", index=df4.index)
eh = ((idx - pd.Timestamp("1970-01-01")) / pd.Timedelta(hours=1)).values.astype("float64")
COST = E.COST; SLP = E.SL_PCT; F8 = E.FUND_8H; DZ_LO, DZ_HI = E.DZ_LO, E.DZ_HI; GER = 0.45; fib = E.FIB
SLIP = 0.0005; BASE = 7.0864; SH = 0.0; MMR = 0.004; K = 1.4


def nf(a, b): return int(np.floor(eh[b] / 8.0) - np.floor(eh[a] / 8.0))
def opvnn(dev, rdir, side):
    if dev is None or np.isnan(dev): return 1.0
    if abs(dev) >= 0.25: return 1.0 if side == rdir else 0.6 if side == -rdir else 1.0
    return 1.0


def king():
    pos = 0; ep = np.nan; ei = -1; sl = np.nan; pb = 0; lastPH = np.nan; lastPL = np.nan; out = []
    for i in range(len(df7)):
        if i < (E.LEFT + E.RIGHT + 1): continue
        nph = i in phc; npl = i in plc
        if nph: lastPH = phc[i][1]
        if npl: lastPL = plc[i][1]
        if pos != 0:
            flip = (pos == 1 and Trend[i] == -1) or (pos == -1 and Trend[i] == 1)
            slbr = (i > ei and not np.isnan(sl)) and ((pos == 1 and L[i] <= sl) or (pos == -1 and H[i] >= sl))
            if slbr or flip:
                dev, rdir = P.dev_rdir(ep, poc7[ei], atr7[ei]) if (atr7[ei] > 0 and not np.isnan(poc7[ei])) else (np.nan, 0)
                feat = str(fs.asof(idx[ei])); cut = SH if (feat == "uptrend" and pos == -1) else 1.0
                out.append(dict(et=idx[ei], xt=idx[i], ep=float(ep), sl=float(sl) if not np.isnan(sl) else float(ep),
                                clo=float(Cl[i]), side=int(pos), reason="sl" if slbr else "flip",
                                base=BASE * opvnn(dev, rdir, pos) * cut, fund=F8 * nf(ei, i)))
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
                dd = 1 if le else -1; ep = Cl[i]; pos = dd; ei = i; pb = 0; sl = ep * (1 - dd * SLP / 100)
    return out


KT = king()
for t in KT:   # SL터치 1분봉의 SL초과 excursion(보수 슬립)
    t["exc"] = 0.0
    if t["reason"] != "sl": continue
    seg = m.loc[t["et"]: t["xt"] + pd.Timedelta(hours=7, minutes=5)]
    hit = seg[seg["low"] <= t["sl"]] if t["side"] == 1 else seg[seg["high"] >= t["sl"]]
    if len(hit):
        em = hit.iloc[0]
        t["exc"] = max(0.0, (t["sl"] - float(em["low"])) / t["ep"] if t["side"] == 1 else (float(em["high"]) - t["sl"]) / t["ep"])


def worst(lev_eff, lev_act):
    hsd = 1.0 / lev_act - MMR - SLIP
    a = PE.PaperAccount(10000.0); ps = []
    for t in KT:
        side = t["side"]; ep = t["ep"]
        if t["reason"] == "flip":
            R = side * (t["clo"] - ep) / ep - COST - t["fund"]
        else:
            adv = max(side * (t["sl"] - ep) / ep - t["exc"], -hsd)   # 보수: SL손익 - 그1분 excursion, 청산버퍼 캡
            R = adv - COST - t["fund"]
        b0 = a.bal
        a.open(Signal(Action.ENTER, side=Side(side), size_pct=t["base"] * K * (lev_eff / lev_act), leverage=lev_act), ts=None, price=100.0)
        a.resolve_replay(R=R, mae=min(0.0, R), fund=0.0); ps.append(a.bal / b0 - 1)
    ps = np.array(ps) * 100
    eq = np.cumprod(1 + ps / 100) * 1e4; mdd = ((eq / np.maximum.accumulate(eq) - 1).min()) * 100
    return (eq[-1] / 1e4 - 1) * 100, mdd, ps.min(), int((ps < -5).sum()), int((ps < -10).sum())


print("=== '급변 단일거래 최악손실' (보수=그1분봉 극단까지 슬립) ===")
print(f"{'노출/실레버':>12} {'수익%(보수)':>11} {'MDD%':>7} {'최악1거래%':>10} {'<-5%':>6} {'<-10%':>6}")
for le, la in [(22, 22), (16, 10), (15, 10), (13, 10), (10, 10), (10, 7), (10, 5), (8, 5)]:
    r, md, mn, n5, n10 = worst(le, la)
    print(f"{str(le)+'/'+str(la):>12} {r:>+10.0f}% {md:>6.0f}% {mn:>9.1f}% {n5:>6} {n10:>6}")
print("\n(최악1거래%=한 번의 급변으로 단일거래가 계좌에 입힌 최대 손실. <-5%/<-10%=그만큼 잃은 거래 수)")
print("보수가정(스톱이 1분봉 극단에 체결)이라 실제론 이보다 나음. 단 '최악 한방'의 상한을 보는 용도.")
