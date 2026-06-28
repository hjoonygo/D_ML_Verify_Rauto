import sys
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\engines")
sys.path.insert(0, r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp")
import trendstack_signal_engine as TS
import ts_honest_A as A
import numpy as np, pandas as pd
def mdd(r): 
    eq=np.cumprod(1+r); return ((eq-np.maximum.accumulate(eq))/np.maximum.accumulate(eq)).min()*100
d=pd.read_csv(A.DATA,usecols=["timestamp","open","high","low","close"])
d["t"]=pd.to_datetime(d["timestamp"],utc=True,format="ISO8601").dt.tz_localize(None)
d=d.dropna(subset=["open","high","low","close"]).set_index("t").sort_index()
df7h=TS.resample_tf(d[["open","high","low","close"]],TS.TF_MIN)
sig=TS.compute_signals(df7h)
print("=== Pullback step-up (Fib trail) redesign: honest 1m, TS entry ===")
print("(higher fib = let winners run more; baseline 0.3/0.5/0.6 = +19% in A)")
for fib in [(0.3,0.5,0.6),(0.2,0.4,0.6),(0.4,0.6,0.8),(0.5,0.7,0.9),(0.6,0.85,0.95),(0.7,0.9,0.98)]:
    A.FIB=fib
    ent=A.ts_replay(df7h,sig)
    T=A.exit_A(ent,df7h,d)
    r=T.ret.values
    sl=100*(T.reason=="sl").mean() if "reason" in T else 0
    print("fib %-18s n%3d  ret%+7.0f%%  MDD%6.1f%%  win%2.0f%%  sl%2.0f%%"%(str(fib),len(T),(np.cumprod(1+r)[-1]-1)*100,mdd(r),100*(r>0).mean(),sl))
