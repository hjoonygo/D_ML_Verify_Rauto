# -*- coding: utf-8 -*-
# [WinnerMonthly] 음수월 최소 승자(R+P80+결합오버레이, exp재사이징−20)의 월별 분포 (세션 260626_02).
import os, sys, json, glob
ROOT = os.path.dirname(os.path.abspath(__file__))
for _ in range(5):
    if os.path.isdir(os.path.join(ROOT,"08_BTC_Data")) and os.path.isdir(os.path.join(ROOT,"04_공용엔진코드")): break
    ROOT=os.path.dirname(ROOT)
RES=os.path.join(ROOT,"03_IDEA4Bot","260623_07_RfRautoAlphaUp")
sys.path.insert(0,os.path.join(ROOT,"04_공용엔진코드","engines")); sys.path.insert(0,RES)
from path_finder import ensure_paths; ensure_paths()
import numpy as np, pandas as pd
import bt_full as B
from blend_opt import rev_side
from fib_replay_1m import load_funding
import rauto_datafeed as DF
from rauto_cex import FeeModel, SlipModel, MMR_T1, MMR_T2, TIER, LIQ_SLIP, LIQ_COST, MK, TK
MERGED=os.path.join(ROOT,"08_BTC_Data","derived","Merged_Data.csv"); MIRROR=r"D:\ML\Verify\08 BTC_Data\BinanceData_AWS_Mirror"
LEV=6.0; DD_THR,DD_SCALE=-0.08,0.5; TP=0.8; GLO,GHI=-10,12


def build_d1m():
    m=pd.read_csv(MERGED,usecols=["timestamp","open","high","low","close","oi_sum"]); m["t"]=pd.to_datetime(m["timestamp"],utc=True,format="ISO8601").dt.tz_localize(None); m=m.dropna(subset=["open"]).set_index("t").sort_index()
    end=m.index.max(); kl=DF.fetch_klines_1m_range(60)
    bk=pd.DataFrame({"open":[k[1] for k in kl],"high":[k[2] for k in kl],"low":[k[3] for k in kl],"close":[k[4] for k in kl]},index=pd.to_datetime([k[0] for k in kl],unit="ms")); bk=bk[bk.index>end].sort_index()
    oi=pd.Series(np.nan,index=bk.index); rows=[]
    for fp in sorted(glob.glob(os.path.join(MIRROR,"BTCUSDT_1m_2026*.csv"))): rows.append(pd.read_csv(fp,usecols=["ts_utc","open_interest"]))
    if rows:
        mm=pd.concat(rows,ignore_index=True); mm["t"]=pd.to_datetime(mm["ts_utc"],format="%Y-%m-%d %H:%M:%S"); mm=mm.drop_duplicates("t").set_index("t"); oi=oi.fillna(mm["open_interest"].reindex(bk.index))
    try:
        oih=DF.fetch_oi_hist(30); oh=pd.Series([o[1] for o in oih],index=pd.to_datetime([o[0] for o in oih],unit="ms")).reindex(bk.index,method="ffill"); oi=oi.fillna(oh)
    except Exception: pass
    oi=oi.ffill().bfill()
    ohlc=pd.concat([m[["open","high","low","close"]],bk]); ohlc=ohlc[~ohlc.index.duplicated(keep="first")].sort_index()
    raw=pd.concat([m["oi_sum"],oi]); raw=raw[~raw.index.duplicated(keep="first")].reindex(ohlc.index).ffill(); ohlc["oi_zscore_24h"]=DF.oi_zscore_from_series(raw).values
    return ohlc


