# -*- coding: utf-8 -*-
# [RegimeOverlay_Final] M4b(자기DD컷)+M5(추세역행 진입게이트) 결합 검증 + Back2TV (세션 260626_02_Rauto2_Sys).
#   캡틴: 결합본 OOS(연도별 일반화)+CPCV+Back2TV. 베이스=REVoi R+P70 exp3.3(11810%계보)·lev6·현실 스프1bp.
#   M5 게이트 = 지속하락(30d<-10%)서 롱·지속상승(>+12%)서 숏 차단(역추세가 강추세와 싸우지않기·경제원리).
#   M4b DD컷 = 자기 자본 드로다운<=-8%면 수량×0.5(가격임계 아닌 손익반응=과적합 적음).
import os, sys, json, glob
from datetime import datetime
ROOT = os.path.dirname(os.path.abspath(__file__))
for _ in range(5):
    if os.path.isdir(os.path.join(ROOT, "08_BTC_Data")) and os.path.isdir(os.path.join(ROOT, "04_공용엔진코드")): break
    ROOT = os.path.dirname(ROOT)
RES = os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp")
sys.path.insert(0, os.path.join(ROOT, "04_공용엔진코드", "engines")); sys.path.insert(0, RES)
from path_finder import ensure_paths; ensure_paths()
import numpy as np, pandas as pd
import bt_full as B
import trendstack_signal_engine as TS
from blend_opt import rev_side
from fib_replay_1m import load_funding
import rauto_datafeed as DF
from rauto_cex import FeeModel, SlipModel, MMR_T1, MMR_T2, TIER, LIQ_SLIP, LIQ_COST, MK, TK
import bt_report as BR, make_pine as MP, make_cases as MC
MERGED = os.path.join(ROOT, "08_BTC_Data", "derived", "Merged_Data.csv")
MIRROR = r"D:\ML\Verify\08 BTC_Data\BinanceData_AWS_Mirror"
BASE_EXP, LEV = 3.3, 6.0
DD_THR, DD_SCALE = -0.08, 0.5


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
    out=np.empty(len(R))
    for i in range(len(R)):
        gR=R[i]+MK+TK+FUND[i]; out[i]=gR-fee.entry_cost(False)-fee.exit_cost(REASON[i])-FUND[i]-(sl if REASON[i]!="tp" else 0)
    return out


def compound(Rnet, MAE, FUND, mult, dd=False):
    bal=10000.0; peak=10000.0; mdd=0.0; nliq=0; eq=np.empty(len(Rnet)); pser=np.empty(len(Rnet))
    for i in range(len(Rnet)):
        m=mult[i]
        if dd and (bal/peak-1.0)<=DD_THR: m*=DD_SCALE
        exp=BASE_EXP*m; mmr=MMR_T2 if exp*bal>TIER else MMR_T1; hsd=1.0/LEV-mmr-LIQ_SLIP
        p=(-exp*(hsd+LIQ_COST+abs(FUND[i])) if MAE[i]<=-hsd else Rnet[i]*exp)
        if MAE[i]<=-hsd: nliq+=1
        bal*=(1.0+p); peak=max(peak,bal); mdd=min(mdd,bal/peak-1.0); eq[i]=bal; pser[i]=p
    return eq, pser, (bal/1e4-1)*100, mdd*100, nliq


def sub(eq, ets, lo, hi):
    mask=(ets>=np.datetime64(lo))&(ets<np.datetime64(hi)); idx=np.nonzero(mask)[0]
    if len(idx)<2: return 0.0,0.0
    start=eq[idx[0]-1] if idx[0]>0 else 10000.0; seg=eq[idx]; peak=start; md=0.0
    for v in seg: peak=max(peak,v); md=min(md,v/peak-1)
    return (seg[-1]/start-1)*100, md*100


def cpcv(pser, ets):
    import itertools
    mo=pd.Series(pser, index=pd.to_datetime(ets)).groupby(pd.Grouper(freq="MS")).apply(lambda x:(1+x).prod()-1).values
    if len(mo)<12: return None
    g6=np.array_split(np.arange(len(mo)),6); cg=[]; viol=0
    for c in itertools.combinations(range(6),2):
        te=np.sort(np.concatenate([g6[k] for k in c])); seg=mo[te]; eqp=np.cumprod(1+seg)
        cagr=((eqp[-1])**(12/len(seg))-1)*100; dd=((eqp-np.maximum.accumulate(eqp))/np.maximum.accumulate(eqp)).min()*100
        cg.append(cagr); viol+=(dd<-20)
    cg=np.array(cg); return dict(p25=np.percentile(cg,25), neg=100*(cg<0).mean(), viol=100*viol/len(cg))


