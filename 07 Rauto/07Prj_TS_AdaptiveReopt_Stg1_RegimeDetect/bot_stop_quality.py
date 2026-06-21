# -*- coding: utf-8 -*-
# [bot_stop_quality.py] C레버: OI-눌림품질 → 손절거리 조정 (king 무수정 상속).
#   가설: 좋은 눌림(OI하락=약손청산)엔 손절 여유(흔들기 회피), 나쁜 눌림(OI상승=신규역포지션)엔 타이트(빨리 컷).
#   ★사이징(PQ)과 달리 손절거리는 거래 결과(청산시점·R)를 바꾸므로 봇 재실행 필요.
#   무수정 원칙: super()._step가 진입/청산/피보/인트라바가드 전부 수행, 본 클래스는 진입 직후 self.sl만 재설정.
#   OFF(ENABLED=False)면 E.SL_PCT(1.0)로 king 동치.
import numpy as np
import trendstack_signal_engine as E
from bot_trendstack_impatient_king import TrendStackImpatientKingBot


class StopQualityKingBot(TrendStackImpatientKingBot):
    META = {"name": "TrendStack_KING_SQ", "version": "sq-v0",
            "fork": "king + OI-pullback-quality stop distance"}
    ENABLED = True
    SL_GOOD = 1.3      # 좋은 눌림(OI하락) 손절 % (여유)
    SL_BAD = 0.8       # 나쁜 눌림(OI상승) 손절 % (타이트)
    OI_LO = -0.5; OI_HI = 0.5
    LONG_ONLY = False  # True면 롱에만 품질손절 적용
    RISK_CONSTANT = False  # True면 size *= E.SL_PCT/sl_pct (손절넓힘=사이즈축소, 총위험 고정→꼬리위험 캡)

    def on_init(self, ctx=None):
        super().on_init(ctx)
        self._last_oi = np.nan
        self._last_sl_pct = E.SL_PCT

    def on_bar(self, market):
        if isinstance(market.aux, dict) and 'oi_change_1h_pct' in market.aux:
            v = market.aux['oi_change_1h_pct']
            self._last_oi = float(v) if v == v else np.nan
        return super().on_bar(market)

    def _sl_pct(self):
        if not self.ENABLED or np.isnan(self._last_oi):
            return E.SL_PCT
        oi = self._last_oi
        if oi <= self.OI_LO: return self.SL_GOOD
        if oi >= self.OI_HI: return self.SL_BAD
        t = (oi - self.OI_LO) / (self.OI_HI - self.OI_LO)
        return self.SL_GOOD + t * (self.SL_BAD - self.SL_GOOD)

    def _step(self, i, arr, sig, dz_oi, eh):
        ev = super()._step(i, arr, sig, dz_oi, eh)
        if ev is not None and ev[0] == 'ENTER':
            d = ev[1]
            self._last_sl_pct = E.SL_PCT
            if not (self.LONG_ONLY and d != 1):
                sp = self._sl_pct()
                self._last_sl_pct = sp
                self.sl = self.entry_price * (1 - d * sp / 100.0)
        return ev

    def _compute_size(self, side, entry_i, sig):
        size, lev, dbg = super()._compute_size(side, entry_i, sig)
        if self.RISK_CONSTANT and self._last_sl_pct > 0:
            size *= E.SL_PCT / self._last_sl_pct   # 손절 넓힐수록 사이즈 축소(총위험 고정)
            dbg['risk_const_mult'] = round(E.SL_PCT / self._last_sl_pct, 3)
        return size, lev, dbg
