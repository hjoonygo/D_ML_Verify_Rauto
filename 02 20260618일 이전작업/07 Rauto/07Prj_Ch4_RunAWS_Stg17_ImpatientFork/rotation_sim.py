# -*- coding: utf-8 -*-
# [rotation_sim.py] 챔피언 로테이션(최근 N주 최고 봇 따라가기) vs 고정 — 4봇 36개월 시뮬. (1회용)
#   봇: R1 성급(vanilla) · R2 성급왕(king) · R3 듀얼k1.1 · R4 듀얼k1.4. 주간 리밸런스.
import os, sys
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
SLIP = 0.0005; BASE = 7.0864; TS_LEV = 22.0; SH = 0.0; SW_SIZE = 26.67; SW_LEV = 15.0; SW_SHORT = SWENG.SHORT_SIZE


def nf(a, b): return int(np.floor(eh[b] / 8.0) - np.floor(eh[a] / 8.0))
def opvnn(dev, rdir, side):
    if dev is None or np.isnan(dev): return 1.0
    if abs(dev) >= 0.25: return 1.0 if side == rdir else 0.6 if side == -rdir else 1.0
    return 1.0


def ts_trades(king):
    pos = 0; ep = np.nan; ei = -1; sl = np.nan; pb = 0; lastPH = np.nan; lastPL = np.nan; out = []
    for i in range(len(df7)):
        if i < (E.LEFT + E.RIGHT + 1): continue
        nph = i in phc; npl = i in plc
        if nph: lastPH = phc[i][1]
        if npl: lastPL = plc[i][1]
        if pos != 0:
            flip = (pos == 1 and Trend[i] == -1) or (pos == -1 and Trend[i] == 1)
            slbr = (i > ei and not np.isnan(sl)) and ((pos == 1 and L[i] <= sl) or (pos == -1 and H[i] >= sl))
            if king: ex = ("sl", sl * (1 - pos * SLIP)) if slbr else (("flip", Cl[i]) if flip else None)
            else: ex = ("flip", Cl[i]) if flip else (("sl", sl * (1 - pos * SLIP)) if slbr else None)
            if ex:
                R = pos * (ex[1] - ep) / ep - COST - F8 * nf(ei, i)
                dev, rdir = P.dev_rdir(ep, poc7[ei], atr7[ei]) if (atr7[ei] > 0 and not np.isnan(poc7[ei])) else (np.nan, 0)
                feat = str(fs.asof(idx[ei])); cut = SH if (feat == "uptrend" and pos == -1) else 1.0
                out.append(dict(xt=idx[i], side=pos, base=BASE * opvnn(dev, rdir, pos) * cut, R=R, mae=min(0.0, R), fund=F8 * nf(ei, i)))
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
        out.append(dict(xt=pd.Timestamp(r["exit_t"]), side=side, base=base, R=float(r["R"]), mae=0.0, fund=0.0, er=float(e) if pd.notna(e) else 0.0))
    return out


def slot_eq(recs, lev, kf):
    acc = PE.PaperAccount(10000.0); rows = []
    for r in recs:
        size = r["base"] * kf(r)
        if size > 0:
            acc.open(Signal(Action.ENTER, side=Side(int(r["side"])), size_pct=size, leverage=lev), ts=None, price=100.0)
            acc.resolve_replay(R=r["R"], mae=r["mae"], fund=r["fund"])
        rows.append((r["xt"], acc.bal))
    return pd.DataFrame(rows, columns=["t", "v"]).groupby("t").last()["v"]


# 4봇 일별 자산곡선
van = ts_trades(False); king = ts_trades(True); SW = load_sw()
days = pd.date_range(df7.index[0].normalize(), df7.index[-1].normalize(), freq="D")
def daily(series): return series.reindex(series.index.union(days)).sort_index().ffill().reindex(days).ffill().fillna(10000.0)
R1 = daily(slot_eq(van, TS_LEV, lambda r: 1.0))
R2 = daily(slot_eq(king, TS_LEV, lambda r: 1.0))
def dual(k, er_thr=0.40, w=0.0):
    t = daily(slot_eq(king, TS_LEV, lambda r: k)); s = daily(slot_eq(SW, SW_LEV, lambda r: k * (w if r["er"] >= er_thr else 1.0)))
    return t + s
R3 = dual(1.1); R4 = dual(1.4)
bots = {"R1성급": R1, "R2성급왕": R2, "R3듀얼k1.1": R3, "R4듀얼k1.4": R4}
# 주간 자산
W = pd.DataFrame({k: v.resample("W").last() for k, v in bots.items()}).dropna()
wret = W.pct_change().fillna(0.0)


def mdd(eq): eq = np.asarray(eq); pk = np.maximum.accumulate(eq); return ((eq / pk - 1).min()) * 100
def stat(weekly_ret, label):
    eq = 10000 * (1 + weekly_ret).cumprod(); tot = (eq.iloc[-1] / 10000 - 1) * 100
    cagr = ((eq.iloc[-1] / 10000) ** (1 / 3.0) - 1) * 100; md = mdd(eq.values)
    print(f"  {label:<20} 수익 {tot:>+8.0f}% · MDD {md:>6.1f}% · Calmar {cagr/abs(md):>5.1f}")
    return tot, md, cagr / abs(md)


print("=== 4봇 단독(주간 복리) ===")
for k in bots: stat(wret[k], k + " 고정")
print("\n=== 챔피언 로테이션 (최근 N주 1등 → 다음주 추종) ===")
for N in (1, 2, 3, 4, 6, 8):
    rot = []
    cols = list(bots.keys())
    for i in range(len(W)):
        if i < N: rot.append(wret.iloc[i].mean()); continue   # 워밍업=균등
        trail = W.iloc[i - 1] / W.iloc[i - 1 - N] - 1   # 최근 N주 수익
        champ = trail.idxmax()
        rot.append(wret.iloc[i][champ])
    stat(pd.Series(rot, index=W.index), f"로테이션 {N}주")
print("\n=== 참고: 균등분산(4봇) ===")
stat(wret.mean(axis=1), "균등분산")
# 로테이션 전환빈도(2주)
N = 2; switches = 0; prev = None
for i in range(N, len(W)):
    champ = (W.iloc[i - 1] / W.iloc[i - 1 - N] - 1).idxmax()
    if prev is not None and champ != prev: switches += 1
    prev = champ
print(f"\n[2주 로테이션] 전환 {switches}회 / {len(W)-N}주 (전환율 {switches/(len(W)-N)*100:.0f}%)")

# ── 추가: R4(고레버) 제외 풀에서 로테이션 (MDD 안전 풀) ──
print("\n=== R4 제외 풀(R1·R2·R3, 다 MDD~-18%)에서 로테이션 ===")
pool = ["R1성급", "R2성급왕", "R3듀얼k1.1"]
Wp = W[pool]; wrp = Wp.pct_change().fillna(0.0)
for N in (2, 3, 4):
    rot = []
    for i in range(len(Wp)):
        if i < N: rot.append(wrp.iloc[i].mean()); continue
        champ = (Wp.iloc[i-1] / Wp.iloc[i-1-N] - 1).idxmax()
        rot.append(wrp.iloc[i][champ])
    stat(pd.Series(rot, index=Wp.index), f"로테(R4제외) {N}주")
stat(wret["R2성급왕"], "  vs R2 고정")
