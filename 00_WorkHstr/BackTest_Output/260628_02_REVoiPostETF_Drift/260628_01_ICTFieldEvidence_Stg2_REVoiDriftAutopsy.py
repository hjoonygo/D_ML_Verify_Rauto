# -*- coding: utf-8 -*-
"""
260628_01_ICTFieldEvidence_Stg2 : REVoi post-ETF DRIFT AUTOPSY
Question: is REVoi's post-ETF PF collapse (1.82->1.04) STRUCTURAL DEATH or RECOVERABLE?
Read-only on verified ledgers (no bot re-impl). Uses ledger_rev_opt_1m (267 COMBO, has reason/side/oi_z)
+ ledger_rev (515 base) for robustness. ETF break = 2024-01-11.
Outputs: yearly/quarterly/long-short decomposition, rolling PF curve, oi_z rolling IC (feature drift),
win/payoff decomposition, Chow-style break test, by-reason split, sized-holdout reconciliation note.
Graph labels English (font-safe).
"""
import os, numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from scipy import stats

OUT = r"D:\ML\RfRauto\00_WorkHstr\BackTest_Output\260628_02_REVoiPostETF_Drift"
LED = r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp"
BASE = "260628_02_REVoiPostETF_Drift"; ETF = pd.Timestamp("2024-01-11")
os.makedirs(OUT, exist_ok=True)
lines=[]
def log(s=""):
    print(s); lines.append(str(s))

def pf(x):
    pos = x[x>0].sum(); neg = abs(x[x<0].sum())
    return pos/neg if neg>0 else np.nan

rev = pd.read_csv(LED+r"\ledger_rev_opt_1m.csv", parse_dates=["et","xt"]).sort_values("et").reset_index(drop=True)
base = pd.read_csv(LED+r"\ledger_rev.csv", parse_dates=["et"]).sort_values("et").reset_index(drop=True)
base = base.rename(columns={"ret":"R"})

log("="*80); log("REVoi post-ETF DRIFT AUTOPSY  [260628_01 Stg2]  ETF=2024-01-11"); log("="*80)
log(f"COMBO ledger n={len(rev)}  base ledger n={len(base)}")

# ---------- 1. yearly / quarterly / long-short decomposition ----------
def decomp(df, label):
    log(f"\n--- {label} : yearly ---")
    df = df.copy(); df["yr"]=df["et"].dt.year
    g = df.groupby("yr")["R"].agg(n="count", sumR="sum", meanR="mean",
                                  win=lambda x:(x>0).mean()*100, PF=pf)
    log(g.round({"sumR":3,"meanR":5,"win":1,"PF":2}).to_string())
    return g

gC = decomp(rev, "COMBO(267)")
gB = decomp(base, "base(515)")
gC.to_csv(OUT+f"\\{BASE}_yearly_COMBO.csv"); gB.to_csv(OUT+f"\\{BASE}_yearly_base.csv")

# quarterly + long/short (COMBO has side)
rev["q"]=rev["et"].dt.to_period("Q").astype(str)
ql=[]
for q,gq in rev.groupby("q"):
    L=gq[gq["side"]==1]["R"]; S=gq[gq["side"]==-1]["R"]
    ql.append({"Q":q,"n":len(gq),"sumR":gq["R"].sum(),"PF":pf(gq["R"]),
               "long_n":len(L),"long_sumR":L.sum(),"short_n":len(S),"short_sumR":S.sum()})
qdf=pd.DataFrame(ql); qdf.to_csv(OUT+f"\\{BASE}_quarterly_longshort.csv",index=False)
log("\n--- COMBO quarterly (long/short) ---"); log(qdf.round(3).to_string(index=False))

# ---------- 2. pre/post ETF win-rate vs payoff decomposition ----------
log("\n"+"-"*80); log("[2] entry-decay vs exit/vol-change : win% & payoff pre/post"); log("-"*80)
def wp(df,label):
    for nm,seg in [("pre",df[df["et"]<ETF]),("post",df[df["et"]>=ETF])]:
        x=seg["R"]; w=x[x>0]; l=x[x<0]
        aw=w.mean() if len(w) else np.nan; al=l.mean() if len(l) else np.nan
        payoff=abs(aw/al) if al and not np.isnan(al) else np.nan
        log(f"  {label} {nm}: n={len(x)} win%={(x>0).mean()*100:.1f} avg_win={aw:+.5f} avg_loss={al:+.5f} payoff={payoff:.2f} PF={pf(x):.2f} meanR={x.mean():+.5f}")
wp(rev,"COMBO"); wp(base,"base")

# ---------- 3. Chow-style structural break test (Welch t + Mann-Whitney) ----------
log("\n"+"-"*80); log("[3] structural break test @ ETF (per-trade R pre vs post)"); log("-"*80)
for df,label in [(rev,"COMBO"),(base,"base")]:
    a=df[df["et"]<ETF]["R"]; b=df[df["et"]>=ETF]["R"]
    t,p=stats.ttest_ind(a,b,equal_var=False)
    u,pu=stats.mannwhitneyu(a,b,alternative="two-sided")
    log(f"  {label}: meanR pre={a.mean():+.5f} post={b.mean():+.5f}  Welch t={t:+.2f} p={p:.3f}  MW p={pu:.3f}  (p<0.05 => significant drop)")

# ---------- 4. rolling PF / meanR curve (the decay trajectory) ----------
W=40
rev["roll_meanR"]=rev["R"].rolling(W).mean()
rev["roll_PF"]=rev["R"].rolling(W).apply(pf,raw=False)
rev["cumR"]=rev["R"].cumsum()

