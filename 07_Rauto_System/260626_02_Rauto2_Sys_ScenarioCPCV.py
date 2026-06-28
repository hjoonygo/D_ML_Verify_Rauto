# -*- coding: utf-8 -*-
# [ScenarioCPCV] 상위 시나리오 CPCV 표준6 검증 (세션 260626_02_Rauto2_Sys).
#   캡틴 지시: 스윕 결과 본 뒤 CPCV 표준6로 검증. 통과 = p25>0 & 음수폴드0 (§5.7).
#   대상 = 베이스 / E1(랠리숏솎) / E2(MA숏솎) / X2(부분익절) / C2(E1+부분익절).
#   ★_cpcv_stats = bot_trust_gates 공용(월수익 6그룹·15경로·연환산 p25). 무수정 호출.
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
from rauto_cex import SlipModel
from bot_trust_gates import _cpcv_stats
MERGED = os.path.join(ROOT, "08_BTC_Data", "derived", "Merged_Data.csv")


def main():
    cfg = json.load(open(os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp", "back2tv_rev_winners.json")))
    p = cfg["REV_MDD25_36mo"]["p"]; rev_tf = p["rev_tf"]
    d = pd.read_csv(MERGED, usecols=["timestamp","open","high","low","close","oi_zscore_24h"])
    d["t"]=pd.to_datetime(d["timestamp"],utc=True,format="ISO8601").dt.tz_localize(None)
    d=d.dropna(subset=["open"]).set_index("t").sort_index()
    fund=load_funding()
    df, side0 = rev_side(d, rev_tf, p["q"], p["qwin"])
    c4=df["close"]; r30=np.nan_to_num(((c4/c4.shift(180)-1)*100).values)
    MA=c4.rolling(200).mean(); dist=np.nan_to_num(((c4/MA-1)*100).fillna(0).values)

    def gen(side, **kw):
        T=B.gen_trades(d,fund,rev_tf,p["piv"],p["N"],(p["f1"],p["f2"],p["f3"]),p["iam"],
                       er_gate=0.0,ext_side=side,align_pivot=True,use_trend_flip=False,arm_bars=p["arm"],**kw)
        return T.sort_values("et").reset_index(drop=True)

    def mask(cond): s=side0.copy(); s[cond]=0; return s
    cands = {
        "베이스": gen(side0),
        "E1.랠리숏솎": gen(mask((side0==-1)&(r30>12))),
        "E2.MA숏솎": gen(mask((side0==-1)&(dist>8))),
        "X2.부분익절": gen(side0, tp_frac=0.5),
        "C2.E1+부분익절": gen(mask((side0==-1)&(r30>12)), tp_frac=0.5),
    }
    print("="*84)
    print("[CPCV 표준6 검증] 6그룹·15경로 · 통과=p25>0 & 음수폴드0 (§5.7)")
    print("="*84)
    print(f"{'시나리오':<16}{'거래':>5}{'복리(사이즈드)':>13}{'MDD':>7}{'p25(연%)':>10}{'음수폴드':>8}{'경로':>5}  판정")
    for nm, T in cands.items():
        pnl,fin,mdd,nl = per_trade_pnl(T,75.0,3.0,SlipModel(0,0))
        p25, neg, npath = _cpcv_stats(T)
        ok = (p25 is not None) and (p25 > 0) and (neg == 0.0)
        negs = "-" if neg is None else f"{neg*100:.0f}%"
        p25s = "-" if p25 is None else f"{p25:+.1f}"
        print(f"{nm:<16}{len(T):>5}{(fin/10000-1)*100:>+12.0f}%{mdd:>6.1f}%{p25s:>10}{negs:>8}{npath:>5}  {'✅통과' if ok else '❌미달'}")
    print("\n[기준] p25>0(최악25%경로도 +) & 음수폴드0% = 표준6 통과 → 채택 자격. MDD−16%면 M20(챔피언)도 통과.")
    return True


if __name__ == "__main__":
    main()
