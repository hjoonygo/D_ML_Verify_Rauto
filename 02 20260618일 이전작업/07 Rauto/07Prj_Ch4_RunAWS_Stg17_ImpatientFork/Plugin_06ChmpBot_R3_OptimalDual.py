# -*- coding: utf-8 -*-
# [Plugin_06ChmpBot_R3_OptimalDual.py] R3 = 최적듀얼 (성급왕TS + 인내SW, k1.1·ER댐핑)
# ──────────────────────────────────────────────────────────────────────
# [정체] 추세봇(성급왕TS) + 횡보봇(인내 SidewayDCA) 듀얼. 두 페이퍼계좌 합산 포트($20k).
#        SW 댐핑: ER>=0.40(추세장)이면 SW size×0.0 = 빠짐(횡보전문). k=1.1(사이즈 배수).
# [엔진] bot_trendstack_impatient_king + bot_sidewaydca_signal + SidewayDCA_Stg7_engine (검증 무수정 §8).
# [설정] 듀얼 $20k(king $10k + SW $10k) · king 레버22 · SW 레버15 · k1.1 · ER_thr0.40 · W0.0 · 손절 5bp.
# [★확정 36개월 현실백테] +8,850% / MDD -18.0% / 754거래 / 승률38% / PF1.94 / 손익비3.14 (듀얼 중 -20% 안전선內)
#        연도 23:+277 24:+548 25:+739 26:+157% · 롱+2112 숏+2284%. SW가 횡보장 보태 승률·PF↑. (CLAUDE.md §15)
# [Rauto 연동] 라이브 슬롯 = test_dual_runner.py (C:\Rauto3, env DUAL_SLOT=R3·DUAL_K=1.1·DUAL_ER=0.40·DUAL_W=0.0). champ=False.
# [재현] python Plugin_06ChmpBot_R3_OptimalDual.py → plugin_common.run_dual(1.1,0.40,0.0). 입력=led36_king.csv + sw_patient_er.csv.
# ──────────────────────────────────────────────────────────────────────
import plugin_common as pc
META = {"slot": "R3", "name": "최적듀얼(OptimalDual)", "engine": "king+SidewayDCA",
        "lev": 22, "sw_lev": 15, "k": 1.1, "er_thr": 0.40, "w": 0.0, "mode": "dual",
        "champion": False, "live_runner": "test_dual_runner.py(DUAL_SLOT=R3)"}
CONFIRMED = {"ret": 8850, "mdd": -18.0, "trades": 754, "winrate": 38, "pf": 1.94, "payoff": 3.14}


def backtest():
    return pc.run_dual(1.1, 0.40, 0.0)


if __name__ == "__main__":
    pc.report(META["name"], backtest())
