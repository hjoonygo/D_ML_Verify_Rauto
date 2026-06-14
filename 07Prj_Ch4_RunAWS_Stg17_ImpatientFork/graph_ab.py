# -*- coding: utf-8 -*-
# [graph_ab.py] 3년 A/B 비교 그래프 (English labels=§5-5 폰트깨짐 방지). ledger_base/imp.csv 사용.
import os
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
lb = pd.read_csv(os.path.join(HERE, "ledger_base.csv"))
li = pd.read_csv(os.path.join(HERE, "ledger_imp.csv"))
for d in (lb, li):
    d['entry_t'] = pd.to_datetime(d['entry_t'])

CB, CI = "#3b6fb0", "#c0504d"   # base=blue, imp=red


def pf(s):
    g = s[s > 0].sum(); b = -s[s < 0].sum()
    return (g / b) if b > 0 else np.nan


def eqcurve(d):
    return d['entry_t'].values, d['bal'].values


fig, ax = plt.subplots(2, 3, figsize=(17, 9))
fig.suptitle("3Y A/B: Patient (baseline) vs Impatient (fork)  |  TS only, $10k start, lev22, identical pipeline\n"
             "(ABSOLUTE returns are illustrative — pipeline does NOT reconcile with confirmed §9; read RELATIVE only)",
             fontsize=12, fontweight="bold")

# 1) Equity curve (log)
t1, e1 = eqcurve(lb); t2, e2 = eqcurve(li)
ax[0,0].plot(t1, e1, color=CB, label=f"Patient  end ${e1[-1]:,.0f}")
ax[0,0].plot(t2, e2, color=CI, label=f"Impatient end ${e2[-1]:,.0f}")
ax[0,0].set_yscale("log"); ax[0,0].axhline(10000, color="gray", ls=":", lw=1)
ax[0,0].set_title("Equity curve (log, $10k start) — illustrative"); ax[0,0].legend(); ax[0,0].grid(alpha=.3)

# 2) Overall: total return %, PF, winrate, MDD
def mdd(e):
    e = np.asarray(e, float); pk = np.maximum.accumulate(e); return ((e-pk)/pk).min()*100
metrics = ["Return%", "PF", "WinRate", "MDD%"]
bv = [ (e1[-1]/10000-1)*100, pf(lb['p']), (lb['p']>0).mean()*100, mdd(e1) ]
iv = [ (e2[-1]/10000-1)*100, pf(li['p']), (li['p']>0).mean()*100, mdd(e2) ]
x = np.arange(len(metrics)); w=.38
# normalize for one axis: plot return on its own scale via twin? keep simple: 4 small bars w/ text
ax[0,1].bar(x-w/2, [bv[0]/100, bv[1], bv[2]/100, bv[3]/100], w, color=CB, label="Patient")
ax[0,1].bar(x+w/2, [iv[0]/100, iv[1], iv[2]/100, iv[3]/100], w, color=CI, label="Impatient")
for i,(b,iva) in enumerate(zip(bv,iv)):
    ax[0,1].text(i-w/2, max(b/100 if metrics[i]!='PF' else b, 0)+.02, f"{b:.1f}", ha="center", fontsize=8, color=CB)
    ax[0,1].text(i+w/2, max(iva/100 if metrics[i]!='PF' else iva,0)+.02, f"{iva:.1f}", ha="center", fontsize=8, color=CI)
ax[0,1].set_xticks(x); ax[0,1].set_xticklabels(metrics); ax[0,1].axhline(0,color="k",lw=.6)
ax[0,1].set_title("Overall (Return%/100, PF, WinRate/100, MDD%/100)"); ax[0,1].legend()

# 3) PF by year
yrs = sorted(set(lb['year']) | set(li['year']))
pb = [pf(lb[lb['year']==y]['p']) for y in yrs]; pi = [pf(li[li['year']==y]['p']) for y in yrs]
x=np.arange(len(yrs))
ax[0,2].bar(x-w/2, pb, w, color=CB, label="Patient"); ax[0,2].bar(x+w/2, pi, w, color=CI, label="Impatient")
ax[0,2].axhline(1, color="gray", ls=":", lw=1)
ax[0,2].set_xticks(x); ax[0,2].set_xticklabels(yrs); ax[0,2].set_title("Profit Factor by Year (>1 = profitable)"); ax[0,2].legend()

# 4) Return contribution by year (%)
def contrib(d, mask): s=d[mask]['p']; return ((1+s).prod()-1)*100 if len(s) else 0
cb=[contrib(lb, lb['year']==y) for y in yrs]; ci=[contrib(li, li['year']==y) for y in yrs]
ax[1,0].bar(x-w/2, cb, w, color=CB, label="Patient"); ax[1,0].bar(x+w/2, ci, w, color=CI, label="Impatient")
ax[1,0].axhline(0,color="k",lw=.6); ax[1,0].set_xticks(x); ax[1,0].set_xticklabels(yrs)
ax[1,0].set_title("Return contribution by Year (%)"); ax[1,0].legend()

# 5) by Regime: PF
regs = sorted(set(lb['feat'].dropna()) | set(li['feat'].dropna()))
pb=[pf(lb[lb['feat']==r]['p']) for r in regs]; pi=[pf(li[li['feat']==r]['p']) for r in regs]
x=np.arange(len(regs))
ax[1,1].bar(x-w/2, pb, w, color=CB, label="Patient"); ax[1,1].bar(x+w/2, pi, w, color=CI, label="Impatient")
ax[1,1].axhline(1, color="gray", ls=":", lw=1)
ax[1,1].set_xticks(x); ax[1,1].set_xticklabels(regs, rotation=15); ax[1,1].set_title("Profit Factor by Regime"); ax[1,1].legend()

# 6) Long/Short: winrate + PF + n
sides=[(1,"LONG"),(-1,"SHORT")]
labels=[f"{nm}" for _,nm in sides]
pbL=[pf(lb[lb['side']==s]['p']) for s,_ in sides]; piL=[pf(li[li['side']==s]['p']) for s,_ in sides]
x=np.arange(len(sides))
ax[1,2].bar(x-w/2, pbL, w, color=CB, label="Patient PF"); ax[1,2].bar(x+w/2, piL, w, color=CI, label="Impatient PF")
ax[1,2].axhline(1, color="gray", ls=":", lw=1)
for i,(s,_) in enumerate(sides):
    nb=len(lb[lb['side']==s]); ni=len(li[li['side']==s])
    ax[1,2].text(i-w/2, pbL[i]+.02, f"n{nb}", ha="center", fontsize=8, color=CB)
    ax[1,2].text(i+w/2, piL[i]+.02, f"n{ni}", ha="center", fontsize=8, color=CI)
ax[1,2].set_xticks(x); ax[1,2].set_xticklabels(labels); ax[1,2].set_title("Profit Factor by Side (Long/Short)"); ax[1,2].legend()

plt.tight_layout(rect=[0,0,1,0.95])
out = os.path.join(HERE, "bt3y_ab_compare.png")
plt.savefig(out, dpi=110, bbox_inches="tight")
print("saved", out)
