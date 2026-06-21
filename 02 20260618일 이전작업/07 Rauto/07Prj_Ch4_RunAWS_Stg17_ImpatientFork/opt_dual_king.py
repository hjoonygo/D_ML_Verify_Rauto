# -*- coding: utf-8 -*-
# [opt_dual_king.py] 성급왕TS(핀고정) + 인내SW 최적조합 — (k,er,w) 스윕, MDD>=-20% 제약, full+OOS. (1회용)
import os, sys, itertools
import numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "bots"))
import trendstack_signal_engine as E, trendstack_poc as P, trendstack_regime as RG, rauto_paper_engine as PE
import SidewayDCA_Stg7_engine as SWENG
from rauto_contract import Signal, Action, Side

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
MDD_LINE = -20.0


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
                out.append(dict(exit_t=idx[i], year=int(idx[i].year), side=pos,
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
    sw = pd.read_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "sw_patient.csv")); out = []
    for _, r in sw.iterrows():
        side = int(r["side"]); base = SW_SIZE * (SW_SHORT if side == -1 else 1.0)
        e = er7.asof(pd.Timestamp(r["entry_t"]))
        out.append(dict(exit_t=pd.Timestamp(r["exit_t"]), year=pd.Timestamp(r["exit_t"]).year, side=side,
                        base=base, R=float(r["R"]), mae=0.0, fund=0.0, er=float(e) if pd.notna(e) else 0.0))
    return out


def run_slot(recs, lev, kfun, years):
    acc = PE.PaperAccount(10000.0); ts = []; bals = []
    for r in recs:
        if years is not None and r["year"] not in years:
            continue
        size = r["base"] * kfun(r)
        if size <= 0:
            ts.append(r["exit_t"]); bals.append(acc.bal); continue
        acc.open(Signal(Action.ENTER, side=Side(int(r["side"])), size_pct=size, leverage=lev), ts=None, price=100.0)
        acc.resolve_replay(R=r["R"], mae=r["mae"], fund=r["fund"])
        ts.append(r["exit_t"]); bals.append(acc.bal)
    return ts, bals


def mdd_of(eq):
    eq = np.asarray(eq, float); pk = np.maximum.accumulate(eq); return ((eq - pk) / pk).min() * 100


def eval_dual(TS, SW, k, et, w, years=None):
    tt, tb = run_slot(TS, TS_LEV, lambda r: k, years)
    st, sb = run_slot(SW, SW_LEV, lambda r: k * (w if r["er"] >= et else 1.0), years)
    a = pd.DataFrame({"t": pd.to_datetime(tt), "ts": tb}).groupby("t").last()
    b = pd.DataFrame({"t": pd.to_datetime(st), "sw": sb}).groupby("t").last() if len(st) else pd.DataFrame({"sw": []})
    tl = pd.DataFrame(index=sorted(set(a.index).union(set(b.index))))
    tl["ts"] = a["ts"].reindex(tl.index).ffill().fillna(10000.0)
    tl["sw"] = (b["sw"].reindex(tl.index).ffill().fillna(10000.0)) if len(b) else 10000.0
    port = (tl["ts"] + tl["sw"]).values
    n = len(set(y for y in (years or {2023, 2024, 2025, 2026}))); cagr = ((port[-1] / 20000.0) ** (1 / max(1, n)) - 1) * 100
    return (port[-1] / 20000.0 - 1) * 100, mdd_of(port), cagr


TS = king_ts(); SW = load_sw()
print(f"[거래] 성급왕TS {len(TS)} / 인내SW {len(SW)}")
# 단독 기준선(king full, $10k)
st, sb = run_slot(TS, TS_LEV, lambda r: 1.0, None)
sret = (sb[-1] / 1e4 - 1) * 100; smdd = mdd_of(sb); scagr = ((sb[-1] / 1e4) ** (1 / 3.0) - 1) * 100
print(f"[기준] 성급왕 단독: 수익 {sret:+.0f}% · MDD {smdd:.1f}% · Calmar {scagr/abs(smdd):.1f}")

KS = [0.6, 0.77, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4]; ERT = [0.35, 0.40, 0.45]; WD = [0.0, 0.25, 0.5, 0.75, 1.0]
rows = []
for k, et, w in itertools.product(KS, ERT, WD):
    ret, mdd, cagr = eval_dual(TS, SW, k, et, w)
    rows.append(dict(k=k, er=et, w=w, ret=ret, mdd=mdd, calmar=cagr / abs(mdd)))
R = pd.DataFrame(rows)
ok = R[R["mdd"] >= MDD_LINE]
best_ret = ok.sort_values("ret", ascending=False).iloc[0]
best_cal = R.sort_values("calmar", ascending=False).iloc[0]
print(f"\n=== 전표본 최적 (MDD>=-20% 제약, 최대수익) ===")
print(f"  k={best_ret.k} er={best_ret.er} w={best_ret.w} → 수익 {best_ret.ret:+.0f}% · MDD {best_ret.mdd:.1f}% · Calmar {best_ret.calmar:.1f}")
print(f"=== 전표본 최고 Calmar(무제약) ===")
print(f"  k={best_cal.k} er={best_cal.er} w={best_cal.w} → 수익 {best_cal.ret:+.0f}% · MDD {best_cal.mdd:.1f}% · Calmar {best_cal.calmar:.1f}")
print(f"  (§9기본 k0.77/er0.4/w0.5: " + " ".join(f"{c}={R[(R.k==0.77)&(R.er==0.40)&(R.w==0.5)].iloc[0][c]:.1f}" for c in ["ret","mdd","calmar"]) + ")")

# OOS: 2023-24 최적 → 2025-26 적용
tr_years = {2023, 2024}; te_years = {2025, 2026}
tro = []
for k, et, w in itertools.product(KS, ERT, WD):
    ret, mdd, cagr = eval_dual(TS, SW, k, et, w, tr_years)
    tro.append(dict(k=k, er=et, w=w, ret=ret, mdd=mdd))
TR = pd.DataFrame(tro); TRok = TR[TR["mdd"] >= MDD_LINE].sort_values("ret", ascending=False).iloc[0]
te_ret, te_mdd, te_cagr = eval_dual(TS, SW, TRok.k, TRok.er, TRok.w, te_years)
print(f"\n=== OOS (2023-24 학습 최적 → 2025-26 검증) ===")
print(f"  학습최적: k={TRok.k} er={TRok.er} w={TRok.w} (학습 수익 {TRok.ret:+.0f}% MDD {TRok.mdd:.1f}%)")
print(f"  ★검증(2025-26): 수익 {te_ret:+.0f}% · MDD {te_mdd:.1f}% · {'PASS(흑자·MDD준수)' if te_ret>0 and te_mdd>=MDD_LINE else 'FAIL'}")
# 단독도 OOS 비교(같은 2025-26)
sst, ssb = run_slot(TS, TS_LEV, lambda r: 1.0, te_years)
print(f"  (성급왕 단독 2025-26: 수익 {(ssb[-1]/1e4-1)*100:+.0f}% · MDD {mdd_of(ssb):.1f}%)")
R.to_csv("opt_dual_king.csv", index=False)
print("\nsaved opt_dual_king.csv")
