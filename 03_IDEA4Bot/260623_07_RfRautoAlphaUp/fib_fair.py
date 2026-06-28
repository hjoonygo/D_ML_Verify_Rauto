import sys
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\engines")
sys.path.insert(0, r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp")
import trendstack_signal_engine as TS
import ts_honest_A as A
import numpy as np, pandas as pd
def mdd(r):
    eq=np.cumprod(1+r); return ((eq-np.maximum.accumulate(eq))/np.maximum.accumulate(eq)).min()*100
def cagr(r):
    eq=np.cumprod(1+r); return (eq[-1]**(1/3)-1)*100
d=pd.read_csv(A.DATA,usecols=["timestamp","open","high","low","close"])
d["t"]=pd.to_datetime(d["timestamp"],utc=True,format="ISO8601").dt.tz_localize(None)
d=d.dropna(subset=["open","high","low","close"]).set_index("t").sort_index()
df7h=TS.resample_tf(d[["open","high","low","close"]],TS.TF_MIN)
sig=TS.compute_signals(df7h)
print("=== Fib trail: wide grid (initial SL x fib ratios), TS entry, honest 1m ===")
print("initSL%  fib                   n   ret%    CAGR%   MDD%   win%  sl%")
best=None
for slp in [1.0,1.5,2.0,2.5,3.0,4.0,5.0]:
    TS.SL_PCT=slp
    for fib in [(0.3,0.5,0.6),(0.4,0.6,0.8),(0.5,0.7,0.9),(0.7,0.9,0.98)]:
        A.FIB=fib
        ent=A.ts_replay(df7h,sig); T=A.exit_A(ent,df7h,d); r=T.ret.values
        sl=100*(T.reason=="sl").mean(); rt=(np.cumprod(1+r)[-1]-1)*100
        print("  %.1f    %-19s %3d  %+6.0f%%  %+5.0f%%  %5.1f%%  %2.0f%%  %2.0f%%"%(slp,str(fib),len(T),rt,cagr(r),mdd(r),100*(r>0).mean(),sl))
        if best is None or rt>best[0]: best=(rt,slp,fib,mdd(r))
print("--> best ret: %+.0f%% at initSL %.1f%% fib %s (MDD %.1f%%)"%(best[0],best[1],best[2],best[3]))
print("[compare] B(vol SL + 3pct trail) = +111pct/MDD-44.6/SQN1.71")