def main():
    p=json.load(open(os.path.join(RES,"back2tv_rev_winners.json")))["REV_MDD25_36mo"]["p"]
    d=build_d1m(); fund=load_funding(); _,side=rev_side(d,p["rev_tf"],p["q"],p["qwin"])
    T=B.gen_trades(d,fund,p["rev_tf"],p["piv"],p["N"],(p["f1"],p["f2"],p["f3"]),p["iam"],er_gate=0.0,ext_side=side,align_pivot=True,use_trend_flip=False,arm_bars=p["arm"],tp_frac=TP).sort_values("et").reset_index(drop=True)
    fee=FeeModel(); slip=SlipModel(0.0,1.0); sl=slip.market_exit_slip()
    R=T["R"].values.astype(float); FUND=T["fund"].values.astype(float); MAE=T["mae"].values.astype(float); REA=T["reason"].values
    Rnet=np.array([R[i]+MK+TK+FUND[i]-fee.entry_cost(False)-fee.exit_cost(REA[i])-FUND[i]-(sl if REA[i]!="tp" else 0) for i in range(len(R))])
    ets=pd.to_datetime(T["et"]).values; sd=T["side"].astype(int).values; mc=d["close"].values; mt=d.index.values
    r30=np.zeros(len(T))
    for i in range(len(T)):
        a=int(np.searchsorted(mt,np.datetime64(pd.Timestamp(ets[i])),"left"))
        if a>0: r30[i]=(mc[a]/mc[max(0,a-43200)]-1)*100
    gate=np.where(((r30<GLO)&(sd==1))|((r30>GHI)&(sd==-1)),0.0,1.0)

    def comp(exp0):
        bal=10000.0;peak=10000.0;mdd=0.0;p_=np.empty(len(Rnet))
        for i in range(len(Rnet)):
            m=gate[i]
            if (bal/peak-1.0)<=DD_THR: m*=DD_SCALE
            exp=exp0*m; mmr=MMR_T2 if exp*bal>TIER else MMR_T1; hsd=1.0/LEV-mmr-LIQ_SLIP
            pp=(-exp*(hsd+LIQ_COST+abs(FUND[i])) if MAE[i]<=-hsd else Rnet[i]*exp); bal*=(1+pp);peak=max(peak,bal);mdd=min(mdd,bal/peak-1);p_[i]=pp
        return p_,(bal/1e4-1)*100,mdd*100
    # MDD−20 재사이징
    exp=2.5; res=None
    for e in np.arange(2.5,6.01,0.1):
        pp,tot,mdd=comp(e)
        if mdd>=-20.0: exp,res=(e,(pp,tot,mdd))
        else: break
    pp,tot,mdd=res
    s=pd.Series(pp,index=pd.to_datetime(ets)); mo=s.groupby(pd.Grouper(freq="MS")).apply(lambda x:(1+x).prod()-1)*100
    print("="*78); print(f"[음수월 최소 승자 — R+P80+레짐오버레이, exp{exp:.1f}/lev{LEV}] 전기간 {tot:+.0f}% · MDD {mdd:.1f}%"); print("="*78)
    print(f"음수월 {int((mo<0).sum())}/{len(mo)} (양수 {100*(mo>=0).mean():.0f}%) · 평균월 {mo.mean():+.1f}% · 최악월 {mo.min():+.1f}% · 최고월 {mo.max():+.1f}%")
    print("\n[월별 수익률 그리드 % — ●=음수]")
    df=mo.to_frame("r"); df["y"]=df.index.year; df["m"]=df.index.month
    print("연도   " + "".join(f"{mm:>7}" for mm in range(1,13)))
    for y in sorted(df["y"].unique()):
        cells=[]
        for mm in range(1,13):
            v=df[(df.y==y)&(df.m==mm)]["r"]
            if len(v)==0: cells.append(f"{'·':>7}")
            else:
                x=v.iloc[0]; cells.append(f"{('●' if x<0 else '')}{x:>+6.0f}")
        print(f"{y}  "+"".join(cells))
    print(f"\n[최근 2달] " + " · ".join(f"{idx.strftime('%y-%m')} {v:+.1f}%" for idx,v in mo[mo.index>=pd.Timestamp('2026-05-01')].items()))
    print("\n[해석] 음수월 최소가 목표. 음수월도 대부분 한 자릿수%(평균월 +대비 작음)면 꾸준=좋음. in-sample 천장이라 채택은 OOS·페이퍼 後.")
    return True


if __name__=="__main__": main()
