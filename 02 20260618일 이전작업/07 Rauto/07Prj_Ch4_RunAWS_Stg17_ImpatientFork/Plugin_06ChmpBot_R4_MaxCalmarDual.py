# -*- coding: utf-8 -*-
# [Plugin_06ChmpBot_R4_MaxCalmarDual.py] R4 = 최고Calmar듀얼 (성급왕TS + 인내SW, k1.4·ER댐핑)
# ──────────────────────────────────────────────────────────────────────
# [정체] R3와 동일 구조, 사이즈 배수만 k1.4(더 크게 베팅). 절대수익 최고이나 MDD 큼.
# [엔진] bot_trendstack_impatient_king + bot_sidewaydca_signal + SidewayDCA_Stg7_engine (검증 무수정 §8).
# [설정] 듀얼 $20k · king 레버22 · SW 레버15 · k1.4 · ER_thr0.40 · W0.0 · 손절 5bp.
# [★확정 36개월 현실백테] +30,156% / MDD -23.4% / 754거래 / 승률38% / PF1.94 / 손익비3.14
#        ★★경고: MDD -23.4% = -20% 절대선 위반 → 실거래 부적합(고수익이나 도달 전 한도 위반 위험). 실거래는 R2/R3 권장.
#        연도 23:+423 24:+891 25:+1286 26:+225% · 롱+4458 숏+5032%. (CLAUDE.md §15)
# [Rauto 연동] 라이브 슬롯 = test_dual_runner.py (C:\Rauto4, env DUAL_SLOT=R4·DUAL_K=1.4·DUAL_ER=0.40·DUAL_W=0.0). champ=False.
# [재현] python Plugin_06ChmpBot_R4_MaxCalmarDual.py → plugin_common.run_dual(1.4,0.40,0.0). 입력=led36_king.csv + sw_patient_er.csv.
# ──────────────────────────────────────────────────────────────────────
import plugin_common as pc
META = {"slot": "R4", "name": "최고Calmar듀얼(MaxCalmarDual)", "engine": "king+SidewayDCA",
        "lev": 22, "sw_lev": 15, "k": 1.4, "er_thr": 0.40, "w": 0.0, "mode": "dual",
        "champion": False, "warn": "MDD -23.4% = -20% 위반, 실거래 부적합", "live_runner": "test_dual_runner.py(DUAL_SLOT=R4)"}
CONFIRMED = {"ret": 30156, "mdd": -23.4, "trades": 754, "winrate": 38, "pf": 1.94, "payoff": 3.14}


def backtest():
    return pc.run_dual(1.4, 0.40, 0.0)


if __name__ == "__main__":
    pc.report(META["name"], backtest())
