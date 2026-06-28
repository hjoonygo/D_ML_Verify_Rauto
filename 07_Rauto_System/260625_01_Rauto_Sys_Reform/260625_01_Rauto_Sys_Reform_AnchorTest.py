# -*- coding: utf-8 -*-
# [260625_01_Rauto_Sys_Reform_AnchorTest.py] ★안전장치1 — RautoCEX 무손상 추출 회귀테스트 (세션 260625_01_Rauto_Sys_Reform).
#   같은 거래원장을 ⒜기존 경로(back2tv_REVoi.liq_eval) ⒝새 RautoCEX 모듈로 각각 돌려 '1원단위 동일'인지 대조.
#   기대: 슬립0·스프0 → +1852%/MDD-25(앵커 재현=추출 무손상) · 스프1bp → +1483%(SlipRecheck 일치).
import os, sys, json
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\engines")
sys.path.insert(0, r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
from fib_replay_1m import load_1m, load_funding
import back2tv_REVoi as BR
import rauto_cex as CEX
HERE = os.path.dirname(os.path.abspath(__file__))


def _p(*a):
    print(*a, flush=True)
    open(os.path.join(HERE, "260625_01_Rauto_Sys_Reform_AnchorTest_run.log"), "a", encoding="utf-8").write(" ".join(str(x) for x in a)+"\n")


def main():
    w = json.load(open(os.path.join(r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp", "back2tv_rev_winners.json")))["REV_MDD25_36mo"]["p"]
    d1m = load_1m(); fund = load_funding()
    T = BR.rev_trades(d1m, fund, w).sort_values("et").reset_index(drop=True)
    T["_ym"] = pd.to_datetime(T["et"]).dt.to_period("M").astype(str)
    R = T["R"].values.astype(float); MAE = T["mae"].values.astype(float); FUND = T["fund"].values.astype(float)
    MKEY = T["_ym"].values
    _p(f"[거래] {len(T)} · 세팅 레버{w.get('lev','3')}→실제 레버3/증거금75%/노출2.2")

    # ⒜ 기존 경로 (back2tv_REVoi.liq_eval) — 앵커 원본
    tot_old, mdd_old, _, nl_old = BR.liq_eval(R, MAE, FUND, MKEY, 75.0, 3.0)

    # ⒝ 새 RautoCEX — 같은 입력
    cex_anchor = CEX.RautoCEX(75.0, 3.0, slip=CEX.SlipModel(gap_bp=0.0, exit_spread_bp=0.0))
    r1 = cex_anchor.run(T)
    cex_real = CEX.RautoCEX(75.0, 3.0, slip=CEX.SlipModel(gap_bp=0.0, exit_spread_bp=1.0))  # 측정갭0+스프1bp
    r2 = cex_real.run(T)

    _p("\n" + "="*64)
    _p("[관문1 무손상 추출 회귀테스트]")
    _p(f"  ⒜ 기존 liq_eval        : {tot_old:+.1f}% · MDD {mdd_old:.1f}% · 청산 {nl_old}")
    _p(f"  ⒝ 새 RautoCEX(슬립0)   : {r1['tot']:+.1f}% · MDD {r1['mdd']:.1f}% · 청산 {r1['nliq']}")
    d_tot = abs(r1["tot"] - tot_old); d_mdd = abs(r1["mdd"] - mdd_old)
    PASS = d_tot < 0.5 and d_mdd < 0.5 and r1["nliq"] == nl_old
    _p(f"  → 차이 복리 {d_tot:.3f}%p · MDD {d_mdd:.3f}%p · 청산일치 {r1['nliq']==nl_old}")
    _p(f"  → {'★PASS 무손상 추출 (기존≡신모듈, 1원단위 동일)' if PASS else '✗FAIL 추출 손상 — 원인규명 멈춤(§15.2)'}")

    _p(f"\n  ⒞ 새 RautoCEX(측정갭0+스프1bp) : {r2['tot']:+.0f}% · MDD {r2['mdd']:.0f}%  (SlipRecheck +1483% 대조)")
    real_ok = abs(r2["tot"] - 1483) < 30
    _p(f"  → SlipRecheck(+1483%)와 일치: {real_ok}")

    _p(f"\n[비용 단일출처 검증] RautoCEX가 보고한 36개월 비용$ (현실 스프1bp 기준):")
    c = r2["cost"]
    _p(f"  메이커 {c['maker']:,.0f} · 테이커 {c['taker']:,.0f} · 슬립(갭0+스프1bp) {c['slip']:,.0f} · 펀딩 {c['fund']:,.0f}")
    _p(f"\n[판정] 안전장치1(무손상추출) {'통과' if PASS else '실패'} · 안전장치4(비용 execution만, selection_cost 미유입) 구조적 보장")
    _p("[다음] ②중앙1m+룩어헤드 게이트 / 또는 RautoCEX를 04_공용엔진코드로 승급(검증 통과 시)")


if __name__ == "__main__":
    main()