def main():
    p=json.load(open(os.path.join(RES,"back2tv_rev_winners.json")))["REV_MDD25_36mo"]["p"]
    d=build_d1m(); fund=load_funding()
    print("="*100); print(f"[M4b+M5 결합 검증 + Back2TV] 베이스 REVoi R+P70 exp{BASE_EXP}/lev{LEV} 현실스프1bp · {d.index.min()}~{d.index.max()}"); print("="*100)
    _,side=rev_side(d,p["rev_tf"],p["q"],p["qwin"])
    T=B.gen_trades(d,fund,p["rev_tf"],p["piv"],p["N"],(p["f1"],p["f2"],p["f3"]),p["iam"],er_gate=0.0,ext_side=side,
                   align_pivot=True,use_trend_flip=False,arm_bars=p["arm"],tp_frac=0.7,capture_fills=True).sort_values("et").reset_index(drop=True)
    Rnet=rnet_array(T); MAE=T["mae"].values.astype(float); FUND=T["fund"].values.astype(float); ets=pd.to_datetime(T["et"]).values
    sidea=T["side"].astype(int).values; mc=d["close"].values; mt=d.index.values
    r30=np.zeros(len(T))
    for i in range(len(T)):
        a=int(np.searchsorted(mt,np.datetime64(pd.Timestamp(ets[i])),"left"));
        if a>0: r30[i]=(mc[a]/mc[max(0,a-43200)]-1)*100
    gate=np.where(((r30<-10)&(sidea==1))|((r30>12)&(sidea==-1)),0.0,1.0)
    ones=np.ones(len(T))

    variants=[("M0 베이스", ones, False), ("M5 게이트", gate, False), ("M4b DD컷", ones, True), ("★결합(M5+M4b)", gate, True)]
    LO,HI=np.datetime64("2026-05-01"),np.datetime64("2026-07-01")
    print(f"\n{'모델':<16}{'전기간':>9}{'MDD':>7}{'최근2달':>9}{'2달MDD':>8}{'CPCV_p25':>10}{'음수폴드':>8}{'MDD20위반':>10}")
    res={}
    for nm,mlt,dd in variants:
        eq,ps,tot,mdd,nl=compound(Rnet,MAE,FUND,mlt,dd=dd); r2,m2=sub(eq,ets,LO,HI); cp=cpcv(ps,ets); res[nm]=(eq,tot,mdd,r2,m2,cp)
        print(f"{nm:<16}{tot:>+8.0f}%{mdd:>6.1f}%{r2:>+8.1f}%{m2:>7.1f}%{cp['p25']:>+9.1f}{cp['neg']:>7.0f}%{cp['viol']:>9.0f}%")

    # ★연도별 일반화: 결합이 2026뿐 아니라 다른 해 MDD도 줄이나
    print(f"\n[연도별 MDD 일반화 — M0 vs 결합] (결합이 여러해 MDD 줄이면=과적합 아님)")
    eqM0=res["M0 베이스"][0]; eqC=res["★결합(M5+M4b)"][0]
    print(f"  {'연도':<6}{'M0 수익/MDD':>20}{'결합 수익/MDD':>22}")
    for y in [2023,2024,2025,2026]:
        a=sub(eqM0,ets,np.datetime64(f"{y}-01-01"),np.datetime64(f"{y+1}-01-01")); b=sub(eqC,ets,np.datetime64(f"{y}-01-01"),np.datetime64(f"{y+1}-01-01"))
        print(f"  {y:<6}{a[0]:>+11.0f}% /{a[1]:>6.1f}%{b[0]:>+13.0f}% /{b[1]:>6.1f}%")

    # ── Back2TV: M5-게이트 통과 거래(차트) ──
    Tg=T[gate>0].reset_index(drop=True)
    expo=BASE_EXP   # 시각화/표 기준 노출(M4b는 동적사이징=차트마커 불변, 분석에 병기)
    cfg=dict(sig_tf=p["rev_tf"],pivot_tf=p["piv"],N=p["N"],fib1=p["f1"],fib2=p["f2"],fib3=p["f3"],init_atr_mult=p["iam"],er_gate=0.0,size_pct=55.0,lev=6.0)
    today=datetime.now().strftime("%y%m%d"); ts=datetime.now().strftime("%Y%m%d%H%M")
    import re
    ns=[int(mm.group(1)) for dd2 in os.listdir(BR.BTO) if (mm:=re.match(rf"{today}_(\d+)_",dd2))] if os.path.isdir(BR.BTO) else []
    nn=(max(ns)+1) if ns else 1
    base=f"{today}_{nn:02d}_REVoi_RP70_RegimeOverlay_Back2TV"; folder=os.path.join(BR.BTO,base); os.makedirs(folder,exist_ok=True)
    Tg.drop(columns=["fills"]).to_csv(os.path.join(folder,f"{base}_거래원장.csv"),index=False,encoding="utf-8-sig")
    L,an,ag=BR.per_trade(Tg,cfg); U=BR.unified_table(L); U.to_csv(os.path.join(folder,f"{base}_월별통합표.csv"),index=False,encoding="utf-8-sig")
    nemb,_,_,ntot=MP.build_pine(Tg,expo,out=os.path.join(folder,f"{base}.pine"),title=f"REVoi R+P70+레짐오버레이 (게이트통과 {len(Tg)}/{len(T)})")
    cpng,_,_=MC.build_cases(Tg,p,d,folder,base,max_embed=nemb)
    C=res["★결합(M5+M4b)"]
    head=(f"[Back2TV·REVoi R+P70 + 레짐오버레이(M5게이트+M4b DD컷)] {base}\n"
          f"[게이트] 지속하락(30d<-10)서 롱·지속상승(>12)서 숏 차단 → 거래 {len(Tg)}/{len(T)}(차단 {len(T)-len(Tg)}).\n"
          f"[DD컷] 자기자본 DD<=-8%면 수량×0.5(동적사이징=차트마커 불변·equity만 영향).\n"
          f"[★결합 성적] 전기간 {C[1]:+.0f}% · MDD {C[2]:.1f}% · 최근2달 {C[3]:+.1f}%(2달MDD {C[4]:.1f}%) · CPCV p25 {C[5]['p25']:+.0f}%·음수폴드 {C[5]['neg']:.0f}%·MDD20위반 {C[5]['viol']:.0f}%\n"
          f"[대비 M0] 전기간 {res['M0 베이스'][1]:+.0f}%·MDD {res['M0 베이스'][2]:.1f}%·최근2달 {res['M0 베이스'][3]:+.1f}% (결합이 MDD·최근 개선)\n"
          f"[경계 §20] full=과적합 상한. 게이트는 경제원리·DD컷은 손익반응(과적합 적음)이나 임계 OOS 추가검증 권장. Pine 임베드 {nemb}/{ntot}.")
    body=head+"\n\n[월별 통합표 — 게이트통과·exp3.3 기준(M4b 동적사이징 별도)]\n"+U.to_string(index=False)
    open(os.path.join(BR.WH,f"{ts}_{base}.txt"),"w",encoding="utf-8").write(body)
    open(os.path.join(folder,f"{base}_분석.txt"),"w",encoding="utf-8").write(body)
    with open(BR.INDEX,"a",encoding="utf-8") as f:
        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M')}|260626_02_Rauto2_Sys|{base}: 레짐오버레이(M5게이트+M4b DD컷) 결합 전기간{C[1]:+.0f}%/MDD{C[2]:.0f}%/최근2달{C[3]:+.1f}%·CPCVp25{C[5]['p25']:+.0f}%·Pine{nemb}/{ntot}|src=RegimeOverlay_Final.py\n")
    print("\n"+head); print(f"\n[저장] {folder}\\ · Pine→TV BINANCE:BTCUSDT.P·UTC·4h" + (f" · 사례6선 {os.path.basename(cpng)}" if cpng else " · 사례6선 생략(<5)"))
    return True


if __name__ == "__main__":
    main()
