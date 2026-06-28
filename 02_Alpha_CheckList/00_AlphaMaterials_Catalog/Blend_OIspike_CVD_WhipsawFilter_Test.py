# -*- coding: utf-8 -*-
# [Blend] OI spike(변동성) + CVD(실수급 방향) 배합 → "휩쏘 vs 진짜 변동" 구분되나?
#   CVD = rolling 1h 순테이커매수 / 거래량 (-1~1). OI spike 시점 |CVD| 강도로 그룹 분리.
#   진입방향 = CVD 부호. forward 6h MAE/MFE/final(진입방향 기준). 강CVD=추세? 약CVD=휩쏘?
import os, numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
DATA=r"D:\ML\RfRauto\08_BTC_Data\derived\Merged_Data.csv"
OUT=r"D:\ML\RfRauto\02_Alpha_CheckList\00_AlphaMaterials_Catalog\graphs\Blend_OIspike_CVD_WhipsawFilter_Result.png"
W=1440; COOL=360; K=360  # z롤링24h, 쿨다운6h, forward 6h
d=pd.read_csv(DATA,usecols=["timestamp","close","volume","taker_buy_volume","oi_change_1h_pct","oi_was_missing"])
c=d["close"].values.astype(float); vol=d["volume"].values.astype(float); tbv=d["taker_buy_volume"].values.astype(float)
net=2*tbv-vol  # 순테이커매수(+매수우위)
sv=pd.Series(net).rolling(60).sum().values; vv=pd.Series(vol).rolling(60).sum().values
cvd=np.where(vv>0, sv/vv, np.nan)  # -1~1 매수우위(1h)
oichg=pd.to_numeric(d["oi_change_1h_pct"],errors="coerce")
mu=oichg.rolling(W).mean(); sd=oichg.rolling(W).std(); z=((oichg-mu)/sd).values
miss=pd.to_numeric(d["oi_was_missing"],errors="coerce").fillna(0).values; z[miss==1]=np.nan
n=len(c)
# OI spike 이벤트 (|z|>2, 쿨다운)
mask=(np.abs(z)>2)&~np.isnan(z)&~np.isnan(cvd)
idx=np.where(mask)[0]; ev=[]; last=-10**9
for i in idx:
    if i-last>=COOL and i+K<n: ev.append(i); last=i
ev=np.array(ev)
print(f"[OI spike 이벤트] {len(ev)}건 (|z|>2, 6h쿨다운)")
# 각 이벤트: CVD부호로 진입방향, forward 6h MAE/MFE/final
rows=[]
for i in ev:
    dr=np.sign(cvd[i]);  dr = dr if dr!=0 else 1
    win=c[i:i+K+1]; rel=dr*(win/c[i]-1.0)  # 진입방향 기준 수익곡선
    rows.append((abs(cvd[i]), rel.max(), rel.min(), rel[-1]))
A=np.array(rows)  # [|cvd|, MFE, MAE, final]
cvabs=A[:,0]; MFE=A[:,1]; MAE=A[:,2]; FIN=A[:,3]
# |CVD| 3분위 그룹
q33,q67=np.quantile(cvabs,[.33,.67])
grp={"weak |CVD|":cvabs<=q33, "mid":(cvabs>q33)&(cvabs<=q67), "strong |CVD|":cvabs>q67}
print(f"\n{'group':<14}{'n':>5}{'final%':>9}{'MFE%':>8}{'MAE%':>8}{'win%':>7}{'whip(|MAE|/MFE)':>16}")
res={}
for g,m in grp.items():
    f=FIN[m]; mf=MFE[m]; ma=MAE[m]
    whip=np.mean(np.abs(ma)/np.maximum(mf,1e-9))
    res[g]=(len(f),f.mean()*100,mf.mean()*100,ma.mean()*100,100*(f>0).mean(),whip)
    print(f"{g:<14}{len(f):>5}{f.mean()*100:>+9.3f}{mf.mean()*100:>+8.3f}{ma.mean()*100:>+8.3f}{100*(f>0).mean():>6.0f}%{whip:>16.2f}")
# ── 그래프 ──
gl=list(grp.keys()); col=["crimson","gray","seagreen"]
fig,ax=plt.subplots(2,3,figsize=(17,9.5))
ax[0,0].bar(gl,[res[g][1] for g in gl],color=col); ax[0,0].axhline(0,c="k",lw=.6); ax[0,0].set_ylabel("final ret % (entry=CVD dir)")
ax[0,0].set_title("(1) Directional final return\nstrong CVD higher = direction survives?")
x=np.arange(3); w=0.35
ax[0,1].bar(x-w/2,[res[g][2] for g in gl],w,label="MFE(up)",color="seagreen")
ax[0,1].bar(x+w/2,[res[g][3] for g in gl],w,label="MAE(down)",color="crimson")
ax[0,1].set_xticks(x); ax[0,1].set_xticklabels(gl,fontsize=8); ax[0,1].legend(); ax[0,1].set_title("(2) MFE vs MAE\nwhipsaw=both big & cancel")
ax[0,2].bar(gl,[res[g][4] for g in gl],color=col); ax[0,2].axhline(50,c="k",ls=":"); ax[0,2].set_ylabel("win% (final>0)")
ax[0,2].set_title("(3) Hit rate\n>50% = CVD picks direction")
ax[1,0].bar(gl,[res[g][5] for g in gl],color=col); ax[1,0].set_ylabel("|MAE|/MFE")
ax[1,0].set_title("(4) Whipsaw index\nhigh=chop(round-trip), low=trend")
# signed equity (strong vs weak)
for g,cc in [("weak |CVD|","crimson"),("strong |CVD|","seagreen")]:
    eq=np.cumprod(1+FIN[grp[g]]); ax[1,1].plot(eq,label=g,c=cc)
ax[1,1].legend(); ax[1,1].set_title("(5) Cumprod of CVD-dir entries"); ax[1,1].axhline(1,c="k",lw=.5)
ax[1,2].axis("off")
sg=res["strong |CVD|"]; wk=res["weak |CVD|"]
verdict=("BLEND TEST: OI spike + CVD\n\n"
        f"strong|CVD|: final {sg[1]:+.3f}% win {sg[4]:.0f}% whip {sg[5]:.2f}\n"
        f"weak  |CVD|: final {wk[1]:+.3f}% win {wk[4]:.0f}% whip {wk[5]:.2f}\n\n"
        "READ:\n"
        " - strong final>weak & win>50 => CVD picks\n"
        "   real move (use as entry direction)\n"
        " - weak whip high => that is the whipsaw\n"
        "   (avoid entry / widen SL there)\n\n"
        "If separation is clear => ingredient blend WORKS")
ax[1,2].text(0,0.95,verdict,fontsize=9,va="top",family="monospace")
plt.suptitle("Blend: OI spike (vol) + CVD (real flow) -> whipsaw vs real move",fontsize=13)
plt.tight_layout(); plt.savefig(OUT,dpi=110); print("\n[graph]",OUT)
try: os.startfile(OUT)
except Exception as e: print("open fail",e)
