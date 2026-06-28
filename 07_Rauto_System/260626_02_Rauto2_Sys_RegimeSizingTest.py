# -*- coding: utf-8 -*-
# [RegimeSizingTest] 장세판별 → 동적수량/진입게이트가 수익(특히 최근2달)을 개선하나 (세션 260626_02_Rauto2_Sys).
#   캡틴: 변동성 등 장세판별로 유불리 정밀인지 → 수량/진입 엄격화. ★최근 2달(2026-05~06)이 더 중요. 다양한 변수.
#   베이스 = REVoi R+P70(tp0.7), lev6 고정(hsd16.2%≫최악역행5%→청산0), base_exp 동적조절(수량). 현실비용 스프1bp.
#   장세변수(진입시점 과거만=룩어헤드0): 변동성pctl·7일추세·30일지속추세·4H효율비ER·자기 드로다운(equity).
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
import trendstack_signal_engine as TS
from blend_opt import rev_side
import rauto_datafeed as DF
from rauto_cex import FeeModel, SlipModel, MMR_T1, MMR_T2, TIER, LIQ_SLIP, LIQ_COST, MK, TK
MERGED = os.path.join(ROOT, "08_BTC_Data", "derived", "Merged_Data.csv")
MIRROR = r"D:\ML\Verify\08 BTC_Data\BinanceData_AWS_Mirror"
BASE_EXP, LEV = 3.3, 6.0   # ★11,810% 계보(M20 이빠이 exp3.3)로 베이스 통일(캡틴 2026-06-26)


def build_d1m():
    m = pd.read_csv(MERGED, usecols=["timestamp","open","high","low","close","oi_sum"])
    m["t"]=pd.to_datetime(m["timestamp"],utc=True,format="ISO8601").dt.tz_localize(None); m=m.dropna(subset=["open"]).set_index("t").sort_index()
    end=m.index.max()
    kl=DF.fetch_klines_1m_range(60)
    bk=pd.DataFrame({"open":[k[1] for k in kl],"high":[k[2] for k in kl],"low":[k[3] for k in kl],"close":[k[4] for k in kl]},
                    index=pd.to_datetime([k[0] for k in kl],unit="ms")); bk=bk[bk.index>end].sort_index()
    oi_ext=pd.Series(np.nan,index=bk.index)
    rows=[]
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
    """per-trade R_net(exp독립, 현실 스프1bp). p = R_net*exp."""
    fee=FeeModel(); slip=SlipModel(0.0,1.0); sl=slip.market_exit_slip()
    R=T["R"].values.astype(float); FUND=T["fund"].values.astype(float)
    REASON=T["reason"].values if "reason" in T else np.array(["fibstop"]*len(R))
    out=np.empty(len(R))
    for i in range(len(R)):
        gR=R[i]+MK+TK+FUND[i]; ec=fee.entry_cost(False); xc=fee.exit_cost(REASON[i]); mkt=REASON[i]!="tp"
        out[i]=gR-ec-xc-FUND[i]-(sl if mkt else 0.0)
    return out


def compound(Rnet, MAE, FUND, mult, base_exp=BASE_EXP, lev=LEV, dd_cut=None):
    """동적 exp 복리. mult=per-trade 배수(고정모델). dd_cut=(thr,scale): 자기 드로다운<thr면 exp×scale(equity피드백)."""
    bal=10000.0; peak=10000.0; mdd=0.0; nliq=0; eq=np.empty(len(Rnet))
    for i in range(len(Rnet)):
        m=mult[i]
        if dd_cut is not None:
            cur_dd=bal/peak-1.0
            if cur_dd<=dd_cut[0]: m*=dd_cut[1]
        exp=base_exp*m
        mmr=MMR_T2 if exp*bal>TIER else MMR_T1; hsd=1.0/lev-mmr-LIQ_SLIP
        if MAE[i]<=-hsd: p=-exp*(hsd+LIQ_COST+abs(FUND[i])); nliq+=1
        else: p=Rnet[i]*exp
        bal*=(1.0+p); peak=max(peak,bal); mdd=min(mdd,bal/peak-1.0); eq[i]=bal
    return eq, (bal/1e4-1)*100, mdd*100, nliq


def sub_metrics(eq, ets, lo, hi):
    """기간[lo,hi) 수익률·MDD(구간내)."""
    mask=(ets>=np.datetime64(lo))&(ets<np.datetime64(hi))
    if mask.sum()<2: return 0.0, 0.0, int(mask.sum())
    idx=np.nonzero(mask)[0]; seg=eq[idx]; start=eq[idx[0]-1] if idx[0]>0 else 10000.0
    ret=(seg[-1]/start-1)*100; peak=start; md=0.0
    for v in seg: peak=max(peak,v); md=min(md,v/peak-1)
    return ret, md*100, len(idx)


