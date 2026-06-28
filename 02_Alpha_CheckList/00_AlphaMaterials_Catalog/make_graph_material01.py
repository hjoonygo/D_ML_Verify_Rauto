# -*- coding: utf-8 -*-
import os, numpy as np
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
OUT=r"D:\ML\RfRauto\02_Alpha_CheckList\00_AlphaMaterials_Catalog\graphs\Material01_OB_OI_Liquidity_TestResult.png"
# --- OB size (measured 2026-05-23, 13912 pts) ---
lab_ob=["Res top","Res mean","Sup top","Sup mean"]
ob5=[21.6,11.4,0.6,11.9]; ob60=[94.8,52.2,6.7,57.1]
# --- OI spike forward (measured 2026-06) ---
ks=["1h","3h","6h","12h","24h","48h"]
pos_d=[-0.001,-0.014,0.017,0.029,-0.052,-0.005]; pos_p=[0.96,0.61,0.68,0.59,0.48,0.96]
pos_vol=[1.18,1.14,1.16,1.10,1.08,1.03]; neg_vol=[1.35,1.20,1.12,1.03,1.00,1.01]
yr=["2023","2024","2025","2026"]; yr_ret=[0.142,0.100,0.031,0.137]; yr_up=[50,49,52,56]
fig,ax=plt.subplots(2,3,figsize=(17,9.5))
x=np.arange(4); w=0.38
ax[0,0].bar(x-w/2,ob5,w,label="5m TF",color="steelblue"); ax[0,0].bar(x+w/2,ob60,w,label="60m TF",color="indianred")
ax[0,0].set_xticks(x); ax[0,0].set_xticklabels(lab_ob,fontsize=8); ax[0,0].set_ylabel("distance (bp)")
ax[0,0].set_title("(1) Order Block size = TOO SMALL\nSup top 0.6bp ~ coin-flip distance, RR~0.01"); ax[0,0].legend()
ax[0,1].bar(ks,[v for v in pos_d],color=["seagreen" if v>0 else "crimson" for v in pos_d])
for i,p in enumerate(pos_p): ax[0,1].text(i,pos_d[i],f"p{p:.2f}",ha="center",fontsize=7)
ax[0,1].axhline(0,c="k",lw=.6); ax[0,1].set_ylabel("dMean vs baseline (%)")
ax[0,1].set_title("(2) DIRECTION: no edge\nall p>0.1 = not predictive (sugar only)")
ax[0,2].plot(ks,pos_vol,"o-",label="pos spike",color="darkorange"); ax[0,2].plot(ks,neg_vol,"s-",label="neg spike",color="purple")
ax[0,2].axhline(1.0,c="k",ls=":"); ax[0,2].set_ylabel("vol ratio (event/base)")
ax[0,2].set_title("(3) VOLATILITY: spike > 1 = USEFUL\nOI spike marks high-vol (whipsaw) zone"); ax[0,2].legend()
ax[1,0].bar(["up-trend\nentry","down-trend\nentry"],[0.128,0.036],color="teal"); ax[1,0].axhline(0.059,c="gray",ls="--",label="baseline 12h")
ax[1,0].set_ylabel("12h fwd ret (%)"); ax[1,0].set_title("(4) Trend-conditional 12h\n(weak persistence, ~50% up)"); ax[1,0].legend(fontsize=7)
ax[1,1].bar(yr,yr_ret,color="cadetblue"); ax[1,1].set_ylabel("12h fwd ret (%)")
for i,u in enumerate(yr_up): ax[1,1].text(i,yr_ret[i],f"{u}%up",ha="center",fontsize=7)
ax[1,1].set_title("(5) Yearly pos-spike 12h\nsmall + but ~50% up = not direction")
ax[1,2].axis("off")
ax[1,2].text(0.0,0.95,"VERDICT (ingredient view)",fontsize=12,weight="bold")
txt=("Source: YouTube M6jNWDJUlmY (Gemini->ChatGPT)\n"
     "Hypothesis: OI liquidity in/out of OB -> price direction\n\n"
     "[Standalone test]\n"
     " - OB distance ~0 (RR 0.01) -> cannot be SL guard\n"
     " - Direction dMean p>0.1, ~50% up -> NO direction edge\n\n"
     "[But as INGREDIENT]\n"
     " - vol ratio >1 (neg 1h=1.35) -> marks HIGH-VOL\n"
     "   = entry-just-after whipsaw zone\n\n"
     "ROLE: not a direction signal,\n"
     "      but a WHIPSAW / volatility FILTER\n"
     "BLEND: TS entry + 'if OI spike -> widen SL / delay'\n\n"
     "=> Do NOT discard. Keep as ingredient.")
ax[1,2].text(0.0,0.86,txt,fontsize=8.5,va="top",family="monospace")
plt.suptitle("Alpha Material #01: OB + OI Liquidity  (test result, honest)",fontsize=13)
plt.tight_layout(); plt.savefig(OUT,dpi=110); print("[graph]",OUT)
try: os.startfile(OUT)
except Exception as e: print("open fail",e)
