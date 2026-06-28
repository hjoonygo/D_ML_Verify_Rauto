# -*- coding: utf-8 -*-
# [청산 히트맵 POC] ΔOI(신규포지션)를 레버별 청산가(1/lev)에 누적 -> 청산물량 자석 POC.
#   동영상/CoinGlass 방식. 단순 OI POC(53%)보다 강한 자석인지 검증.
import numpy as np, pandas as pd
DATA=r"D:\ML\RfRauto\08_BTC_Data\derived\Merged_Data.csv"
d=pd.read_csv(DATA,usecols=["timestamp","close","oi_change_1h_pct","oi_was_missing"])
c=d["close"].values.astype(float)
oichg=pd.to_numeric(d["oi_change_1h_pct"],errors="coerce").values
ret1=np.zeros(len(c)); ret1[60:]=c[60:]/c[:-60]-1   # 1h 가격변화(롱/숏 신규 방향)
z=((pd.Series(oichg)-pd.Series(oichg).rolling(1440).mean())/pd.Series(oichg).rolling(1440).std()).values
miss=pd.to_numeric(d["oi_was_missing"],errors="coerce").fillna(0).values; z[miss==1]=np.nan
n=len(c); K=360; W=10080
LEVS=[100,50,25,10,5]; LEVW=[1,1,1,1,1]   # 레버 분포(균등 가정)
mask=(np.abs(z)>2)&~np.isnan(z)
idx=np.where(mask)[0]; ev=[]; last=-10**9
for i in idx:
    if i-last>=360 and i+K<n and i-W>=0: ev.append(i); last=i
ev=np.array(ev)
def liq_poc(i):
    px=c[i-W:i]; dOI=oichg[i-W:i]; dr=np.sign(ret1[i-W:i])  # OI변화 방향(가격기준)
    m=(~np.isnan(px))&(~np.isnan(dOI))&(dOI>0)              # 신규 포지션만(OI증가)
    if m.sum()<200: return np.nan
    px=px[m]; w=dOI[m]; dr=dr[m]
    lo,hi=px.min()*0.8, px.max()*1.2
    bins=np.linspace(lo,hi,200); heat=np.zeros(200)
    for lev,lw in zip(LEVS,LEVW):
        liq_long = px*(1-1/lev)   # 롱 청산가(아래)
        liq_short= px*(1+1/lev)   # 숏 청산가(위)
        wl=w*lw*np.clip(dr,0,1); ws=w*lw*np.clip(-dr,0,1)   # 가격상승=롱신규,하락=숏신규
        for liq,wt in [(liq_long,wl),(liq_short,ws)]:
            bi=np.clip(np.digitize(liq,bins),0,199); np.add.at(heat,bi,wt)
    return bins[int(np.argmax(heat))]
hit_oi=[]; hit_liq=[]
for i in ev:
    # 단순 OI POC (대조)
    px=c[i-W:i]; w0=np.abs(oichg[i-W:i]); m=(~np.isnan(px))&(~np.isnan(w0))
    if m.sum()<200: continue
    b=np.linspace(px[m].min(),px[m].max(),60); bi=np.clip(np.digitize(px[m],b),0,59)
    bu=np.zeros(60); np.add.at(bu,bi,w0[m]); oipoc=b[int(np.argmax(bu))]
    lpoc=liq_poc(i)
    if np.isnan(lpoc): continue
    fwd=np.sign(c[i+K]-c[i])
    hit_oi.append(np.sign(oipoc-c[i])==fwd)
    hit_liq.append(np.sign(lpoc-c[i])==fwd)
hit_oi=np.array(hit_oi); hit_liq=np.array(hit_liq)
print(f"[청산 히트맵 POC vs 단순 OI POC] OI spike {len(hit_liq)}건, forward 6h")
print(f"  단순 OI POC 자석 적중률 : {100*hit_oi.mean():.1f}%")
print(f"  ★청산 히트맵 POC 적중률 : {100*hit_liq.mean():.1f}%  (baseline 50%)")
print(f"  레버분포 {LEVS} 균등, ΔOI>0 신규만, 방향=1h가격, 7일윈도우")
