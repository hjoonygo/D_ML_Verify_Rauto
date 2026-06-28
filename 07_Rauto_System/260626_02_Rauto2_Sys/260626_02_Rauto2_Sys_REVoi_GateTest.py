# -*- coding: utf-8 -*-
# [REVoi_GateTest] REVoi 휩소/레짐 게이트 정량화 (세션 260626_02_Rauto2_Sys).
#   진단결과 약점 2구간(본전): ⒜4H ER 0.15~0.30(애매 약추세=휩소) ⒝강상승(30일>+12%)에 숏.
#   게이트 = rev_side의 side를 그 구간서 0으로 마스킹(비침습·룩어헤드0=과거ER/추세만). 그 뒤 gen_trades(검증엔진) 그대로.
#   비교: 베이스 / GateA(ER솎기) / GateB(랠리숏솎기) / GateA+B → 전체 PF·복리·MDD + 연도별.
#   ★in-sample 천장 측정(과적합 주의). 의미있으면 OOS/CPCV 별도.
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "04_공용엔진코드", "engines"))
from path_finder import ensure_paths; ensure_paths()
import numpy as np, pandas as pd
import trendstack_signal_engine as TS
import bt_full as B
from blend_opt import rev_side
from fib_replay_1m import load_funding
from rauto_live import per_trade_pnl
from rauto_cex import SlipModel
MERGED = os.path.join(ROOT, "08_BTC_Data", "derived", "Merged_Data.csv")


def run(d, fund, p, gate=None):
    """gate(df) → boolean mask(True=차단). 반환 (T, pnl, fin, mdd, nl)."""
    df, side = rev_side(d, p["rev_tf"], p["q"], p["qwin"])
    side = side.copy()
    if gate is not None:
        mask = gate(df, side)
        side[mask] = 0
    T = B.gen_trades(d, fund, p["rev_tf"], p["piv"], p["N"], (p["f1"], p["f2"], p["f3"]), p["iam"],
                     er_gate=0.0, ext_side=side, align_pivot=True, use_trend_flip=False, arm_bars=p["arm"])
    if not len(T):
        return T, [], 10000.0, 0.0, 0
    T = T.sort_values("et").reset_index(drop=True)
    pnl, fin, mdd, nl = per_trade_pnl(T, 75.0, 3.0, SlipModel(0, 0))
    return T, pnl, fin, mdd, nl


def er30(df):
    """df(4H) → (ER14, ret30d%) 시리즈(과거만)."""
    c = df["close"]
    net = (c - c.shift(14)).abs(); den = c.diff().abs().rolling(14).sum()
    ER = net / (den + 1e-9)
    r30 = (c / c.shift(180) - 1.0) * 100.0   # 180 4H봉 ≈ 30일
    return ER.values, r30.values


def summary(tag, T, pnl, fin, mdd, nl):
    R = np.array(pnl) / 100.0
    if not len(R):
        print(f"{tag:<14} 거래0"); return
    w = R[R > 0]; l = R[R < 0]; pf = (w.sum()/abs(l.sum())) if len(l) else 9.99
    yr = pd.to_datetime(T["et"]).dt.year.values
    ys = []
    for y in sorted(set(yr)):
        _, _, fy, _, _ = (None, None, *per_trade_pnl(T[yr == y], 75.0, 3.0, SlipModel(0, 0))[1:])
        ys.append(f"{y}:{(fy/10000-1)*100:+.0f}%")
    print(f"{tag:<14} 거래{len(R):>4} PF{pf:>4.2f} 승{round((R>0).mean()*100):>2}% 복리{(fin/10000-1)*100:>+8.1f}% MDD{mdd:>5.1f}%  [{' '.join(ys)}]")


def main():
    cfg = json.load(open(os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp", "back2tv_rev_winners.json")))
    p = cfg["REV_MDD25_36mo"]["p"]
    d = pd.read_csv(MERGED, usecols=["timestamp", "open", "high", "low", "close", "oi_zscore_24h"])
    d["t"] = pd.to_datetime(d["timestamp"], utc=True, format="ISO8601").dt.tz_localize(None)
    d = d.dropna(subset=["open"]).set_index("t").sort_index()
    fund = load_funding()
    print("=" * 88)
    print("[REVoi 휩소/레짐 게이트 정량화] 전 기간 2023-05~2026-04 · honest · in-sample 천장")
    print("=" * 88)
    print(f"{'세팅':<14}{'거래':>6}{'PF':>6}{'승률':>5}{'복리':>10}{'MDD':>7}  [연도별 복리]")

    summary("베이스(무게이트)", *run(d, fund, p, None))

    def gateA(df, side):
        ER, _ = er30(df); return (ER >= 0.15) & (ER < 0.30)        # 애매 약추세 솎기
    summary("A:ER0.15~0.30솎", *run(d, fund, p, gateA))

    def gateB(df, side):
        _, r30 = er30(df); return (side == -1) & (r30 > 12.0)      # 강상승 랠리에 숏 솎기
    summary("B:랠리숏솎", *run(d, fund, p, gateB))

    def gateAB(df, side):
        ER, r30 = er30(df)
        return ((ER >= 0.15) & (ER < 0.30)) | ((side == -1) & (r30 > 12.0))
    summary("A+B", *run(d, fund, p, gateAB))

    # 보너스: 더 좁은 ER게이트(0.18~0.28)
    def gateA2(df, side):
        ER, _ = er30(df); return (ER >= 0.18) & (ER < 0.28)
    summary("A2:ER0.18~0.28", *run(d, fund, p, gateA2))

    print("\n[해석] 게이트가 ⒜복리 유지/상승 + ⒝MDD 개선 + ⒞연도별 더 고름 = 채택가치.")
    print("       베이스 대비 복리 크게 떨어지면(좋은거래까지 솎음) = 기각. in-sample 통과시 OOS/CPCV 필수.")
    return True


if __name__ == "__main__":
    main()
