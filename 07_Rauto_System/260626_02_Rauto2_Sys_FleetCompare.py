# -*- coding: utf-8 -*-
# [FleetCompare] 11개 우수세팅 비교 — 강제청산·레짐별수익·수익달 (세션 260626_02_Rauto2_Sys).
#   캡틴: 각각 우수했던 세팅 전수 → 강제청산횟수 + 레짐별(상승/하락/횡보) 수익 + 양수월/음수월.
#   ★검증엔진 무수정 호출. 레짐스텝=exit_upgrade.build_scale(1.4). 게이트=추세역행 side-mask. DD컷=자기자본 −8%→×0.5.
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
import exit_upgrade as EU
from rauto_cex import FeeModel, SlipModel, MMR_T1, MMR_T2, TIER, LIQ_SLIP, LIQ_COST, MK, TK
MERGED=os.path.join(ROOT,"08_BTC_Data","derived","Merged_Data.csv"); MIRROR=r"D:\ML\Verify\08 BTC_Data\BinanceData_AWS_Mirror"
DD_THR,DD_SCALE=-0.08,0.5


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


def rnet(T):
    fee=FeeModel(); sl=SlipModel(0.0,1.0).market_exit_slip()
    R=T["R"].values.astype(float); F=T["fund"].values.astype(float); REA=T["reason"].values if "reason" in T else np.array(["fibstop"]*len(R))
    return np.array([R[i]+MK+TK+F[i]-fee.entry_cost(False)-fee.exit_cost(REA[i])-F[i]-(sl if REA[i]!="tp" else 0) for i in range(len(R))])


def per_trade_p(Rn, MAE, F, lev, exp0, gate=None, dd=False):
    """per-trade p + nliq. gate=side-mask(0/1), dd=자기DD컷."""
    bal=10000.0; peak=10000.0; nliq=0; p=np.empty(len(Rn))
    for i in range(len(Rn)):
        m=1.0 if gate is None else gate[i]
        if dd and (bal/peak-1.0)<=DD_THR: m*=DD_SCALE
        exp=exp0*m; mmr=MMR_T2 if exp*bal>TIER else MMR_T1; hsd=1.0/lev-mmr-LIQ_SLIP
        if MAE[i]<=-hsd: pp=-exp*(hsd+LIQ_COST+abs(F[i])); nliq+=1
        else: pp=Rn[i]*exp
        bal*=(1+pp); peak=max(peak,bal); p[i]=pp
    return p, nliq, (bal/1e4-1)*100


def reg7(T, d):
    mc=d["close"].values; mt=d.index.values; ets=pd.to_datetime(T["et"]).values; out=[]
    for i in range(len(T)):
        a=int(np.searchsorted(mt,np.datetime64(pd.Timestamp(ets[i])),"left"))
        ch=(mc[a]/mc[max(0,a-10080)]-1)*100 if a>0 else 0
        out.append("up" if ch>3 else ("down" if ch<-3 else "range"))
    return np.array(out)


def main():
    p=json.load(open(os.path.join(RES,"back2tv_rev_winners.json")))["REV_MDD25_36mo"]["p"]
    d=build_d1m(); fund=load_funding(); _,side=rev_side(d,p["rev_tf"],p["q"],p["qwin"]); EU.T_TF=p["rev_tf"]
    sc14,_=EU.build_scale(d,p,1.4)
    def gen(tp, scale):
        return B.gen_trades(d,fund,p["rev_tf"],p["piv"],p["N"],(p["f1"],p["f2"],p["f3"]),p["iam"],er_gate=0.0,ext_side=side,
                            align_pivot=True,use_trend_flip=False,arm_bars=p["arm"],fib_scale=scale,tp_frac=tp).sort_values("et").reset_index(drop=True)
    print("거래생성(4종)...", flush=True)
    L={"tp0":gen(0.0,None), "tp07s":gen(0.7,sc14), "tp07":gen(0.7,None), "tp08":gen(0.8,None)}
    meta={}
    for k,T in L.items():
        Rn=rnet(T); reg=reg7(T,d); r30=np.zeros(len(T)); mc=d["close"].values; mt=d.index.values; ets=pd.to_datetime(T["et"]).values
        for i in range(len(T)):
            a=int(np.searchsorted(mt,np.datetime64(pd.Timestamp(ets[i])),"left"));
            if a>0: r30[i]=(mc[a]/mc[max(0,a-43200)]-1)*100
        sd=T["side"].astype(int).values; gate=np.where(((r30<-10)&(sd==1))|((r30>12)&(sd==-1)),0.0,1.0)
        meta[k]=(T,Rn,T["mae"].values.astype(float),T["fund"].values.astype(float),reg,gate,ets)

    # (이름, ledger, lev, sz, gate?, dd?)
    cfgs=[
        ("1.앵커(tp0)","tp0",3,75,False,False),
        ("2.M0천장tp0","tp0",13,100,False,False),
        ("3.M0천장R+P70","tp07s",16,100,False,False),
        ("4.M30","tp07s",8,65,False,False),
        ("5.M25","tp07s",5,85,False,False),
        ("6.M20(R+P70)","tp07s",6,55,False,False),
        ("7.R+P70단순","tp07",6,55,False,False),
        ("8.M4b DD컷","tp07",6,55,False,True),
        ("9.M5게이트","tp07",6,55,True,False),
        ("10.결합exp3.3","tp07",6,55,True,True),
        ("11.결합R+P80(음수월최소)","tp08",6,75,True,True),
    ]
    print("\n"+"="*108)
    print("[11 우수세팅 비교] 강제청산 · 레짐별수익(상승/하락/횡보 7일추세, 사이즈드 복리%) · 양수월/음수월 · 현실비용")
    print("="*108)
    print(f"{'세팅':<22}{'전기간':>9}{'MDD':>7}{'강제청산':>7}{'상승장':>9}{'하락장':>9}{'횡보장':>9}{'+월/-월':>9}")
    for nm,lk,lev,sz,g,dd in cfgs:
        T,Rn,MAE,F,reg,gate,ets=meta[lk]; exp0=sz/100.0*lev
        pp,nliq,tot=per_trade_p(Rn,MAE,F,lev,exp0,gate=(gate if g else None),dd=dd)
        # MDD
        bal=10000.0;peak=10000.0;mdd=0.0
        for x in pp: bal*=(1+x);peak=max(peak,bal);mdd=min(mdd,bal/peak-1)
        # 레짐별 복리
        def regc(r):
            sel=pp[reg==r]; return (np.prod(1+sel)-1)*100 if len(sel) else 0.0
        # 월별
        mo=pd.Series(pp,index=pd.to_datetime(ets)).groupby(pd.Grouper(freq="MS")).apply(lambda x:(1+x).prod()-1)
        pos=int((mo>=0).sum()); neg=int((mo<0).sum())
        print(f"{nm:<22}{tot:>+8.0f}%{mdd*100:>6.1f}%{nliq:>6}{regc('up'):>+8.0f}%{regc('down'):>+8.0f}%{regc('range'):>+8.0f}%{f'{pos}/{neg}':>9}")
    print("\n[설명] 레짐별수익=그 장세 거래만 복리(상승/하락/횡보는 진입시 7일추세 >+3/<-3/그외). 강제청산=격리마진 청산횟수.")
    print("       +월/-월=양수월/음수월 개수(38개월 중). 전부 in-sample 천장(채택=OOS·페이퍼 後).")
    return True


if __name__=="__main__": main()
