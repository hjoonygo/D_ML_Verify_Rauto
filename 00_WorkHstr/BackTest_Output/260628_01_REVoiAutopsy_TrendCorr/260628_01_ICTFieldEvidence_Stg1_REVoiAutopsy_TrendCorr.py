# -*- coding: utf-8 -*-
"""
260628_01_ICTFieldEvidence_Stg1 : REVoi Failure Autopsy + TrendStack Correlation + H1(post-ETF trend persistence)
- Read-only analysis on verified ledgers + Merged_Data.csv (NO bot re-implementation; uses existing verified ledgers).
- Phase 1a: monthly/quarterly return-stream correlation REVoi vs TrendStack (+ complementarity, drawdown timing, combined portfolio preview = experiment F seed)
- Phase 1b: REVoi failure autopsy - cluster worst trades by ADX / prior-24h trend / realized vol / session (features known-at-entry, shifted, no lookahead)
- Phase 1c: H1 test - return autocorrelation & TSMOM PF pre vs post 2024-01-11 ETF; REVoi & TS performance pre/post
Outputs: CSVs + PNGs + summary txt in this folder. Graph labels English (font-safe, CLAUDE.md 5.5).
"""
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = r"D:\ML\RfRauto\00_WorkHstr\BackTest_Output\260628_01_REVoiAutopsy_TrendCorr"
LED = r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp"
MERGED = r"D:\ML\RfRauto\08_BTC_Data\derived\Merged_Data.csv"
BASE = "260628_01_REVoiAutopsy_TrendCorr"
ETF = pd.Timestamp("2024-01-11")
os.makedirs(OUT, exist_ok=True)
lines = []
def log(s=""):
    print(s)
    lines.append(str(s))

# ---------- load ledgers ----------
rev = pd.read_csv(LED + r"\ledger_rev_opt_1m.csv", parse_dates=["et", "xt"])   # 267 COMBO REVoi (has regime feats)
ts  = pd.read_csv(LED + r"\ledger_ts_1m.csv",  parse_dates=["et", "xt"])       # 45 TrendStack
rev_base = pd.read_csv(LED + r"\ledger_rev.csv", parse_dates=["et"])           # 515 base REVoi (et,ret) robustness
ts_base  = pd.read_csv(LED + r"\ledger_ts.csv",  parse_dates=["et"])           # 34 base TS

log("="*78)
log("Phase 1 : REVoi Autopsy + TrendStack Correlation + H1(post-ETF)  [260628_01]")
log("="*78)
log(f"REVoi(opt/COMBO) trades={len(rev)}  Rsum={rev['R'].sum():.4f} win%={(rev['R']>0).mean()*100:.1f} meanR={rev['R'].mean():.5f}")
log(f"TrendStack       trades={len(ts)}  Rsum={ts['R'].sum():.4f} win%={(ts['R']>0).mean()*100:.1f} meanR={ts['R'].mean():.5f}")
log(f"(robustness) REVoi_base={len(rev_base)} TS_base={len(ts_base)}")

# =====================================================================
# Phase 1a : correlation of return streams (monthly / quarterly)
# =====================================================================
log("\n" + "-"*78)
log("[Phase 1a] REVoi vs TrendStack  return-stream correlation")
log("-"*78)

def monthly(df, col):
    s = df.set_index("et")[col].resample("MS").sum()
    return s

mr = monthly(rev, "R").rename("REVoi")
mt = monthly(ts,  "R").rename("TS")
M = pd.concat([mr, mt], axis=1).fillna(0.0)
M.index.name = "month"
M.to_csv(OUT + f"\\{BASE}_monthly_returns.csv")

# correlations
pear_all = M["REVoi"].corr(M["TS"])
spear_all = M["REVoi"].corr(M["TS"], method="spearman")
both = M[(M["REVoi"]!=0) & (M["TS"]!=0)]
pear_both = both["REVoi"].corr(both["TS"]) if len(both)>2 else np.nan
# quarterly
Q = M.resample("QS").sum()
pear_q = Q["REVoi"].corr(Q["TS"])
log(f"monthly  Pearson r = {pear_all:+.3f}   Spearman = {spear_all:+.3f}   (n={len(M)} months)")
log(f"monthly  Pearson r (both-traded months only, n={len(both)}) = {pear_both:+.3f}")
log(f"quarterly Pearson r = {pear_q:+.3f}   (n={len(Q)} quarters)")

