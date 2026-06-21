# -*- coding: utf-8 -*-
# [r4_audit.py] R4(최고Calmar듀얼 k1.4) 실거래 안전성 비판감사 — 일중MDD·강제청산·OOS·연도별. (1회용)
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


def king_tr():
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
                # mae(실제 보유 중 최대역행) = 진입~청산 봉들의 역행 최대(강제청산 판정용)
                seg_lo = L[ei + 1:i + 1] if i > ei else np.array([ep]); seg_hi = H[ei + 1:i + 1] if i > ei else np.array([ep])
                mae = float(np.min((seg_lo - ep) / ep)) if pos == 1 else float(np.min((ep - seg_hi) / ep)) if len(seg_hi) else 0.0
                out.append(dict(xt=idx[i], year=int(idx[i].year), side=pos, base=BASE * opvnn(dev, rdir, pos) * cut, R=R, mae=min(0.0, mae), fund=F8 * nf(ei, i)))
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
        out.append(dict(xt=pd.Timestamp(r["exit_t"]), year=pd.Timestamp(r["exit_t"]).year, side=side, base=base, R=float(r["R"]), mae=0.0, fund=0.0, er=float(e) if pd.notna(e) else 0.0))
    return out


def slot(recs, lev, kf, years=None):
    acc = PE.PaperAccount(10000.0); rows = []
    for r in recs:
        if years is not None and r["year"] not in years: continue
        size = r["base"] * kf(r)
        if size > 0:
            acc.open(Signal(Action.ENTER, side=Side(int(r["side"])), size_pct=size, leverage=lev), ts=None, price=100.0)
            acc.resolve_replay(R=r["R"], mae=r["mae"], fund=r["fund"])
        rows.append((r["xt"], acc.bal))
    return pd.DataFrame(rows, columns=["t", "v"]).groupby("t").last()["v"], acc.n_liq


KT = king_tr(); SW = load_sw()
days = pd.date_range(df7.index[0].normalize(), df7.index[-1].normalize(), freq="D")
def daily(s): return s.reindex(s.index.union(days)).sort_index().ffill().reindex(days).ffill().fillna(10000.0)
def mddv(eq): eq = np.asarray(eq, float); pk = np.maximum.accumulate(eq); return ((eq / pk - 1).min()) * 100


def r4(years=None, k=1.4, w=0.0, et=0.40):
    t, nlt = slot(KT, TS_LEV, lambda r: k, years); s, nls = slot(SW, SW_LEV, lambda r: k * (w if r["er"] >= et else 1.0), years)
    port = daily(t) + daily(s); return port, nlt, nls


print("=== R4(k1.4) 안전성 감사 — 36개월 전표본 ===")
port, nlt, nls = r4()
dmdd = mddv(port.values)  # 일별 MDD(주간보다 정확)
wk = port.resample("W").last(); wmdd = mddv(wk.values)
dret = port.pct_change().dropna()
print(f"  최종수익 {(port.iloc[-1]/20000-1)*100:+.0f}% | ★일별MDD {dmdd:.1f}% (주간MDD {wmdd:.1f}%) | 최악 1일 {dret.min()*100:.1f}%")
print(f"  ★강제청산(liquidation): TS {nlt}회 / SW {nls}회  (0이면 청산 없음)")
# R2 단독 비교(같은 일별 기준)
r2, nl2 = slot(KT, TS_LEV, lambda r: 1.0); r2d = daily(r2)
print(f"  [비교 R2단독] 수익 {(r2d.iloc[-1]/10000-1)*100:+.0f}% | 일별MDD {mddv(r2d.values):.1f}% | 청산 {nl2}회")
print("\n=== 연도별 (일별MDD) ===")
for y in (2023, 2024, 2025, 2026):
    p, a, b = r4({y})
    if len(p): print(f"  {y}: 수익 {(p.iloc[-1]/20000-1)*100:+6.0f}% | 일별MDD {mddv(p.values):5.1f}% | 청산 TS{a}/SW{b}")
print("\n=== OOS (2023-24 → 2025-26) — k1.4가 미래에도 견고한가 ===")
ptr, _, _ = r4({2023, 2024}); pte, alt, als = r4({2025, 2026})
print(f"  학습(23-24): 수익 {(ptr.iloc[-1]/20000-1)*100:+.0f}% MDD {mddv(ptr.values):.1f}%")
print(f"  ★검증(25-26): 수익 {(pte.iloc[-1]/20000-1)*100:+.0f}% MDD {mddv(pte.values):.1f}% 청산 TS{alt}/SW{als} → {'PASS(흑자)' if pte.iloc[-1]>20000 else 'FAIL'}")
# 최악 주간 5개
print("\n=== 최악 주간 5 (R4) ===")
wr = wk.pct_change().dropna() * 100
for t, v in wr.nsmallest(5).items(): print(f"  {str(t)[:10]}: {v:+.1f}%")
