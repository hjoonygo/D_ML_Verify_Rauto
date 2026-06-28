# -*- coding: utf-8 -*-
# [MinNegMonths] ★음수 월 최소화 최적화 (세션 260626_02_Rauto2_Sys). 캡틴 최우선=매월수익률 음수가 제일 적게.
#   #1(결합 오버레이 −20 재사이징) 위에서 출구(tp0.7/0.8·시간손절)·게이트강도 변수로 '음수 월 개수' 랭킹.
#   베이스 = REVoi + R+P(부분익절) + M5게이트(추세역행 차단) + M4b(자기DD컷). lev6·현실 스프1bp. 각 config는 MDD≈−20 재사이징.
import os, sys, json, glob
ROOT = os.path.dirname(os.path.abspath(__file__))
for _ in range(5):
    if os.path.isdir(os.path.join(ROOT, "08_BTC_Data")) and os.path.isdir(os.path.join(ROOT, "04_공용엔진코드")): break
    ROOT = os.path.dirname(ROOT)
RES = os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp")
sys.path.insert(0, os.path.join(ROOT, "04_공용엔진코드", "engines")); sys.path.insert(0, RES)
from path_finder import ensure_paths; ensure_paths()
import numpy as np, pandas as pd
import bt_full as B
from blend_opt import rev_side
from fib_replay_1m import load_funding
import rauto_datafeed as DF
from rauto_cex import FeeModel, SlipModel, MMR_T1, MMR_T2, TIER, LIQ_SLIP, LIQ_COST, MK, TK
MERGED = os.path.join(ROOT, "08_BTC_Data", "derived", "Merged_Data.csv")
MIRROR = r"D:\ML\Verify\08 BTC_Data\BinanceData_AWS_Mirror"
LEV = 6.0; DD_THR, DD_SCALE = -0.08, 0.5


def build_d1m():
    m = pd.read_csv(MERGED, usecols=["timestamp","open","high","low","close","oi_sum"])
    m["t"]=pd.to_datetime(m["timestamp"],utc=True,format="ISO8601").dt.tz_localize(None); m=m.dropna(subset=["open"]).set_index("t").sort_index()
    end=m.index.max(); kl=DF.fetch_klines_1m_range(60)
    bk=pd.DataFrame({"open":[k[1] for k in kl],"high":[k[2] for k in kl],"low":[k[3] for k in kl],"close":[k[4] for k in kl]},
                    index=pd.to_datetime([k[0] for k in kl],unit="ms")); bk=bk[bk.index>end].sort_index()
    oi_ext=pd.Series(np.nan,index=bk.index); rows=[]
    for fp in sorted(glob.glob(os.path.join(MIRROR,"BTCUSDT_1m_2026*.csv"))): rows.append(pd.read_csv(fp,usecols=["ts_utc","open_interest"]))
    if rows:
        mm=pd.concat(rows,ignore_index=True); mm["t"]=pd.to_datetime(mm["ts_utc"],format="%Y-%m-%d %H:%M:%S"); mm=mm.drop_duplicates("t").set_index("t")
        oi_ext=oi_ext.fillna(mm["open_interest"].reindex(bk.index))
    try:
        oih=DF.fetch_oi_hist(30); oh=pd.Series([o[1] for o in oih],index=pd.to_datetime([o[0] for o in oih],unit="ms")).reindex(bk.index,method="ffill"); oi_ext=oi_ext.fillna(oh)
    except Exception: pass
    oi_ext=oi_ext.ffill().bfill()
    ohlc=pd.concat([m[["open","high","low","close"]],bk]); ohlc=ohlc[~ohlc.index.duplicated(keep="first")].sort_index()
    raw_oi=pd.concat([m["oi_sum"],oi_ext]); raw_oi=raw_oi[~raw_oi.index.duplicated(keep="first")].reindex(ohlc.index).ffill()
    ohlc["oi_zscore_24h"]=DF.oi_zscore_from_series(raw_oi).values
    return ohlc


def rnet_array(T):
    fee=FeeModel(); slip=SlipModel(0.0,1.0); sl=slip.market_exit_slip()
    R=T["R"].values.astype(float); FUND=T["fund"].values.astype(float)
    REASON=T["reason"].values if "reason" in T else np.array(["fibstop"]*len(R))
    return np.array([R[i]+MK+TK+FUND[i]-fee.entry_cost(False)-fee.exit_cost(REASON[i])-FUND[i]-(sl if REASON[i]!="tp" else 0) for i in range(len(R))])


def compound(Rnet, MAE, FUND, mult, exp0, dd=True):
    bal=10000.0; peak=10000.0; mdd=0.0; p=np.empty(len(Rnet))
    for i in range(len(Rnet)):
        m=mult[i]
        if dd and (bal/peak-1.0)<=DD_THR: m*=DD_SCALE
        exp=exp0*m; mmr=MMR_T2 if exp*bal>TIER else MMR_T1; hsd=1.0/LEV-mmr-LIQ_SLIP
        pp=(-exp*(hsd+LIQ_COST+abs(FUND[i])) if MAE[i]<=-hsd else Rnet[i]*exp)
        bal*=(1.0+pp); peak=max(peak,bal); mdd=min(mdd,bal/peak-1.0); p[i]=pp
    return p, (bal/1e4-1)*100, mdd*100


