# -*- coding: utf-8 -*-
# [ML] 직교 마이크로구조 재료들 -> GBM 비선형 최적조합 -> forward 6h return 신호 증폭.
#   ★검증: 시간순 train(앞70%)/OOS(뒤30%). in-sample IC vs OOS IC. 과적합 경계. 피처중요도.
import os, numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
try:
    from sklearn.ensemble import GradientBoostingRegressor
    from scipy.stats import spearmanr; HAS=True
except Exception as e:
    HAS=False; print("sklearn/scipy 없음:",e)
DATA=r"D:\ML\RfRauto\08_BTC_Data\derived\Merged_Data.csv"
OUT=r"D:\ML\RfRauto\02_Alpha_CheckList\00_AlphaMaterials_Catalog\graphs\ML_SignalAmplify_Result.png"
use=["timestamp","close","volume","taker_buy_volume","oi_change_1h_pct","oi_change_5m_pct",
     "oi_change_15m_pct","oi_zscore_24h","oi_was_missing","top_count_ls","top_sum_ls","count_ls",
     "top_retail_divergence","taker_imbalance_5m_avg","taker_vol_ls","count"]
d=pd.read_csv(DATA,usecols=use)
c=d["close"].values.astype(float); vol=d["volume"].values.astype(float); tbv=d["taker_buy_volume"].values.astype(float)
ret1=pd.Series(c).pct_change()
net=2*tbv-vol
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
volz=(pd.Series(vol)-pd.Series(vol).rolling(1440).mean())/pd.Series(vol).rolling(1440).std()
F["vol_z"]=volz.values
K=360; y=np.roll(c,-K)/c-1.0; y[-K:]=np.nan
X=pd.DataFrame(F); n=len(c)
samp=np.zeros(n,bool); samp[::60]=True   # 60분 간격 샘플(중첩완화)
ok=samp & X.notna().all(axis=1).values & ~np.isnan(y) & (np.arange(n)>1440) & (np.arange(n)<n-K)
Xs=X[ok].reset_index(drop=True); ys=y[ok]; cols=list(Xs.columns)
print(f"[ML] 샘플 {len(Xs)}건 · 피처 {len(cols)}개 · 타겟=forward {K}분 수익")
if HAS:
    sp=int(len(Xs)*0.7)
    Xtr,ytr=Xs.iloc[:sp].values,ys[:sp]; Xte,yte=Xs.iloc[sp:].values,ys[sp:]
    m=GradientBoostingRegressor(n_estimators=300,max_depth=3,subsample=0.7,learning_rate=0.02,random_state=0)
    m.fit(Xtr,ytr)
    ptr=m.predict(Xtr); pte=m.predict(Xte)
    ic_tr=spearmanr(ptr,ytr).correlation; ic_te=spearmanr(pte,yte).correlation
    print(f"\n[신호강도 IC(Spearman)]  in-sample {ic_tr:+.4f}  |  ★OOS {ic_te:+.4f}")
    print("  (OOS IC가 양수로 살아있어야 진짜 증폭. in-sample만 높으면 과적합)")
    # OOS 분위별 forward 수익 (상위 예측 vs 하위)
    q=pd.qcut(pte,5,labels=False,duplicates="drop")
    print("\n[OOS 예측분위별 실제 forward 6h 수익]")
    qm=[]
    for g in range(5):
        mm=q==g; qm.append(yte[mm].mean()*100)
        print(f"  Q{g+1}: n{mm.sum()} 평균 {yte[mm].mean()*100:+.3f}%  승률 {100*(yte[mm]>0).mean():.0f}%")
    spread=qm[-1]-qm[0]; print(f"  ★롱숏 스프레드(Q5-Q1) {spread:+.3f}%")
    imp=sorted(zip(cols,m.feature_importances_),key=lambda x:-x[1])
    print("\n[피처 중요도 top]")
    for k,v in imp[:8]: print(f"  {k:<16}{v:.3f}")
    # 그래프
    fig,ax=plt.subplots(2,2,figsize=(15,9))
    ax[0,0].bar(["in-sample","OOS"],[ic_tr,ic_te],color=["gray","seagreen"]); ax[0,0].axhline(0,c="k",lw=.6)
    ax[0,0].set_title(f"(1) Signal IC: in {ic_tr:+.3f} vs OOS {ic_te:+.3f}\n(OOS must stay + = real)")
    ax[0,1].bar([f"Q{i+1}" for i in range(len(qm))],qm,color=["crimson" if v<0 else "seagreen" for v in qm])
    ax[0,1].set_title(f"(2) OOS fwd ret by predicted quintile\nspread Q5-Q1 {spread:+.3f}%"); ax[0,1].axhline(0,c="k",lw=.6)
    nm=[k for k,_ in imp[:10]][::-1]; vl=[v for _,v in imp[:10]][::-1]
    ax[1,0].barh(nm,vl,color="steelblue"); ax[1,0].set_title("(3) Feature importance (top10)")
    eq=np.cumprod(1+np.where(q==4,yte,0)); ax[1,1].plot(eq,c="navy",label="long top-Q5 only")
    ax[1,1].plot(np.cumprod(1+np.where(q==0,-yte,0)),c="crimson",label="short bot-Q1")
    ax[1,1].legend(); ax[1,1].set_title("(4) OOS equity: trade only extreme signal")
    plt.suptitle("ML signal amplify: orthogonal microstructure -> GBM (OOS honest)",fontsize=13)
    plt.tight_layout(); plt.savefig(OUT,dpi=110); print("\n[graph]",OUT)
    try: os.startfile(OUT)
    except: pass