# complementarity: when REVoi loses, what does TS do?
rev_loss_m = M[M["REVoi"] < 0]
log(f"\nComplementarity (Kaminski test): months REVoi<0 = {len(rev_loss_m)}")
log(f"  in those months: TS mean R = {rev_loss_m['TS'].mean():+.4f} ; TS>0 in {int((rev_loss_m['TS']>0).sum())}/{len(rev_loss_m)} months")
rev_win_m = M[M["REVoi"] > 0]
log(f"  months REVoi>0 = {len(rev_win_m)} : TS mean R = {rev_win_m['TS'].mean():+.4f}")

# combined portfolio preview (equal weight per trade-return stream)
M["Combo"] = M["REVoi"] + M["TS"]
def eq_curve(s):  # compounded equity from monthly summed unsized R (rough preview)
    return (1+s).cumprod()
for c in ["REVoi","TS","Combo"]:
    eq = eq_curve(M[c])
    dd = eq/eq.cummax() - 1
    log(f"  {c:6s}: sumR={M[c].sum():+.3f}  maxDD(monthly,unsized)={dd.min()*100:+.1f}%")

# drawdown timing correlation
ddR = (eq_curve(M["REVoi"]) / eq_curve(M["REVoi"]).cummax() - 1)
ddT = (eq_curve(M["TS"]) / eq_curve(M["TS"]).cummax() - 1)
log(f"  drawdown-series correlation REVoi vs TS = {ddR.corr(ddT):+.3f}  (low/neg = diversify)")

# =====================================================================
# Phase 1b : REVoi failure autopsy (regime features known-at-entry)
# =====================================================================
log("\n" + "-"*78)
log("[Phase 1b] REVoi Failure Autopsy : where does the mean-reverter die?")
log("-"*78)

# load merged minimal, build 8H bars (REVoi entries at 0/8/16 UTC = 8H grid)
m = pd.read_csv(MERGED, usecols=["timestamp","open","high","low","close","volume"], parse_dates=["timestamp"])
m["timestamp"] = m["timestamp"].dt.tz_localize(None)   # UTC -> naive to match ledger et
m = m.set_index("timestamp").sort_index()
o = m["open"].resample("8h").first()
h = m["high"].resample("8h").max()
l = m["low"].resample("8h").min()
c = m["close"].resample("8h").last()
v = m["volume"].resample("8h").sum()
bar = pd.DataFrame({"open":o,"high":h,"low":l,"close":c,"volume":v}).dropna()

def adx(df, n=14):
    hi,lo,cl = df["high"],df["low"],df["close"]
    up = hi.diff(); dn = -lo.diff()
    pdm = ((up>dn)&(up>0))*up
    mdm = ((dn>up)&(dn>0))*dn
    tr = pd.concat([(hi-lo),(hi-cl.shift()).abs(),(lo-cl.shift()).abs()],axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/n,adjust=False).mean()
    pdi = 100*(pdm.ewm(alpha=1/n,adjust=False).mean()/atr)
    mdi = 100*(mdm.ewm(alpha=1/n,adjust=False).mean()/atr)
    dx = 100*(pdi-mdi).abs()/(pdi+mdi).replace(0,np.nan)
    return dx.ewm(alpha=1/n,adjust=False).mean()

feat = pd.DataFrame(index=bar.index)
feat["adx"] = adx(bar,14)
feat["ret_24h"] = bar["close"].pct_change(3)        # trend over 24h ending at bar close
feat["realvol"] = bar["close"].pct_change().rolling(21).std()  # 7d realized vol (8H rets)
# stamp features at bar CLOSE time (=bar_start+8h) so merge_asof picks the bar completed AT entry (no lookahead)
feat.index = feat.index + pd.Timedelta("8h")

rev_s = rev.sort_values("et").reset_index(drop=True)
A = pd.merge_asof(rev_s, feat, left_on="et", right_index=True, direction="backward")
A["abs_trend"] = A["ret_24h"].abs()
A["session"] = A["et"].dt.hour.map({0:"Asia",8:"EU",16:"US"}).fillna("other")
# fading-trend flag: side opposite to prior 24h trend sign
A["fading"] = ((A["side"]==1)&(A["ret_24h"]<0)) | ((A["side"]==-1)&(A["ret_24h"]>0))
A.to_csv(OUT + f"\\{BASE}_revoi_trades_with_regime.csv", index=False)

