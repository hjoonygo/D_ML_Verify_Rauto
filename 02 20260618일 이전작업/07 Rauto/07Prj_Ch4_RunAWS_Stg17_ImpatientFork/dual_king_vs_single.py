# -*- coding: utf-8 -*-
# [dual_king_vs_single.py] 듀얼(성급왕TS + 참을성SW + k·ER댐핑) vs 성급왕 단독 — 객관 비교. (1회용)
#   TS=성급왕(인트라바손절·5bp슬립) / SW=참을성(sw_patient.csv, 14bp) / 결합=k0.77·er0.40·w0.5(§9 확정).
#   객관성: ①동일 TS비용 ②return%·MDD%·Calmar(위험조정) ③위험맞춤(단독을 듀얼 MDD로 스케일) 병기.
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "bots"))
import trendstack_signal_engine as E, trendstack_poc as P, trendstack_regime as RG, rauto_paper_engine as PE
import SidewayDCA_Stg7_engine as SWENG
from rauto_contract import Signal, Action, Side
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

DATA = r"D:\ML\Verify\Merged_Data.csv"
df = pd.read_csv(DATA, usecols=lambda c: c in ("timestamp", "open", "high", "low", "close", "volume", "oi_zscore_24h"))
df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert(None); df = df.set_index("timestamp")
ohlc = df[["open", "high", "low", "close"]]; df7 = E.resample_tf(ohlc, E.TF_MIN)
vol7 = df["volume"].resample(f"{E.TF_MIN}min", label="left", closed="left").sum().reindex(df7.index).fillna(0.0)
oi7 = df["oi_zscore_24h"].resample(f"{E.TF_MIN}min", label="left", closed="left").last().reindex(df7.index).values
sig = E.compute_signals(df7); Trend = sig["Trend"]; phc = sig["ph_conf"]; plc = sig["pl_conf"]; er = sig["er"]
er7 = pd.Series(er, index=df7.index)
H = df7["high"].values; L = df7["low"].values; Cl = df7["close"].values; idx = df7.index; mid = (H + L) / 2.0
atr7 = E.compute_atr(H, L, Cl, E.ATR_PERIOD); poc7 = P.compute_poc(H, L, mid, vol7.values, 60, 50)
df4 = E.resample_tf(ohlc, 240)
try:
    _, fs = RG.feat_struct_of(df4, 8); fs.index = df4.index
except Exception:
    fs = pd.Series("range", index=df4.index)
eh = ((idx - pd.Timestamp("1970-01-01")) / pd.Timedelta(hours=1)).values.astype("float64")
COST = E.COST; SLP = E.SL_PCT; F8 = E.FUND_8H; DZ_LO, DZ_HI = E.DZ_LO, E.DZ_HI; GER = 0.45; fib = E.FIB
SLIP = 0.0005; BASE = 7.0864; TS_LEV = 22.0; SH = 0.0
SW_SIZE = 26.67; SW_LEV = 15.0; SW_SHORT = SWENG.SHORT_SIZE
K = 0.77; ER_THR = 0.40; W = 0.5   # §9 확정 듀얼


def nf(a, b): return int(np.floor(eh[b] / 8.0) - np.floor(eh[a] / 8.0))
def opvnn(dev, rdir, side):
    if dev is None or np.isnan(dev): return 1.0
    if abs(dev) >= 0.25: return 1.0 if side == rdir else 0.6 if side == -rdir else 1.0
    return 1.0


def king_ts():
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
                out.append(dict(exit_t=idx[i], year=int(idx[i].year), side=pos, feat=feat,
                                base=BASE * opvnn(dev, rdir, pos) * cut, R=R, mae=min(0.0, R), fund=F8 * nf(ei, i)))
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


def load_sw():
    sw = pd.read_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "sw_patient.csv"))
    out = []
    for _, r in sw.iterrows():
        side = int(r["side"]); base = SW_SIZE * (SW_SHORT if side == -1 else 1.0)
        e = er7.asof(pd.Timestamp(r["entry_t"]))
        out.append(dict(exit_t=pd.Timestamp(r["exit_t"]), year=pd.Timestamp(r["exit_t"]).year, side=side,
                        base=base, R=float(r["R"]), mae=0.0, fund=0.0, er=float(e) if pd.notna(e) else 0.0))
    return out


def run_slot(recs, lev, kfun):
    acc = PE.PaperAccount(10000.0); ts = []; bals = []
    for r in recs:
        size = r["base"] * kfun(r)
        if size <= 0:
            ts.append(r["exit_t"]); bals.append(acc.bal); continue
        acc.open(Signal(Action.ENTER, side=Side(int(r["side"])), size_pct=size, leverage=lev), ts=None, price=100.0)
        acc.resolve_replay(R=r["R"], mae=r["mae"], fund=r["fund"])
        ts.append(r["exit_t"]); bals.append(acc.bal)
    return ts, bals


