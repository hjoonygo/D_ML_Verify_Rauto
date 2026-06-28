# -*- coding: utf-8 -*-
# [ScenarioSweep] REVoi 휩소/레짐 12시나리오 백테 (세션 260626_02_Rauto2_Sys).
#   선행연구 근거(웹조사+§20/§23): ①역추세는 추세거슬러 fade 금지(200MA/ADX) ②횡보(낮은ER)서 유리
#     ③★역추세엔 가격손절보다 시간손절·부분익절(타이트 가격손절 역효과) ④레짐적응 트레일(추세선 조이고 횡보선 풀기).
#   적용 = 진입게이트(side 마스킹·룩어헤드0) + 청산조정(bt_full knob: time_stop/tp_frac/trend_flip/init_atr/fib_scale).
#   ★무손상: rev_side·gen_trades(검증엔진) 무수정·호출만. 게이트=side 0마스킹, 청산=엔진 파라미터.
import os, sys, json
ROOT = os.path.dirname(os.path.abspath(__file__))
for _ in range(5):   # RfRauto 루트 상향탐색(08_BTC_Data·04_공용엔진코드 있는 곳)
    if os.path.isdir(os.path.join(ROOT, "08_BTC_Data")) and os.path.isdir(os.path.join(ROOT, "04_공용엔진코드")):
        break
    ROOT = os.path.dirname(ROOT)
sys.path.insert(0, os.path.join(ROOT, "04_공용엔진코드", "engines"))
from path_finder import ensure_paths; ensure_paths()
import numpy as np, pandas as pd
import bt_full as B
from blend_opt import rev_side
from fib_replay_1m import load_funding
from rauto_live import per_trade_pnl
from rauto_cex import SlipModel
MERGED = os.path.join(ROOT, "08_BTC_Data", "derived", "Merged_Data.csv")


def main():
    cfg = json.load(open(os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp", "back2tv_rev_winners.json")))
    p = cfg["REV_MDD25_36mo"]["p"]; rev_tf=p["rev_tf"]
    d = pd.read_csv(MERGED, usecols=["timestamp","open","high","low","close","oi_zscore_24h"])
    d["t"]=pd.to_datetime(d["timestamp"],utc=True,format="ISO8601").dt.tz_localize(None)
    d=d.dropna(subset=["open"]).set_index("t").sort_index()
    fund=load_funding()
    df, side0 = rev_side(d, rev_tf, p["q"], p["qwin"])   # 1회 계산, 모든 시나리오 공유
    c4 = df["close"]
    r30 = ((c4/c4.shift(180)-1)*100).values             # 30일 추세
    net=(c4-c4.shift(14)).abs(); den=c4.diff().abs().rolling(14).sum(); ER=(net/(den+1e-9)).values  # 4H ER
    MA=c4.rolling(200).mean(); dist=((c4/MA-1)*100).fillna(0).values   # 200(4H)MA 이격
    vrng=((df["high"]-df["low"])/df["close"]).rolling(6).mean()        # 24h 변동
    vratio=(vrng/vrng.rolling(30).mean()).fillna(1).values             # 변동 확장비
    r30n=np.nan_to_num(r30); ERn=np.nan_to_num(ER)

    def gen(side, **kw):
        T = B.gen_trades(d, fund, rev_tf, p["piv"], p["N"], (p["f1"],p["f2"],p["f3"]),
                         kw.pop("iam", p["iam"]), er_gate=0.0, ext_side=side, align_pivot=True,
                         use_trend_flip=kw.pop("use_trend_flip", False), arm_bars=p["arm"], **kw)
        if not len(T): return None
        T=T.sort_values("et").reset_index(drop=True)
        pnl,fin,mdd,nl=per_trade_pnl(T,75.0,3.0,SlipModel(0,0))
        return T,np.array(pnl)/100.0,fin,mdd,nl

    def row(tag, res):
        if res is None: print(f"{tag:<22} 거래0"); return
        T,R,fin,mdd,nl=res; w=R[R>0]; l=R[R<0]; pf=(w.sum()/abs(l.sum())) if len(l) else 9.99
        yr=pd.to_datetime(T["et"]).dt.year.values; ys=[]
        for y in sorted(set(yr)):
            _,fy,_,_=per_trade_pnl(T[yr==y],75.0,3.0,SlipModel(0,0)); ys.append(f"{y%100}:{(fy/10000-1)*100:+.0f}")
        print(f"{tag:<22}{len(R):>5} PF{pf:>4.2f} 승{round((R>0).mean()*100):>2}% {(fin/10000-1)*100:>+8.0f}% MDD{mdd:>5.1f}% [{' '.join(ys)}]")

    print("="*100)
    print("[REVoi 12시나리오 스윕] 전기간 honest · 진입게이트(룩어헤드0)+청산조정 · 복리=언사이즈드 사이징")
    print("="*100)
    print(f"{'시나리오':<22}{'거래':>5}{'  PF':>6}{'승률':>5}{'복리':>9}{'MDD':>7} [연도별]")

    sB = side0
    row("0.베이스", gen(sB))
    # ── 진입게이트 ──
    def m(cond): s=side0.copy(); s[cond]=0; return s
    row("E1.랠리숏솎(30d>12)", gen(m((side0==-1)&(r30n>12))))
    row("E2.MA이격숏솎(>8%)", gen(m((side0==-1)&(dist>8))))
    row("E3.강ER역추세솎", gen(m(((side0==-1)&(ERn>0.4)&(r30n>0))|((side0==1)&(ERn>0.4)&(r30n<0)))))
    row("E4.변동확장솎(>1.6)", gen(m(vratio>1.6)))
    # ── 청산조정 ──
    row("X1.시간손절(6봉)", gen(sB, time_stop_bars=6, time_stop_minR=0.0))
    row("X2.부분익절(tp.5)", gen(sB, tp_frac=0.5))
    row("X3.추세전환청산", gen(sB, use_trend_flip=True))
    row("X4.넓은초기손절x1.5", gen(sB, iam=p["iam"]*1.5))
    fsc = np.where(ERn>0.40, 1.3, 1.0).astype(float)     # 레짐적응 트레일: 강추세봉=조임(1.3)
    row("X5.레짐적응트레일", gen(sB, fib_scale=fsc))
    # ── 조합(베스트 진입 E1 + 청산) ──
    sE1 = m((side0==-1)&(r30n>12))
    row("C1.E1+시간손절", gen(sE1, time_stop_bars=6, time_stop_minR=0.0))
    row("C2.E1+부분익절", gen(sE1, tp_frac=0.5))
    row("C3.E1+레짐트레일", gen(sE1, fib_scale=fsc))
    print("\n[기준] 채택후보 = 베이스 대비 복리 유지/↑ + MDD↓ + 연도별 고름. 상위 2~3개 → CPCV 표준6.")
    return True


if __name__ == "__main__":
    main()
