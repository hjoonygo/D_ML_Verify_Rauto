# -*- coding: utf-8 -*-
# [LevSweepLiq] 부분익절 REVoi의 레버×사이즈 스윕 + 강제청산 검증 (세션 260626_02_Rauto2_Sys).
#   캡틴: MDD−20%까지 채우되 극한레버+최소사이즈로 수익극대화. ★강제청산 로직 제대로 확인.
#   강제청산(rauto_cex.MarginModel): hsd=1/lev−mmr−slip; mae<=−hsd면 청산(손실=exp×(hsd+cost+|fund|)).
#   ★핵심: hsd는 lev만의 함수(사이즈 무관). 극한레버→hsd 극소→REVoi 역행구간서 대량청산(역추세는 역행 견뎌야 수익).
import os, sys, json
ROOT = os.path.dirname(os.path.abspath(__file__))
for _ in range(5):
    if os.path.isdir(os.path.join(ROOT, "08_BTC_Data")) and os.path.isdir(os.path.join(ROOT, "04_공용엔진코드")): break
    ROOT = os.path.dirname(ROOT)
sys.path.insert(0, os.path.join(ROOT, "04_공용엔진코드", "engines"))
from path_finder import ensure_paths; ensure_paths()
import numpy as np, pandas as pd
import bt_full as B
from blend_opt import rev_side
from fib_replay_1m import load_funding
from rauto_live import per_trade_pnl
from rauto_cex import SlipModel, MMR_T1, LIQ_SLIP
MERGED = os.path.join(ROOT, "08_BTC_Data", "derived", "Merged_Data.csv")


def main():
    cfg = json.load(open(os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp", "back2tv_rev_winners.json")))
    p = cfg["REV_MDD25_36mo"]["p"]; rev_tf = p["rev_tf"]
    d = pd.read_csv(MERGED, usecols=["timestamp","open","high","low","close","oi_zscore_24h"])
    d["t"]=pd.to_datetime(d["timestamp"],utc=True,format="ISO8601").dt.tz_localize(None)
    d=d.dropna(subset=["open"]).set_index("t").sort_index()
    fund=load_funding()
    df, side0 = rev_side(d, rev_tf, p["q"], p["qwin"])
    T = B.gen_trades(d, fund, rev_tf, p["piv"], p["N"], (p["f1"],p["f2"],p["f3"]), p["iam"],
                     er_gate=0.0, ext_side=side0, align_pivot=True, use_trend_flip=False,
                     arm_bars=p["arm"], tp_frac=0.5).sort_values("et").reset_index(drop=True)
    mae = T["mae"].values.astype(float)
    print("="*90)
    print(f"[부분익절 REVoi 레버 스윕 + 강제청산 검증] 거래 {len(T)}")
    print("="*90)
    print(f"REVoi mae(역행) 분포: 중앙{np.median(mae)*100:.2f}% · 5%분위{np.percentile(mae,5)*100:.2f}% · 1%분위{np.percentile(mae,1)*100:.2f}% · 최악{mae.min()*100:.2f}%")
    print("\n[강제청산 문턱 hsd=1/lev−0.0045 + 그 문턱에 걸리는 REVoi 거래수(=mae<=−hsd)]")
    print(f"  {'레버':>5}{'hsd(청산문턱)':>14}{'청산걸림거래':>12}")
    for lev in [3,5,10,20,30,50,75,100,125]:
        hsd = 1.0/lev - MMR_T1 - LIQ_SLIP
        nliqp = int((mae <= -hsd).sum())
        print(f"  {lev:>5}x{hsd*100:>12.2f}%{nliqp:>10}건 ({100*nliqp/len(T):.0f}%)")

    print("\n[레버별: MDD≤−20% 채우는 최대 exposure → 수익/청산]")
    print(f"  {'레버':>5}{'증거금%':>8}{'exposure':>9}{'복리':>11}{'MDD':>8}{'강제청산':>8}")
    grid_exp = [1.0,1.5,2.0,2.25,2.5,2.75,3.0,3.5,4.0,5.0,6.0,8.0]
    best_overall = None
    for lev in [3,5,10,20,30,50,100]:
        best = None
        for exp in grid_exp:
            size = exp*100.0/lev
            pnl, fin, mdd, nliq = per_trade_pnl(T, size, lev, SlipModel(0,0))
            if mdd >= -20.0 and fin > 0:
                if best is None or fin > best[1]:
                    best = (size, fin, mdd, nliq, exp)
        if best:
            size,fin,mdd,nliq,exp = best
            ret=(fin/10000-1)*100
            print(f"  {lev:>5}x{size:>7.1f}%{exp:>9.2f}{ret:>+10.0f}%{mdd:>7.1f}%{nliq:>7}")
            if best_overall is None or ret > best_overall[0]:
                best_overall = (ret, lev, size, mdd, nliq, exp)
        else:
            print(f"  {lev:>5}x  (MDD−20% 내 양수해 없음 = 청산이 수익 잠식)")

    print("\n[캡틴 가설 직접검증 — '극한레버 + 최소사이즈' (exposure 동일 2.25로 맞춤)]")
    print(f"  {'레버':>5}{'증거금%':>8}{'복리':>11}{'MDD':>8}{'강제청산':>8}")
    for lev in [3,10,30,50,100]:
        size = 2.25*100.0/lev   # 동일 exposure=2.25
        pnl, fin, mdd, nliq = per_trade_pnl(T, size, lev, SlipModel(0,0))
        print(f"  {lev:>5}x{size:>7.2f}%{(fin/10000-1)*100:>+10.0f}%{mdd:>7.1f}%{nliq:>7}")

    if best_overall:
        ret,lev,size,mdd,nliq,exp = best_overall
        print(f"\n[최적] 레버{lev}x·증거금{size:.1f}%(exp{exp:.2f}) → 복리 {ret:+.0f}% · MDD{mdd:.1f}% · 강제청산 {nliq}")
    print("[해석] 동일 exposure서 레버↑ = hsd↓ = 청산↑ = 수익 잠식. REVoi(역추세)는 역행 견뎌야 수익 → 저레버 필수.")
    return True


if __name__ == "__main__":
    main()
