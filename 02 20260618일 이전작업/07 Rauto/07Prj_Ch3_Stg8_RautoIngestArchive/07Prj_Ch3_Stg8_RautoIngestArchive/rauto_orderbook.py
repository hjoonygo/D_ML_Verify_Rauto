# [파일명] rauto_orderbook.py
# 코드길이: 약 120줄 / 내부버전: rauto_orderbook_v1 / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] Binance USDⓈ-M 선물 Diff Depth 스트림으로 로컬 호가창을 정확히 유지한다.
#        REST 스냅샷 + 증분(@depth) 메시지를 시퀀스(U/u/pu)로 검증하고, 누락(갭) 감지 시
#        재동기화가 필요함을 알린다(엔진/수집 서비스가 스냅샷 재요청).
# [규칙(Binance 선물)]
#  - 첫 적용 이벤트: U <= lastUpdateId <= u
#  - 이후 이벤트: pu(직전 final id) == 직전 이벤트의 u  (불일치 → 갭 → 재동기화)
#  - qty=0 인 호가는 제거
# [Lookahead] 해당 없음(실시간 호가 유지).
# ── 사용 파일 ── 없음(표준 라이브러리만)
# ── 함수 In/Out ──
#  OrderBook()                  In: -        → Out: 호가창
#   .set_snapshot(snap)  In: {lastUpdateId,bids[[p,q]],asks[[p,q]]} → Out: 스냅샷 적용·버퍼 재생
#   .apply_diff(ev)      In: {U,u,pu,b,a}    → Out: 'buffered'|'stale'|'applied'|'applied_first'|'gap'
#   .best_bid()/best_ask()/mid()  In: -      → Out: 가격|None
#   .status()            In: -               → Out: {synced,last_update_id,prev_u,levels,gaps,need_resync}
# ── 상수 ── 없음
# ─────────────────────────────────────────────────────────────────────────
from typing import Optional, Dict, Any, List


def _f(x):
    return float(x)


class OrderBook:
    def __init__(self):
        self.bids: Dict[float, float] = {}
        self.asks: Dict[float, float] = {}
        self.last_update_id: Optional[int] = None
        self.synced: bool = False
        self.prev_u: Optional[int] = None
        self.buffer: List[dict] = []
        self.gaps: int = 0
        self.need_resync: bool = False

    def _apply_levels(self, ev: dict):
        for p, q in ev.get('b', []):
            price, qty = _f(p), _f(q)
            if qty == 0.0:
                self.bids.pop(price, None)
            else:
                self.bids[price] = qty
        for p, q in ev.get('a', []):
            price, qty = _f(p), _f(q)
            if qty == 0.0:
                self.asks.pop(price, None)
            else:
                self.asks[price] = qty

    def set_snapshot(self, snap: dict):
        self.bids = {_f(p): _f(q) for p, q in snap.get('bids', []) if _f(q) != 0.0}
        self.asks = {_f(p): _f(q) for p, q in snap.get('asks', []) if _f(q) != 0.0}
        self.last_update_id = int(snap['lastUpdateId'])
        self.synced = False
        self.prev_u = None
        self.need_resync = False
        # 버퍼에 쌓인 증분을 순서대로 재생
        buffered, self.buffer = self.buffer, []
        for ev in buffered:
            self.apply_diff(ev)

    def apply_diff(self, ev: dict) -> str:
        if self.last_update_id is None:
            self.buffer.append(ev)          # 스냅샷 전 도착분은 버퍼
            return 'buffered'
        U, u = int(ev['U']), int(ev['u'])
        pu = ev.get('pu')
        pu = int(pu) if pu is not None else None

        if not self.synced:
            if u < self.last_update_id:
                return 'stale'              # 스냅샷보다 과거 → 버림
            if U <= self.last_update_id <= u:
                self._apply_levels(ev)
                self.synced = True
                self.prev_u = u
                return 'applied_first'
            return 'stale'

        # 동기화 상태: 연속성 검증
        if pu is not None and pu != self.prev_u:
            self.synced = False
            self.last_update_id = None
            self.prev_u = None
            self.gaps += 1
            self.need_resync = True         # 스냅샷 재요청 필요
            return 'gap'

        self._apply_levels(ev)
        self.prev_u = u
        return 'applied'

    def best_bid(self) -> Optional[float]:
        return max(self.bids) if self.bids else None

    def best_ask(self) -> Optional[float]:
        return min(self.asks) if self.asks else None

    def mid(self) -> Optional[float]:
        b, a = self.best_bid(), self.best_ask()
        return (b + a) / 2.0 if (b is not None and a is not None) else None

    def status(self) -> Dict[str, Any]:
        return {"synced": self.synced, "last_update_id": self.last_update_id,
                "prev_u": self.prev_u, "bids": len(self.bids), "asks": len(self.asks),
                "gaps": self.gaps, "need_resync": self.need_resync, "mid": self.mid()}
