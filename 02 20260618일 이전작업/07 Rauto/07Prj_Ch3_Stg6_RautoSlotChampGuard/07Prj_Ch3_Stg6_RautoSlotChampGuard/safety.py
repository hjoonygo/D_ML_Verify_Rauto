# [파일명] safety.py
# 코드길이: 약 80줄 / 내부버전: safety_v1 / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] 무인 24h 운영 안전장치(기본형). (요구사항 4)
#        - 킬스위치(수동/원격): 즉시 신규진입 차단
#        - 서킷브레이커: 계좌 MDD <= -20% 도달 시 자동 차단(차단=신규진입 정지)
#        - 연속손실 카운터: N회 연속손실 시 일시정지
#        - 사람 오버라이드: reset()으로 해제
# [주의] 킬스위치가 엉뚱하게 작동하면 역효과 → '신규진입만' 막고, 보유포지션 처리/청산은
#        엔진·봇 로직에 맡긴다(여기선 게이트 역할). 트리거는 보수적으로.
# [Lookahead] 해당 없음.
# ── 사용 파일 ── 없음
# ── 함수 In/Out ──
#  SafetyGuard(mdd_limit,max_consec) In: 한도(기본-20%)·연속손실한도(기본4) → Out: 가드
#   .trip_kill()        In: -        → Out: 킬스위치 ON
#   .reset()            In: -        → Out: 킬·서킷·연속손실 해제(사람 오버라이드)
#   .on_equity(mdd_pct) In: 현재 MDD% → Out: -20% 이하면 서킷 트립
#   .on_trade(p)        In: 1거래손익p → Out: 연속손실 카운트(이익이면 0으로 리셋)
#   .allow_entry()      In: -        → Out: 신규진입 허용 여부(bool)
#   .status()           In: -        → Out: 상태 dict(killed,circuit,consec,halted)
# ── 상수 ── 기본 mdd_limit=-20.0 / max_consec=4
# ─────────────────────────────────────────────────────────────────────────
from typing import Dict, Any


class SafetyGuard:
    def __init__(self, mdd_limit: float = -20.0, max_consec: int = 4):
        self.mdd_limit = mdd_limit
        self.max_consec = max_consec
        self.killed = False
        self.circuit = False        # -20% 차단
        self.consec_losses = 0
        self.consec_halt = False    # 연속손실 일시정지

    def trip_kill(self) -> None:
        self.killed = True

    def reset(self) -> None:
        self.killed = False
        self.circuit = False
        self.consec_losses = 0
        self.consec_halt = False

    def on_equity(self, mdd_pct: float) -> None:
        if mdd_pct <= self.mdd_limit:
            self.circuit = True

    def on_trade(self, p: float) -> None:
        if p < 0:
            self.consec_losses += 1
            if self.max_consec > 0 and self.consec_losses >= self.max_consec:
                self.consec_halt = True   # max_consec<=0 이면 연속손실 차단 비활성(충실 재현용)
        else:
            self.consec_losses = 0

    def allow_entry(self) -> bool:
        return not (self.killed or self.circuit or self.consec_halt)

    def status(self) -> Dict[str, Any]:
        return {"killed": self.killed, "circuit": self.circuit,
                "consec_losses": self.consec_losses, "consec_halt": self.consec_halt,
                "halted": not self.allow_entry()}
