# -*- coding: utf-8 -*-
# [rauto_orchestrator.py] ★[0] 관제센터 v0 — Rauto 구조개혁 ④모듈 (세션 260625_01_RautoSysReform2).
#   책임 = 오케스트레이션: 봇(계약 make_trades) → RautoCEX(체결+비용)로 연결해 봇 하나를 처음~끝 구동.
#   ★봇 무관: 계약(make_trades(d1m,fund)→원장)을 구현한 어떤 봇이든(REVoi·TS·SW) 동일하게 받아 돌린다.
#   ★책임 경계(퀀트 표준): 봇=알파(신호+진입/청산) · Rauto=사이징·리스크·배분·챔피언(여긴 사이징만, 나머지 추후) · RautoCEX=체결·비용·마진.
#   ★검증엔진 무수정·호출만(§15.1). 배치경로는 검증된 WiredAnchorTest와 동일 순서 → 앵커 1원단위 재현(무손상).
#   ★Sim(백테) v0. Live 이벤트구동(step)은 시드만 — DataHub.bars(now) 룩어헤드 게이트 사용 예정(안전장치6).
from path_finder import ensure_paths
ensure_paths()
import pandas as pd
from rauto_datahub import DataHub
from rauto_cex import RautoCEX, SlipModel


class RautoOrchestrator:
    """[0] 관제센터: 봇(계약 make_trades) + 사이징 → RautoCEX 연결·구동. 봇 무관(어떤 봇이든 계약만 맞으면)."""

    def __init__(self, bot, size_pct, lev, slip=None, leg1_taker=False):
        self.bot = bot                                      # 봇 계약: make_trades(d1m, fund) → 거래원장
        self.size_pct = float(size_pct)                     # ★사이징 = Rauto 결정(봇 아님)
        self.lev = float(lev)
        self.cex = RautoCEX(self.size_pct, self.lev,
                            slip=slip or SlipModel(0.0, 0.0), leg1_taker=leg1_taker)
        self.hub = None

    def run_backtest(self, d1m, fund):
        """배치 드라이버 — 봇 원장 → CEX 비용·복리.
           반환 = dict(tot,mdd,nliq,monthly,cost,final, trades, bot).
           ★순서는 검증된 WiredAnchorTest(봇 원장 → CEX)와 동일 → 무손상. DataHub는 중앙 1m 단일출처로 보관(이벤트구동 시드)."""
        self.hub = DataHub(d1m)                             # 중앙 1m 단일출처 (배치는 d1m 직접, 이벤트구동 시 hub.bars(now))
        T = self.bot.make_trades(d1m, fund)                # ★봇 계약 호출(신호+진입/청산 = 봇 알파)
        T["_ym"] = pd.to_datetime(T["et"]).dt.to_period("M").astype(str)   # 월 키(CEX 월별집계용)
        r = self.cex.run(T)                                # 체결·비용·복리(execution_cost만)
        r["trades"] = T
        r["bot"] = getattr(self.bot, "NAME", "?")
        return r

    def step(self, now):
        """[미구현·Live 시드] 이벤트구동 1봉 진행 — DataHub.bars(now) 룩어헤드 게이트로 '마감된 봉'만 받아 처리.
           안전장치6(벡터 백테와 이벤트 라이브가 같은 Fill/Slip/Fee 코드 공유)을 Live 단계서 구현. 배치는 run_backtest 사용."""
        raise NotImplementedError("이벤트구동(step)은 Live 단계 과제 — 현재는 run_backtest(배치)만 지원")
