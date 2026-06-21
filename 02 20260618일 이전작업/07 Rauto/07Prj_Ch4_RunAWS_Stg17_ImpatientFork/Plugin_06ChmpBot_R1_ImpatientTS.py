# -*- coding: utf-8 -*-
# [Plugin_06ChmpBot_R1_ImpatientTS.py] R1 = TS-성급 단독 (TrendStackImpatientBot)
# ──────────────────────────────────────────────────────────────────────
# [정체] 추세추종 7H. 피벗확인 안 기다리고 즉시 진입(성급). OI무덤·ER0.45 게이트, OPVnN 사이징,
#        업트렌드 숏컷, 피보 트레일 손절(1%→트레일).
# [엔진] trendstack_signal_engine + bot_trendstack_impatient (검증 무수정 §8). 재구현 금지.
# [설정] 단독 $10k · 레버22 · k1.0 · 손절 5bp 스톱슬립(검증 A/B '0~20bp 견고'). 진입/청산슬립 ~0(measure_slippage).
# [★확정 36개월 현실백테] +5,932% / MDD -20.0% / 666거래 / 승률34% / PF1.72 / 손익비3.38
#        연도 23:+133 24:+244 25:+288 26:+94% · 롱+614 숏+745%(전부 양수). (CLAUDE.md §15)
# [Rauto 연동] 라이브 슬롯 = test_Rauto1.py (C:\Rauto1). 제어앱 차트 b25(open_et 체결분 정렬). champ=False.
# [재현] python Plugin_06ChmpBot_R1_ImpatientTS.py
#        → plugin_common.run_single('imp',1.0). 입력=led36_imp_pinned.csv(핀고정 검증엔진 on_bar 산출).
#        깊은재현(원장 재생성): bt36_ledgers.py + Merged_Data.csv(05_Data DATA_NOTE 참조).
# ──────────────────────────────────────────────────────────────────────
import plugin_common as pc
META = {"slot": "R1", "name": "TS-성급(ImpatientTS)", "engine": "bot_trendstack_impatient",
        "lev": 22, "k": 1.0, "mode": "single", "champion": False, "live_runner": "test_Rauto1.py"}
CONFIRMED = {"ret": 5932, "mdd": -20.0, "trades": 666, "winrate": 34, "pf": 1.72, "payoff": 3.38}


def backtest():
    return pc.run_single('imp', 1.0)


if __name__ == "__main__":
    pc.report(META["name"], backtest())
