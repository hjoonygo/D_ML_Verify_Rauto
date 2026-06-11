# -*- coding: utf-8 -*-
# [파일명] ob_mtf.py  (Stage2 동봉, MTF OB)
# 코드길이: 약 110줄, 내부버전명: obmtf_v1, 로직 축약/생략 없이 전체 출력
#
# [목적] 상위 TF(5/15/60분) OB로 SL/TP선을 잡는다. 청산은 1분봉(별도).
#   보고서 df_ob_tf 설계: 진입은 1분 시점이지만 OB는 상위 TF 봉에서 확정된 것만 사용.
#   1분봉을 상위 TF로 리샘플링 -> 그 TF에서 pivot -> 진입 1분시점 이전 '확정된' 상위TF OB 조회.
#
# [미래참조 가드] 진입 1분시점 ts 기준, 그 ts가 속한 상위TF 봉은 '미완성'이므로 제외.
#   직전 '완성된' 상위TF 봉까지만(=ts보다 봉마감이 빠른 것), 추가로 pivot 가드 w_tf봉.
#
# [함수 In/Out]
#   resample_tf(df1m, tf_min) -> df_tf (OHLC, index=봉시작시각)
#   precompute_tf_pivots(df_tf, w) -> (hp_ts[], lp_ts[], hp_top[], hp_bot[], lp_top[], lp_bot[])
#       상위TF pivot의 '봉마감시각'과 top/bottom 배열(시각 오름차순)
#   nearest_above_mtf(price, entry_ts, ...) -> (top, bottom) or None  (저항 OB, SL용)
#   nearest_below_mtf(price, entry_ts, ...) -> (top, bottom) or None  (지지 OB, TP용)
# ==============================================================================

import numpy as np
import pandas as pd


def resample_tf(df1m, tf_min):
    """1분봉 -> tf_min분봉 OHLC. index=봉시작시각."""
    rule = f"{tf_min}min"
    agg = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}
    df_tf = df1m[['open', 'high', 'low', 'close']].resample(rule, label='left', closed='left').agg(agg).dropna()
    return df_tf


def precompute_tf_pivots(df_tf, w, tf_min):
    """상위TF pivot 1회 계산(벡터화). 반환: pivot의 '봉마감시각' + top/bottom.
       봉마감시각 = 봉시작 + tf_min분 (그 시각 이후에야 그 봉이 '확정'됨 = 미래참조 가드)."""
    high = df_tf['high'].values; low = df_tf['low'].values
    starts = df_tf.index.values
    n = len(high)
    if n < 2 * w + 1:
        z = np.array([], dtype='datetime64[ns]'); f = np.array([], dtype=float)
        return z, z, f, f, f, f
    from numpy.lib.stride_tricks import sliding_window_view
    win = 2 * w + 1
    hmax = sliding_window_view(high, win).max(axis=1)
    lmin = sliding_window_view(low, win).min(axis=1)
    centers = np.arange(w, n - w)
    hp_mask = high[w:n - w] == hmax
    lp_mask = low[w:n - w] == lmin
    hp_c = centers[hp_mask]; lp_c = centers[lp_mask]
    tf_delta = np.timedelta64(tf_min, 'm')
    # 확정시각 = pivot봉이 '우측 w봉'까지 확인돼야 pivot 확정 => (center+w)봉 마감시각
    hp_confirm = starts[hp_c + w] + tf_delta
    lp_confirm = starts[lp_c + w] + tf_delta
    return (hp_confirm, lp_confirm,
            high[hp_c], low[hp_c],      # 저항OB: top=high, bottom=low
            high[lp_c], low[lp_c])      # 지지OB: top=high, bottom=low


def nearest_above_mtf(price, entry_ts, hp_confirm, hp_top, hp_bot):
    """진입가 위 가장 가까운 저항 OB(SL용). 확정시각<=entry_ts 인 것만(미래참조 가드).
       bottom>price 인 것 중 bottom 최소(가까운 것)."""
    mask = hp_confirm <= np.datetime64(entry_ts)
    if not mask.any():
        return None
    bots = hp_bot[mask]; tops = hp_top[mask]
    cand = bots > price
    if not cand.any():
        return None
    bb = bots[cand]; tt = tops[cand]
    j = np.argmin(bb)        # 가장 가까운(낮은 bottom)
    return (float(tt[j]), float(bb[j]))


def nearest_below_mtf(price, entry_ts, lp_confirm, lp_top, lp_bot):
    """진입가 아래 가장 가까운 지지 OB(TP용). top<price 인 것 중 top 최대(가까운 것)."""
    mask = lp_confirm <= np.datetime64(entry_ts)
    if not mask.any():
        return None
    tops = lp_top[mask]; bots = lp_bot[mask]
    cand = tops < price
    if not cand.any():
        return None
    tt = tops[cand]; bb = bots[cand]
    j = np.argmax(tt)        # 가장 가까운(높은 top)
    return (float(tt[j]), float(bb[j]))