# worst 15% vs rest
thr = A["R"].quantile(0.15)
worst = A[A["R"]<=thr]; rest = A[A["R"]>thr]
log(f"worst 15% trades (n={len(worst)}, R<= {thr:.4f}) vs rest (n={len(rest)}):")
cmp_rows=[]
for f in ["adx","abs_trend","realvol","atr_pct"]:
    wv, rv = worst[f].mean(), rest[f].mean()
    cmp_rows.append({"feature":f,"worst_mean":wv,"rest_mean":rv,"ratio":wv/rv if rv else np.nan})
    log(f"   {f:10s}: worst={wv:.4f}  rest={rv:.4f}  ratio={wv/rv if rv else float('nan'):.2f}")
pd.DataFrame(cmp_rows).to_csv(OUT + f"\\{BASE}_autopsy_worst_vs_rest.csv", index=False)

# mean R by ADX quantile and by abs_trend quantile (the money charts)
def by_q(df, key, k=5):
    q = pd.qcut(df[key], k, labels=[f"Q{i+1}" for i in range(k)], duplicates="drop")
    g = df.groupby(q, observed=True)["R"].agg(["count","mean","sum"])
    g["win%"] = df.groupby(q, observed=True).apply(lambda x:(x["R"]>0).mean()*100, include_groups=False)
    return g
adx_q = by_q(A.dropna(subset=["adx"]), "adx")
trd_q = by_q(A.dropna(subset=["abs_trend"]), "abs_trend")
log("\nREVoi mean R by ADX quintile (Q5=strongest trend):")
log(adx_q.to_string())
log("\nREVoi mean R by |prior-24h trend| quintile (Q5=strongest):")
log(trd_q.to_string())
adx_q.to_csv(OUT + f"\\{BASE}_R_by_ADX_quintile.csv")
trd_q.to_csv(OUT + f"\\{BASE}_R_by_trendstrength_quintile.csv")

# fading vs not, session
log(f"\nFading-the-trend trades: n={int(A['fading'].sum())}  meanR={A.loc[A['fading'],'R'].mean():+.5f}  | non-fading meanR={A.loc[~A['fading'],'R'].mean():+.5f}")
sess = A.groupby("session")["R"].agg(["count","mean","sum"])
log("By session:\n" + sess.to_string())

# =====================================================================
# Phase 1c : H1 - post-ETF trend persistence
# =====================================================================
log("\n" + "-"*78)
log("[Phase 1c] H1 : did trend persistence rise & mean-reversion fall after 2024-01-11 ETF?")
log("-"*78)

day = m["close"].resample("1D").last().dropna()
dret = day.pct_change().dropna()
pre = dret[dret.index < ETF]; post = dret[dret.index >= ETF]
log(f"daily returns: pre n={len(pre)}  post n={len(post)}")
ac_rows=[]
for lag in [1,2,3,5]:
    ap = pre.autocorr(lag); aq = post.autocorr(lag)
    ac_rows.append({"lag":lag,"pre_autocorr":ap,"post_autocorr":aq})
    log(f"  daily autocorr lag{lag}: pre={ap:+.4f}  post={aq:+.4f}  (higher=more trend persistence)")
pd.DataFrame(ac_rows).to_csv(OUT + f"\\{BASE}_H1_autocorr_pre_post.csv", index=False)

# simple TSMOM: sign(prior daily ret) * next daily ret  -> PF & hit
def tsmom_stats(r):
    sig = np.sign(r.shift(1)); pnl = (sig*r).dropna()
    pf = pnl[pnl>0].sum() / abs(pnl[pnl<0].sum()) if (pnl<0).any() else np.nan
    return pf, (pnl>0).mean()*100, pnl.sum()
for nm,r in [("pre",pre),("post",post)]:
    pf,hit,tot = tsmom_stats(r)
    log(f"  TSMOM(1d) {nm}: PF={pf:.3f} hit%={hit:.1f} sumPnL={tot:+.4f}")

# REVoi & TS performance pre/post (from ledgers, split at ETF by entry time)
def perf(df, col, label):
    p = df[df["et"]<ETF]; q = df[df["et"]>=ETF]
    def st(x):
        if len(x)==0: return "n=0"
        pf = x[x[col]>0][col].sum()/abs(x[x[col]<0][col].sum()) if (x[col]<0).any() else float("nan")
        return f"n={len(x)} sumR={x[col].sum():+.3f} win%={(x[col]>0).mean()*100:.0f} PF={pf:.2f} meanR={x[col].mean():+.5f}"
    log(f"  {label} pre : {st(p)}")
    log(f"  {label} post: {st(q)}")
