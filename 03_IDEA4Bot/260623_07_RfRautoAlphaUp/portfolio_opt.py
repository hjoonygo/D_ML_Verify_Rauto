import sys, os
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\engines")
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\verification")
sys.path.insert(0, r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp")
import trendstack_signal_engine as TS
import vol_sizing_compare as V
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
DATA=r"D:\ML\RfRauto\08_BTC_Data\derived\Merged_Data.csv"
COST=0.0008; SL_MULT=1.5; TRAIL=0.03; TF=TS.TF_MIN
HERE=r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp"
def exit_seq(d, ents):
    ti=d.index; O=d["open"].values; H=d["high"].values; L=d["low"].values; C=d["close"].values
    aps=[e["atr_pct"] for e in ents]; med=np.median(aps) if aps else 0.02
    ents=sorted(ents,key=lambda e:e["et_fill"]); rows=[]; last_xt=None
    for e in ents:
        if last_xt is not None and e["et_fill"]<last_xt: continue
        side=e["side"]; entry=e["entry"]; ap=e["atr_pct"]; oi=e["oi_z"]
        risk=float(np.clip(ap*SL_MULT,0.008,0.05)); si=ti.searchsorted(e["et_fill"])
        if si>=len(ti): continue
        isl=entry*(1-risk) if side==1 else entry*(1+risk); TSL=isl; hwm=H[si]; lwm=L[si]; ex=None; xi=len(ti)-1
        for i in range(si,len(ti)):
            if side==1 and L[i]<=TSL: ex=min(O[i],TSL); xi=i; break
            if side==-1 and H[i]>=TSL: ex=max(O[i],TSL); xi=i; break
            if H[i]>hwm: hwm=H[i]
            if L[i]<lwm: lwm=L[i]
            TSL=max(TSL,hwm*(1-TRAIL)) if side==1 else min(TSL,lwm*(1+TRAIL))
        if ex is None: ex=C[-1]
        ret=side*(ex-entry)/entry-COST
        soi=np.clip(1-0.3*max(0,oi-1.5),0.25,1); sat=np.clip(med/ap,0.25,1)
        rows.append(dict(et=e["et"], ret=ret*sat*soi)); last_xt=ti[xi]
    return pd.DataFrame(rows)
d=pd.read_csv(DATA,usecols=["timestamp","open","high","low","close","oi_zscore_24h"])
d["t"]=pd.to_datetime(d["timestamp"],utc=True,format="ISO8601").dt.tz_localize(None)
d=d.dropna(subset=["open","high","low","close"]).set_index("t").sort_index()
doi=pd.to_numeric(d["oi_zscore_24h"],errors="coerce")
df7h=TS.resample_tf(d[["open","high","low","close"]],TF); sig=TS.compute_signals(df7h)
tstr=TS.run_strategy(df7h,sig,0,"none",0.8,gate_mode="er",gate_er=0.45,split_mode="A",split_n=3,fib=(0.3,0.5,0.6))
atrp=sig["atr"]/df7h["close"].values; er=sig["er"]; oi7=doi.reindex(df7h.index,method="ffill").values; idx7=df7h.index
ts_e=[]
for tr in tstr:
    ei=idx7.get_loc(tr["entry_t"])
    if er[ei]<0.40: continue
    ts_e.append(dict(et=pd.Timestamp(tr["entry_t"]), et_fill=pd.Timestamp(tr["entry_t"])+pd.Timedelta(minutes=TF),
        side=int(tr["side"]), entry=float(tr["entry"]), atr_pct=float(atrp[ei]) if atrp[ei]>0 else 0.02,
        oi_z=float(oi7[ei]) if not np.isnan(oi7[ei]) else 0.0))
TSL_=exit_seq(d, ts_e)
d2,S,oi_int=V.build(V.find_data()); oimap=dict(zip(list(S.index), list(oi_int)))
rev_e=[]
for t,row in S.iterrows():
    if row["side"]==0: continue
    tn=t.tz_localize(None) if t.tz is not None else t
    rev_e.append(dict(et=tn, et_fill=tn, side=int(row["side"]), entry=float(row["open8"]),
        atr_pct=float(row["atr_pct"]), oi_z=float(oimap.get(t,0.0))))
REV=exit_seq(d, rev_e)
TSL_["m"]=TSL_.et.dt.to_period("M"); REV["m"]=REV.et.dt.to_period("M")
tsm=TSL_.groupby("m").ret.apply(lambda x:((1+x).prod()-1)); revm=REV.groupby("m").ret.apply(lambda x:((1+x).prod()-1))
allm=sorted(set(tsm.index)|set(revm.index)); ts_s=tsm.reindex(allm,fill_value=0.0).values; rev_s=revm.reindex(allm,fill_value=0.0).values
def em(m): 
    eq=np.cumprod(1+m); return (eq[-1]-1)*100, ((eq-np.maximum.accumulate(eq))/np.maximum.accumulate(eq)).min()*100, eq
print("=== 1) WEIGHT SWEEP (TS/REV, monthly) ===")
res=[]
for w in [0.0,0.2,0.3,0.4,0.5,0.7,1.0]:
    p=w*ts_s+(1-w)*rev_s; pt,pm,_=em(p); cg=((1+pt/100)**(1/3)-1)*100; res.append((w,pt,pm,cg))
    print("TS%3.0f/REV%3.0f : tot %+6.0f%%  MDD %6.1f%%  CAGR %5.1f%%/yr"%(w*100,(1-w)*100,pt,pm,cg))
valid=[r for r in res if r[2]>-20]; bw=max(valid,key=lambda r:r[3])[0] if valid else 0.5
print("--> best weight (MDD>-20, max CAGR): TS%.0f/REV%.0f"%(bw*100,(1-bw)*100))
print("=== 2) LEVERAGE on best weight ===")
pbase=bw*ts_s+(1-bw)*rev_s
for lev in [1.0,1.5,2.0,2.5,3.0]:
    pl=pbase*lev; pt,pm,pe=em(pl); cg=((1+pt/100)**(1/3)-1)*100; mc=((1+pt/100)**(1/36)-1)*100
    print("lev %.1f : tot %+7.0f%%  MDD %6.1f%%  CAGR %6.1f%%/yr  monthly %+.2f%%  month+ %2.0f%%  %s"%(lev,pt,pm,cg,mc,100*(pl>0).mean(),"<=-20 OK" if pm>-20 else "VIOLATE"))
plt.figure(figsize=(10,5))
for lev in [1.0,1.5,2.0]:
    _,_,pe=em(pbase*lev); plt.plot(pe,label="lev %.1f"%lev)
plt.legend(); plt.title("Portfolio TS%.0f/REV%.0f - leverage (monthly compound)"%(bw*100,(1-bw)*100)); plt.tight_layout()
plt.savefig(os.path.join(HERE,"ts_report_opt.png"),dpi=110); print("[graph] ts_report_opt.png")