def mdd_of(eq):
    eq = np.asarray(eq, float); pk = np.maximum.accumulate(eq); return ((eq - pk) / pk).min() * 100


def curve(ts, b):
    return pd.DataFrame({"t": pd.to_datetime(ts), "v": b}).groupby("t").last()


def metr(eq, cap, label):
    eq = np.asarray(eq, float); ret = (eq[-1] / cap - 1) * 100; cagr = ((eq[-1] / cap) ** (1 / 3.0) - 1) * 100
    mdd = mdd_of(eq); calmar = cagr / abs(mdd)
    print(f"  {label:<16} 수익 {ret:>+8.0f}% · CAGR {cagr:>6.0f}% · MDD {mdd:>6.1f}% · Calmar {calmar:>6.1f}")
    return ret, mdd, cagr, calmar


TS = king_ts(); SW = load_sw()
print(f"[거래] 성급왕TS {len(TS)} / 참을성SW {len(SW)} | k{K}·er{ER_THR}·w{W}")
# 단독: TS만 $10k, full size
st, sb = run_slot(TS, TS_LEV, lambda r: 1.0)
single = curve(st, sb)
print("\n=== 성급왕 단독 ($10k) ===")
rS = metr(single["v"].values, 10000.0, "성급왕 단독")
# 듀얼: TS×k + SW×k×ER댐핑, 포트 $20k
dt, db = run_slot(TS, TS_LEV, lambda r: K)
swt, swb = run_slot(SW, SW_LEV, lambda r: K * (W if r["er"] >= ER_THR else 1.0))
cT = curve(dt, db); cW = curve(swt, swb)
tl = pd.DataFrame(index=sorted(set(cT.index).union(set(cW.index))))
tl["ts"] = cT["v"].reindex(tl.index).ffill().fillna(10000.0)
tl["sw"] = cW["v"].reindex(tl.index).ffill().fillna(10000.0)
tl["port"] = tl["ts"] + tl["sw"]
print("\n=== 듀얼 (성급왕TS+참을성SW, 포트 $20k) ===")
rD = metr(tl["port"].values, 20000.0, "듀얼")
print(f"    (구성: TS최종 ${tl['ts'].iloc[-1]:,.0f} / SW최종 ${tl['sw'].iloc[-1]:,.0f})")
# 위험맞춤: 단독을 듀얼 MDD로 스케일(노출∝MDD 근사) → 같은 위험서 누가 더 버나
scale = abs(rD[1]) / abs(rS[1])
print(f"\n=== 위험맞춤 비교 (단독을 듀얼 MDD {rD[1]:.1f}%로 스케일, ×{scale:.2f}) ===")
print(f"  단독(위험맞춤) CAGR≈ {rS[2]*scale:>6.0f}%  vs  듀얼 CAGR {rD[2]:>6.0f}%  → {'듀얼 우위' if rD[2]>rS[2]*scale else '단독 우위'}")
print(f"  [원칙] Calmar 높을수록 위험대비 우수: 단독 {rS[3]:.1f} vs 듀얼 {rD[3]:.1f}")
# 연도별 MDD 비교
print("\n=== 연도별 MDD (듀얼이 횡보 쿠션으로 낮추나) ===")
for y in (2023, 2024, 2025, 2026):
    sM = mdd_of(single[single.index.year == y]["v"].values) if (single.index.year == y).any() else 0
    dM = mdd_of(tl[tl.index.year == y]["port"].values) if (tl.index.year == y).any() else 0
    print(f"  {y}: 단독 MDD {sM:>6.1f}% | 듀얼 MDD {dM:>6.1f}%")

# 그래프
fig, ax = plt.subplots(1, 2, figsize=(14, 5))
ax[0].plot(single.index, single["v"] / 10000.0, label="KING single", color="#3b82f6")
ax[0].plot(tl.index, tl["port"] / 20000.0, label="DUAL (KING+SW)", color="#1d9e75")
ax[0].set_yscale("log"); ax[0].set_title("Growth multiple (normalized, log)"); ax[0].legend(); ax[0].grid(alpha=.2)
for eqs, dts, c, nm in [(single["v"].values, single.index, "#3b82f6", "KING single"), (tl["port"].values, tl.index, "#1d9e75", "DUAL")]:
    pk = np.maximum.accumulate(eqs); ax[1].fill_between(dts, (eqs / pk - 1) * 100, 0, alpha=.4, color=c, label=nm)
ax[1].axhline(-20, color="#e24b4a", ls="--", lw=1, label="-20% limit"); ax[1].set_title("Drawdown %"); ax[1].legend(); ax[1].grid(alpha=.2)
plt.tight_layout(); plt.savefig("dual_vs_single.png", dpi=110, bbox_inches="tight"); print("\nsaved dual_vs_single.png")
