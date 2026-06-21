# -*- coding: utf-8 -*-
# [analyze_36mo_deep.py] 성급 vs 성급왕 36개월 다각도 정밀분석 + 6패널 그래프 (1회용)
#   배치 replay(resample 그리드·5bp 슬립·단독 k1.0·lev22) = CPCV와 동일 틀.
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
H = df7["high"].values; L = df7["low"].values; Cl = df7["close"].values; idx = df7.index
mid = (H + L) / 2.0
atr7 = E.compute_atr(H, L, Cl, E.ATR_PERIOD); poc7 = P.compute_poc(H, L, mid, vol7.values, 60, 50)
df4 = E.resample_tf(ohlc, 240)
try:
    _, fs = RG.feat_struct_of(df4, 8); fs.index = df4.index
except Exception:
    fs = pd.Series("range", index=df4.index)
eh = ((idx - pd.Timestamp("1970-01-01")) / pd.Timedelta(hours=1)).values.astype("float64")
COST = E.COST; SLP = E.SL_PCT; F8 = E.FUND_8H; DZ_LO, DZ_HI = E.DZ_LO, E.DZ_HI; GER = 0.45; fib = E.FIB
SLIP = 0.0005; BASE = 7.0864; LEV = 22.0; SH = 0.0; K = 1.0


def nf(a, b):
    return int(np.floor(eh[b] / 8.0) - np.floor(eh[a] / 8.0))


def opvnn(dev, rdir, side):
    if dev is None or np.isnan(dev):
        return 1.0
    if abs(dev) >= 0.25:
        return 1.0 if side == rdir else 0.6 if side == -rdir else 1.0
    return 1.0


def replay(king):
    pos = 0; ep = np.nan; ei = -1; sl = np.nan; pb = 0; lastPH = np.nan; lastPL = np.nan; out = []
    for i in range(len(df7)):
        if i < (E.LEFT + E.RIGHT + 1):
            continue
        nph = i in phc; npl = i in plc
        if nph: lastPH = phc[i][1]
        if npl: lastPL = plc[i][1]
        if pos != 0:
            flip = (pos == 1 and Trend[i] == -1) or (pos == -1 and Trend[i] == 1)
            slbr = (i > ei and not np.isnan(sl)) and ((pos == 1 and L[i] <= sl) or (pos == -1 and H[i] >= sl))
            ex = None
            if king:
                if slbr: ex = ("sl", sl * (1 - pos * SLIP))
                elif flip: ex = ("flip", Cl[i])
            else:
                if flip: ex = ("flip", Cl[i])
                elif slbr: ex = ("sl", sl * (1 - pos * SLIP))
            if ex:
                R = pos * (ex[1] - ep) / ep - COST - F8 * nf(ei, i)
                dev, rdir = P.dev_rdir(ep, poc7[ei], atr7[ei]) if (atr7[ei] > 0 and not np.isnan(poc7[ei])) else (np.nan, 0)
                feat = str(fs.asof(idx[ei])); cut = SH if (feat == "uptrend" and pos == -1) else 1.0
                size = BASE * opvnn(dev, rdir, pos) * cut * K
                out.append(dict(xt=idx[i], side=pos, feat=feat, R=R, size=size, fund=F8 * nf(ei, i), reason=ex[0]))
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


def acct(trd):
    acc = PE.PaperAccount(10000.0); eq = []; dt = []
    for t in trd:
        b0 = acc.bal
        acc.open(Signal(Action.ENTER, side=Side(t["side"]), size_pct=t["size"], leverage=LEV), ts=None, price=100.0)
        acc.resolve_replay(R=t["R"], mae=min(0.0, t["R"]), fund=t["fund"])
        t["p"] = acc.bal / b0 - 1; t["bal"] = acc.bal; eq.append(acc.bal); dt.append(t["xt"])
    return acc, np.array(eq), pd.to_datetime(dt)


def stats(trd, eq):
    p = np.array([t["p"] for t in trd]); R = np.array([t["R"] for t in trd])
    pk = np.maximum.accumulate(eq); mdd = (eq / pk - 1).min() * 100
    cagr = ((eq[-1] / 1e4) ** (1 / 3.0) - 1) * 100
    tpy = len(p) / 3.0; sharpe = p.mean() / p.std() * np.sqrt(tpy)
    s = 0; mx = 0
    for x in p:
        s = s + 1 if x < 0 else 0; mx = max(mx, s)
    return dict(n=len(p), ret=(eq[-1] / 1e4 - 1) * 100, cagr=cagr, mdd=mdd, calmar=cagr / abs(mdd),
                sharpe=sharpe, wr=(p > 0).mean() * 100, pf=R[R > 0].sum() / -R[R < 0].sum(),
                payoff=p[p > 0].mean() / abs(p[p < 0].mean()), best=p.max() * 100, worst=p.min() * 100, maxlose=mx)