def resize_to_mdd20(Rnet, MAE, FUND, mult, dd=True):
    """MDD≈−20 맞추는 exp 탐색(결합 오버레이 path-dep). 반환 (exp, p, tot, mdd)."""
    best=(2.5,None,0,0)
    for e in np.arange(2.5, 6.01, 0.1):
        p,tot,mdd=compound(Rnet,MAE,FUND,mult,e,dd=dd)
        if mdd>=-20.0: best=(e,p,tot,mdd)
        else: break
    return best


def monthly_stats(p, ets):
    s=pd.Series(p, index=pd.to_datetime(ets))
    mo=s.groupby(pd.Grouper(freq="MS")).apply(lambda x:(1+x).prod()-1)*100
    neg=int((mo<0).sum()); tot=len(mo); worst=mo.min(); avg=mo.mean(); pos_pct=100*(mo>=0).mean()
    rec=mo[mo.index>=pd.Timestamp("2026-05-01")]
    rec_neg=int((rec<0).sum()); rec_n=len(rec)
    return mo, neg, tot, worst, avg, pos_pct, rec_neg, rec_n


def main():
    p=json.load(open(os.path.join(RES,"back2tv_rev_winners.json")))["REV_MDD25_36mo"]["p"]
    d=build_d1m(); fund=load_funding()
    print("="*104); print(f"[★음수 월 최소화 최적화] 결합 오버레이(M5게이트+M4b DD컷) · 각 config MDD≈−20 재사이징 · 현실비용"); print("="*104)
    _,side=rev_side(d,p["rev_tf"],p["q"],p["qwin"]); sidea=side
    mc=d["close"].values; mt=d.index.values

    def gen(tp, ts):
        return B.gen_trades(d,fund,p["rev_tf"],p["piv"],p["N"],(p["f1"],p["f2"],p["f3"]),p["iam"],er_gate=0.0,ext_side=side,
                            align_pivot=True,use_trend_flip=False,arm_bars=p["arm"],tp_frac=tp,
                            time_stop_bars=ts,time_stop_minR=0.0).sort_values("et").reset_index(drop=True)

    def r30_of(T):
        ets=pd.to_datetime(T["et"]).values; out=np.zeros(len(T))
        for i in range(len(T)):
            a=int(np.searchsorted(mt,np.datetime64(pd.Timestamp(ets[i])),"left"))
            if a>0: out[i]=(mc[a]/mc[max(0,a-43200)]-1)*100
        return out, ets

    configs=[("R+P70", 0.7, 0, (-10,12)), ("R+P80", 0.8, 0, (-10,12)),
             ("R+P70+강게이트", 0.7, 0, (-7,8)), ("R+P80+강게이트", 0.8, 0, (-7,8)),
             ("R+P70+시간손절6", 0.7, 6, (-10,12)), ("R+P80+시간손절6", 0.8, 6, (-10,12)),
             ("R+P80+강게이트+TS6", 0.8, 6, (-7,8))]
    print(f"\n{'config':<20}{'exp':>5}{'전기간':>9}{'MDD':>7}{'음수월':>8}{'양수%':>7}{'최악월':>8}{'평균월':>7}{'최근음수월':>10}")
    rows=[]
    for nm, tp, ts, (glo,ghi) in configs:
        T=gen(tp,ts); Rnet=rnet_array(T); MAE=T["mae"].values.astype(float); FUND=T["fund"].values.astype(float)
        r30,ets=r30_of(T); sd=T["side"].astype(int).values
        gate=np.where(((r30<glo)&(sd==1))|((r30>ghi)&(sd==-1)),0.0,1.0)
        exp,pp,tot,mdd=resize_to_mdd20(Rnet,MAE,FUND,gate)
        mo,neg,totm,worst,avg,pospct,rneg,rn=monthly_stats(pp,ets)
        rows.append((nm,neg,tot,mdd,pospct,worst,avg,rneg,rn,exp))
        print(f"{nm:<20}{exp:>5.1f}{tot:>+8.0f}%{mdd:>6.1f}%{neg:>5}/{totm:<2}{pospct:>6.0f}%{worst:>+7.1f}%{avg:>+6.1f}%{rneg:>6}/{rn:<2}")

    rows.sort(key=lambda r:(r[1], -r[2]))   # 음수월 적은 순, 동률=수익 높은 순
    best=rows[0]
    print(f"\n[★음수월 최소 승자] {best[0]} — 음수월 {best[1]}/{best[2]} (양수 {best[4]:.0f}%) · 전기간 {(best[2] and 0)}", end="")
    print(f" MDD{best[3]:.1f}% · 최근음수월 {best[7]}/{best[8]} · exp{best[9]:.1f}")
    print(f"\n[해석] 음수월 최소가 1순위(캡틴). 동률이면 수익 높은 쪽. 최근음수월(2026-05~06)도 같이 봄.")
    print(f"       단 in-sample 천장 — 채택은 OOS·CPCV·라이브 페이퍼 확인 後. 음수월 '0'은 비현실(욕심), '최소화'가 목표.")
    return True


if __name__ == "__main__":
    main()
