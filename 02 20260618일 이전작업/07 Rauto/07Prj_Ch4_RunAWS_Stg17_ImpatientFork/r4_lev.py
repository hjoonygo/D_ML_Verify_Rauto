# -*- coding: utf-8 -*-
# [r4_lev.py] R4(듀얼 k1.4) 레버별 실제수익 — TS레버 변경 + 현실 스톱슬립(10bp)+갭청산, 일별 MDD. (1회용)
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "bots"))
import trendstack_signal_engine as E, trendstack_poc as P, trendstack_regime as RG, rauto_paper_engine as PE
import SidewayDCA_Stg7_engine as SWENG
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
er7 = pd.Series(er, index=df7.index)
H = df7["high"].values; L = df7["low"].values; Cl = df7["close"].values; idx = df7.index; mid = (H + L) / 2.0
atr7 = E.compute_atr(H, L, Cl, E.ATR_PERIOD); poc7 = P.compute_poc(H, L, mid, vol7.values, 60, 50)
df4 = E.resample_tf(m[["open", "high", "low", "close"]], 240)
try:
    _, fs = RG.feat_struct_of(df4, 8); fs.index = df4.index
except Exception:
    fs = pd.Series("range", index=df4.index)
eh = ((idx - pd.Timestamp("1970-01-01")) / pd.Timedelta(hours=1)).values.astype("float64")
COST = E.COST; SLP = E.SL_PCT; F8 = E.FUND_8H; DZ_LO, DZ_HI = E.DZ_LO, E.DZ_HI; GER = 0.45; fib = E.FIB
SLIP = 0.0005; BASE = 7.0864; SH = 0.0; MMR = 0.004; SW_SIZE = 26.67; SW_LEV = 15.0; SW_SHORT = SWENG.SHORT_SIZE
FIX_SLIP = 0.001; K = 1.4; ERT = 0.40; WD = 0.0


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
                out.append(dict(xt=idx[i], ep=float(ep), sl=float(sl) if not np.isnan(sl) else float(ep), clo=float(Cl[i]),
                                side=int(pos), reason="sl" if slbr else "flip", base=BASE * opvnn(dev, rdir, pos) * cut,
                                fund=F8 * nf(ei, i), et=idx[ei]))
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
for t in KT:                                   # SL터치 1분봉 시가역행(갭판정)
    t["open_adv"] = 0.0
    if t["reason"] != "sl": continue
    seg = m.loc[t["et"]: t["xt"] + pd.Timedelta(hours=7, minutes=5)]
    hit = seg[seg["low"] <= t["sl"]] if t["side"] == 1 else seg[seg["high"] >= t["sl"]]
    if len(hit):
        eo = float(hit.iloc[0]["open"]); t["open_adv"] = (eo - t["ep"]) / t["ep"] if t["side"] == 1 else (t["ep"] - eo) / t["ep"]
SW = []
sw = pd.read_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "sw_patient.csv"))
for _, r in sw.iterrows():
    side = int(r["side"]); e = er7.asof(pd.Timestamp(r["entry_t"]))
    SW.append(dict(xt=pd.Timestamp(r["exit_t"]), side=side, base=SW_SIZE * (SW_SHORT if side == -1 else 1.0),
                   R=float(r["R"]) - 0.0014, er=float(e) if pd.notna(e) else 0.0))
days = pd.date_range(df7.index[0].normalize(), df7.index[-1].normalize(), freq="D")
def daily(s): return s.reindex(s.index.union(days)).sort_index().ffill().reindex(days).ffill().fillna(10000.0)
def mddv(eq): eq = np.asarray(eq, float); pk = np.maximum.accumulate(eq); return ((eq / pk - 1).min()) * 100


def Rof(t, lev):
    hsd = 1.0 / lev - MMR - SLIP; side = t["side"]; ep = t["ep"]
    if t["reason"] == "flip": return side * (t["clo"] - ep) / ep - COST - t["fund"]
    if t["open_adv"] <= -hsd: return -hsd - COST - t["fund"]
    return max(side * (t["sl"] - ep) / ep - FIX_SLIP, -hsd) - COST - t["fund"]


def run(lev):
    aT = PE.PaperAccount(10000.0); bt = []
    for t in KT:
        aT.open(Signal(Action.ENTER, side=Side(t["side"]), size_pct=t["base"] * K, leverage=lev), ts=None, price=100.0)
        aT.resolve_replay(R=Rof(t, lev), mae=min(0.0, Rof(t, lev)), fund=0.0); bt.append((t["xt"], aT.bal))
    aW = PE.PaperAccount(10000.0); bw = []
    for t in SW:
        weff = WD if t["er"] >= ERT else 1.0
        aW.open(Signal(Action.ENTER, side=Side(t["side"]), size_pct=t["base"] * K * weff, leverage=SW_LEV), ts=None, price=100.0)
        if t["base"] * K * weff > 0: aW.resolve_replay(R=t["R"], mae=0.0, fund=0.0)
        bw.append((t["xt"], aW.bal))
    T = daily(pd.DataFrame(bt, columns=["t", "v"]).groupby("t").last()["v"])
    W = daily(pd.DataFrame(bw, columns=["t", "v"]).groupby("t").last()["v"]) if bw else daily(pd.Series(dtype=float))
    port = (T + W).values
    nl = sum(1 for t in KT if t["reason"] == "sl" and t["open_adv"] <= -(1.0 / lev - MMR - SLIP))
    return (port[-1] / 20000 - 1) * 100, mddv(port), nl, aT.bal


print("=== R4(듀얼 k1.4) 레버별 — 현실(10bp슬립+갭청산), 일별MDD ===")
print(f"{'TS레버':>6} {'포트수익%':>10} {'일별MDD%':>9} {'갭청산':>6} {'TS슬롯최종$':>12}")
for lev in (22, 15, 10, 8, 7, 5):
    ret, mdd, nl, tb = run(lev)
    flag = "  ←-20% 위반" if mdd < -20 else ("  ←안전" if nl == 0 and mdd >= -20 else "")
    print(f"{lev:>6} {ret:>+9.0f}% {mdd:>8.1f}% {nl:>6} {tb:>11,.0f}{flag}")
print("\n(현 R4=lev22. 일별MDD는 거래체결시점보다 깊은 진짜 MDD. 갭청산0 & MDD>-20% = 실거래 안전구간)")