# ---------- 5. oi_z gating-feature rolling IC (feature drift) ----------
log("\n"+"-"*80); log("[5] gate feature oi_z : rolling IC vs R (does the gate decay?)"); log("-"*80)
icpre=stats.spearmanr(rev[rev["et"]<ETF]["oi_z"], rev[rev["et"]<ETF]["R"]).correlation
icpost=stats.spearmanr(rev[rev["et"]>=ETF]["oi_z"], rev[rev["et"]>=ETF]["R"]).correlation
log(f"  oi_z~R Spearman IC: pre={icpre:+.3f}  post={icpost:+.3f}")
rev["roll_ic_oiz"]=rev["R"].rolling(W).corr(rev["oi_z"])   # pearson rolling (proxy)
# also atr_pct IC
log(f"  atr_pct~R Spearman IC: pre={stats.spearmanr(rev[rev['et']<ETF]['atr_pct'],rev[rev['et']<ETF]['R']).correlation:+.3f}  post={stats.spearmanr(rev[rev['et']>=ETF]['atr_pct'],rev[rev['et']>=ETF]['R']).correlation:+.3f}")

# ---------- 6. by-reason decomposition pre/post ----------
log("\n"+"-"*80); log("[6] by exit-reason pre/post"); log("-"*80)
for nm,seg in [("pre",rev[rev["et"]<ETF]),("post",rev[rev["et"]>=ETF])]:
    r=seg.groupby("reason")["R"].agg(n="count",sumR="sum",meanR="mean",PF=pf)
    log(f"  [{nm}]\n"+r.round({"sumR":3,"meanR":5,"PF":2}).to_string())

# ---------- 7. sized held-out reconciliation note ----------
log("\n"+"-"*80); log("[7] reconciliation: PF 1.04 post-ETF vs sized held-out +2121%"); log("-"*80)
post=rev[rev["et"]>=ETF]["R"]
log(f"  post-ETF unsized: sumR={post.sum():+.3f} meanR={post.mean():+.5f} PF={pf(post):.2f} n={len(post)}")
log("  => sized held-out +2121%(lev3) coexists with thin unsized edge ONLY via leverage compounding.")
log("  => RISK FLAG: thin edge (PF~1.04) x leverage = fragile. Champion sizing must use post-ETF regime, not full-sample.")

# ---------- charts ----------
plt.rcParams.update({"figure.dpi":110,"font.size":9})
# A: rolling PF + meanR with ETF line
fig,(a1,a2)=plt.subplots(2,1,figsize=(12,6),sharex=True)
a1.plot(rev["et"],rev["roll_PF"],color="#3066BE"); a1.axhline(1,color="k",lw=0.6,ls="--")
a1.axvline(ETF,color="#C1121F",lw=1.5,ls=":"); a1.text(ETF,a1.get_ylim()[1]*0.9," ETF 2024-01-11",color="#C1121F",fontsize=8)
a1.set_title(f"REVoi rolling PF (window={W} trades) - the decay trajectory"); a1.set_ylabel("PF")
a2.plot(rev["et"],rev["roll_meanR"]*100,color="#2E933C"); a2.axhline(0,color="k",lw=0.6)
a2.axvline(ETF,color="#C1121F",lw=1.5,ls=":"); a2.set_ylabel("rolling mean R %"); a2.set_title("rolling mean R")
plt.tight_layout(); plt.savefig(OUT+f"\\{BASE}_chartA_rolling_decay.png"); plt.close()

# B: yearly PF bar (COMBO + base)
fig,ax=plt.subplots(figsize=(8,4))
yrs=sorted(set(gC.index)|set(gB.index)); x=np.arange(len(yrs)); w=0.38
ax.bar(x-w/2,[gC["PF"].get(y,np.nan) for y in yrs],w,label="COMBO(267)",color="#3066BE")
ax.bar(x+w/2,[gB["PF"].get(y,np.nan) for y in yrs],w,label="base(515)",color="#8D99AE")
ax.axhline(1,color="k",lw=0.6,ls="--"); ax.set_xticks(x); ax.set_xticklabels(yrs)
ax.set_title("REVoi PF by year (drift)"); ax.set_ylabel("PF"); ax.legend()
plt.tight_layout(); plt.savefig(OUT+f"\\{BASE}_chartB_yearly_PF.png"); plt.close()

# C: cumR with ETF + oi_z rolling IC
fig,(c1,c2)=plt.subplots(2,1,figsize=(12,6),sharex=True)
c1.plot(rev["et"],rev["cumR"],color="#3066BE"); c1.axvline(ETF,color="#C1121F",lw=1.5,ls=":")
c1.set_title("REVoi cumulative R (slope = edge; ETF break marked)"); c1.set_ylabel("cum R")
c2.plot(rev["et"],rev["roll_ic_oiz"],color="#E07A00"); c2.axhline(0,color="k",lw=0.6)
c2.axvline(ETF,color="#C1121F",lw=1.5,ls=":"); c2.set_title(f"oi_z gate rolling IC vs R (window={W}) - feature drift"); c2.set_ylabel("rolling corr")
plt.tight_layout(); plt.savefig(OUT+f"\\{BASE}_chartC_cumR_oiz_ic.png"); plt.close()

with open(OUT+f"\\{BASE}_analysis.txt","w",encoding="utf-8") as f:
    f.write("\n".join(lines))
log("\n[OK] outputs -> "+OUT)
