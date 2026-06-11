# [파일명] bot_trendstack_replay.py
# 코드길이: 약 90줄 / 내부버전: trendstack_ch3s2_replay_v1 / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] TrendStack '자기완결 봇' (Task2 1차 슬라이스, 리플레이형).
#        - 진입 타이밍·방향(side)은 검증된 원장에서 재생한다.
#          (진입신호 '생성' 소스(R/P/E 전략모듈)는 미보유 → 사장님 원칙대로 추정 금지.)
#        - '사이징'은 봇이 직접 판단: OPVnN 역추세 축소 + 업트렌드숏 컷 (검증된 Ch3 Stg2 로직 이식).
#        엔진엔 size_pct·leverage만 넘기고, 엔진이 집행/청산/비용을 처리한다.
# [검증근거] 사이징식 = test_07Prj_Ch3_Stg2_..._UptrendShortCut.py (load_join / rule_mult_arr)
#            m_base = NMULT if (|dev|>=OPV and side==-regime_dir) else 1.0   (OPVnN 역추세 축소)
#            m      = m_base*SH if (feat=='uptrend' and side==-1) else m_base (업트렌드 역행 숏 컷)
#            노출 EXP=1.559 (= 증거금 7.086% × 레버 22). size_pct = EXP/LEV*100*m
# [Lookahead] feat(regime)은 진입봉 마감 '이하' asof값만 사용(드라이버가 공급). 미래참조 없음.
# ── 사용 파일 ── rauto_contract.py (BotPlugin, Signal, Side, Action, MarketBar, Fill)
# ── 함수 In/Out ──
#  on_init(ctx)   In: 설정dict          → Out: 내부상태(base_margin_pct, 카운터) 초기화
#  on_bar(market) In: MarketBar(aux: side,feat,dev,regime_dir) → Out: Signal(ENTER, size_pct=EXP/LEV*100*m)
#  on_fill(fill)  In: Fill 통지          → Out: 체결 카운트
# ── 상수 ── EXP 1.559 / LEV 22 / OPV 0.25 / NMULT 0.60 / SH 0.0(업트렌드숏컷)
# ─────────────────────────────────────────────────────────────────────────
from rauto_contract import BotPlugin, Signal, Side, Action, MarketBar, Fill
from typing import Optional, Dict, Any


class TrendStackReplay(BotPlugin):
    META = {"name": "TrendStack", "version": "ch3s2-replay-v1",
            "timeframe": "8h", "needs": ["regime", "dev", "regime_dir"]}

    EXP = 1.559        # 명목노출 (검증 상수)
    LEV = 22.0         # 레버리지
    OPV = 0.25         # OPVnN 발동 임계 |dev|
    NMULT = 0.60       # 역추세 축소 승수
    SH = 0.0           # 업트렌드 역행 숏 컷 승수 (SH_best)

    def on_init(self, ctx: Dict[str, Any]) -> None:
        self.base_margin_pct = self.EXP / self.LEV * 100.0   # ≈ 7.086% (검증 EXP의 정확표현)
        self.n_signals = 0
        self.n_fills = 0

    def on_bar(self, market: MarketBar) -> Optional[Signal]:
        a = market.aux
        side_i = int(a.get("side", 0))          # +1 LONG / -1 SHORT (원장 재생)
        if side_i == 0:
            return None
        feat = a.get("feat")                     # 실시간 장세(asof backward)
        dev = a.get("dev")
        rd = a.get("regime_dir")

        # 1) OPVnN 역추세 축소: |dev|>=OPV 이고 진입방향이 장세방향의 반대면 NMULT
        m_base = 1.0
        try:
            if dev is not None and rd in (1, -1) and abs(float(dev)) >= self.OPV and side_i == -int(rd):
                m_base = self.NMULT
        except (TypeError, ValueError):
            m_base = 1.0

        # 2) 업트렌드 역행 숏 컷: 실시간 장세 uptrend 인데 숏이면 m_base*SH
        m = m_base * self.SH if (feat == "uptrend" and side_i == -1) else m_base

        size_pct = self.base_margin_pct * m
        side = Side.LONG if side_i == 1 else Side.SHORT
        self.n_signals += 1
        return Signal(action=Action.ENTER, side=side,
                      size_pct=size_pct, leverage=self.LEV,
                      reason=f"m_base={m_base:g} m={m:g} feat={feat}",
                      confidence=None)

    def on_fill(self, fill: Fill) -> None:
        self.n_fills += 1
