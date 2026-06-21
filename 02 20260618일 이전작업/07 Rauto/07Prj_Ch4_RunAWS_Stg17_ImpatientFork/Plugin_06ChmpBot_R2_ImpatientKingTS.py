# -*- coding: utf-8 -*-
# [Plugin_06ChmpBot_R2_ImpatientKingTS.py] R2 = TS-성급왕 단독 ★챔피언 (TrendStackImpatientKingBot)
# ──────────────────────────────────────────────────────────────────────
# [정체] 성급TS + 1분 인트라바 손절가드 + 재진입 쿨다운 + 7H 그리드 핀고정(GRID_ANCHOR).
#        유일 차이=손절을 7H마감이 아닌 매 1분 검사→터치 즉시 손절(추세전환보다 우선). 그 외 성급과 1:1 동일.
# [엔진] bot_trendstack_impatient_king (성급 상속, on_bar만 확장; 검증엔진 무수정 §8·§1 래퍼).
# [설정] 단독 $10k · 레버22 · k1.0 · 손절 5bp 스톱슬립. 봉경계 핀고정으로 백테 resample 그리드와 정렬.
# [★확정 36개월 현실백테] +11,397% / MDD -17.3% / 668거래 / 승률34% / PF1.90 / 손익비3.69 ★단위자본 최강
#        연도 23:+173 24:+316 25:+376 26:+113% · 롱+960 숏+984%. CPCV 표준6 통과(p25+24%, INDEX254). (CLAUDE.md §15)
# [Rauto 연동] 라이브 슬롯 = test_Rauto2.py (C:\Rauto2). champ=True(챔피언). 제어앱 상단 트로피 표시. b25 정렬.
# [재현] python Plugin_06ChmpBot_R2_ImpatientKingTS.py → plugin_common.run_single('king',1.0). 입력=led36_king.csv.
# ──────────────────────────────────────────────────────────────────────
import plugin_common as pc
META = {"slot": "R2", "name": "TS-성급왕(ImpatientKingTS)", "engine": "bot_trendstack_impatient_king",
        "lev": 22, "k": 1.0, "mode": "single", "champion": True, "live_runner": "test_Rauto2.py"}
CONFIRMED = {"ret": 11397, "mdd": -17.3, "trades": 668, "winrate": 34, "pf": 1.90, "payoff": 3.69}


def backtest():
    return pc.run_single('king', 1.0)


if __name__ == "__main__":
    pc.report(META["name"], backtest())
