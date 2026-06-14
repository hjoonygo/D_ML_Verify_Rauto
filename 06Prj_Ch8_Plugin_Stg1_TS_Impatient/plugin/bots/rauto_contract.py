# [파일명] rauto_contract.py
# 코드길이: 약 95줄 / 내부버전: rauto_contract_v1 / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] 봇 ↔ Rauto 엔진 '신호계약(동결본)'. 슬롯당 1개 자기완결 봇이 이 인터페이스를 구현한다.
#        봇은 진입/청산/사이징을 스스로 판단해 Signal을 반환하고, 엔진은 집행만 한다.
# [Lookahead] 계약 자체엔 미래참조 없음. market.aux의 regime/feat는 진입봉 마감 '이하' asof값만 담는다.
# ── 사용 파일 ── 없음 (표준 라이브러리 dataclasses/enum/typing/abc만)
# ── 정의 In/Out ──
#  Action(Enum)         ENTER / EXIT / FLIP / HOLD
#  Side(Enum)           LONG=+1 / SHORT=-1 / FLAT=0
#  Signal(dataclass)    봇→엔진. In: 봇판단  Out: action,side,size_pct,leverage,sl,tp,reason,confidence
#  MarketBar(dataclass) 엔진→봇. In: 시장1봉  Out: ts,tf,o,h,l,c,v,oi,lsr,regime,aux(리플레이컨텍스트)
#  Fill(dataclass)      엔진→봇 통지. In: 체결  Out: ts,action,side,price,size_pct,leverage,exposure,fee
#  BotPlugin(ABC)       META / on_init(ctx) / on_bar(market)->Signal|None / on_fill(fill)
# ── 상수 ── 없음
# ─────────────────────────────────────────────────────────────────────────
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any, Dict
from abc import ABC, abstractmethod


class Action(Enum):
    ENTER = "ENTER"
    EXIT = "EXIT"
    FLIP = "FLIP"
    HOLD = "HOLD"


class Side(Enum):
    LONG = 1
    SHORT = -1
    FLAT = 0


@dataclass
class Signal:
    action: Action
    side: Side = Side.FLAT
    size_pct: float = 0.0      # 봇 자본 대비 '증거금' % (예: 7.086)
    leverage: float = 1.0      # 봇이 정한 레버리지 (예: 22)
    sl: Optional[float] = None
    tp: Optional[float] = None
    reason: str = ""
    confidence: Optional[float] = None


@dataclass
class MarketBar:
    ts: Any                    # 진입봉 마감 시각(타임스탬프)
    tf: str = "1m"
    o: float = 0.0
    h: float = 0.0
    l: float = 0.0
    c: float = 0.0
    v: float = 0.0
    oi: Optional[float] = None
    lsr: Optional[float] = None
    regime: Optional[str] = None
    aux: Dict[str, Any] = field(default_factory=dict)   # 리플레이 컨텍스트(side,feat,dev,regime_dir)


@dataclass
class Fill:
    ts: Any
    action: Action
    side: Side
    price: float
    size_pct: float
    leverage: float
    exposure: float            # = size_pct/100 * leverage (자본대비 명목노출)
    fee: float = 0.0


class BotPlugin(ABC):
    """슬롯당 1개 로드되는 자기완결 봇의 표준 인터페이스."""
    META: Dict[str, Any] = {"name": "base", "version": "0", "timeframe": "1m", "needs": []}

    @abstractmethod
    def on_init(self, ctx: Dict[str, Any]) -> None:
        ...

    @abstractmethod
    def on_bar(self, market: MarketBar) -> Optional[Signal]:
        ...

    def on_fill(self, fill: Fill) -> None:
        return None