perf(rev, "R", "REVoi")
perf(ts,  "R", "TrendStack")

# =====================================================================
# Charts
# =====================================================================
plt.rcParams.update({"figure.dpi":110,"font.size":9})
# 1) monthly returns REVoi vs TS
fig,ax=plt.subplots(figsize=(12,4))
x=np.arange(len(M)); w=0.4
ax.bar(x-w/2, M["REVoi"]*100, w, label="REVoi (mean-reversion)", color="#3066BE")
ax.bar(x+w/2, M["TS"]*100, w, label="TrendStack (trend)", color="#E07A00")
ax.axhline(0,color="k",lw=0.6); ax.set_title("Phase1a: Monthly unsized return (sum R, %) - REVoi vs TrendStack")
ax.set_ylabel("monthly sum R (%)"); ax.legend()
step=max(1,len(M)//12); ax.set_xticks(x[::step]); ax.set_xticklabels([d.strftime("%y-%m") for d in M.index[::step]],rotation=45,fontsize=7)
plt.tight_layout(); plt.savefig(OUT+f"\\{BASE}_chart1_monthly.png"); plt.close()

# 2) equity + drawdown
fig,(a1,a2)=plt.subplots(2,1,figsize=(12,6),sharex=True,gridspec_kw={"height_ratios":[2,1]})
for c,col in [("REVoi","#3066BE"),("TS","#E07A00"),("Combo","#2E933C")]:
    a1.plot(M.index, eq_curve(M[c]).values, label=c, color=col)
a1.set_title("Phase1a: Compounded equity (unsized monthly R - preview only) & drawdown"); a1.legend(); a1.set_ylabel("equity x")
a2.fill_between(M.index, (eq_curve(M["REVoi"])/eq_curve(M["REVoi"]).cummax()-1).values*100, color="#3066BE", alpha=0.5, label="REVoi DD")
a2.fill_between(M.index, (eq_curve(M["Combo"])/eq_curve(M["Combo"]).cummax()-1).values*100, color="#2E933C", alpha=0.4, label="Combo DD")
a2.set_ylabel("drawdown %"); a2.legend()
plt.tight_layout(); plt.savefig(OUT+f"\\{BASE}_chart2_equity_dd.png"); plt.close()

# 3) REVoi mean R by trend strength (autopsy money chart)
fig,(b1,b2)=plt.subplots(1,2,figsize=(12,4))
b1.bar(range(len(adx_q)), adx_q["mean"].values*100, color="#C1121F"); b1.axhline(0,color="k",lw=0.6)
b1.set_xticks(range(len(adx_q))); b1.set_xticklabels(adx_q.index); b1.set_title("REVoi mean R by ADX quintile (Q5=strong trend)"); b1.set_ylabel("mean R %")
b2.bar(range(len(trd_q)), trd_q["mean"].values*100, color="#C1121F"); b2.axhline(0,color="k",lw=0.6)
b2.set_xticks(range(len(trd_q))); b2.set_xticklabels(trd_q.index); b2.set_title("REVoi mean R by |prior-24h trend| quintile (Q5=strong)"); b2.set_ylabel("mean R %")
plt.tight_layout(); plt.savefig(OUT+f"\\{BASE}_chart3_autopsy.png"); plt.close()

# 4) pre/post ETF autocorr
fig,ax=plt.subplots(figsize=(7,4))
acdf=pd.DataFrame(ac_rows); xx=np.arange(len(acdf)); w=0.38
ax.bar(xx-w/2, acdf["pre_autocorr"], w, label="pre-ETF", color="#8D99AE")
ax.bar(xx+w/2, acdf["post_autocorr"], w, label="post-ETF (2024-01-11+)", color="#E07A00")
ax.axhline(0,color="k",lw=0.6); ax.set_xticks(xx); ax.set_xticklabels([f"lag{l}" for l in acdf['lag']])
ax.set_title("H1: daily return autocorrelation pre vs post ETF (higher=trend persists)"); ax.set_ylabel("autocorrelation"); ax.legend()
plt.tight_layout(); plt.savefig(OUT+f"\\{BASE}_chart4_H1_autocorr.png"); plt.close()

# write summary
with open(OUT+f"\\{BASE}_analysis.txt","w",encoding="utf-8") as f:
    f.write("\n".join(lines))
log("\n[OK] outputs written to: " + OUT)
log("charts: chart1_monthly, chart2_equity_dd, chart3_autopsy, chart4_H1_autocorr")
