# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\engines")
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\verification")
sys.path.insert(0, r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp")
import trendstack_signal_engine as TS
import ts_honest_A as A
import analyze_backtest as AB
import numpy as np, pandas as pd
HERE=r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp"
def mdd(r): eq=np.cumprod(1+r); return ((eq-np.maximum.accumulate(eq))/np.maximum.accumulate(eq)).min()*100
def tot(r): return (np.cumprod(1+r)[-1]-1)*100
d=pd.read_csv(A.DATA,usecols=["timestamp","open","high","low","close","oi_zscore_24h"])
d["t"]=pd.to_datetime(d["timestamp"],utc=True,format="ISO8601").dt.tz_localize(None)
d=d.dropna(subset=["open","high","low","close"]).set_index("t").sort_index()
doi=pd.to_numeric(d["oi_zscore_24h"],errors="coerce")
df7h=TS.resample_tf(d[["open","high","low","close"]],TS.TF_MIN); sig=TS.compute_signals(df7h)
atrp=sig["atr"]/df7h["close"].values; oi7=doi.reindex(df7h.index,method="ffill").values
print("=== Pullback step-up (Fib trail) DONE RIGHT: VolSL + ATRxOI sizing ===")
def sizing(T):
    med=np.median(T.atr_e.values); soi=np.clip(1-0.3*np.maximum(0,T.oi_e.values-1.5),0.25,1); sat=np.clip(med/T.atr_e.values,0.25,1)
    return T.ret.values*sat*soi
print("sl_mult   n    raw ret/MDD          sized ret/MDD")
for slm in [1.0,1.5,2.0,2.5]:
    ent=A.ts_replay(df7h,sig,atrp,oi7,vol_sl=True,sl_mult=slm)
    T=A.exit_A(ent,df7h,d); r=T.ret.values; rs=sizing(T)
    print("  %.1f    %3d   %+5.0f%% / %5.1f%%      %+5.0f%% / %5.1f%%"%(slm,len(T),tot(r),mdd(r),tot(rs),mdd(rs)))
ent=A.ts_replay(df7h,sig,atrp,oi7,vol_sl=True,sl_mult=1.5)
T=A.exit_A(ent,df7h,d); T["ret"]=sizing(T)
png=os.path.join(HERE,"ts_report_pullback_alpha.png")
AB.analyze(T,"Fib Pullback Step-up + VolSL + ATRxOI Sizing",png)
try: os.startfile(png)
except Exception as e: print("open fail",e)
print("[compare] B(our exit,no sizing) +111%/-44.6% | fib 1%SL no-sizing +19%/-37%")
