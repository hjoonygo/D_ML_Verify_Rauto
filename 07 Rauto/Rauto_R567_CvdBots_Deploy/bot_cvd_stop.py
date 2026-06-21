# -*- coding: utf-8 -*-
# [bot_cvd_stop.py] R5/R6/R7 라이브봇 = 챔피언king + OI손절거리(StopQuality) + CVD흡수 사이징.
#   변종(env): both(R5 TS_CvdBoth) / rc_both(R6 TS_CvdRcBoth) / long(R7 TS_CvdLong).
#   CVD가중 = clip(1 + GAIN*(-side*cvd_z), 0.55, 1.45) — 흐름 역행(흡수)에 비중↑. cvd_z는 aux(인과적 롤링z).
#   무수정 원칙: StopQualityKingBot 상속, _compute_size만 CVD가중 곱. aux 없으면 가중1.0=king동치.
import numpy as np
from bot_stop_quality import StopQualityKingBot


class CvdStopBot(StopQualityKingBot):
    META = {"name": "TS_CvdStop", "fork": "king + OIstop + CVD-absorption sizing (live R5/6/7)"}
    CVD_GAIN = 0.40; CVD_LO = 0.55; CVD_HI = 1.45

    def on_init(self, ctx=None):
        super().on_init(ctx)
        self._last_cvd_z = np.nan

    def on_bar(self, market):
        if isinstance(market.aux, dict) and 'cvd_z' in market.aux:
            v = market.aux['cvd_z']; self._last_cvd_z = float(v) if v == v else np.nan
        return super().on_bar(market)   # StopQuality(OI손절) → king(인트라바가드) → 신호

    def _cvd_weight(self, side):
        z = self._last_cvd_z
        if np.isnan(z): return 1.0
        return float(np.clip(1.0 + self.CVD_GAIN * (-side * z), self.CVD_LO, self.CVD_HI))

    def _compute_size(self, side, entry_i, sig):
        size, lev, dbg = super()._compute_size(side, entry_i, sig)   # king OPVnN(+RISK_CONSTANT)
        w = self._cvd_weight(side); dbg['cvd_w'] = round(w, 3)
        return size * w, lev, dbg
