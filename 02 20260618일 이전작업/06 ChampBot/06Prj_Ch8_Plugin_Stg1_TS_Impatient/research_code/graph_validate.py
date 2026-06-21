# -*- coding: utf-8 -*-
import os
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
HERE = os.path.dirname(os.path.abspath(__file__))
d = pd.read_csv(os.path.join(HERE, "validate_costsweep.csv"))
cb = d['cost'].values * 10000
CB, CI = "#3b6fb0", "#c0504d"
# 거래당 평균 net R(bp) — validate_ab 출력값
ptr_base = [43.63, 33.63, 28.63, 17.63]; ptr_imp = [52.11, 42.11, 37.11, 26.11]

fig, ax = plt.subplots(2, 2, figsize=(14, 9))
fig.suptitle("Is the gap REAL? Cost-sensitivity stress test (k0.77 applied, $10k, 3Y)\n"
             "Impatient stays ABOVE Patient at EVERY cost — gap is real, not a fee/frequency artifact",
             fontsize=12, fontweight="bold")

ax[0,0].plot(cb, d['base_ret'], 'o-', color=CB, label="Patient")
ax[0,0].plot(cb, d['imp_ret'], 's-', color=CI, label="Impatient")
ax[0,0].set_yscale("log"); ax[0,0].set_xlabel("normal-exit cost (bp, round trip)")
ax[0,0].set_ylabel("3Y return % (log)"); ax[0,0].axvline(19, color="gray", ls=":", lw=1)
ax[0,0].text(19, ax[0,0].get_ylim()[0]*1.3, " realistic 19bp", fontsize=8, color="gray")
ax[0,0].set_title("Final return vs cost"); ax[0,0].legend(); ax[0,0].grid(alpha=.3, which="both")

ax[0,1].plot(cb, d['base_pf'], 'o-', color=CB, label="Patient")
ax[0,1].plot(cb, d['imp_pf'], 's-', color=CI, label="Impatient")
ax[0,1].axhline(1, color="gray", ls=":", lw=1); ax[0,1].axvline(19, color="gray", ls=":", lw=1)
ax[0,1].set_xlabel("cost (bp)"); ax[0,1].set_ylabel("Profit Factor")
ax[0,1].set_title("PF vs cost (Impatient higher at all costs)"); ax[0,1].legend(); ax[0,1].grid(alpha=.3)

ax[1,0].plot(cb, d['base_mdd'], 'o-', color=CB, label="Patient")
ax[1,0].plot(cb, d['imp_mdd'], 's-', color=CI, label="Impatient")
ax[1,0].axhline(-20, color="red", ls="--", lw=1, label="-20% line")
ax[1,0].axvline(19, color="gray", ls=":", lw=1)
ax[1,0].set_xlabel("cost (bp)"); ax[1,0].set_ylabel("MDD %")
ax[1,0].set_title("MDD vs cost (both breach -20% at realistic cost!)"); ax[1,0].legend(); ax[1,0].grid(alpha=.3)

ax[1,1].plot(cb, ptr_base, 'o-', color=CB, label="Patient")
ax[1,1].plot(cb, ptr_imp, 's-', color=CI, label="Impatient")
ax[1,1].axhline(0, color="k", lw=.6); ax[1,1].axvline(19, color="gray", ls=":", lw=1)
ax[1,1].set_xlabel("cost (bp)"); ax[1,1].set_ylabel("avg NET R per trade (bp)")
ax[1,1].set_title("Per-trade quality (frequency-independent)\nImpatient ~+8.5bp better EVERY trade"); ax[1,1].legend(); ax[1,1].grid(alpha=.3)

plt.tight_layout(rect=[0,0,1,0.94])
out = os.path.join(HERE, "validate_costsweep.png")
plt.savefig(out, dpi=110, bbox_inches="tight"); print("saved", out)