imp = replay(False); king = replay(True)
aI, eqI, dI = acct(imp); aK, eqK, dK = acct(king)
sI = stats(imp, eqI); sK = stats(king, eqK)
print("지표              성급        성급왕")
for k, lab in [("n", "거래수"), ("ret", "총수익%"), ("cagr", "CAGR%"), ("mdd", "MDD%"), ("calmar", "Calmar"),
               ("sharpe", "Sharpe"), ("wr", "승률%"), ("pf", "PF"), ("payoff", "손익비"),
               ("best", "최대익%"), ("worst", "최대손%"), ("maxlose", "최장연속손실")]:
    print(f"{lab:<14}{sI[k]:>10.1f}{sK[k]:>12.1f}")

fig = plt.figure(figsize=(16, 9))
ax = fig.add_subplot(2, 3, 1); ax.plot(dI, eqI, label="Impatient", color="#9aa6b2"); ax.plot(dK, eqK, label="KING", color="#3b82f6")
ax.set_yscale("log"); ax.set_title("1) Equity curve (log, $10k start)"); ax.legend(fontsize=8); ax.grid(alpha=.2)
ax = fig.add_subplot(2, 3, 2)
for eq, dt, c, nm in [(eqI, dI, "#9aa6b2", "Impatient"), (eqK, dK, "#3b82f6", "KING")]:
    pk = np.maximum.accumulate(eq); ax.fill_between(dt, (eq / pk - 1) * 100, 0, alpha=.4, color=c, label=nm)
ax.set_title("2) Drawdown (underwater) %"); ax.legend(fontsize=8); ax.grid(alpha=.2)
dk = pd.DataFrame(king); dk["ym"] = pd.to_datetime(dk["xt"]).dt.to_period("M")
mret = dk.groupby("ym")["p"].apply(lambda s: (np.prod(1 + s.values) - 1) * 100)
mat = mret.to_frame("r"); mat["y"] = mat.index.year; mat["m"] = mat.index.month
piv = mat.pivot_table(index="y", columns="m", values="r")
ax = fig.add_subplot(2, 3, 3); im = ax.imshow(piv.values, cmap="RdYlGn", vmin=-30, vmax=30, aspect="auto")
ax.set_xticks(range(len(piv.columns))); ax.set_xticklabels(piv.columns, fontsize=7)
ax.set_yticks(range(len(piv.index))); ax.set_yticklabels(piv.index, fontsize=8)
ax.set_title("3) KING monthly return % (green=+)"); plt.colorbar(im, ax=ax, fraction=.046)
ax = fig.add_subplot(2, 3, 4); pk = np.array([t["p"] for t in king]) * 100
ax.hist(pk, bins=50, color="#3b82f6", alpha=.85); ax.axvline(0, color="#555", lw=1)
ax.set_title("4) KING per-trade return % (fat right tail)"); ax.set_yscale("log"); ax.grid(alpha=.2)
ax = fig.add_subplot(2, 3, 5); Rk = np.array([t["R"] for t in king]); W = 60; rp = []
for i in range(W, len(Rk)):
    w = Rk[i - W:i]; g = w[w > 0].sum(); b = -w[w < 0].sum(); rp.append(g / b if b > 0 else 3)
ax.plot(dK[W:], rp, color="#1d9e75"); ax.axhline(1, color="#e24b4a", ls="--", lw=1)
ax.set_title("5) KING rolling 60-trade PF (>1=profit)"); ax.grid(alpha=.2); ax.set_ylim(0, 4)
ax = fig.add_subplot(2, 3, 6)
for feat, c in [("downtrend", "#e24b4a"), ("range", "#caa53a"), ("uptrend", "#3b82f6")]:
    sub = dk[dk["feat"] == feat].sort_values("xt")
    ax.plot(pd.to_datetime(sub["xt"]), np.cumsum(sub["p"].values) * 100, label=feat, color=c)
ax.set_title("6) KING cumulative contribution by regime %"); ax.legend(fontsize=8); ax.grid(alpha=.2)
plt.tight_layout(); plt.savefig("king_36mo_deep.png", dpi=105, bbox_inches="tight"); print("saved king_36mo_deep.png")
