# -*- coding: utf-8 -*-
"""
260628_01_ICTFieldEvidence_Stg3 : DENSE TREND BOT (Donchian breakout + chandelier ATR trail)
NEW STANDING RULE (captain 2026-06-28): alpha return checks use POST-ETF data ONLY (2024-01-01+).
- Build dense trend bot on 8H bars (aligns with REVoi grid). Sweep N={10,20,30,40} transparently (no return-max cherry-pick).
- Evaluate POST-2024 only. Compare to existing sparse TrendStack. Measure correlation to REVoi(post-2024) + combined portfolio.
- gross R + net R (8bp round-trip, CLAUDE.md 7 ver-B). Graph labels English.
"""
import os, numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

OUT = r"D:\ML\RfRauto\00_WorkHstr\BackTest_Output\260628_03_DenseTrendBot"
LED = r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp"
MERGED = r"D:\ML\RfRauto\08_BTC_Data\derived\Merged_Data.csv"
BASE = "260628_03_DenseTrendBot"; START = pd.Timestamp("2024-01-01"); COST_BP = 8.0
os.makedirs(OUT, exist_ok=True)
lines=[]
def log(s=""): print(s); lines.append(str(s))
def pf(x):
    x=np.asarray(x); pos=x[x>0].sum(); neg=abs(x[x<0].sum()); return pos/neg if neg>0 else np.nan

# ---------- 8H bars ----------
m = pd.read_csv(MERGED, usecols=["timestamp","open","high","low","close","volume"], parse_dates=["timestamp"])
m["timestamp"]=m["timestamp"].dt.tz_localize(None); m=m.set_index("timestamp").sort_index()
bar = pd.DataFrame({"open":m["open"].resample("8h").first(),"high":m["high"].resample("8h").max(),
                    "low":m["low"].resample("8h").min(),"close":m["close"].resample("8h").last()}).dropna()
log("="*80); log("DENSE TREND BOT  [260628_01 Stg3]  POST-ETF ONLY (2024-01-01+)"); log("="*80)
log(f"8H bars: {len(bar)}  range {bar.index.min()} ~ {bar.index.max()}")

