# -*- coding: utf-8 -*-
# [DN 청산헌터 백테] 추세(EMA=평균단가선) + OI POC 자석 되돌림 진입 + 직전저점 손절 + 1:1.5 RR. 1m 정직체결.
import sys, os
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\verification")
import analyze_backtest as AB
import numpy as np, pandas as pd
DATA=r"D:\ML\RfRauto\08_BTC_Data\derived\Merged_Data.csv"
HERE=r"D:\ML\RfRauto\02_Alpha_CheckList\00_AlphaMaterials_Catalog"
COST=0.0008
d=pd.read_csv(DATA,usecols=["timestamp","open","high","low","close","oi_change_1h_pct"])
d["t"]=pd.to_datetime(d["timestamp"],utc=True,format="ISO8601").dt.tz_localize(None)
d=d.dropna(subset=["open","high","low","close"]).set_index("t").sort_index()
r=d.resample("15min"); o15=r["open"].first(); h15=r["high"].max(); l15=r["low"].min(); c15=r["close"].last()
oichg15=d["oi_change_1h_pct"].abs().resample("15min").sum()
df=pd.DataFrame({"o":o15,"h":h15,"l":l15,"c":c15,"oi":oichg15}).dropna()
idx15=df.index; o=df.o.values; h=df.h.values; l=df.l.values; c=df.c.values; oiw=df.oi.values
em=pd.Series(c).ewm(span=50).mean().values
N=len(df); W=672
poc=np.full(N,np.nan)
for j in range(W,N,16):
    px=c[j-W:j]; wt=oiw[j-W:j]; m=~np.isnan(px)&~np.isnan(wt)
    if m.sum()<100: continue
    lo,hi=px[m].min(),px[m].max()
    if hi<=lo: continue
    bins=np.linspace(lo,hi,60); bi=np.clip(np.digitize(px[m],bins),0,59)
    build=np.zeros(60); np.add.at(build,bi,wt[m]); poc[j:min(j+16,N)]=bins[int(np.argmax(build))]
ti=d.index; O1=d["open"].values; H1=d["high"].values; L1=d["low"].values; C1=d["close"].values
NEAR=0.003; trades=[]; last_xt=None
for j in range(W,N):
    if np.isnan(poc[j]) or np.isnan(em[j]): continue
    et_fill=idx15[j]+pd.Timedelta(minutes=15)
    if last_xt is not None and et_fill<last_xt: continue
    pj=poc[j]
    longc = c[j]>em[j] and abs(l[j]-pj)/pj<NEAR and c[j]>o[j]
    shortc= c[j]<em[j] and abs(h[j]-pj)/pj<NEAR and c[j]<o[j]
    if longc: side=1; entry=c[j]; sl=l[j]*(1-0.0005)
    elif shortc: side=-1; entry=c[j]; sl=h[j]*(1+0.0005)
    else: continue
    risk=abs(entry-sl)
    if risk/entry<0.001: continue
    tp=entry+1.5*risk if side==1 else entry-1.5*risk
    si=ti.searchsorted(et_fill)
    if si>=len(ti): continue
    ex=None; reason=None; kk=si
    for k in range(si,min(si+4320,len(ti))):
        kk=k
        if side==1:
            if L1[k]<=sl: ex=min(O1[k],sl); reason="sl"; break
            if H1[k]>=tp: ex=max(O1[k],tp); reason="tp"; break
        else:
            if H1[k]>=sl: ex=max(O1[k],sl); reason="sl"; break
            if L1[k]<=tp: ex=min(O1[k],tp); reason="tp"; break
    if ex is None: ex=C1[min(si+4320,len(ti)-1)]; reason="timeout"
    ret=side*(ex-entry)/entry-COST
    trades.append(dict(ret=ret,side=side,year=int(idx15[j].year),et=idx15[j],tag=reason))
    last_xt=ti[min(kk,len(ti)-1)]
T=pd.DataFrame(trades)
print(f"[DN 청산헌터 백테] {len(T)}거래 (15m, NEAR={NEAR*100:.1f}%, 1:1.5 RR, 1m정직, 비용8bp)")
print(f"  청산사유: {dict(T.tag.value_counts())}")
print(f"  tp비율 {100*(T.tag=='tp').mean():.0f}% | 승률 {100*(T.ret>0).mean():.0f}%")
AB.analyze(T,"DN Liquidation Hunter (video method, honest 1m)",os.path.join(HERE,"graphs","DN_LiquidationHunter_Backtest.png"))
try: os.startfile(os.path.join(HERE,"graphs","DN_LiquidationHunter_Backtest.png"))
except: pass
