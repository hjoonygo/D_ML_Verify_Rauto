# -*- coding: utf-8 -*-
# =============================================================================
# [ts_impatient_plugin.py] TrendStack "Impatient(성급)" 실행 Plugin 모듈
#   06Prj_Ch8_Plugin_Stg1_TS_Impatient · 2026-06-15
# -----------------------------------------------------------------------------
# [무엇] 추세추종 TrendStack의 '성급(인내심 없는)' 변종을 라이브 실행 프로파일과 함께
#        하나의 Plugin으로 묶은 것. 신호 로직은 bot_trendstack_impatient.TrendStackImpatientBot
#        (검증된 _step, 동치 True)을 그대로 쓰고, 여기서는 '체결 방식'을 명세한다.
#
# [성급(Impatient)의 정의 — 한 줄]  진입에 피벗 새 확정(new_pl/new_ph) 대기를 제거하고,
#   추세 방향이면 즉시 진입한다. (기존=인내심: 피벗 확정까지 중앙 9봉=63h 대기)
#   → 추세 초반을 더 일찍·더 많이 잡는다. 3년 백테 전 연도·전 장세·롱숏 모두 우위(CPCV 표준6 통과).
#
# [★실행 프로파일 — 캡틴 확정 2026-06-15]
#   · 진입(ENTER) = 지정가(LIMIT) @ 신호봉 종가.  7h봉은 7시간 창이라 신호가 지정가가
#     다음 봉 안에 100% 체결됨(검증: verify_limit_fill.py, TS 716건 100%). 메이커 수수료.
#     ※욕심(passive offset)으로 더 유리하게 걸면 역선택(좋은 거래 놓침) — 신호가 그대로 권장.
#   · 청산(EXIT) = 시장가(MARKET).  손절(SL)은 스톱 → 시장가 강제(메이커 불가). trend_flip 청산도
#     본 프로파일에선 시장가 통일(캡틴 지시 "청산만 시장가").
#   · 현실 비용 ≈ 진입 메이커 2bp + 청산 테이커 6bp = 왕복 ~8bp.
#     이 비용에서 성급TS 단독 3년 = +1368% / MDD -18.3% (절대선 -20% 이내) / Calmar 75.
#
# [★성급의 향후 확장 가능성 — 추가 알파 연구 필요(미검증, 신뢰15)]
#   '성급(피벗대기 제거)'은 단지 진입 1축만 바꾼 것인데도 큰 개선을 냈다. 같은 '성급' 원리를
#   다음 축들에 적용하면 추가 알파 여지가 있다(별도 사이클서 측정·검증 후에만 채택):
#     ① 부분 익절/피라미딩 타이밍을 성급화(피벗 대기 없이 단계 추가).
#     ② 추세 재확인 없이 같은 방향 재진입 빈도/사이즈 최적화.
#     ③ 멀티 TF 성급(4H/7h 동시 플립 시 가중).
#     ④ '성급'을 강신호(ER·ADX)로 게이팅해 횡보 휩쓸림만 선별 차단(N표본 누적 후 ML 후보).
#   ※경고(검증 결과): '성급'은 추세추종에만 약이다. 평균회귀(SidewayDCA)에 성급을 적용하면
#     '떨어지는 칼 잡기'로 역효과(2026 PF 0.77 손실). 봇 성격에 맞춰서만 적용할 것.
#
# [무수정 원칙] §8 해시락 엔진/봇(trendstack_signal_engine·bot_trendstack_signal·rauto_*)은
#   무수정. 본 plugin은 TrendStackImpatientBot(서브클래스 래퍼)을 import만 한다.
# [In] MarketBar(1m 스트림)   [Out] Signal(ENTER/EXIT/HOLD) + EXEC_PROFILE로 라우팅 힌트
# [주의] 실제 지정가/시장가 주문 라우팅은 라이브 '주문 모듈'(미구축, LiveTransition 체크리스트 B)이
#   EXEC_PROFILE을 읽어 수행한다. 본 모듈은 신호+프로파일 명세까지가 책임 범위.
# =============================================================================
import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__))
_BOTS = os.path.join(_HERE, "bots")
if _BOTS not in sys.path:
    sys.path.insert(0, _BOTS)

from bot_trendstack_impatient import TrendStackImpatientBot
from rauto_contract import Action, Side

# ── 실행 프로파일(주문 모듈이 읽는 라우팅 명세) ──
EXEC_PROFILE = {
    "entry": {"order_type": "LIMIT", "price": "signal_close", "offset_bp": 0,
              "tif": "GTC", "max_wait_bars": 1, "fallback": "MARKET",
              "note": "7h창 100% 체결(검증). offset 0 권장(역선택 회피)."},
    "exit":  {"order_type": "MARKET",
              "note": "SL=스톱→시장가 강제. trend_flip도 시장가 통일(캡틴 지시)."},
    "cost_assumption_bp": {"entry_maker": 2, "exit_taker": 6, "round_trip": 8},
    "verified": {"mdd_pct": -18.3, "ret_3y_pct": 1368, "calmar": 75,
                 "cpcv_std6_p25_pct": 1027, "cpcv_worst_path_pct": 830,
                 "basis": "3Y 2023-05~2026-04, $10k, lev22, k0.77, entry-limit/exit-market ~8bp"},
}

META = {
    "name": "TS_Impatient_Plugin",
    "version": "06Prj_Ch8_Stg1",
    "signal_class": "TrendStackImpatientBot (impatient-v1, no-pivot-wait entry, warmup-guard)",
    "engine": "SpTrd_Fib_V1_Champion(1:1) via trendstack_signal_engine (unmodified, §8)",
    "exec_profile": EXEC_PROFILE,
    "status": "BACKTEST-VALIDATED candidate (6 gates passed). Live (06-19 paper) = final gate.",
    "alpha_save_reminder": ("최종 채택 시 G:\\내 드라이브\\00AI개발지식DB\\자산관리\\유동자산\\"
                            "자동매매\\06 ChampBot\\00ALPHA_Confirm_Bot 에 반드시 저장(세션 유실 방지)."),
}


def make_bot(config=None):
    """검증된 성급 TS 신호봇 인스턴스 생성(+on_init)."""
    bot = TrendStackImpatientBot()
    bot.on_init({"config": config or {}})
    return bot


def route_signal(sig):
    """Signal → 주문 라우팅 명세 반환(라이브 주문모듈이 소비). 신호 자체는 무변경."""
    if sig is None or sig.action == Action.HOLD:
        return None
    if sig.action == Action.ENTER:
        return {"action": "ENTER", "side": sig.side.name, "size_pct": sig.size_pct,
                "leverage": sig.leverage, **EXEC_PROFILE["entry"]}
    if sig.action == Action.EXIT:
        return {"action": "EXIT", **EXEC_PROFILE["exit"]}
    return None


if __name__ == "__main__":
    print("[TS_Impatient_Plugin]")
    for k, v in META.items():
        print(f"  {k}: {v}")
