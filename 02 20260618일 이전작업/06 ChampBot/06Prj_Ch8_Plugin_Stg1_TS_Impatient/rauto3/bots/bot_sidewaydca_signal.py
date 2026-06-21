# -*- coding: utf-8 -*-
# [파일명] bot_sidewaydca_signal.py
# 코드길이: 약 360줄 | 내부버전: bot_sidewaydca_signal_v1 (Ch4 Stg7 스트리밍 1:1 추출)
# ─────────────────────────────────────────────────────────────────────────────
# [목적] SidewayDCA 신호봇 — 박제 엔진(SidewayDCA_Stg7_engine, dfdfac43)의 run_bot_honest
#        루프바디를 라이브 스트리밍(1분 on_bar)으로 1:1 추출. TrendStack Stg9/10 패턴 계승.
#   - 8h 버킷 누적(에포크 480분 = UTC 00/08/16, 엔진 resample과 동일 경계)
#   - 진입/시간손절/DCA '결정' = 8h봉 마감 시(엔진과 동일), 체결 = 다음 1분봉 시가(=엔진 open_[j+1])
#   - 1분 경로청산 = 보유 중 매 1분 on_bar에서 tp_poc/trailSL/sl_deep 터치 검사,
#     동일 1분봉 동시터치는 손절 우선(엔진 568줄 보수 규칙 그대로)
#   - 필터/사이징 = 원장(07Prj_Ch2 Stg1) PROD 설정: precise(atr<0.9) + OI z>=1.0(★엔진 CFG 0.0 아님)
#     사이징 = 확정알파 증거금 26.67% × 레버15 (노출 4.0), 숏 0.5배
#   - feat 공급 = market.aux 주입(atr_ratio·oi_zscore_24h) — 캡틴 확정 ①
#   - 스톱아웃 -10%·비용·펀딩·P&L = 신호봇 범위 밖(실행엔진/래퍼 담당 — 캡틴 확정 ②)
#
# [★정직 공지 — 인과성 1봉 지연 2건 (배치엔진은 봉 j 경로검사에 봉 j 완성값을 쓴다)]
#   ① sl_deep의 ATR: 배치 atr[j](봉 j 자기범위 포함, 가중 1/14) → 라이브는 atr[j-1] (미래 모름)
#   ② trailSL 스텝업: 피벗 '확정'창이 봉 j를 포함 → 라이브는 봉 j 마감 후 반영
#   POC(60봉 과거창)·tp_poc·진입판정은 완전 인과 → 지연 없음. 영향은 test의 원장 1:1 대조가
#   숫자로 측정한다(§2 결과재현). 불일치 건은 전수 보고.
#
# [워밍업] 8h봉 60개(=20일, POC_LOOKBACK 지배). 그 전엔 HOLD(reason=warmup).
#
# [함수 In->Out]
#   SidewayDCASignalBot(BotPlugin)
#    .on_init(ctx)                  상태·설정 초기화
#    .on_bar(market: MarketBar(1m)) -> Signal|None   ①펜딩체결 ②1분 경로청산 가드 ③8h누적/마감
#    ._close_8h()                   8h봉 마감 처리: 지표 갱신→피벗/트레일→시간손절→DCA→진입결정→가드레벨
#    ._poc_window(hi_idx)           bars[hi_idx-60, hi_idx) POC (엔진 compute_poc 루프바디 1:1)
#    ._pivot_confirm(j)             엔진 sliding_window 피벗확정(LEFT4/RIGHT1/유일최대) 1:1
#    ._guard_check(market)          보유 중 1분 터치검사 -> ('EXIT', px, reason)|None
#    .flush_partial()               리플레이 전용: 말미 부분버킷을 엔진처럼 1봉으로 마감 처리
#    .trades                        리플레이 수집 거래(원장 대조용 — P&L 없음)
# ==============================================================================
import os, sys, math
import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_BOTS = os.path.join(_HERE, "bots")
for _p in (_HERE, _BOTS):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import SidewayDCA_Stg7_engine as ENG            # 박제(무수정 import)
from rauto_contract import BotPlugin, Signal, Action, Side, MarketBar

