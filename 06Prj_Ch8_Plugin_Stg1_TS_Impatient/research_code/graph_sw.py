# -*- coding: utf-8 -*-
import os
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
HERE = os.path.dirname(os.path.abspath(__file__))


def pf(s):
    s = np.asarray(s); g = s[s > 0].sum(); b = -s[s < 0].sum(); return (g / b) if b > 0 else np.nan


def load(n):
    d = pd.read_csv(os.path.join(HERE, f"sw_{n}.csv")); return d


P, I, M = load("patient"), load("impatient"), load("middle")
names = ["Patient", "Impatient", "Middle"]
dats = [P, I, M]
cols = ["#3b6fb0", "#c0504d", "#e0a33e"]

# 표준 지표
rets = []; mdds = []
for d in dats:
    eq = np.concatenate([[10000.0], d['bal'].values]); pk = np.maximum.accumulate(eq)
    mdds.append(((eq - pk) / pk).min() * 100); rets.append((eq[-1] / 10000 - 1) * 100)
pfs = [pf(d['p']) for d in dats]; ns = [len(d) for d in dats]

fig, ax = plt.subplots(2, 2, figsize=(14, 9))
fig.suptitle("SW (SidewayDCA) 3Y: Patient vs Impatient vs Middle  |  $10k, lev15, k0.77\n"
             "Opposite to TS — making the mean-reversion bot impatient HURTS its job (worse MDD, lower PF)",
             fontsize=12, fontweight="bold")

# 1) return & MDD
x = np.arange(3); w = .35
ax[0,0].bar(x - w/2, rets, w, color="#5b9bd5", label="Return %")
ax[0,0].bar(x + w/2, mdds, w, color="#c0504d", label="MDD %")
ax[0,0].axhline(-20, color="red", ls="--", lw=1, label="-20% line")
for i in range(3):
    ax[0,0].text(i - w/2, rets[i] + 5, f"{rets[i]:.0f}%", ha="center", fontsize=9)
    ax[0,0].text(i + w/2, mdds[i] - 3, f"{mdds[i]:.0f}%", ha="center", fontsize=9, color="#c0504d")
ax[0,0].set_xticks(x); ax[0,0].set_xticklabels(names); ax[0,0].set_title("Return vs MDD (all breach -20% standalone)"); ax[0,0].legend()

# 2) PF & trades
ax[0,1].bar(x - w/2, pfs, w, color="#70ad47", label="PF")
ax[0,1].axhline(1, color="gray", ls=":", lw=1)
ax2 = ax[0,1].twinx(); ax2.bar(x + w/2, ns, w, color="#7f7f7f", label="Trades")
for i in range(3):
    ax[0,1].text(i - w/2, pfs[i] + .03, f"{pfs[i]:.2f}", ha="center", fontsize=9, color="#548235")
    ax2.text(i + w/2, ns[i] + 5, f"{ns[i]}", ha="center", fontsize=9, color="#404040")
ax[0,1].set_xticks(x); ax[0,1].set_xticklabels(names); ax[0,1].set_ylabel("PF"); ax2.set_ylabel("Trades")
ax[0,1].set_title("PF (Patient best) & Trade count (Impatient most)")

# 3) PF by year
yrs = [2023, 2024, 2025, 2026]
for k, (d, nm, cc) in enumerate(zip(dats, names, cols)):
    pv = [pf(d[d['year'] == y]['p']) for y in yrs]
    ax[1,0].plot(yrs, pv, 'o-', color=cc, label=nm)
ax[1,0].axhline(1, color="gray", ls=":", lw=1)
ax[1,0].set_xticks(yrs); ax[1,0].set_title("SW Profit Factor by Year"); ax[1,0].legend(); ax[1,0].grid(alpha=.3)

# 4) Dual combo: combined MDD & return (hardcoded from run)
combos = ["TS-imp\nALONE", "+SW\nPatient", "+SW\nImpatient", "+SW\nMiddle"]
cmdd = [-16.8, -15.5, -16.6, -15.9]
# return normalized per-dollar: TS alone on $10k=+1766%; duals on $20k → show final $ instead
cbal = [186590, 204886, 234568, 202543]
xb = np.arange(4)
axb = ax[1,1]
b1 = axb.bar(xb, cmdd, 0.5, color=["#888", "#3b6fb0", "#c0504d", "#e0a33e"])
axb.axhline(-20, color="red", ls="--", lw=1, label="-20% line")
for i, m in enumerate(cmdd):
    axb.text(i, m - 0.6, f"{m}%", ha="center", fontsize=9)
axb.set_xticks(xb); axb.set_xticklabels(combos, fontsize=8); axb.set_ylabel("Combined MDD %")
axb.set_title("Dual MDD: SW cushion (Patient best -15.5%, Impatient ~none)"); axb.legend()

plt.tight_layout(rect=[0, 0, 1, 0.93])
out = os.path.join(HERE, "sw_compare.png")
plt.savefig(out, dpi=110, bbox_inches="tight"); print("saved", out)

# 콘솔 per-year 표
print("\nSW per-year PF / return contribution:")
for d, nm in zip(dats, names):
    cells = " ".join(f"{y}:PF{pf(d[d['year']==y]['p']):.2f}/{((1+d[d['year']==y]['p']).prod()-1)*100:+.0f}%" for y in yrs)
    print(f"  {nm:>9}: {cells}")
