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
    # 보유관리: 진입 정렬 후 이전 청산시각 이후 진입만 (한 포지션씩)
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
allm=sorted(set(tsm.index)|set(revm.index)); ts_s=tsm.reindex(allm,fill_value=0.0); rev_s=revm.reindex(allm,fill_value=0.0)
corr=np.corrcoef(ts_s.values,rev_s.values)[0,1]; port=0.5*ts_s.values+0.5*rev_s.values
def em(m): 
    eq=np.cumprod(1+m); return (eq[-1]-1)*100, ((eq-np.maximum.accumulate(eq))/np.maximum.accumulate(eq)).min()*100, eq
tt,tm,_=em(ts_s.values); rt,rm,_=em(rev_s.values); pt,pm,pe=em(port)
print("=== PORTFOLIO (TS regime + reversion, 50/50, monthly compound) ===")
print("TS only   : tot %+.0f%%  MDD %.1f%%  (%d trades)"%(tt,tm,len(TSL_)))
print("REV only  : tot %+.0f%%  MDD %.1f%%  (%d trades)"%(rt,rm,len(REV)))
print("PORT 50/50: tot %+.0f%%  MDD %.1f%%  CAGR %.1f%%/yr  monthly+ %.0f%%"%(pt,pm,((1+pt/100)**(1/3)-1)*100,100*(port>0).mean()))
print("CORRELATION (monthly): %.2f"%corr)
fig,ax=plt.subplots(1,2,figsize=(14,5))
ax[0].plot(np.cumprod(1+ts_s.values),label="TS",c="orange"); ax[0].plot(np.cumprod(1+rev_s.values),label="REV",c="steelblue"); ax[0].plot(pe,label="PORT",c="navy",lw=2); ax[0].legend(); ax[0].set_title("Equity monthly (PORT MDD %.0f%%, corr %.2f)"%(pm,corr))
dd=(pe-np.maximum.accumulate(pe))/np.maximum.accumulate(pe)*100; ax[1].fill_between(range(len(dd)),dd,0,color="crimson",alpha=.5); ax[1].set_title("Portfolio Drawdown")
plt.tight_layout(); plt.savefig(os.path.join(HERE,"ts_report_portfolio.png"),dpi=110); print("[graph] ts_report_portfolio.png")
