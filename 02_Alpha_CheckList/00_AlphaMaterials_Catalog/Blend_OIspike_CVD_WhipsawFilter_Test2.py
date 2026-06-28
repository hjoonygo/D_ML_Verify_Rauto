# -*- coding: utf-8 -*-
# [Blend v2] 휩쏘 직접정의 + OI방향-CVD일치. 휩쏘=진입후 손절(-TH)건드리고 final>0(역행후회복).
#   진짜추세=final>=TH. 그룹: (OI 증/감) x (|CVD| 강/약). 어느 배합이 휩쏘 적고 추세 많나?
import os, numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
DATA=r"D:\ML\RfRauto\08_BTC_Data\derived\Merged_Data.csv"
OUT=r"D:\ML\RfRauto\02_Alpha_CheckList\00_AlphaMaterials_Catalog\graphs\Blend_OIspike_CVD_WhipsawFilter_v2.png"
W=1440; COOL=360; K=360; TH=0.008  # 손절/추세 임계 0.8%
d=pd.read_csv(DATA,usecols=["timestamp","close","volume","taker_buy_volume","oi_change_1h_pct","oi_was_missing"])
c=d["close"].values.astype(float); vol=d["volume"].values.astype(float); tbv=d["taker_buy_volume"].values.astype(float)
net=2*tbv-vol; sv=pd.Series(net).rolling(60).sum().values; vv=pd.Series(vol).rolling(60).sum().values
cvd=np.where(vv>0, sv/vv, np.nan)
oichg=pd.to_numeric(d["oi_change_1h_pct"],errors="coerce")
mu=oichg.rolling(W).mean(); sd=oichg.rolling(W).std(); z=((oichg-mu)/sd).values
oiraw=oichg.values
miss=pd.to_numeric(d["oi_was_missing"],errors="coerce").fillna(0).values; z[miss==1]=np.nan
n=len(c)
mask=(np.abs(z)>2)&~np.isnan(z)&~np.isnan(cvd)
idx=np.where(mask)[0]; ev=[]; last=-10**9
for i in idx:
    if i-last>=COOL and i+K<n: ev.append(i); last=i
ev=np.array(ev)
cvabs=np.abs(cvd[ev]); med=np.median(cvabs)
rows=[]
for i in ev:
    dr=np.sign(cvd[i]); dr=dr if dr!=0 else 1
    win=c[i:i+K+1]; rel=dr*(win/c[i]-1.0)
    MAE=rel.min(); FIN=rel[-1]; MFE=rel.max()
    whip = (MAE<=-TH) and (FIN>0)      # 역행후 회복 = 휩쏘
    real = FIN>=TH                      # 한방향 지속 = 진짜추세
    loss = FIN<=-TH                     # 역행지속 = 진짜손실
    rows.append((abs(cvd[i]), oiraw[i], dr, MAE, MFE, FIN, whip, real, loss))
A=pd.DataFrame(rows,columns=["cvabs","oi","dir","MAE","MFE","FIN","whip","real","loss"])
A["oi_up"]=A["oi"]>0; A["cvd_strong"]=A["cvabs"]>med
print(f"[이벤트 {len(A)}건] 손절/추세 임계 ±{TH*100:.1f}%, forward 6h")
print(f"{'group':<22}{'n':>5}{'whip%':>8}{'real%':>8}{'loss%':>8}{'final%':>9}{'win%':>7}")
groups=[("OI up + CVD strong",  A.oi_up & A.cvd_strong),
        ("OI up + CVD weak",    A.oi_up & ~A.cvd_strong),
        ("OI down + CVD strong", ~A.oi_up & A.cvd_strong),
        ("OI down + CVD weak",  ~A.oi_up & ~A.cvd_strong),
        ("ALL spikes",           A.index>=0)]
res={}
for g,m in groups:
    s=A[m]
    res[g]=(len(s),100*s.whip.mean(),100*s.real.mean(),100*s.loss.mean(),s.FIN.mean()*100,100*(s.FIN>0).mean())
    print(f"{g:<22}{len(s):>5}{100*s.whip.mean():>7.0f}%{100*s.real.mean():>7.0f}%{100*s.loss.mean():>7.0f}%{s.FIN.mean()*100:>+9.3f}{100*(s.FIN>0).mean():>6.0f}%")
gl=[g for g,_ in groups[:4]]
fig,ax=plt.subplots(2,2,figsize=(15,9))
x=np.arange(4); w=0.27
ax[0,0].bar(x-w,[res[g][1] for g in gl],w,label="whipsaw%",color="orange")
ax[0,0].bar(x,[res[g][2] for g in gl],w,label="real-trend%",color="seagreen")
ax[0,0].bar(x+w,[res[g][3] for g in gl],w,label="real-loss%",color="crimson")
ax[0,0].set_xticks(x); ax[0,0].set_xticklabels(gl,fontsize=7,rotation=10); ax[0,0].legend(); ax[0,0].set_title("(1) Outcome mix by blend\nwant: low whipsaw, high real-trend")
ax[0,1].bar(gl,[res[g][4] for g in gl],color="navy"); ax[0,1].axhline(0,c="k",lw=.6)
ax[0,1].set_xticklabels(gl,fontsize=7,rotation=10); ax[0,1].set_title("(2) Final return % (CVD-dir entry)")
ax[1,0].bar(gl,[res[g][5] for g in gl],color="teal"); ax[1,0].axhline(50,c="k",ls=":")
ax[1,0].set_xticklabels(gl,fontsize=7,rotation=10); ax[1,0].set_title("(3) Win% (final>0)")
ax[1,1].axis("off")
best=max(gl,key=lambda g:res[g][2]-res[g][1])
verdict=("BLEND v2: whipsaw vs real move\n\nper group (whip / real-trend / final):\n"
        +"\n".join(f" {g[:20]:<20} {res[g][1]:.0f}% / {res[g][2]:.0f}% / {res[g][4]:+.2f}%" for g in gl)
        +f"\n\nbest real-minus-whip: {best}\n\n"
        "READ: if one blend has clearly\n LOW whipsaw + HIGH real-trend\n => that is the entry-quality filter")
ax[1,1].text(0,0.95,verdict,fontsize=9,va="top",family="monospace")
plt.suptitle("Blend v2: OI direction x CVD strength -> whipsaw vs real move",fontsize=13)
plt.tight_layout(); plt.savefig(OUT,dpi=110); print("\n[graph]",OUT)
try: os.startfile(OUT)
except Exception as e: print("open fail",e)
