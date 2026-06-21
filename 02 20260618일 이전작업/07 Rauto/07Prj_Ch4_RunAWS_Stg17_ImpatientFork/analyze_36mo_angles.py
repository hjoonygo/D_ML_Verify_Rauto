# -*- coding: utf-8 -*-
# [analyze_36mo_angles.py] 성급왕 36개월 추가각도: 보유시간·요일/시간대·진입사유·손실국면 (1회용)
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "bots"))
import trendstack_signal_engine as E, trendstack_poc as P, trendstack_regime as RG, rauto_paper_engine as PE
from rauto_contract import Signal, Action, Side
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

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
def opvnn(dev, rdir, side):
    if dev is None or np.isnan(dev): return 1.0
    if abs(dev) >= 0.25: return 1.0 if side == rdir else 0.6 if side == -rdir else 1.0
    return 1.0


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
                mlt = opvnn(dev, rdir, pos); size = BASE * mlt * cut * K
                out.append(dict(et=idx[ei], xt=idx[i], hold_h=(i - ei) * 7, side=pos, feat=feat, reason=ex[0],
                                mlt=mlt, dev=dev, R=R, size=size, fund=F8 * nf(ei, i)))
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


trd = replay()
acc = PE.PaperAccount(10000.0); eq = []
for t in trd:
    b0 = acc.bal
    acc.open(Signal(Action.ENTER, side=Side(t["side"]), size_pct=t["size"], leverage=LEV), ts=None, price=100.0)
    acc.resolve_replay(R=t["R"], mae=min(0.0, t["R"]), fund=t["fund"])
    t["p"] = acc.bal / b0 - 1; t["bal"] = acc.bal; eq.append(acc.bal)
D = pd.DataFrame(trd); D["et"] = pd.to_datetime(D["et"]); eq = np.array(eq)


def grp(g):
    if not len(g): return (0, 0.0, 0.0, 0.0)
    R = g["R"].values; pf = R[R > 0].sum() / -R[R < 0].sum() if (R < 0).any() else 9.9
    return (len(g), (g["p"] > 0).mean() * 100, g["p"].sum() * 100, pf)


print("=== ① 보유시간별 ===")
bins = [0, 7, 14, 28, 56, 112, 1e9]; labs = ["~7h", "7-14h", "14-28h", "28-56h", "56-112h", "112h+"]
D["hb"] = pd.cut(D["hold_h"], bins, labels=labs, right=False)
for lb in labs:
    n, wr, c, pf = grp(D[D["hb"] == lb]); print(f"  {lb:<8}: {n:>3}건 승률{wr:>4.0f}% 기여{c:>+6.0f}% PF{pf:.2f}")
print(f"  (보유 중앙값 {D['hold_h'].median():.0f}h · 평균 {D['hold_h'].mean():.0f}h)")

print("=== ② 요일별(진입, UTC) ===")
wd = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]; D["wd"] = D["et"].dt.weekday
for i, nm in enumerate(wd):
    n, wr, c, pf = grp(D[D["wd"] == i]); print(f"  {nm}: {n:>3}건 승률{wr:>4.0f}% 기여{c:>+6.0f}% PF{pf:.2f}")
print("=== ②b 시간대별(진입시각, UTC) ===")
D["hr"] = D["et"].dt.hour
for hr in sorted(D["hr"].unique()):
    n, wr, c, pf = grp(D[D["hr"] == hr]); print(f"  {hr:02d}시: {n:>3}건 승률{wr:>4.0f}% 기여{c:>+6.0f}% PF{pf:.2f}")

print("=== ③ 진입사유별 ===")
print("  [방향]")
for s, nm in [(1, "롱"), (-1, "숏")]:
    n, wr, c, pf = grp(D[D["side"] == s]); print(f"    {nm}: {n:>3}건 승률{wr:>4.0f}% 기여{c:>+6.0f}% PF{pf:.2f}")
print("  [OPVnN 사이징]")
for m, nm in [(1.0, "회귀/중립(N=1.0)"), (0.6, "역회귀(n=0.6)")]:
    n, wr, c, pf = grp(D[np.isclose(D["mlt"], m)]); print(f"    {nm:<16}: {n:>3}건 승률{wr:>4.0f}% 기여{c:>+6.0f}% PF{pf:.2f}")
print("  [청산사유]")
for r, nm in [("sl", "손절(인트라바)"), ("flip", "추세전환")]:
    n, wr, c, pf = grp(D[D["reason"] == r]); print(f"    {nm:<12}: {n:>3}건 승률{wr:>4.0f}% 기여{c:>+6.0f}% PF{pf:.2f}")

