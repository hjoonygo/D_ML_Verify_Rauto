# -*- coding: utf-8 -*-
# [pullback_quality_gate.py] ★핵심로직 기본방향 (챗GPT5.5에게 보여줄 PoC 설계)
# ─────────────────────────────────────────────────────────────────────────
# 데이터 검증 결과(성급왕 668거래 in-sample, pullback_quality_poc.py):
#   · 진입 직전 OI변화(1h) 3분위 기대값: OI하락 +0.81% > 중간 +0.72% > OI상승 +0.44% (롱: +0.88 vs +0.30)
#     → 챗GPT "OI 감소 눌림 = 좋은 연속" 가설 CONFIRMED(특히 롱, PF 2.38 vs 1.42).
#   · 거래량수축 IC +0.108(롱 +0.137): 진입시 거래량 '확대'가 결과 좋음 → 챗GPT "거래량 감소=좋은눌림"과 반대(반박).
#   · CVD(7h) 측면비대칭: 롱 IC -0.17 / 숏 +0.18 → 흐름 역행(흡수) 신호. 별도 검증가치.
#
# 설계 방향 = 진입 '차단'이 아니라 '사이징 가중'(챗GPT의 PQS→Position Sizing과 동일 철학,
#   우리 기존 OPVnN 사이징의 자연 확장). king 무수정 상속 + _compute_size만 래핑.
#   ★이건 '기본방향 스케치'다. 실제 채택은 36개월 재실행 + CPCV 표준6 통과 후(§15). 아직 미검증.
# ─────────────────────────────────────────────────────────────────────────
import numpy as np
from bot_trendstack_impatient_king import TrendStackImpatientKingBot


class PullbackQualityKingBot(TrendStackImpatientKingBot):
    """king + OI-눌림품질 사이징. aux에 oi_change_1h_pct가 들어온다고 가정(라이브 Dauto 제공)."""
    META = {"name": "TrendStack_KING_PQ", "version": "pq-v0-poc",
            "fork": "king + OI-pullback-quality position sizing (PoC, 미검증)"}

    # 가중 파라미터(데이터 기반 초기값, CPCV로 재최적 예정)
    PQ_FULL = 1.15   # 좋은 눌림(OI 강하락) 가중 상한
    PQ_CUT = 0.70    # 나쁜 눌림(OI 상승) 가중 하한
    PQ_OI_LO = -0.5  # oi_change_1h_pct(%) 이하 = 좋은 눌림(롱/숏 약손 청산)
    PQ_OI_HI = 0.5   # 이상 = 나쁜 눌림(신규 역포지션 유입)

    def on_init(self, ctx=None):
        super().on_init(ctx)
        self._last_oi_chg_1h = np.nan

    def on_bar(self, market):
        # Dauto aux에서 OI 1h 변화율 캐시(없으면 NaN → 가중 1.0 = king 동치)
        if isinstance(market.aux, dict) and 'oi_change_1h_pct' in market.aux:
            v = market.aux['oi_change_1h_pct']
            self._last_oi_chg_1h = float(v) if v == v else np.nan
        return super().on_bar(market)

    def _pq_weight(self):
        """OI변화 → 눌림품질 가중. 좋은눌림(OI하락)=PQ_FULL, 나쁜눌림(OI상승)=PQ_CUT, 중간=선형보간."""
        oi = self._last_oi_chg_1h
        if np.isnan(oi):
            return 1.0  # 데이터 없으면 king 그대로(동치 보존)
        if oi <= self.PQ_OI_LO:
            return self.PQ_FULL
        if oi >= self.PQ_OI_HI:
            return self.PQ_CUT
        # 선형 보간
        t = (oi - self.PQ_OI_LO) / (self.PQ_OI_HI - self.PQ_OI_LO)
        return self.PQ_FULL + t * (self.PQ_CUT - self.PQ_FULL)

    def _compute_size(self, side, entry_i, sig):
        size, lev, dbg = super()._compute_size(side, entry_i, sig)  # 기존 OPVnN+숏컷 그대로
        w = self._pq_weight()
        dbg['pq_weight'] = round(w, 3); dbg['oi_chg_1h'] = self._last_oi_chg_1h
        return size * w, lev, dbg


# ── 검증 로드맵(아직 안 한 것 — 정직) ──
# 1) 이 봇으로 36개월 재실행(bt36_ledgers 경로) → OFF(w=1) 동치로 king +11397% 재현 확인.
# 2) PQ_FULL/PQ_CUT/임계 그리드 → full표본 개선폭 측정.
# 3) ★CPCV 표준6(15경로) 통과만 채택. p25·최악폴드·MDD -20% 위반0 확인.
# 4) CVD 측면비대칭(롱 -0.17/숏 +0.18) 별도 레버로 추가 검증.