BUCKET_MIN     = 480                            # 8h (에포크 정렬 = 엔진 resample 00/08/16 UTC)
BASE_LEV       = 15.0                           # 확정알파 레버
BASE_SIZE_PCT  = 26.67                          # 증거금% (= EXP4.0/레버15)
PROD_FILTER_MODE  = 'precise'
PROD_ATR_LO       = 0.9
PROD_ATR_HI       = 1.3
PROD_FILTER_SCENS = ('regime_shift',)
PROD_OI_FILTER    = True
PROD_OI_Z_HI      = 1.0                         # ★원장 PROD(Ch2 Stg1 64줄). 엔진 CFG 0.0 아님
PROD_OI_SCENS     = ('regime_shift',)
WARMUP_BARS    = ENG.POC_LOOKBACK               # 60 (8h봉)


class SidewayDCASignalBot(BotPlugin):
    META = {"name": "SidewayDCA", "version": "ch4s7-stream", "timeframe": "8h",
            "needs": ["volume", "aux:atr_ratio", "aux:oi_zscore_24h"],
            "engine": "SidewayDCA_Stg7_engine(dfdfac43, 1:1)",
            "sizing": "margin26.67%xLev15(EXP4.0), short x0.5"}

    # ── 라이프사이클 ──
    def on_init(self, ctx=None):
        c = (ctx or {}).get("config", {})
        self.size_pct  = c.get("base_size_pct", BASE_SIZE_PCT)
        self.lev       = c.get("leverage", BASE_LEV)
        self.sl_mult   = c.get("sl_mult", ENG.DEFAULT_SLMULT)        # 1.8
        self.par       = dict(ENG.BEST_PAR); self.par.update(c.get("par", {}))
        self.fmode     = c.get("filter_mode", PROD_FILTER_MODE)
        self.atr_lo    = c.get("atr_lo", PROD_ATR_LO)
        self.atr_hi    = c.get("atr_hi", PROD_ATR_HI)
        self.fscens    = set(c.get("filter_scens", PROD_FILTER_SCENS))
        self.oi_on     = c.get("oi_filter", PROD_OI_FILTER)
        self.oi_z_hi   = c.get("oi_z_hi", PROD_OI_Z_HI)
        self.oi_scens  = set(c.get("oi_filter_scens", PROD_OI_SCENS))
        # 8h 히스토리(마감봉)
        self.ts8 = []; self.o8 = []; self.h8 = []; self.l8 = []; self.c8 = []; self.v8 = []
        self.ar8 = []; self.oz8 = []               # aux: 버킷 내 마지막 비NaN (엔진 resample 'last')
        self.atr = np.zeros(0); self.adx = np.zeros(0); self.atrcmp = np.zeros(0, bool)
        self.ph_conf = {}; self.pl_conf = {}
        self.lastPH = np.nan; self.lastPL = np.nan
        # 진행 중 버킷
        self._bk = None; self._cur = None          # [ts0,o,h,l,c,v]
        self._cur_ar = np.nan; self._cur_oz = np.nan
        # 포지션 상태(엔진 상태변수 1:1)
        self._reset_pos()
        self.pending = None                        # 8h마감 결정 → 다음 1분 시가 체결
        self.trades = []                           # 리플레이 수집(원장 대조)
        self.blocked_n = 0
        self._exited_in_cur = False                # 엔진 612줄 continue 1:1 — 청산봉엔 진입판정 금지

    def _reset_pos(self):
        self.pos = 0.0; self.side = 0; self.avg = np.nan
        self.entry_fill_idx = -1; self.entry_ts = None
        self.nfilled = 0; self.pb = 0
        self.trailSL = np.nan; self.poc_t = np.nan; self.scen0 = None
        self.deep_guard = np.nan; self.A_at_entry = np.nan

    # ── POC: 엔진 compute_poc 루프바디 1:1 (bars[hi-60, hi) 단일창) ──
    def _poc_window(self, hi_idx):
        lb = ENG.POC_LOOKBACK; bins = ENG.POC_BINS
        s = hi_idx - lb
        if s < 0:
            return np.nan
        h = np.asarray(self.h8[s:hi_idx]); l = np.asarray(self.l8[s:hi_idx])
        v = np.asarray(self.v8[s:hi_idx]); mid = (h + l) / 2.0
        lo = l.min(); hi = h.max()
        if hi <= lo:
            return float(self.c8[hi_idx - 1])
        edges = np.linspace(lo, hi, bins + 1)
        idxb = np.clip(np.digitize(mid, edges) - 1, 0, bins - 1)
        hist = np.zeros(bins); np.add.at(hist, idxb, v)
        k = int(hist.argmax())
        return float((edges[k] + edges[k + 1]) / 2.0)

    # ── 피벗확정: 엔진 precompute(327~338) 유일최대/최소 조건 1:1. 확정 index=j(center=j-1) ──
    def _pivot_confirm(self, j):
        L, R = ENG.LEFT, ENG.RIGHT
        c = j - R
        if c - L < 0:
            return False, False
        hw = np.asarray(self.h8[c - L:c + R + 1]); lw = np.asarray(self.l8[c - L:c + R + 1])
        hc = self.h8[c]; lc = self.l8[c]
        is_ph = (hc == hw.max()) and int((hw == hw.max()).sum()) == 1
        is_pl = (lc == lw.min()) and int((lw == lw.min()).sum()) == 1
        if is_ph:
            self.ph_conf[j] = float(hc)
        if is_pl:
            self.pl_conf[j] = float(lc)
        return is_ph, is_pl

    def _blocked(self, scen_now, ar, oz):
        # 엔진 blocked() 1:1 — NaN이면 그 필터 통과(안전)
        if self.fmode != 'off' and scen_now in self.fscens and not np.isnan(ar):
            if self.fmode == 'precise' and ar < self.atr_lo:
                return True
            if self.fmode == 'both_ends' and ((ar < self.atr_lo) or (ar >= self.atr_hi)):
                return True
        if self.oi_on and scen_now in self.oi_scens and not np.isnan(oz):
            if oz >= self.oi_z_hi:
                return True
        return False

    # ── 1분 경로청산 가드 (엔진 551~570 1:1, 동시터치 손절우선) ──
    def _guard_check(self, market):
        stops = []
        if not np.isnan(self.trailSL):
            stops.append((self.trailSL, 'sl_trail'))
        if not np.isnan(self.deep_guard):
            stops.append((self.deep_guard, 'sl_deep'))
        tp = self.poc_t
        if self.side == 1:
            eff = max((v for v, _ in stops), default=np.nan)
            reason = sorted(stops, reverse=True)[0][1] if stops else None
            stop_hit = (not np.isnan(eff)) and (market.l <= eff)
            tp_hit = (not np.isnan(tp)) and (market.h >= tp)
        else:
            eff = min((v for v, _ in stops), default=np.nan)
            reason = sorted(stops)[0][1] if stops else None
            stop_hit = (not np.isnan(eff)) and (market.h >= eff)
            tp_hit = (not np.isnan(tp)) and (market.l <= tp)
        if stop_hit:                                  # 동시터치 → 손절 우선(보수)
            return eff, reason
        if tp_hit:
            return tp, 'tp_poc'
        return None

    def _record_exit(self, exit_px, reason, exit_idx, exit_ts):
        self.trades.append({'entry_t': self.entry_ts, 'exit_t': exit_ts,
                            'side': self.side, 'entry': self.avg, 'exit': float(exit_px),
                            'reason': reason, 'bars': exit_idx - self.entry_fill_idx,
                            'scen': self.scen0, 'nfilled': self.nfilled})
        self._reset_pos()

    # ── 8h봉 마감 처리 (엔진 루프바디의 '봉마감 결정' 부분 1:1) ──
    def _close_8h(self):
        ts0, o, h, l, c, v = self._cur
        self.ts8.append(ts0); self.o8.append(o); self.h8.append(h)
        self.l8.append(l); self.c8.append(c); self.v8.append(v)
        self.ar8.append(self._cur_ar); self.oz8.append(self._cur_oz)
        n = len(self.c8); j = n - 1
        out = None

        # 지표(엔진 함수 무수정 호출 — 전체 재계산, n<=수천이라 가벼움)
        H = np.asarray(self.h8); Lo = np.asarray(self.l8); C = np.asarray(self.c8)
        self.atr = ENG.compute_atr(H, Lo, C, ENG.ATR_PERIOD)
        self.adx = ENG.compute_adx(H, Lo, C, ENG.ADX_N)
        atr_sma = pd.Series(self.atr).rolling(ENG.ATR_SMA_N, min_periods=1).mean().values
        self.atrcmp = self.atr < atr_sma * ENG.ATR_COMP_K

        new_ph, new_pl = self._pivot_confirm(j)
        if new_ph:
            self.lastPH = self.ph_conf[j]
        if new_pl:
            self.lastPL = self.pl_conf[j]

        A = self.atr[j]; P = self._poc_window(j)     # P=poc[j] (bars[j-60,j) — 완전 인과)
        strong = self.adx[j] >= self.par['adx_hi']
        dev = (c - P) / A if (not np.isnan(P) and not np.isnan(A) and A > 0) else np.nan

        if self.pos != 0:
            # (1) 피보 스텝업 트레일 (엔진 518~526) — 라이브는 봉마감 후 반영(정직공지 ②)
            aa, dd = self.par['a'], self.par['d']
            if self.side == 1 and new_pl and not np.isnan(self.lastPH):
                self.pb += 1; ratio = min(aa + dd * (self.pb - 1), 0.95)
                cand = self.lastPH - ratio * (self.lastPH - self.lastPL)
                self.trailSL = cand if np.isnan(self.trailSL) else max(self.trailSL, cand)
            elif self.side == -1 and new_ph and not np.isnan(self.lastPL):
                self.pb += 1; ratio = min(aa + dd * (self.pb - 1), 0.95)
                cand = self.lastPL + ratio * (self.lastPH - self.lastPL)
                self.trailSL = cand if np.isnan(self.trailSL) else min(self.trailSL, cand)
            # (4) 시간손절 (엔진 573 — 1분 경로 출구 없을 때만 여기 도달)
            if (j - self.entry_fill_idx) >= ENG.TIME_STOP:
                self._record_exit(c, 'time', j, ts0)
                out = Signal(Action.EXIT, side=Side.FLAT, reason="time")
            # DCA 추가(엔진 575~582) — BEST_PAR nDCA=1이라 실전 미발동(1:1 보존)
            elif (self.nfilled < self.par['nDCA'] and not np.isnan(dev) and not strong):
                addable = ((self.side == 1 and dev < 0 and abs(dev) <= self.par['dist_max'] and new_pl) or
                           (self.side == -1 and dev > 0 and abs(dev) <= self.par['dist_max'] and new_ph))
                if addable:
                    self.pending = {'kind': 'add'}
        elif not self._exited_in_cur:
            # 진입 결정(엔진 614~633): 닫힌봉 j 판정 → 다음봉 시가 체결
            #   (이 봉에서 1분 경로청산이 있었으면 엔진 612줄 continue와 동일하게 스킵)
            if not np.isnan(dev) and not np.isnan(A) and not strong and n >= WARMUP_BARS:
                ar = self.ar8[j] if self.ar8[j] is not None else np.nan
                oz = self.oz8[j] if self.oz8[j] is not None else np.nan
                d = 0
                if new_pl and dev < 0 and abs(dev) <= self.par['dist_max']:
                    d = 1
                elif self.par['short_on'] and new_ph and dev > 0 and abs(dev) <= self.par['dist_max']:
                    d = -1
                if d != 0:
                    scen_now = ENG.scen_label(self.adx[j], dev, bool(self.atrcmp[j]), self.par['adx_hi'])
                    if self._blocked(scen_now, ar, oz):
                        self.blocked_n += 1
                    else:
                        self.pending = {'kind': 'enter', 'side': d, 'A': float(A),
                                        'P': float(P), 'scen': scen_now}
                        sz = self.size_pct * (ENG.SHORT_SIZE if d == -1 else 1.0)
                        out = Signal(Action.ENTER, side=Side(d), size_pct=round(sz, 4),
                                     leverage=self.lev, reason=f"entry|scen={scen_now}|dev={dev:.3f}",
                                     confidence=0.6)

        self._exited_in_cur = False
        # 다음(진행) 버킷용 가드 레벨: P_guard=poc[j+1](bars[j-59,j] — 인과), A_guard=atr[j](1봉 지연)
        if self.pos != 0 or (self.pending and self.pending['kind'] == 'enter'):
            P_next = self._poc_window(j + 1)
            sd = self.side if self.pos != 0 else self.pending['side']
            if not np.isnan(P_next) and not np.isnan(A):
                self.deep_guard = P_next - self.sl_mult * A if sd == 1 else P_next + self.sl_mult * A
        return out

    # ── 라이브: 1m 스트림 ──
    def on_bar(self, market: MarketBar):
        bk = int(pd.Timestamp(market.ts).value // 60_000_000_000) // BUCKET_MIN
        out = None
        # 버킷 경계: 직전 버킷 마감 처리(이 1분봉이 새 8h봉의 첫 봉)
        if self._bk is not None and bk != self._bk:
            out = self._close_8h()
            self._cur = None
        if self._cur is None:
            self._bk = bk
            bkt_ts = pd.Timestamp(bk * BUCKET_MIN * 60 * 1_000_000_000)   # 버킷 경계(=엔진 label left)
            self._cur = [bkt_ts, market.o, market.h, market.l, market.c, market.v or 0.0]
            self._cur_ar = np.nan; self._cur_oz = np.nan
            # 펜딩 체결: 다음봉 시가(=이 1분봉 시가 = 엔진 open_[j+1])
            if self.pending is not None:
                pd_ = self.pending; self.pending = None
                if pd_['kind'] == 'enter':
                    px = market.o
                    w = 1.0 * (ENG.SHORT_SIZE if pd_['side'] == -1 else 1.0)   # nDCA=1 weights[0]=1.0
                    self.pos = w; self.side = pd_['side']; self.avg = px; self.nfilled = 1
                    self.entry_fill_idx = len(self.c8); self.entry_ts = bkt_ts
                    self.pb = 0
                    self.trailSL = px - pd_['side'] * self.par['dist_max'] * pd_['A'] \
                        if pd_['side'] == 1 else px + self.par['dist_max'] * pd_['A']
                    self.poc_t = pd_['P']; self.scen0 = pd_['scen']
                elif pd_['kind'] == 'add' and self.pos != 0:
                    px = market.o
                    w = 0.0   # nDCA=1: weights 소진 — 도달 불가(1:1 보존용)
                    if w > 0:
                        newp = self.pos + w
                        self.avg = (self.avg * self.pos + px * w) / newp
                        self.pos = newp; self.nfilled += 1
        else:
            self._cur[2] = max(self._cur[2], market.h)
            self._cur[3] = min(self._cur[3], market.l)
            self._cur[4] = market.c
            self._cur[5] += (market.v or 0.0)
        # aux: 버킷 내 마지막 비NaN (엔진 resample 'last')
        ax = market.aux or {}
        ar = ax.get('atr_ratio'); oz = ax.get('oi_zscore_24h')
        if ar is not None and not (isinstance(ar, float) and math.isnan(ar)):
            self._cur_ar = float(ar)
        if oz is not None and not (isinstance(oz, float) and math.isnan(oz)):
            self._cur_oz = float(oz)

        # 1분 경로청산 가드(보유 중, 매 1분)
        if self.pos != 0:
            hit = self._guard_check(market)
            if hit is not None:
                px, reason = hit
                self._record_exit(px, reason, len(self.c8), self._cur[0])
                self._exited_in_cur = True
                return Signal(Action.EXIT, side=Side.FLAT, reason=reason)
        if out is not None:
            return out
        if len(self.c8) < WARMUP_BARS:
            return Signal(Action.HOLD, reason="warmup")
        return None

    # ── 리플레이 전용: 말미 부분버킷을 엔진처럼 마지막 1봉으로 마감 처리 ──
    def flush_partial(self):
        if self._cur is not None:
            self._close_8h()
            self._cur = None
            self.pending = None    # 다음봉 없음 → 체결 불가(엔진 j+1<n 조건과 동일 결과)
