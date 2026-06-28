import sys, os
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\engines")
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\verification")
import trendstack_signal_engine as TS
import analyze_backtest as AB
import numpy as np, pandas as pd, itertools
DATA = r"D:\ML\RfRauto\08_BTC_Data\derived\Merged_Data.csv"
COST=0.0008; SL_MULT=1.5; TF=TS.TF_MIN; TRAIL=0.03
HERE=os.path.dirname(os.path.abspath(__file__))
def mdd(r): eq=np.cumprod(1+r); return ((eq-np.maximum.accumulate(eq))/np.maximum.accumulate(eq)).min()*100
def tot(r): return (np.cumprod(1+r)[-1]-1)*100
def sqn(R): return R.mean()/R.std()*np.sqrt(len(R)) if R.std()>0 else 0
def cpcv(r,g=6):
    gs=np.array_split(np.arange(len(r)),g); ps=[]
    for c in itertools.combinations(range(g),2):
        rr=r[np.concatenate([gs[k] for k in c])]
        ps.append(rr.mean()/rr.std()*np.sqrt(len(rr)/3) if rr.std()>0 else 0)
    return np.percentile(ps,25)
def get_entries(d,doi):
    df7h=TS.resample_tf(d[["open","high","low","close"]],TF)
    sig=TS.compute_signals(df7h)
    trades=TS.run_strategy(df7h,sig,0,"none",0.8,gate_mode="er",gate_er=0.45,split_mode="A",split_n=3,fib=(0.3,0.5,0.6))
    atrp=sig["atr"]/df7h["close"].values; er=sig["er"]; adx=sig["adx"]
    oi7=doi.reindex(df7h.index,method="ffill").values; idx7=df7h.index
    for tr in trades:
        ei=idx7.get_loc(tr["entry_t"])
        tr["atr_pct"]=float(atrp[ei]) if atrp[ei]>0 else 0.02
        tr["oi_z"]=float(oi7[ei]) if not np.isnan(oi7[ei]) else 0.0
        tr["er"]=float(er[ei]); tr["adx"]=float(adx[ei])
    return trades
def sim(d,trades,er_min,adx_min,floor):
    ti=d.index; O=d["open"].values; H=d["high"].values; L=d["low"].values; C=d["close"].values
    out=[]
    for tr in trades:
        if tr["er"]<er_min or tr["adx"]<adx_min: continue
        side=int(tr["side"]); entry=float(tr["entry"]); ap=tr["atr_pct"]
        risk=float(np.clip(ap*SL_MULT,0.008,0.05))
        et=pd.Timestamp(tr["entry_t"])+pd.Timedelta(minutes=TF)
        si=ti.searchsorted(et)
        if si>=len(ti): continue
        init_sl=entry*(1-risk) if side==1 else entry*(1+risk); TSL=init_sl
        hwm=H[si]; lwm=L[si]; ex=None; tag="trailing"
        for i in range(si,len(ti)):
            if side==1 and L[i]<=TSL: ex=min(O[i],TSL); break
            if side==-1 and H[i]>=TSL: ex=max(O[i],TSL); break
            if H[i]>hwm: hwm=H[i]
            if L[i]<lwm: lwm=L[i]
            TSL=max(TSL,hwm*(1-TRAIL)) if side==1 else min(TSL,lwm*(1+TRAIL))
        if ex is None: ex=C[-1]
        if abs(TSL-init_sl)<1e-9: tag="initial_SL"
        out.append(dict(ret=side*(ex-entry)/entry-COST,risk=risk,atr_e=ap,oi_e=tr["oi_z"],side=side,tag=tag,year=et.year,et=et))
    T=pd.DataFrame(out)
    med=np.median(T.atr_e.values)
    soi=np.clip(1-0.3*np.maximum(0,T.oi_e.values-1.5),floor,1)
    sat=np.clip(med/T.atr_e.values,floor,1)
    T["ret"]=T.ret.values*sat*soi
    return T
def main():
    d=pd.read_csv(DATA,usecols=["timestamp","open","high","low","close","oi_zscore_24h"])
    d["t"]=pd.to_datetime(d["timestamp"],utc=True,format="ISO8601").dt.tz_localize(None)
    d=d.dropna(subset=["open","high","low","close"]).set_index("t").sort_index()
    doi=pd.to_numeric(d["oi_zscore_24h"],errors="coerce")
    trades=get_entries(d[["open","high","low","close"]],doi)
    print("[TS entry %d] regime filter + sizing"%len(trades))
    print("%-20s%5s%8s%8s%7s%8s%5s"%("variant","n","ret%","MDD%","SQN","CPCV","u20"))
    cfgs=[("base_noFilter",0,0,0.25),("ER>=0.40",0.40,0,0.25),("ER>=0.50",0.50,0,0.25),("ADX>=25",0,25,0.25),("ER0.40_floor.15",0.40,0,0.15)]
    best=None; bestnm=None
    for nm,e,a,f in cfgs:
        T=sim(d,trades,e,a,f); r=T.ret.values
        ok="O" if (tot(r)>0 and cpcv(r)>0 and mdd(r)>-20) else ""
        print("%-20s%5d%+8.0f%+8.1f%7.2f%+8.2f%5s"%(nm,len(T),tot(r),mdd(r),sqn((T.ret/T.risk).values),cpcv(r),ok))
        if best is None or mdd(r)>mdd(best.ret.values): best=T; bestnm=nm
    AB.analyze(best,"TS Regime Filter Sizing %s"%bestnm,os.path.join(HERE,"ts_report_regime.png"))
main()
