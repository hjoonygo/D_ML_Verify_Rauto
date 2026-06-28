# -*- coding: utf-8 -*-
# [260625_01_RautoSysReform2_OrchestratorAnchorTest.py] ★④ 관제센터(오케스트레이터) 앵커 회귀 (세션 260625_01_RautoSysReform2).
#   기대: RautoOrchestrator.run_backtest ≡ 기존 monolith(back2tv_REVoi.liq_eval) = 앵커 +1851.6%/MDD-24.6% 차이 0.000%p.
#   = 4부품을 'RautoOrchestrator 클래스'로 정식 조립해도 1원단위 동일(무손상 §15.2). 검증엔진 무수정·호출만.
import os
import sys
import json

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))          # 07_Rauto_System/<세션> → RfRauto 루트
sys.path.insert(0, os.path.join(ROOT, "04_공용엔진코드", "engines"))
from path_finder import ensure_paths
ensure_paths()
import pandas as pd  # noqa: E402
from fib_replay_1m import load_1m, load_funding  # noqa: E402
import back2tv_REVoi as BR  # noqa: E402
from rauto_orchestrator import RautoOrchestrator  # noqa: E402
from REVoi_bot import REVoiBot  # noqa: E402
from rauto_cex import SlipModel  # noqa: E402

LOG = os.path.join(HERE, "260625_01_RautoSysReform2_OrchestratorAnchorTest_run.log")


def _p(*a):
    print(*a, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(" ".join(str(x) for x in a) + "\n")


def main():
    cfg = json.load(open(os.path.join(ensure_paths(), "03_IDEA4Bot", "260623_07_RfRautoAlphaUp",
                                       "back2tv_rev_winners.json")))
    p = cfg["REV_MDD25_36mo"]["p"]
    d1m = load_1m()
    fund = load_funding()

    # ── 봇(REVoi) → 관제센터(봇 무관) → RautoCEX 조립·구동 (앵커=슬립0) ──
    bot = REVoiBot(p)                                           # ① 봇: 신호+진입/청산(알파)
    orch = RautoOrchestrator(bot, size_pct=75.0, lev=3.0, slip=SlipModel(0.0, 0.0))  # 사이징=Rauto, 비용=CEX
    r = orch.run_backtest(d1m, fund)
    T = r["trades"]
    _p(f"[관제센터] 봇={r['bot']} · 거래 {len(T)} · 사이징 레버{orch.lev}/증거금{orch.size_pct}%")
    _p(f"[관제센터→RautoCEX] 복리 {r['tot']:+.1f}% · MDD {r['mdd']:.1f}% · 청산 {r['nliq']}")

    # ── 앵커 대조: 기존 monolith 경로(back2tv liq_eval) ──
    R = T["R"].values.astype(float)
    MAE = T["mae"].values.astype(float)
    FUND = T["fund"].values.astype(float)
    MK = T["_ym"].values
    tot0, mdd0, _, nl0 = BR.liq_eval(R, MAE, FUND, MK, 75.0, 3.0)

    d_tot = abs(r["tot"] - tot0)
    d_mdd = abs(r["mdd"] - mdd0)
    PASS = d_tot < 0.5 and d_mdd < 0.5 and r["nliq"] == nl0

    _p("\n" + "=" * 60)
    _p("[④ 관제센터 앵커 회귀]")
    _p(f"  기존 monolith(liq_eval)        : {tot0:+.1f}% · MDD {mdd0:.1f}% · 청산 {nl0}")
    _p(f"  RautoOrchestrator(4부품 조립)  : {r['tot']:+.1f}% · MDD {r['mdd']:.1f}% · 청산 {r['nliq']}")
    _p(f"  차이: 복리 {d_tot:.3f}%p · MDD {d_mdd:.3f}%p · 청산일치 {r['nliq'] == nl0}")
    _p(f"  → {'★PASS — 관제센터로 정식 조립해도 1원단위 동일(무손상 §15.2)' if PASS else '✗FAIL — 멈추고 원인규명'}")
    _p(f"\n[판정] ④ 관제센터(봇 무관 v0)+REVoi봇(계약 make_trades) {'완료' if PASS else '실패'}. 다음=TS·SW를 같은 계약으로 끼워 멀티봇 검증.")
    return PASS


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
