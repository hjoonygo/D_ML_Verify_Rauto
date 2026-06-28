# -*- coding: utf-8 -*-
# [rauto_cex.py] ★RautoCEX v0 — Rauto 구조개혁 ③모듈(체결+비용)의 독립모듈 첫 추출 (세션 260625_01_Rauto_Sys_Reform).
#   책임 = '실행 P&L'만: FeeModel(수수료) + SlipModel(슬립) + FillModel(체결판정) + MarginModel(격리마진·강제청산).
#   ★안전장치2(FillModel 철칙): '가격 도달 ≠ 체결 보장'. 스톱=시장가+슬립, 지정가=도달해도 미체결 가능.
#   ★안전장치4(비용 2레이어): 여기는 execution_cost만. 신호선정용 selection_cost(4bp)는 절대 안 들어온다.
#   ★안전장치1(무손상 추출): 기본값(슬립0·스프0)이면 기존 백테와 1원단위 동일(rauto_paper_engine·bt_full 미러).
#   Sim 모드(백테)용 v0. Live 모드는 같은 인터페이스로 실거래소 체결을 받는 구현체로 교체(미구현).
import numpy as np

# 실행비용 상수 (단일출처 — 앞으로 비용은 '여기'에서만 정의. 신호엔진 COST=0.0004는 여기 아님=selection_cost)
MK, TK, SPRD = 0.0002, 0.0004, 0.0001              # 메이커2bp / 테이커4bp / 호가스프레드1bp
MMR_T1, MMR_T2, TIER = 0.004, 0.005, 50000.0       # 유지증거금 티어1/티어2 / 티어경계$
LIQ_SLIP, LIQ_COST = 0.0005, 0.0014                # 강제청산식 내부상수(엔진 불변, rauto_paper_engine 동일)


class FeeModel:
    """수수료: 진입 메이커/테이커, 청산 메이커(부분익절)/테이커(스톱), 펀딩(실측 per-trade)."""
    def __init__(self, mk=MK, tk=TK, sprd=SPRD):
        self.mk, self.tk, self.sprd = mk, tk, sprd

    def entry_cost(self, leg1_taker):
        # 진입 3분할: 되돌림2레그=메이커. 1차레그(1/3)=즉시진입 → 메이커(기본) 또는 테이커(보수).
        return self.mk + (self.tk - self.mk) / 3.0 if leg1_taker else self.mk

    def exit_cost(self, reason):
        # 부분익절(P)=지정가 메이커 / fibstop·timestop·flip=시장가 테이커. (이 setting은 전부 fibstop)
        return self.mk if reason == "tp" else self.tk


class SlipModel:
    """슬립: ★FillModel 철칙 — 시장가(테이커) 체결에만 붙는다. 지정가(메이커)=0.
       gap_bp = 캡틴 측정(exec_realism 1m갭, 기본 0). exit_spread_bp = 1m이 못 보는 호가스프레드.
       extra_bp = 변동성/OI 조건부 추가(기본 0, 실측보정 전까지 0)."""
    def __init__(self, gap_bp=0.0, exit_spread_bp=0.0, extra_bp=0.0):
        self.gap = gap_bp / 1e4; self.spread = exit_spread_bp / 1e4; self.extra = extra_bp / 1e4

    def market_exit_slip(self):
        return self.gap + self.spread + self.extra   # 시장가 청산 1건당 추가 분율


class MarginModel:
    """격리마진·유지증거금·강제청산 (rauto_paper_engine.resolve_replay 1:1)."""
    def __init__(self, size_pct, lev):
        self.exp = size_pct / 100.0 * lev; self.lev = lev

    def step(self, bal, R_net, mae, fund):
        """1거래 손익분율 p 반환. mae<=-hsd면 강제청산."""
        mmr = MMR_T2 if self.exp * bal > TIER else MMR_T1
        hsd = 1.0 / self.lev - mmr - LIQ_SLIP
        if mae <= -hsd:
            return -self.exp * (hsd + LIQ_COST + abs(fund)), True   # 강제청산
        return R_net * self.exp, False


class RautoCEX:
    """체결+비용 독립모듈. 입력 = 거래원장(R·mae·fund·reason; R엔 기존 기본비용이 박혀있음).
       내부에서 gross로 복원 후 자기 FeeModel/SlipModel로 재차감 → '비용 단일출처'."""
    def __init__(self, size_pct, lev, fee=None, slip=None, leg1_taker=False, mode="sim"):
        self.size_pct, self.lev = size_pct, lev
        self.fee = fee or FeeModel(); self.slip = slip or SlipModel()
        self.margin = MarginModel(size_pct, lev); self.leg1_taker = leg1_taker; self.mode = mode

    def _gross_R(self, R, fund):
        # bt_full: R = grossR - (MK + TK) - fund → 복원. (이 setting은 진입 메이커+청산 테이커 가정)
        return R + MK + TK + fund

    def run(self, trades):
        """반환: dict(tot%, mdd%, nliq, monthly{ym:$}, cost{maker$,taker$,spread$,slip$,fund$})."""
        R = trades["R"].values.astype(float); MAE = trades["mae"].values.astype(float)
        FUND = trades["fund"].values.astype(float)
        REASON = trades["reason"].values if "reason" in trades else np.array(["fibstop"] * len(R))
        MKEY = trades["_ym"].values if "_ym" in trades else np.array([0] * len(R))
        bal = 10000.0; peak = 10000.0; mdd = 0.0; nliq = 0
        monthly = {}; cost = dict(maker=0.0, taker=0.0, spread=0.0, slip=0.0, fund=0.0)
        slip_mkt = self.slip.market_exit_slip()
        for i in range(len(R)):
            gR = self._gross_R(R[i], FUND[i])
            ec = self.fee.entry_cost(self.leg1_taker)              # 진입 수수료(분율)
            xc = self.fee.exit_cost(REASON[i])                     # 청산 수수료(분율)
            is_mkt_exit = REASON[i] != "tp"                        # 시장가 청산 여부
            sl = slip_mkt                                          # 슬립모델이 gap+스프레드+extra 통합 관리
            R_net = gR - ec - xc - FUND[i] - (sl if is_mkt_exit else 0.0)
            bal0 = bal
            p, liq = self.margin.step(bal, R_net, MAE[i], FUND[i])
            if liq: nliq += 1
            bal *= (1.0 + p)
            notion = self.margin.exp * bal0
            monthly[MKEY[i]] = monthly.get(MKEY[i], 0.0) + (bal - bal0)
            if not liq:
                cost["maker"] += notion * (ec if not self.leg1_taker else MK)
                cost["taker"] += notion * (xc if is_mkt_exit else 0.0)
                cost["slip"] += notion * (sl if is_mkt_exit else 0.0)
                cost["fund"] += notion * FUND[i]
            if bal > peak: peak = bal
            dd = bal / peak - 1.0
            if dd < mdd: mdd = dd
            if bal <= 0: break
        tot = (bal / 10000.0 - 1.0) * 100.0
        return dict(tot=tot, mdd=mdd * 100.0, nliq=nliq, monthly=monthly, cost=cost, final=bal)
