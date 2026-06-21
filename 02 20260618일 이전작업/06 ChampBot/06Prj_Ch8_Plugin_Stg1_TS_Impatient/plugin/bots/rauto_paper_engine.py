# [파일명] rauto_paper_engine.py
# 코드길이: 약 110줄 / 내부버전: rauto_paper_v1 / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] 슬롯별 가상(페이퍼) 계좌. 슬리피지·강제청산(하드스탑)·왕복비용·MMR티어를 반영해
#        봇 신호를 집행하고 잔액/MDD/Calmar를 추적한다. (Rauto 가상거래환경의 1봇 단위)
# [검증근거] 비용·청산 모델은 검증된 Ch3 Stg2 compound()식을 1:1 이식
#            (test_07Prj_Ch3_Stg2_TrendStack_UptrendShortCut.py L118-131).
#            리플레이 모드 1거래 손익 p:
#              mmr = MMR_T2 if exposure*bal > TIER else MMR_T1
#              hsd = 1/leverage - mmr - SLIP                 (하드스탑=청산버퍼 거리)
#              p   = -exposure*(hsd+COST+|fund|)  if mae<=-hsd (강제청산)
#                  =  R*exposure                  otherwise   (정상청산)
# [Lookahead] 없음. 거래는 진입시각 순서대로 순차복리(검증식과 동일). 미래 데이터 미사용.
# ── 사용 파일 ── rauto_contract.py (Signal, Side, Action, Fill)
# ── 함수 In/Out ──
#  PaperAccount(start)                      In: 초기자본          Out: 계좌객체
#   .open(sig, ts, price)   In: Signal·시각·가격 → Out: 포지션개설(exposure 기록)·Fill 반환
#   .resolve_replay(R,mae,fund) In: 실현R·MAE·펀딩 → Out: 손익p 적용·잔액/MDD갱신·거래기록·p반환
#   .metrics()              In: -            → Out: (수익%, MDD%, Calmar)
# ── 상수 ── MMR_T1 .004 / MMR_T2 .005 / TIER 50000 / COST .0014 / SLIP .0005 / START 10000
# ─────────────────────────────────────────────────────────────────────────
from rauto_contract import Signal, Side, Action, Fill

MMR_T1 = 0.004
MMR_T2 = 0.005
TIER = 50000.0
COST = 0.0014      # 왕복 수수료+체결비용
SLIP = 0.0005      # 슬리피지 버퍼
START = 10000.0


class PaperAccount:
    def __init__(self, start_balance: float = START):
        self.start = start_balance
        self.bal = start_balance
        self.peak = start_balance
        self.mdd = 0.0
        self.equity = [start_balance]
        self.trades = []          # 체결/청산 기록
        self.pos = None           # 현재 포지션
        self.n_liq = 0            # 강제청산 횟수

    def open(self, sig: Signal, ts=None, price: float = 0.0) -> Fill:
        exposure = sig.size_pct / 100.0 * sig.leverage
        self.pos = {
            "side": sig.side, "exposure": exposure, "leverage": sig.leverage,
            "size_pct": sig.size_pct, "ts": ts, "entry_price": price, "reason": sig.reason,
        }
        return Fill(ts=ts, action=Action.ENTER, side=sig.side, price=price,
                    size_pct=sig.size_pct, leverage=sig.leverage, exposure=exposure, fee=0.0)

    def resolve_replay(self, R: float, mae: float, fund: float):
        """검증된 Ch3 Stg2 1거래 손익식(슬리피지·강제청산·비용·MMR티어 포함)으로 포지션 청산."""
        if self.pos is None:
            return None
        exp = self.pos["exposure"]
        lev = self.pos["leverage"]
        if exp == 0.0:
            p = 0.0
            liq = False                       # 사이징 0(예: 업트렌드숏컷) → 무거래
        else:
            mmr = MMR_T2 if exp * self.bal > TIER else MMR_T1
            hsd = 1.0 / lev - mmr - SLIP       # 하드스탑(청산버퍼) 거리
            if mae <= -hsd:                    # 강제청산: 손익 = -노출×(하드스탑+비용+|펀딩|)
                p = -exp * (hsd + COST + abs(fund))
                liq = True
                self.n_liq += 1
            else:                              # 정상청산: 손익 = 실현R × 노출
                p = R * exp
                liq = False
        self.bal *= (1.0 + p)
        if self.bal > self.peak:
            self.peak = self.bal
        dd = self.bal / self.peak - 1.0
        if dd < self.mdd:
            self.mdd = dd
        self.equity.append(self.bal)
        self.trades.append({
            "side": self.pos["side"].name, "exposure": exp, "R": R, "mae": mae,
            "fund": fund, "p": p, "liq": liq, "bal": self.bal,
        })
        self.pos = None
        return p

    def metrics(self):
        ret = (self.bal / self.start - 1.0) * 100.0
        mdd = self.mdd * 100.0
        cal = (ret / abs(mdd)) if self.mdd < 0 else float("nan")
        return ret, mdd, cal