def wilder_atr(b,n=14):
    h,l,c=b["high"],b["low"],b["close"]
    tr=pd.concat([(h-l),(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    return tr.ewm(alpha=1/n,adjust=False).mean()

def donchian_trend(b, N=20, atr_n=14, k=3.0, cost_bp=0.0):
    up=b["high"].rolling(N).max().shift(1).values
    dn=b["low"].rolling(N).min().shift(1).values
    atr=wilder_atr(b,atr_n).values
    c=b["close"].values; h=b["high"].values; l=b["low"].values; idx=b.index
    pos=0; entry=0.0; et=None; ext=None; tr=[]
    for i in range(len(b)):
        if np.isnan(up[i]) or np.isnan(atr[i]): continue
        p=c[i]; a=atr[i]
        if pos==0:
            if p>up[i]: pos=1; entry=p; et=idx[i]; ext=h[i]
            elif p<dn[i]: pos=-1; entry=p; et=idx[i]; ext=l[i]
        elif pos==1:
            ext=max(ext,h[i]); stop=ext-k*a
            if p<stop or p<dn[i]:
                R=(p/entry-1)-cost_bp/1e4*2; tr.append((et,idx[i],1,entry,p,R,"trail"))
                pos=0
                if p<dn[i]: pos=-1; entry=p; et=idx[i]; ext=l[i]
        elif pos==-1:
            ext=min(ext,l[i]); stop=ext+k*a
            if p>stop or p>up[i]:
                R=-(p/entry-1)-cost_bp/1e4*2; tr.append((et,idx[i],-1,entry,p,R,"trail"))
                pos=0
                if p>up[i]: pos=1; entry=p; et=idx[i]; ext=h[i]
    if pos!=0:
        p=c[-1]; R=((p/entry-1) if pos==1 else -(p/entry-1))-cost_bp/1e4*2
        tr.append((et,idx[-1],pos,entry,p,R,"eod"))
    return pd.DataFrame(tr,columns=["et","xt","side","entry","exit","R","reason"])

# ---------- sweep N (transparent, post-2024 eval) ----------
log("\n--- N sweep (post-2024 eval, gross & net 8bp) ---")
sweep=[]
ledgers={}
for N in [10,20,30,40]:
    g=donchian_trend(bar,N=N,cost_bp=0.0)        # gross
    n8=donchian_trend(bar,N=N,cost_bp=COST_BP)   # net
    gp=g[g["et"]>=START]; np8=n8[n8["et"]>=START]
    ledgers[N]=np8
    sweep.append({"N":N,"trades_post":len(gp),"gross_sumR":gp["R"].sum(),"gross_PF":pf(gp["R"]),
                  "net_sumR":np8["R"].sum(),"net_PF":pf(np8["R"]),"win%":(np8["R"]>0).mean()*100})
    log(f"  N={N:2d}: trades={len(gp):3d}  gross PF={pf(gp['R']):.2f} sumR={gp['R'].sum():+.3f} | net8bp PF={pf(np8['R']):.2f} sumR={np8['R'].sum():+.3f} win%={(np8['R']>0).mean()*100:.0f}")
pd.DataFrame(sweep).to_csv(OUT+f"\\{BASE}_N_sweep.csv",index=False)

# primary = classic Donchian-20 (a-priori, not return-max), net 8bp
N_PRIMARY=20
trend=ledgers[N_PRIMARY].copy()
trend.to_csv(OUT+f"\\{BASE}_trend_ledger_N20_post2024.csv",index=False)
log(f"\n[PRIMARY] Donchian-{N_PRIMARY} (a-priori classic, net 8bp), post-2024: trades={len(trend)} PF={pf(trend['R']):.2f} sumR={trend['R'].sum():+.3f} meanR={trend['R'].mean():+.5f} win%={(trend['R']>0).mean()*100:.0f}")

# ---------- load REVoi + sparse TS, restrict post-2024 ----------
rev=pd.read_csv(LED+r"\ledger_rev_opt_1m.csv",parse_dates=["et","xt"])
revp=rev[rev["et"]>=START].copy()
ts_old=pd.read_csv(LED+r"\ledger_ts_1m.csv",parse_dates=["et","xt"])
tsp=ts_old[ts_old["et"]>=START].copy()
log(f"\nPOST-2024 baselines: REVoi trades={len(revp)} PF={pf(revp['R']):.2f} sumR={revp['R'].sum():+.3f} | sparse-TS trades={len(tsp)} PF={pf(tsp['R']):.2f} sumR={tsp['R'].sum():+.3f}")

# ---------- correlation + combined portfolio (monthly, post-2024) ----------
def monthly(df,col="R"): return df.set_index("et")[col].resample("MS").sum()
M=pd.concat([monthly(revp).rename("REVoi"),monthly(trend).rename("DenseTrend"),monthly(tsp).rename("SparseTS")],axis=1).fillna(0.0)
M.index.name="month"; M.to_csv(OUT+f"\\{BASE}_monthly_post2024.csv")
log("\n--- POST-2024 correlation (monthly) ---")
log(f"  REVoi vs DenseTrend : Pearson={M['REVoi'].corr(M['DenseTrend']):+.3f}  Spearman={M['REVoi'].corr(M['DenseTrend'],method='spearman'):+.3f}  (n={len(M)} months)")
log(f"  REVoi vs SparseTS   : Pearson={M['REVoi'].corr(M['SparseTS']):+.3f}")
# complementarity
loss=M[M["REVoi"]<0]
log(f"  months REVoi<0 = {len(loss)} : DenseTrend mean={loss['DenseTrend'].mean():+.4f} (>0 in {int((loss['DenseTrend']>0).sum())}/{len(loss)})")

def eqc(s): return (1+s).cumprod()
M["Combo50"]=0.5*M["REVoi"]+0.5*M["DenseTrend"]
for c in ["REVoi","DenseTrend","Combo50"]:
    eq=eqc(M[c]); dd=eq/eq.cummax()-1
    log(f"  {c:11s}: sumR={M[c].sum():+.3f}  finalEq={eq.iloc[-1]:.3f}x  maxDD(monthly,unsized)={dd.min()*100:+.1f}%")
ddR=(eqc(M["REVoi"])/eqc(M["REVoi"]).cummax()-1); ddT=(eqc(M["DenseTrend"])/eqc(M["DenseTrend"]).cummax()-1)
log(f"  drawdown-series corr REVoi vs DenseTrend = {ddR.corr(ddT):+.3f}")

# ---------- quarterly long/short of dense trend (post-2024, §19) ----------
trend["q"]=trend["et"].dt.to_period("Q").astype(str)
ql=[]
for q,gq in trend.groupby("q"):
    L=gq[gq["side"]==1]["R"]; S=gq[gq["side"]==-1]["R"]
    ql.append({"Q":q,"n":len(gq),"sumR":gq["R"].sum(),"PF":pf(gq["R"]),"long_sumR":L.sum(),"short_sumR":S.sum()})
qdf=pd.DataFrame(ql); qdf.to_csv(OUT+f"\\{BASE}_trend_quarterly_longshort.csv",index=False)
log("\n--- DenseTrend quarterly long/short (post-2024) ---"); log(qdf.round(3).to_string(index=False))

# ---------- charts ----------
plt.rcParams.update({"figure.dpi":110,"font.size":9})
# 1 monthly bars 3-way
fig,ax=plt.subplots(figsize=(12,4)); x=np.arange(len(M)); w=0.4
ax.bar(x-w/2,M["REVoi"]*100,w,label="REVoi (mean-rev)",color="#3066BE")
ax.bar(x+w/2,M["DenseTrend"]*100,w,label="DenseTrend (Donchian-20)",color="#E07A00")
ax.axhline(0,color="k",lw=0.6); ax.set_title("POST-2024 monthly unsized R% : REVoi vs DenseTrend"); ax.set_ylabel("monthly sum R %"); ax.legend()
st=max(1,len(M)//12); ax.set_xticks(x[::st]); ax.set_xticklabels([d.strftime("%y-%m") for d in M.index[::st]],rotation=45,fontsize=7)
plt.tight_layout(); plt.savefig(OUT+f"\\{BASE}_chart1_monthly_post2024.png"); plt.close()
# 2 equity + dd
fig,(a1,a2)=plt.subplots(2,1,figsize=(12,6),sharex=True,gridspec_kw={"height_ratios":[2,1]})
for c,col in [("REVoi","#3066BE"),("DenseTrend","#E07A00"),("Combo50","#2E933C")]:
    a1.plot(M.index,eqc(M[c]).values,label=c,color=col)
a1.set_title("POST-2024 compounded equity (unsized monthly R - preview) & drawdown"); a1.legend(); a1.set_ylabel("equity x")
a2.fill_between(M.index,(eqc(M["REVoi"])/eqc(M["REVoi"]).cummax()-1).values*100,color="#3066BE",alpha=0.5,label="REVoi DD")
a2.fill_between(M.index,(eqc(M["Combo50"])/eqc(M["Combo50"]).cummax()-1).values*100,color="#2E933C",alpha=0.4,label="Combo DD")
a2.set_ylabel("drawdown %"); a2.legend(); plt.tight_layout(); plt.savefig(OUT+f"\\{BASE}_chart2_equity_dd_post2024.png"); plt.close()
# 3 N sweep
sw=pd.DataFrame(sweep); fig,ax=plt.subplots(figsize=(8,4))
ax.plot(sw["N"],sw["gross_PF"],"o-",label="gross PF",color="#3066BE")
ax.plot(sw["N"],sw["net_PF"],"s--",label="net 8bp PF",color="#C1121F"); ax.axhline(1,color="k",lw=0.6,ls=":")
ax2=ax.twinx(); ax2.bar(sw["N"],sw["trades_post"],width=3,alpha=0.2,color="gray"); ax2.set_ylabel("trades (post-2024)")
ax.set_xlabel("Donchian N"); ax.set_ylabel("PF"); ax.set_title("Trend bot N-sweep (post-2024): PF & trade count"); ax.legend(loc="upper left")
plt.tight_layout(); plt.savefig(OUT+f"\\{BASE}_chart3_Nsweep.png"); plt.close()

with open(OUT+f"\\{BASE}_analysis.txt","w",encoding="utf-8") as f: f.write("\n".join(lines))
log("\n[OK] outputs -> "+OUT)
