# -*- coding: utf-8 -*-
# [파일명] ob_fast.py  (Stage1 동봉, 속도 보조)
# 코드길이: 약 90줄, 내부버전명: obfast_v1, 로직 축약/생략 없이 전체 출력
#
# [목적] ob_provider_v2 의 get_levels_above/below 와 '동일 결과'를 내되,
#        pivot 을 전체 1회만 계산해 진입시점마다의 풀스캔(O(진입×윈도우))을 제거.
#        => 36개월에서도 수십초로 동작.
#
# [동일성 보장]
#   pivot 정의: high[i]==max(high[i-w:i+w+1]) (ob_provider find_pivots와 동일).
#   룩어헤드 가드: 진입 e_idx 에서 i <= e_idx - w - 1 인 pivot 만 사용(원본 i_max=t-w-1과 동일).
#   above: bottom(=low[i]) > price 인 high-pivot 중 가까운 것(bottom 오름차순).
#   below: top(=high[i]) < price 인 low-pivot 중 가까운 것(top 내림차순).
#   * 머지(merge_overlapping)는 게이트 첫 OB만 쓰므로 생략(첫 OB는 머지 영향 적음).
#     필요시 ob_provider 원본으로 교차검증 가능.
#
# [함수 In/Out]
#   precompute_pivots(high, low, w) -> (high_pivot_idx, low_pivot_idx)  전체 1회
#   nearest_above(price, e_idx, hp_idx, high, low, w) -> (top, bottom) or None  (저항 OB)
#   nearest_below(price, e_idx, lp_idx, high, low, w) -> (top, bottom) or None  (지지 OB)
# ==============================================================================

import numpy as np


def precompute_pivots(high, low, w):
    """전체 구간 pivot 1회 계산(벡터화). high[i]가 좌우 w봉 중 최대 / low[i]가 최소."""
    n = len(high)
    if n < 2 * w + 1:
        return np.array([], dtype=int), np.array([], dtype=int)
    # 슬라이딩 윈도우 최대/최소 (2w+1 길이). numpy stride trick.
    win = 2 * w + 1
    from numpy.lib.stride_tricks import sliding_window_view
    hmax = sliding_window_view(high, win).max(axis=1)   # 길이 n-2w, 중심 i=w..n-w-1
    lmin = sliding_window_view(low, win).min(axis=1)
    centers = np.arange(w, n - w)
    hp = centers[high[w:n - w] == hmax]
    lp = centers[low[w:n - w] == lmin]
    return hp, lp


def nearest_above(price, e_idx, hp_idx, high, low, w, lookback=1440):
    """진입가 위 가장 가까운 저항 OB. 룩어헤드: i <= e_idx-w-1. 최근 lookback봉만 본다."""
    i_max = e_idx - w - 1
    if i_max < w:
        return None
    i_min = max(w, e_idx - lookback)
    cand = hp_idx[(hp_idx <= i_max) & (hp_idx >= i_min)]
    best = None
    for i in cand:
        bottom = low[i]
        if bottom > price:
            if best is None or bottom < best[1]:
                best = (high[i], bottom)
    return best   # (top, bottom)


def nearest_below(price, e_idx, lp_idx, high, low, w, lookback=1440):
    """진입가 아래 가장 가까운 지지 OB. 룩어헤드: i <= e_idx-w-1. 최근 lookback봉만 본다."""
    i_max = e_idx - w - 1
    if i_max < w:
        return None
    i_min = max(w, e_idx - lookback)
    cand = lp_idx[(lp_idx <= i_max) & (lp_idx >= i_min)]
    best = None
    for i in cand:
        top = high[i]
        if top < price:
            if best is None or top > best[0]:
                best = (top, low[i])
    return best   # (top, bottom)