def main():
    p=json.load(open(os.path.join(RES,"back2tv_rev_winners.json")))["REV_MDD25_36mo"]["p"]
    d=build_d1m()
    print("="*96); print(f"[장세판별 동적수량/진입게이트 테스트] base_exp{BASE_EXP}/lev{LEV} · 현실 스프1bp · {d.index.min()}~{d.index.max()}"); print("="*96)
    _,side=rev_side(d,p["rev_tf"],p["q"],p["qwin"])
    fund=_load_fund()
    T=B.gen_trades(d,fund,p["rev_tf"],p["piv"],p["N"],(p["f1"],p["f2"],p["f3"]),p["iam"],er_gate=0.0,ext_side=side,
                   align_pivot=True,use_trend_flip=False,arm_bars=p["arm"],tp_frac=0.7).sort_values("et").reset_index(drop=True)
    Rnet=rnet_array(T); MAE=T["mae"].values.astype(float); FUND=T["fund"].values.astype(float)
    ets=pd.to_datetime(T["et"]).values

    # ── 장세변수(진입시점 과거만) ──
    c4=TS.resample_tf(d[["open","high","low","close"]],p["rev_tf"])["close"]
    mc=d["close"].values; mt=d.index.values; mh=d["high"].values; ml=d["low"].values
    n=len(T); vol=np.zeros(n); r7=np.zeros(n); r30=np.zeros(n); er=np.zeros(n)
    net=(c4-c4.shift(14)).abs(); den=c4.diff().abs().rolling(14).sum(); ER4=(net/(den+1e-9)); ei=ER4.index.values; ev=ER4.values
    for i in range(n):
        a=int(np.searchsorted(mt,np.datetime64(pd.Timestamp(ets[i])),"left"))
        if a<=0: continue
        a1=max(0,a-1440); a7=max(0,a-10080); a30=max(0,a-43200)
        vol[i]=(mh[a1:a+1].max()-ml[a1:a+1].min())/mc[a]*100
        r7[i]=(mc[a]/mc[a7]-1)*100; r30[i]=(mc[a]/mc[a30]-1)*100
        j=int(np.searchsorted(ei,np.datetime64(pd.Timestamp(ets[i])),"right"))-1; er[i]=ev[j] if 0<=j<len(ev) and ev[j]==ev[j] else 0
    volq=pd.Series(vol).rank(pct=True).values   # 변동성 백분위(과거전체 근사)

    LO,HI=np.datetime64("2026-05-01"),np.datetime64("2026-07-01")   # ★최근 2달
    ones=np.ones(n)
    # ★참조: exp3.3 베이스를 2026-04까지만(최근손실 제외)=11,810% 계보 확인
    eq0,_,_,_=compound(Rnet,MAE,FUND,ones)
    ref04,refmdd,_=sub_metrics(eq0, ets, np.datetime64("2023-05-01"), np.datetime64("2026-05-01"))
    print(f"\n[참조] exp{BASE_EXP} · 2023-05~2026-04(최근손실 제외) 복리 {ref04:+.0f}% (=11,810% 계보·슬립0은 더↑) → 최근2달 포함하면 아래 M0")
    def run(tag, mult, dd_cut=None):
        eq,tot,mdd,nl=compound(Rnet,MAE,FUND,mult,dd_cut=dd_cut)
        r2,m2,n2=sub_metrics(eq,ets,LO,HI)
        ntr=int((mult>0).sum()) if dd_cut is None else n
        print(f"  {tag:<24}{tot:>+9.0f}%{mdd:>7.1f}%{'':2}|{r2:>+8.1f}%{m2:>7.1f}%{n2:>5}거래")
        return tot,mdd,r2,m2

    print(f"\n  {'모델':<24}{'전기간복리':>10}{'MDD':>7}  |{'최근2달':>9}{'2달MDD':>7}{'2달n':>7}")
    run("M0 베이스(동적없음)", ones)
    # M1 변동성타겟(고변동서 수량↓) — 역추세엔 역효과 가설검증
    run("M1 변동성타겟(고변동↓)", np.clip(0.5/np.clip(volq,0.1,1),0.3,1.3))
    # M1b 역: 저변동서 수량↓(횡보출혈 회피)
    run("M1b 저변동수량↓", np.where(volq<=0.33,0.5,1.0))
    # M2 지속추세 방어(|30일|강하면 수량↓)
    run("M2 지속추세|30d|>12 →0.4", np.where(np.abs(r30)>12,0.4,1.0))
    run("M2b 지속추세 점진", np.clip(1.0-np.abs(r30)/30.0,0.3,1.0))
    # M3 강추세ER 방어
    run("M3 강추세ER>0.4 →0.5", np.where(er>0.4,0.5,1.0))
    # M5 진입게이트: 지속하락(30d<-10)서 롱 차단 + 지속상승(30d>12)서 숏 차단
    sidea=T["side"].astype(int).values
    gate=np.where(((r30<-10)&(sidea==1))|((r30>12)&(sidea==-1)),0.0,1.0)   # 지속하락서 롱·지속상승서 숏 차단
    run("M5 진입게이트(역추세역행차단)", gate)
    # M6 복합: M2 + M5
    run("M6 복합(지속추세↓+게이트)", np.where(np.abs(r30)>12,0.4,1.0)*gate)
    # M4 자기 드로다운 컷(equity피드백): DD<-12%면 수량 0.4
    run("M4 자기DD<-12% →0.4", ones, dd_cut=(-0.12,0.4))
    run("M4b 자기DD<-8% →0.5", ones, dd_cut=(-0.08,0.5))

    print("\n[해석] ★최근2달 컬럼이 핵심. M0 대비 최근2달 손실↓ + 전기간 복리 유지면 = 장세판별 효과.")
    print("       전기간 크게 깎이며 최근만 좋으면 = 과최적화 의심(추후 OOS).")
    return True


def _load_fund():
    from fib_replay_1m import load_funding
    return load_funding()


if __name__ == "__main__":
    main()
