# -*- coding: utf-8 -*-
# [bot_sidewaydca_impatient.py] SW "참을성 없는" 분기 변종 2종 (§8 엔진/기존봇 무수정, 서브클래스).
#   기존 SW 진입 = 피벗확정(new_pl/new_ph) + dev조건. 분기 = 피벗확정 대기 제거(정도 차이).
#   _close_8h는 기존과 1:1 동일하되 진입 '방향판정'만 self._entry_dir()로 분리 → 변종은 _entry_dir만 교체.
#   ★개념경고: SW는 평균회귀(눌림목 매수)라 피벗=바닥확인 안전장치. 제거 시 '떨어지는 칼' 위험(TS와 정반대).
import numpy as np
import pandas as pd
import bot_sidewaydca_signal as SB
from bot_sidewaydca_signal import SidewayDCASignalBot
ENG = SB.ENG
from rauto_contract import Signal, Action, Side
WARMUP_BARS = SB.WARMUP_BARS


class _ImpatientBaseSW(SidewayDCASignalBot):
    """_close_8h를 기존과 1:1 복제하되 진입 방향판정만 self._entry_dir()로 위임."""

    def _entry_dir(self, new_pl, new_ph, dev, j):
        raise NotImplementedError

    def _close_8h(self):
        ts0, o, h, l, c, v = self._cur
        self.ts8.append(ts0); self.o8.append(o); self.h8.append(h)
        self.l8.append(l); self.c8.append(c); self.v8.append(v)
        self.ar8.append(self._cur_ar); self.oz8.append(self._cur_oz)
        n = len(self.c8); j = n - 1
        out = None

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

        A = self.atr[j]; P = self._poc_window(j)
        strong = self.adx[j] >= self.par['adx_hi']
        dev = (c - P) / A if (not np.isnan(P) and not np.isnan(A) and A > 0) else np.nan

        if self.pos != 0:
            aa, dd = self.par['a'], self.par['d']
            if self.side == 1 and new_pl and not np.isnan(self.lastPH):
                self.pb += 1; ratio = min(aa + dd * (self.pb - 1), 0.95)
                cand = self.lastPH - ratio * (self.lastPH - self.lastPL)
                self.trailSL = cand if np.isnan(self.trailSL) else max(self.trailSL, cand)
            elif self.side == -1 and new_ph and not np.isnan(self.lastPL):
                self.pb += 1; ratio = min(aa + dd * (self.pb - 1), 0.95)
                cand = self.lastPL + ratio * (self.lastPH - self.lastPL)
                self.trailSL = cand if np.isnan(self.trailSL) else min(self.trailSL, cand)
            if (j - self.entry_fill_idx) >= ENG.TIME_STOP:
                self._record_exit(c, 'time', j, ts0)
                out = Signal(Action.EXIT, side=Side.FLAT, reason="time")
            elif (self.nfilled < self.par['nDCA'] and not np.isnan(dev) and not strong):
                addable = ((self.side == 1 and dev < 0 and abs(dev) <= self.par['dist_max'] and new_pl) or
                           (self.side == -1 and dev > 0 and abs(dev) <= self.par['dist_max'] and new_ph))
                if addable:
                    self.pending = {'kind': 'add'}
        elif not self._exited_in_cur:
            if not np.isnan(dev) and not np.isnan(A) and not strong and n >= WARMUP_BARS:
                ar = self.ar8[j] if self.ar8[j] is not None else np.nan
                oz = self.oz8[j] if self.oz8[j] is not None else np.nan
                d = self._entry_dir(new_pl, new_ph, dev, j)        # ★분기점(변종마다 교체)
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
        if self.pos != 0 or (self.pending and self.pending['kind'] == 'enter'):
            P_next = self._poc_window(j + 1)
            sd = self.side if self.pos != 0 else self.pending['side']
            if not np.isnan(P_next) and not np.isnan(A):
                self.deep_guard = P_next - self.sl_mult * A if sd == 1 else P_next + self.sl_mult * A
        return out


class SidewayDCAImpatientBot(_ImpatientBaseSW):
    """성급(full): 피벗확정 완전 제거 — dev 조건만으로 진입(떨어지는 칼 위험 최대)."""
    META = dict(SidewayDCASignalBot.META, name="SidewayDCA_IMP", version="impatient-full")

    def _entry_dir(self, new_pl, new_ph, dev, j):
        dm = self.par['dist_max']
        if dev < 0 and abs(dev) <= dm:
            return 1
        if self.par['short_on'] and dev > 0 and abs(dev) <= dm:
            return -1
        return 0


class SidewayDCAMiddleBot(_ImpatientBaseSW):
    """중간(1봉 턴): dev조건 + 직전봉 대비 안 밀림(c[j]>=c[j-1] 롱 / <= 숏) = 약한 1봉 멈춤확인."""
    META = dict(SidewayDCASignalBot.META, name="SidewayDCA_MID", version="impatient-1bar")

    def _entry_dir(self, new_pl, new_ph, dev, j):
        dm = self.par['dist_max']
        turn_up = (j >= 1 and self.c8[j] >= self.c8[j - 1])
        turn_dn = (j >= 1 and self.c8[j] <= self.c8[j - 1])
        if turn_up and dev < 0 and abs(dev) <= dm:
            return 1
        if self.par['short_on'] and turn_dn and dev > 0 and abs(dev) <= dm:
            return -1
        return 0