print("=== ④ 손실국면(드로다운 에피소드 Top5) ===")
pk = np.maximum.accumulate(eq); ddv = eq / pk - 1
episodes = []; in_dd = False; start = 0
for i in range(len(ddv)):
    if ddv[i] < -1e-9 and not in_dd: in_dd = True; start = i; trough = i
    elif in_dd:
        if ddv[i] < ddv[trough]: trough = i
        if ddv[i] >= -1e-9:
            episodes.append((start, trough, i)); in_dd = False
if in_dd: episodes.append((start, trough, len(ddv) - 1))
ep_info = []
for s, tr, e in episodes:
    depth = ddv[tr] * 100; dur = (D["et"].iloc[min(e, len(D) - 1)] - D["et"].iloc[s]).days
    feat_mode = D["feat"].iloc[s:e + 1].mode()
    ep_info.append((depth, dur, str(D["et"].iloc[s])[:10], str(D["et"].iloc[min(tr, len(D) - 1)])[:10], feat_mode.iloc[0] if len(feat_mode) else "-"))
ep_info.sort()
print(f"  {'깊이%':>7} {'기간(일)':>7} {'시작':>11} {'저점':>11} {'주국면'}")
for depth, dur, s, tr, fm in ep_info[:5]:
    print(f"  {depth:>7.1f} {dur:>7d} {s:>11} {tr:>11} {fm}")
# 연속손실 streak
streaks = []; s = 0; ssum = 0; sstart = None
for _, t in D.iterrows():
    if t["p"] < 0:
        if s == 0: sstart = t["et"]
        s += 1; ssum += t["p"]
    else:
        if s >= 4: streaks.append((s, ssum * 100, str(sstart)[:10]))
        s = 0; ssum = 0
streaks.sort(reverse=True)
print("  [연속손실 4회+ streak]")
for n, loss, st in streaks[:5]:
    print(f"    {n}연패 합{loss:+.1f}% (시작 {st})")

# ===== 그래프 6패널 =====
fig = plt.figure(figsize=(16, 9))
ax = fig.add_subplot(2, 3, 1); g = [grp(D[D["hb"] == lb]) for lb in labs]
ax.bar(labs, [x[2] for x in g], color="#3b82f6"); ax.set_title("1) Contribution % by holding time")
for i, x in enumerate(g): ax.text(i, x[2], f"n{x[0]}", ha="center", fontsize=7)
ax.tick_params(axis="x", labelsize=7); ax.grid(alpha=.2)
ax = fig.add_subplot(2, 3, 2); g = [grp(D[D["wd"] == i]) for i in range(7)]
ax.bar(wd, [x[2] for x in g], color=["#3b82f6" if x[2] >= 0 else "#e24b4a" for x in g]); ax.set_title("2) Contribution % by weekday (entry)"); ax.grid(alpha=.2)
ax = fig.add_subplot(2, 3, 3); hrs = sorted(D["hr"].unique()); g = [grp(D[D["hr"] == hr]) for hr in hrs]
ax.bar([str(h) for h in hrs], [x[2] for x in g], color="#1d9e75"); ax.set_title("3) Contribution % by entry hour (UTC)"); ax.tick_params(axis="x", labelsize=7); ax.grid(alpha=.2)
ax = fig.add_subplot(2, 3, 4); cats = ["Long", "Short", "Regr\nN1.0", "Counter\nn0.6", "Exit:SL", "Exit:Flip"]
vals = [grp(D[D["side"] == 1])[2], grp(D[D["side"] == -1])[2], grp(D[np.isclose(D["mlt"], 1.0)])[2],
        grp(D[np.isclose(D["mlt"], 0.6)])[2], grp(D[D["reason"] == "sl"])[2], grp(D[D["reason"] == "flip"])[2]]
ax.bar(cats, vals, color="#caa53a"); ax.set_title("4) Contribution % by entry/exit reason"); ax.tick_params(axis="x", labelsize=7); ax.grid(alpha=.2)
ax = fig.add_subplot(2, 3, 5); ax.fill_between(D["et"], ddv * 100, 0, color="#e24b4a", alpha=.4); ax.set_title("5) Drawdown episodes (underwater %)"); ax.grid(alpha=.2)
ax = fig.add_subplot(2, 3, 6); ax.hist(D["hold_h"], bins=40, color="#3b82f6", alpha=.85); ax.set_title("6) Holding time distribution (hours)"); ax.set_yscale("log"); ax.grid(alpha=.2)
plt.tight_layout(); plt.savefig("king_36mo_angles.png", dpi=105, bbox_inches="tight"); print("\nsaved king_36mo_angles.png")
