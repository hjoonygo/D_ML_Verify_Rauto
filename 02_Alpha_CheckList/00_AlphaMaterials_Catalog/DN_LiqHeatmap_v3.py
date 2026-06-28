# -*- coding: utf-8 -*-
# [DN v3] 청산 히트맵 POC(레버별 청산가 누적)를 자석으로 DN 매매법 재백테. 추세EMA+스윙손절+RR스윕.
import numpy as np, pandas as pd
DATA=r"D:\ML\RfRauto\08_BTC_Data\derived\Merged_Data.csv"; COST=0.0008
d=pd.read_csv(DATA,usecols=["timestamp","open","high","low","close","oi_change_1h_pct"])
d["t"]=pd.to_datetime(d["timestamp"],utc=True,format="ISO8601").dt.tz_localize(None)
d=d.dropna(subset=["open","high","low","close"]).set_index("t").sort_index()
r=d.resample("15min"); o15=r["open"].first(); h15=r["high"].max(); l15=r["low"].min(); c15=r["close"].last()
oichg15=d["oi_change_1h_pct"].resample("15min").sum()
df=pd.DataFrame({"o":o15,"h":h15,"l":l15,"c":c15,"oi":oichg15}).dropna()
o=df.o.values; h=df.h.values; l=df.l.values; c=df.c.values; oi=df.oi.values; idx15=df.index
em=pd.Series(c).ewm(span=50).mean().values
N=len(df); W=672; LEVS=[100,50,25,10,5]
dr=np.zeros(N); dr[4:]=np.sign(c[4:]-c[:-4])   # 1h 가격방향(롱/숏 신규)
poc=np.full(N,np.nan)
for j in range(W,N,16):
    px=c[j-W:j]; dO=oi[j-W:j]; di=dr[j-W:j]
    m=(~np.isnan(px))&(~np.isnan(dO))&(dO>0)
    if m.sum()<100: continue
    px=px[m]; w=dO[m]; di=di[m]
    lo,hi=px.min()*0.85,px.max()*1.15; bins=np.linspace(lo,hi,150); heat=np.zeros(150)
    for lev in LEVS:
        for liq,wt in [(px*(1-1/lev),w*np.clip(di,0,1)),(px*(1+1/lev),w*np.clip(-di,0,1))]:
            bi=np.clip(np.digitize(liq,bins),0,149); np.add.at(heat,bi,wt)
    poc[j:min(j+16,N)]=bins[int(np.argmax(heat))]
ti=d.index; O1=d["open"].values; H1=d["high"].values; L1=d["low"].values; C1=d["close"].values
def mdd(x): eq=np.cumprod(1+x); return ((eq-np.maximum.accumulate(eq))/np.maximum.accumulate(eq)).min()*100
def run(NEAR,SWING,RR):
    trades=[]; last_xt=None
    for j in range(W,N):
        if np.isnan(poc[j]) or np.isnan(em[j]): continue
        et_fill=idx15[j]+pd.Timedelta(minutes=15)
        if last_xt is not None and et_fill<last_xt: continue
        pj=poc[j]
        longc=c[j]>em[j] and abs(l[j]-pj)/pj<NEAR and c[j]>o[j]
        shortc=c[j]<em[j] and abs(h[j]-pj)/pj<NEAR and c[j]<o[j]
        if longc: side=1; entry=c[j]; sl=l[max(0,j-SWING):j+1].min()*(1-0.0005)
        elif shortc: side=-1; entry=c[j]; sl=h[max(0,j-SWING):j+1].max()*(1+0.0005)
        else: continue
        risk=abs(entry-sl)
        if risk/entry<0.0015: continue
        tp=entry+RR*risk if side==1 else entry-RR*risk
        si=ti.searchsorted(et_fill)
        if si>=len(ti): continue
        ex=None; kk=si
        for k in range(si,min(si+8640,len(ti))):
            kk=k
            if side==1:
                if L1[k]<=sl: ex=min(O1[k],sl); break
                if H1[k]>=tp: ex=max(O1[k],tp); break
            else:
                if H1[k]>=sl: ex=max(O1[k],sl); break
                if L1[k]<=tp: ex=min(O1[k],tp); break
        if ex is None: ex=C1[min(si+8640,len(ti)-1)]
        trades.append(side*(ex-entry)/entry-COST); last_xt=ti[min(kk,len(ti)-1)]
    a=np.array(trades)
    print(f"NEAR{NEAR*100:.1f}% SW{SWING} RR{RR}: n{len(a)} 총{(np.cumprod(1+a)[-1]-1)*100:+.0f}% MDD{mdd(a):.0f}% 승{100*(a>0).mean():.0f}%")
print("[DN v3 — 청산 히트맵 POC 자석]")
for NEAR in [0.003,0.002]:
    for RR in [1.5,2.0,3.0]:
        run(NEAR,10,RR)
