# -*- coding: utf-8 -*-
# [rauto_datahub.py] ★DataHub — Rauto 구조개혁 ②모듈(관제센터 데이터층) (세션 260625_01_Rauto_Sys_Reform).
#   책임 = 중앙 1m봉 단일출처 + 봇별 TF 변환 + ★미래참조차단(룩어헤드) 게이트.
#   ★핵심규칙: 기존 resample_tf는 label='left'(봉 라벨=시작시각). 봉 마감 = 라벨 + TF분.
#     → '마감시각(close_time) <= now'인 봉만 공개. 라벨시각에 그 봉을 쓰면 미래참조(=차단 대상).
#   ★안전장치3: 이 게이트를 단위테스트(미래봉 주입 시 차단)로 검증해야 함(AnchorTest_LookAhead).
import pandas as pd
import trendstack_signal_engine as TS   # 리샘플 단일출처 재사용(무손상=기존과 봉단위 동일)


class DataHub:
    """중앙 1m → 봇별 TF, 룩어헤드 차단. now(현재 1m시각)를 넘기면 '마감된 봉'만 돌려준다."""

    def __init__(self, d1m):
        # d1m = DatetimeIndex(분단위) OHLC. 단일출처(모든 봇이 이 1개를 공유).
        self._1m = d1m.sort_index()
        self._cache = {}

    def resample(self, tf_min):
        """전구간 tf봉(+close_time). 기존 TS.resample_tf와 봉단위 동일(무손상)."""
        if tf_min not in self._cache:
            df = TS.resample_tf(self._1m, tf_min).copy()
            df["close_time"] = df.index + pd.Timedelta(minutes=int(tf_min))   # ★마감시각
            self._cache[tf_min] = df
        return self._cache[tf_min]

    def bars(self, tf_min, now):
        """now 시각까지 '마감 완료된' tf봉만 (룩어헤드 차단). now=현재 1m 시각."""
        df = self.resample(tf_min)
        return df[df["close_time"] <= pd.Timestamp(now)]

    def latest_closed(self, tf_min, now):
        """now 기준 가장 최근 마감 tf봉 1개(없으면 None). 봇이 신호계산에 쓰는 '확정봉'."""
        b = self.bars(tf_min, now)
        return b.iloc[-1] if len(b) else None

    # ── 진단용(게이트 없는 잘못된 접근 = 라벨<=now). 테스트에서 '게이트가 막는 누수'를 보여줄 때만. ──
    def _naive_label_leq(self, tf_min, now):
        df = self.resample(tf_min)
        return df[df.index <= pd.Timestamp(now)]
