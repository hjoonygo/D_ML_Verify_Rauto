# -*- coding: utf-8 -*-
import os
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
HERE = os.path.dirname(os.path.abspath(__file__))

ts = pd.read_csv(os.path.join(HERE, "opt_tsalone.csv")); ts['t'] = pd.to_datetime(ts['t'])
de = pd.read_csv(os.path.join(HERE, "opt_default.csv")); de['t'] = pd.to_datetime(de['t'])
be = pd.read_csv(os.path.join(HERE, "opt_best.csv")); be['t'] = pd.to_datetime(be['t'])
allc = pd.read_csv(os.path.join(HERE, "opt_allcombos.csv"))

# 성장배수(per-dollar 비교): TS=bal/10k, 듀얼=port/20k
ts['mul'] = ts['bal'] / 10000.0
de['mul'] = de['port'] / 20000.0
be['mul'] = be['port'] / 20000.0

NAMES = ["1) Impatient-TS alone", "2) Dual default (k0.77/w0.5)", "3) Dual re-opt (k0.85/w0.0)"]
RET = [946, 524, 653]; MDD = [-20.8, -17.2, -17.9]; CAL = [46, 30, 37]
COL = ["#888888", "#3b6fb0", "#c0504d"]

fig, ax = plt.subplots(2, 2, figsize=(15, 10))
fig.suptitle("FINAL 3-WAY @ REALISTIC 14bp cost (limit/maker assumed): TS alone vs Dual(default) vs Dual(re-opt)\n"
             "3Y per-dollar | TS-alone BREACHES -20% at 14bp -> SW cushion REQUIRED | OOS(23-24->25-26) holds",
             fontsize=11, fontweight="bold")

# 1) 성장배수(log)
ax[0,0].plot(ts['t'], ts['mul'], color=COL[0], label=f"{NAMES[0]}  x{ts['mul'].iloc[-1]:.1f}")
ax[0,0].plot(de['t'], de['mul'], color=COL[1], label=f"{NAMES[1]}  x{de['mul'].iloc[-1]:.1f}")
ax[0,0].plot(be['t'], be['mul'], color=COL[2], label=f"{NAMES[2]}  x{be['mul'].iloc[-1]:.1f}")
ax[0,0].set_yscale("log"); ax[0,0].axhline(1, color="gray", ls=":", lw=1)
ax[0,0].set_title("Equity growth multiple (per dollar, log)"); ax[0,0].legend(); ax[0,0].grid(alpha=.3, which="both")

# 2) Return / MDD / Calmar
x = np.arange(3); w = .25
ax[0,1].bar(x - w, [r/100 for r in RET], w, color="#5b9bd5", label="Return (x100%)")
ax[0,1].bar(x, [abs(m)/10 for m in MDD], w, color="#c0504d", label="|MDD|/10 %")
ax[0,1].bar(x + w, [c/100 for c in CAL], w, color="#70ad47", label="Calmar/100")
for i in range(3):
    ax[0,1].text(i - w, RET[i]/100 + .3, f"+{RET[i]}%", ha="center", fontsize=8)
    ax[0,1].text(i, abs(MDD[i])/10 + .1, f"{MDD[i]}%", ha="center", fontsize=8, color="#c0504d")
    ax[0,1].text(i + w, CAL[i]/100 + .1, f"{CAL[i]}", ha="center", fontsize=8, color="#548235")
ax[0,1].set_xticks(x); ax[0,1].set_xticklabels(["TS\nalone", "Dual\ndefault", "Dual\nopt"]);
ax[0,1].set_title("Return / MDD / Calmar  (opt: best return & Calmar, but MDD at edge)"); ax[0,1].legend(fontsize=8)

# 3) 최적화 프론티어 산점도 (전 90조합)
ok = allc[allc['mdd'] >= -20]; bad = allc[allc['mdd'] < -20]
ax[1,0].scatter(bad['mdd'], bad['ret'], c="#cccccc", s=18, label="MDD<-20% (rejected)")
ax[1,0].scatter(ok['mdd'], ok['ret'], c="#9cc3e6", s=22, label="MDD>=-20% (allowed)")
ax[1,0].scatter([-17.2], [524], c="#3b6fb0", s=90, marker="D", label="Default", zorder=5)
ax[1,0].scatter([-17.9], [653], c="#c0504d", s=140, marker="*", label="Optimal (k0.85)", zorder=5)
ax[1,0].axvline(-20, color="red", ls="--", lw=1)
ax[1,0].set_xlabel("Combined MDD %"); ax[1,0].set_ylabel("3Y return % (on $20k)")
ax[1,0].set_title("Optimization frontier (90 combos) — optimal hugs the -20% edge"); ax[1,0].legend(fontsize=8)

# 4) 연도별 수익% (커브에서)
def yearly(df, col, base):
    s = df.set_index('t')[col]
    yr = s.resample('YE').last()
    out = {}; prev = base
    for ts_, v in yr.items():
        out[ts_.year] = (v/prev - 1)*100; prev = v
    return out
ya = yearly(ts, 'bal', 10000.0); yd = yearly(de, 'port', 20000.0); yb = yearly(be, 'port', 20000.0)
yrs = sorted(set(ya) | set(yd) | set(yb)); xq = np.arange(len(yrs))
ax[1,1].bar(xq - w, [ya.get(y,0) for y in yrs], w, color=COL[0], label="TS alone")
ax[1,1].bar(xq, [yd.get(y,0) for y in yrs], w, color=COL[1], label="Dual default")
ax[1,1].bar(xq + w, [yb.get(y,0) for y in yrs], w, color=COL[2], label="Dual opt")
ax[1,1].axhline(0, color="k", lw=.6); ax[1,1].set_xticks(xq); ax[1,1].set_xticklabels(yrs)
ax[1,1].set_title("Return % by Year (per dollar)"); ax[1,1].legend(fontsize=8)

plt.tight_layout(rect=[0, 0, 1, 0.93])
out = os.path.join(HERE, "final_3way.png")
plt.savefig(out, dpi=110, bbox_inches="tight"); print("saved", out)
print("yearly TS:", {k: round(v) for k,v in ya.items()})
print("yearly default:", {k: round(v) for k,v in yd.items()})
print("yearly opt:", {k: round(v) for k,v in yb.items()})
