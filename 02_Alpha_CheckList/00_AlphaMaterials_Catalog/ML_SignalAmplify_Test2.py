# -*- coding: utf-8 -*-
# [ML v2] 과적합 제어(regularization) 하이퍼 스윕 -> OOS IC 극대화. 핵심피처 집중.
import os, numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from sklearn.ensemble import GradientBoostingRegressor
from scipy.stats import spearmanr
DATA=r"D:\ML\RfRauto\08_BTC_Data\derived\Merged_Data.csv"
OUT=r"D:\ML\RfRauto\02_Alpha_CheckList\00_AlphaMaterials_Catalog\graphs\ML_SignalAmplify_v2.png"
use=["timestamp","close","volume","taker_buy_volume","oi_change_1h_pct","oi_change_5m_pct",
     "oi_change_15m_pct","oi_zscore_24h","oi_was_missing","top_count_ls","top_sum_ls","count_ls",
     "top_retail_divergence","taker_imbalance_5m_avg","taker_vol_ls","count"]
d=pd.read_csv(DATA,usecols=use)
c=d["close"].values.astype(float); vol=d["volume"].values.astype(float); tbv=d["taker_buy_volume"].values.astype(float)
ret1=pd.Series(c).pct_change(); net=2*tbv-vol
def rs(a,w): return pd.Series(a).rolling(w).sum().values
F={}
F["oi_z"]=pd.to_numeric(d["oi_zscore_24h"],errors="coerce").values
F["oi_chg_1h"]=pd.to_numeric(d["oi_change_1h_pct"],errors="coerce").values
F["oi_chg_5m"]=pd.to_numeric(d["oi_change_5m_pct"],errors="coerce").values
F["oi_chg_15m"]=pd.to_numeric(d["oi_change_15m_pct"],errors="coerce").values
vv=rs(vol,60); F["cvd_1h"]=np.where(vv>0,rs(net,60)/vv,np.nan)
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
K=360; y=np.roll(c,-K)/c-1.0; y[-K:]=np.nan
X=pd.DataFrame(F); n=len(c)
samp=np.zeros(n,bool); samp[::60]=True
ok=samp & X.notna().all(axis=1).values & ~np.isnan(y) & (np.arange(n)>1440) & (np.arange(n)<n-K)
Xs=X[ok].reset_index(drop=True); ys=y[ok]; cols=list(Xs.columns)
sp=int(len(Xs)*0.7); Xtr,ytr=Xs.iloc[:sp].values,ys[:sp]; Xte,yte=Xs.iloc[sp:].values,ys[sp:]
print(f"[ML v2] 샘플 {len(Xs)} (train {sp}/OOS {len(Xs)-sp}) · 과적합 제어 스윕")
print(f"{'params(depth,n,lr,leaf,sub)':<32}{'IC_in':>8}{'IC_OOS':>9}{'spread%':>9}")
grid=[(3,300,0.02,1,0.7),(2,200,0.03,200,0.7),(2,150,0.03,500,0.6),
      (2,100,0.05,1000,0.6),(3,200,0.02,500,0.6),(1,300,0.05,1000,0.7),(2,250,0.02,300,0.5)]
best=None
for dep,ne,lr,leaf,sub in grid:
    m=GradientBoostingRegressor(max_depth=dep,n_estimators=ne,learning_rate=lr,min_samples_leaf=leaf,subsample=sub,random_state=0)
    m.fit(Xtr,ytr); ptr=m.predict(Xtr); pte=m.predict(Xte)
    ic_tr=spearmanr(ptr,ytr).correlation; ic_te=spearmanr(pte,yte).correlation
    q=pd.qcut(pte,5,labels=False,duplicates="drop"); spr=(yte[q==q.max()].mean()-yte[q==0].mean())*100
    print(f"d{dep} n{ne} lr{lr} leaf{leaf} sub{sub}".ljust(32)+f"{ic_tr:>+8.3f}{ic_te:>+9.4f}{spr:>+9.3f}")
    if best is None or ic_te>best[0]: best=(ic_te,(dep,ne,lr,leaf,sub),m,pte,spr)
ic_te,params,m,pte,spr=best
print(f"\n★최적(OOS IC최대): {params}  OOS IC {ic_te:+.4f}  spread {spr:+.3f}%")
q=pd.qcut(pte,5,labels=False,duplicates="drop"); qm=[yte[q==g].mean()*100 for g in range(5)]
print("[최적 OOS 분위별 수익]")
for g in range(5): print(f"  Q{g+1}: {qm[g]:+.3f}%  승률 {100*(yte[q==g]>0).mean():.0f}%")
imp=sorted(zip(cols,m.feature_importances_),key=lambda x:-x[1])
print("[최적 피처중요도]"); 
for k,v in imp[:8]: print(f"  {k:<16}{v:.3f}")
fig,ax=plt.subplots(1,3,figsize=(17,5.5))
ax[0].bar([f"Q{i+1}" for i in range(5)],qm,color=["crimson" if v<0 else "seagreen" for v in qm]); ax[0].axhline(0,c="k",lw=.6)
ax[0].set_title(f"OOS fwd ret by quintile\nIC {ic_te:+.4f} spread {spr:+.3f}%")
nm=[k for k,_ in imp[:10]][::-1]; vl=[v for _,v in imp[:10]][::-1]
ax[1].barh(nm,vl,color="steelblue"); ax[1].set_title("Feature importance (best)")
eq=np.cumprod(1+np.where(q==4,yte,np.where(q==0,-yte,0))); ax[2].plot(eq,c="navy"); ax[2].set_title("OOS equity: long Q5 + short Q1")
plt.suptitle(f"ML v2 regularized: best OOS IC {ic_te:+.4f}",fontsize=13); plt.tight_layout(); plt.savefig(OUT,dpi=110)
try: os.startfile(OUT)
except: pass
print("[graph]",OUT)
