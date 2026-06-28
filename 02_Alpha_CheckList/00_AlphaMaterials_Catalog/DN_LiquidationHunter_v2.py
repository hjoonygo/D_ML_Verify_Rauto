# -*- coding: utf-8 -*-
# [DN v2] 손절=스윙저점(FVG근사,넓힘) + 자석 NEAR 좁힘 + RR 스윕. 추세 EMA. 1m정직.
import sys, os
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\verification")
import numpy as np, pandas as pd
DATA=r"D:\ML\RfRauto\08_BTC_Data\derived\Merged_Data.csv"; COST=0.0008
d=pd.read_csv(DATA,usecols=["timestamp","open","high","low","close","oi_change_1h_pct"])
d["t"]=pd.to_datetime(d["timestamp"],utc=True,format="ISO8601").dt.tz_localize(None)
d=d.dropna(subset=["open","high","low","close"]).set_index("t").sort_index()
r=d.resample("15min"); o15=r["open"].first(); h15=r["high"].max(); l15=r["low"].min(); c15=r["close"].last()
oichg15=d["oi_change_1h_pct"].abs().resample("15min").sum()
df=pd.DataFrame({"o":o15,"h":h15,"l":l15,"c":c15,"oi":oichg15}).dropna()
idx15=df.index; o=df.o.values; h=df.h.values; l=df.l.values; c=df.c.values; oiw=df.oi.values
em=pd.Series(c).ewm(span=50).mean().values
N=len(df); W=672; poc=np.full(N,np.nan)
for j in range(W,N,16):
    px=c[j-W:j]; wt=oiw[j-W:j]; m=~np.isnan(px)&~np.isnan(wt)
    if m.sum()<100: continue
    lo,hi=px[m].min(),px[m].max()
    if hi<=lo: continue
    bins=np.linspace(lo,hi,60); bi=np.clip(np.digitize(px[m],bins),0,59)
    build=np.zeros(60); np.add.at(build,bi,wt[m]); poc[j:min(j+16,N)]=bins[int(np.argmax(build))]
ti=d.index; O1=d["open"].values; H1=d["high"].values; L1=d["low"].values; C1=d["close"].values
def mdd(x): eq=np.cumprod(1+x); return ((eq-np.maximum.accumulate(eq))/np.maximum.accumulate(eq)).min()*100
def run(NEAR,SWING,RR):
    trades=[]; last_xt=None
    for j in range(W,N):
        if np.isnan(poc[j]) or np.isnan(em[j]): continue
        et_fill=idx15[j]+pd.Timedelta(minutes=15)
        if last_xt is not None and et_fill<last_xt: continue
        pj=poc[j]
        longc = c[j]>em[j] and abs(l[j]-pj)/pj<NEAR and c[j]>o[j]
        shortc= c[j]<em[j] and abs(h[j]-pj)/pj<NEAR and c[j]<o[j]
        if longc: side=1; entry=c[j]; sl=l[max(0,j-SWING):j+1].min()*(1-0.0005)
        elif shortc: side=-1; entry=c[j]; sl=h[max(0,j-SWING):j+1].max()*(1+0.0005)
        else: continue
        risk=abs(entry-sl)
        if risk/entry<0.0015: continue
        tp=entry+RR*risk if side==1 else entry-RR*risk
        si=ti.searchsorted(et_fill)
        if si>=len(ti): continue
        ex=None; reason=None; kk=si
        for k in range(si,min(si+8640,len(ti))):
            kk=k
            if side==1:
                if L1[k]<=sl: ex=min(O1[k],sl); reason="sl"; break
                if H1[k]>=tp: ex=max(O1[k],tp); reason="tp"; break
            else:
                if H1[k]>=sl: ex=max(O1[k],sl); reason="sl"; break
                if L1[k]<=tp: ex=min(O1[k],tp); reason="tp"; break
        if ex is None: ex=C1[min(si+8640,len(ti)-1)]; reason="to"
        trades.append((side*(ex-entry)/entry-COST, reason)); last_xt=ti[min(kk,len(ti)-1)]
    T=pd.DataFrame(trades,columns=["ret","tag"]); rr=T.ret.values
    win=100*(rr>0).mean(); tp_=100*(T.tag=="tp").mean()
    print(f"NEAR{NEAR*100:.1f}% SWING{SWING} RR{RR}: n{len(T)} 총{(np.cumprod(1+rr)[-1]-1)*100:+.0f}% MDD{mdd(rr):.0f}% 승{win:.0f}% tp{tp_:.0f}%")
print("[DN v2 스윕] 손절=스윙저점(FVG근사), 자석 좁힘, RR 스윕")
for NEAR in [0.002,0.001]:
    for SWING in [5,10]:
        for RR in [1.5,2.0,3.0]:
            run(NEAR,SWING,RR)
