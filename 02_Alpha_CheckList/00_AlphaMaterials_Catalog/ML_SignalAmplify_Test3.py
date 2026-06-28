# -*- coding: utf-8 -*-
# [ML v3] 피처 확장(VPIN·CVD다이버전스·MTF확장·포지셔닝변화) -> OOS IC 한계까지. best params 고정.
import os, numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from sklearn.ensemble import GradientBoostingRegressor
from scipy.stats import spearmanr
DATA=r"D:\ML\RfRauto\08_BTC_Data\derived\Merged_Data.csv"
OUT=r"D:\ML\RfRauto\02_Alpha_CheckList\00_AlphaMaterials_Catalog\graphs\ML_SignalAmplify_v3.png"
use=["timestamp","close","volume","taker_buy_volume","oi_change_1h_pct","oi_change_5m_pct",
     "oi_change_15m_pct","oi_zscore_24h","oi_was_missing","top_count_ls","top_sum_ls","count_ls",
     "top_retail_divergence","taker_imbalance_5m_avg","taker_vol_ls","count"]
d=pd.read_csv(DATA,usecols=use)
c=d["close"].values.astype(float); vol=d["volume"].values.astype(float); tbv=d["taker_buy_volume"].values.astype(float)
ret1=pd.Series(c).pct_change(); net=2*tbv-vol
def rs(a,w): return pd.Series(a).rolling(w).sum().values
def sh(a,w): return pd.Series(a).shift(w).values
F={}
F["oi_z"]=pd.to_numeric(d["oi_zscore_24h"],errors="coerce").values
F["oi_chg_1h"]=pd.to_numeric(d["oi_change_1h_pct"],errors="coerce").values
F["oi_chg_5m"]=pd.to_numeric(d["oi_change_5m_pct"],errors="coerce").values
F["oi_chg_15m"]=pd.to_numeric(d["oi_change_15m_pct"],errors="coerce").values
vv=rs(vol,60); cvd1=np.where(vv>0,rs(net,60)/vv,np.nan); F["cvd_1h"]=cvd1
vv4=rs(vol,240); F["cvd_4h"]=np.where(vv4>0,rs(net,240)/vv4,np.nan)
F["ret_4h"]=c/np.roll(c,240)-1; F["ret_12h"]=c/np.roll(c,720)-1; F["ret_24h"]=c/np.roll(c,1440)-1
F["rvol_1h"]=ret1.rolling(60).std().values
F["top_count_ls"]=pd.to_numeric(d["top_count_ls"],errors="coerce").values
F["top_sum_ls"]=pd.to_numeric(d["top_sum_ls"],errors="coerce").values
F["count_ls"]=pd.to_numeric(d["count_ls"],errors="coerce").values
F["whale_div"]=pd.to_numeric(d["top_retail_divergence"],errors="coerce").values
F["taker_imb"]=pd.to_numeric(d["taker_imbalance_5m_avg"],errors="coerce").values
F["taker_ls"]=pd.to_numeric(d["taker_vol_ls"],errors="coerce").values
volz=(pd.Series(vol)-pd.Series(vol).rolling(1440).mean())/pd.Series(vol).rolling(1440).std(); F["vol_z"]=volz.values
# ── v3 신규 피처 ──
F["vpin_1h"]=np.where(vv>0, rs(np.abs(net),60)/vv, np.nan)          # 주문흐름 독성(불균형 강도)
r1h=c/np.roll(c,60)-1; F["cvd_div"]=r1h*cvd1                          # 가격ret * CVD (음수=다이버전스)
F["ret_2h"]=c/np.roll(c,120)-1; F["ret_48h"]=c/np.roll(c,2880)-1     # MTF 확장
F["oiz_chg"]=F["oi_z"]-sh(F["oi_z"],60)                              # OI z 변화율
F["ls_chg"]=F["top_count_ls"]-sh(F["top_count_ls"],60)              # 포지셔닝 변화율
F["cvd_chg"]=cvd1-sh(cvd1,60)                                        # CVD 변화율
K=360; y=np.roll(c,-K)/c-1.0; y[-K:]=np.nan
X=pd.DataFrame(F); n=len(c)
samp=np.zeros(n,bool); samp[::60]=True
ok=samp & X.notna().all(axis=1).values & ~np.isnan(y) & (np.arange(n)>2880) & (np.arange(n)<n-K)
Xs=X[ok].reset_index(drop=True); ys=y[ok]; cols=list(Xs.columns)
sp=int(len(Xs)*0.7); Xtr,ytr=Xs.iloc[:sp].values,ys[:sp]; Xte,yte=Xs.iloc[sp:].values,ys[sp:]
print(f"[ML v3] 샘플 {len(Xs)} · 피처 {len(cols)}개 (v2 17 + 신규 6)")
m=GradientBoostingRegressor(max_depth=2,n_estimators=100,learning_rate=0.05,min_samples_leaf=1000,subsample=0.6,random_state=0)
m.fit(Xtr,ytr); ptr=m.predict(Xtr); pte=m.predict(Xte)
ic_tr=spearmanr(ptr,ytr).correlation; ic_te=spearmanr(pte,yte).correlation
q=pd.qcut(pte,5,labels=False,duplicates="drop"); qm=[yte[q==g].mean()*100 for g in range(5)]; spr=qm[-1]-qm[0]
print(f"[신호강도] in {ic_tr:+.3f}  ★OOS {ic_te:+.4f}  (v2 OOS +0.0225)  spread {spr:+.3f}%")
print("[OOS 분위별 수익]")
for g in range(5): print(f"  Q{g+1}: {qm[g]:+.3f}%  승률 {100*(yte[q==g]>0).mean():.0f}%")
imp=sorted(zip(cols,m.feature_importances_),key=lambda x:-x[1])
print("[피처중요도 top10]")
for k,v in imp[:10]: print(f"  {k:<16}{v:.3f}")
fig,ax=plt.subplots(1,3,figsize=(17,5.5))
ax[0].bar([f"Q{i+1}" for i in range(5)],qm,color=["crimson" if v<0 else "seagreen" for v in qm]); ax[0].axhline(0,c="k",lw=.6)
ax[0].set_title(f"v3 OOS quintile\nIC {ic_te:+.4f} spread {spr:+.3f}%")
nm=[k for k,_ in imp[:12]][::-1]; vl=[v for _,v in imp[:12]][::-1]; ax[1].barh(nm,vl,color="steelblue"); ax[1].set_title("v3 feature importance")
eq=np.cumprod(1+np.where(q==4,yte,np.where(q==0,-yte,0))); ax[2].plot(eq,c="navy"); ax[2].set_title("OOS equity: long Q5 + short Q1")
plt.suptitle(f"ML v3: {len(cols)} features, OOS IC {ic_te:+.4f}",fontsize=13); plt.tight_layout(); plt.savefig(OUT,dpi=110)
try: os.startfile(OUT)
except: pass
print("[graph]",OUT)
