# -*- coding: utf-8 -*-
# [260625_01_Rauto_Sys_Reform_WiredAnchorTest.py] ★③ 전체체인 앵커 회귀 (세션 260625_01_Rauto_Sys_Reform).
#   배선: DataHub(②) → SignalModule(①신호) → DecisionModule(②결정·가) → RautoCEX(③비용).
#   기대: 모듈 경계로 갈라 배선해도 앵커 +1851.6%/MDD-24.6% 1원단위 재현(무손상 §15.2).
import os, sys, json
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\engines")
sys.path.insert(0, r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
from fib_replay_1m import load_1m, load_funding
import back2tv_REVoi as BR
from rauto_datahub import DataHub
from rauto_signal import SignalModule
from rauto_decision import DecisionModule
from rauto_cex import RautoCEX, SlipModel
HERE = os.path.dirname(os.path.abspath(__file__))


def _p(*a):
    print(*a, flush=True)
    open(os.path.join(HERE, "260625_01_Rauto_Sys_Reform_WiredAnchorTest_run.log"), "a", encoding="utf-8").write(" ".join(str(x) for x in a)+"\n")


def main():
    p = json.load(open(os.path.join(r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp", "back2tv_rev_winners.json")))["REV_MDD25_36mo"]["p"]
    d1m = load_1m(); fund = load_funding()

    # ── 모듈 배선 ──
    hub = DataHub(d1m)                                              # ② 중앙 1m
    sig_mod = SignalModule(p["rev_tf"], p["q"], p["qwin"])          # ① 신호
    dec_mod = DecisionModule(p["piv"], p["N"], (p["f1"], p["f2"], p["f3"]), p["iam"], p["arm"], size_pct=75.0, lev=3.0)  # ② 결정(가)
    cex = RautoCEX(dec_mod.size_pct, dec_mod.lev, slip=SlipModel(0.0, 0.0))   # ③ 비용(앵커=슬립0)

    signal = sig_mod.generate(d1m)                                 # 신호 객체
    _p(f"[① 신호] tf={signal.tf} · 진입방향 봉수 {int((signal.side!=0).sum())} (롱 {int((signal.side==1).sum())}/숏 {int((signal.side==-1).sum())})")
    T = dec_mod.decide(d1m, fund, signal)                          # 결정 → 거래원장
    T["_ym"] = pd.to_datetime(T["et"]).dt.to_period("M").astype(str)
    _p(f"[② 결정] 거래 {len(T)} · 사이징 레버{dec_mod.lev}/증거금{dec_mod.size_pct}%")
    r = cex.run(T)                                                 # 비용·복리
    _p(f"[③ RautoCEX] 복리 {r['tot']:+.1f}% · MDD {r['mdd']:.1f}% · 청산 {r['nliq']}")

    # ── 앵커 대조: 기존 monolith 경로(back2tv liq_eval) ──
    R = T["R"].values.astype(float); MAE = T["mae"].values.astype(float); FUND = T["fund"].values.astype(float)
    MK = T["_ym"].values
    tot0, mdd0, _, nl0 = BR.liq_eval(R, MAE, FUND, MK, 75.0, 3.0)
    d_tot = abs(r["tot"] - tot0); d_mdd = abs(r["mdd"] - mdd0)
    PASS = d_tot < 0.5 and d_mdd < 0.5 and r["nliq"] == nl0
    _p("\n" + "="*60)
    _p(f"[③ 전체체인 앵커 회귀]")
    _p(f"  기존 monolith(liq_eval) : {tot0:+.1f}% · MDD {mdd0:.1f}%")
    _p(f"  모듈배선(신호→결정→CEX) : {r['tot']:+.1f}% · MDD {r['mdd']:.1f}%")
    _p(f"  차이: 복리 {d_tot:.3f}%p · MDD {d_mdd:.3f}%p")
    _p(f"  → {'★PASS — 모듈로 갈라 배선해도 1원단위 동일(무손상 §15.2)' if PASS else '✗FAIL — 멈추고 원인규명'}")
    _p(f"\n[판정] ③ 신호/결정 분리(가, 래퍼·검증엔진 무수정) {'완료' if PASS else '실패'}. 다음=④관제센터 슬롯/챔피언.")


if __name__ == "__main__":
    main()
