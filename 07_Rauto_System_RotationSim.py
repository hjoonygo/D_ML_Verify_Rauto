# -*- coding: utf-8 -*-
# [RotationSim] 챔피언 자동전환 시뮬 — 레짐전환 vs 최근수익전환 vs 단일봇 (세션 260626_02_Rauto2_Sys).
#   캡틴: 레짐별 수익기록→레짐오면 자동전환(레짐 잘맞추냐가 관건). 8봇 시뮬해 단일봇보다 높으면 OK.
#         안되면 최근 1~2주 최고수익봇 전환을 근거로. ★전부 인과(과거만)·룩어헤드0(오라클만 상한참고).
import os, sys, json, glob
ROOT = os.path.dirname(os.path.abspath(__file__))
for _ in range(5):
    if os.path.isdir(os.path.join(ROOT,"08_BTC_Data")) and os.path.isdir(os.path.join(ROOT,"04_공용엔진코드")): break
    ROOT=os.path.dirname(ROOT)
RES=os.path.join(ROOT,"03_IDEA4Bot","260623_07_RfRautoAlphaUp")
sys.path.insert(0,os.path.join(ROOT,"04_공용엔진코드","engines")); sys.path.insert(0,RES)
from path_finder import ensure_paths; ensure_paths()
import numpy as np, pandas as pd
from fib_replay_1m import load_funding
from REVoi_bot import REVoiBot
from rauto_live import per_trade_pnl
from rauto_cex import SlipModel
import rauto_datafeed as DF
MERGED=os.path.join(ROOT,"08_BTC_Data","derived","Merged_Data.csv"); MIRROR=r"D:\ML\Verify\08 BTC_Data\BinanceData_AWS_Mirror"


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


def weekly_mat(d, fund, P, fleet, norm_exp=None):
    """각 봇 주간수익률 행렬(index=주, col=봇). norm_exp 주면 그 노출로 정규화(레짐비교용)."""
    cols={}
    for nm,ap,lev,sz,dd in fleet:
        p=dict(P)
        for k in ("tp_frac","regime_factor","gate","gate_lo","gate_hi"):
            if k in ap: p[k]=ap[k]
        T=REVoiBot(p).make_trades(d,fund)
        if norm_exp is not None: lev,sz=6.0, norm_exp*100.0/6.0   # 동일노출 정규화(lev6 고정)
        pnl,_,_,_=per_trade_pnl(T,sz,lev,SlipModel(0,1.0),dd_cut=dd)   # 현실 스프1bp
        s=pd.Series(np.array(pnl)/100.0, index=pd.to_datetime(T["et"]))
        cols[nm]=s.groupby(pd.Grouper(freq="W")).apply(lambda x:(1+x).prod()-1)
    W=pd.DataFrame(cols).fillna(0.0)
    return W


def stats(ret):
    eq=np.cumprod(1+ret.values); tot=(eq[-1]-1)*100
    peak=np.maximum.accumulate(eq); mdd=((eq-peak)/peak).min()*100
    pos=100*(ret.values>0).mean()
    return tot, mdd, pos


def regime_week(d, weeks):
    """각 주 시작시점 7일추세 레짐(상승>+3/하락<-3/횡보). 인과(과거 7일)."""
    c=d["close"]; lab=[]
    for w in weeks:
        t=pd.Timestamp(w)
        try:
            cn=c.asof(t); cp=c.asof(t-pd.Timedelta(days=7)); ch=(cn/cp-1)*100
        except Exception: ch=0
        lab.append("up" if ch>3 else ("down" if ch<-3 else "range"))
    return np.array(lab)


def simulate(W, reg, tag):
    weeks=W.index; bots=W.columns.tolist(); A=W.values; nb=len(bots); nw=len(weeks)
    # 규칙별 주간수익
    def run(picker):
        r=np.empty(nw)
        for i in range(nw):
            b=picker(i); r[i]=A[i,b]
        return pd.Series(r,index=weeks)
    # 오라클(상한·룩어헤드)
    orc=run(lambda i: int(np.argmax(A[i])))
    # 레짐 인과: 과거 같은레짐 평균 최고봇
    def reg_pick(i):
        if i<8: return bots.index(STATIC)
        past=reg[:i]; cur=reg[i]; m=(past==cur)
        if m.sum()<2: return bots.index(STATIC)
        return int(np.argmax(A[:i][m].mean(axis=0)))
    rg=run(reg_pick)
    # 최근 1주/2주 최고봇
    r1=run(lambda i: int(np.argmax(A[i-1])) if i>=1 else bots.index(STATIC))
    r2=run(lambda i: int(np.argmax(A[i-2:i].sum(axis=0))) if i>=2 else bots.index(STATIC))
    eqw=pd.Series(A.mean(axis=1),index=weeks)   # 등가중(전봇 동시·평균)
    print(f"\n[{tag}] (주간 리밸런스 · 현실비용)")
    print(f"  {'규칙':<18}{'복리':>11}{'MDD':>8}{'양수주%':>8}")
    for nm,sr in [("오라클(상한·룩어헤드)",orc),("레짐전환(인과)",rg),("최근1주전환",r1),("최근2주전환",r2),("등가중(전봇평균)",eqw)]:
        t,m,pp=stats(sr); print(f"  {nm:<18}{t:>+10.0f}%{m:>7.1f}%{pp:>7.0f}%")
    print(f"  {'─단일봇─':<18}")
    best=(None,-1e9)
    for b in bots:
        t,m,pp=stats(W[b]);
        if t>best[1]: best=(b,t)
        print(f"  {b:<18}{t:>+10.0f}%{m:>7.1f}%{pp:>7.0f}%")
    print(f"  → 최고단일봇 = {best[0]} ({best[1]:+.0f}%)")
    return orc,rg,r1,r2,best


STATIC="M20챔피언"
def main():
    P=json.load(open(os.path.join(RES,"back2tv_rev_winners.json")))["REV_MDD25_36mo"]["p"]
    d=build_d1m(); fund=load_funding()
    fleet=[("M20챔피언",{"tp_frac":0.7,"regime_factor":1.4},6,55,None),
     ("R+P70단순",{"tp_frac":0.7},6,55,None),
     ("M25고수익",{"tp_frac":0.7,"regime_factor":1.4},5,85,None),
     ("M30",{"tp_frac":0.7,"regime_factor":1.4},8,65,None),
     ("M0천장",{"tp_frac":0.7,"regime_factor":1.4},16,100,None),
     ("M4b",{"tp_frac":0.7},6,55,[-0.08,0.5]),
     ("M5게이트",{"tp_frac":0.7,"gate":True},6,55,None),
     ("결합R+P80",{"tp_frac":0.8,"gate":True},6,75,[-0.08,0.5])]
    print("="*70); print("[챔피언 자동전환 시뮬레이션] 8봇 · 주간 리밸런스"); print("="*70)
    # (1) 네이티브(각자 레버=레버가 결과 지배)
    Wn=weekly_mat(d,fund,P,fleet,norm_exp=None); reg=regime_week(d,Wn.index)
    simulate(Wn,reg,"① 네이티브 사이징(레버 그대로)")
    # (2) 동일노출 exp3.0(레짐·알파만 비교)
    Wm=weekly_mat(d,fund,P,fleet,norm_exp=3.0)
    simulate(Wm,reg,"② 동일노출 exp3.0 정규화(레짐/알파 순수비교)")
    print("\n[판정 기준] 레짐전환 or 최근전환 > 최고단일봇 = '가능'. 오라클(상한)과의 격차 = 레짐예측 난이도.")
    return True


if __name__=="__main__": main()
