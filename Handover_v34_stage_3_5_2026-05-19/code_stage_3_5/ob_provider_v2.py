# -*- coding: utf-8 -*-
"""
[파일명] ob_provider.py
코드길이: 402줄, 내부버전명: v0.1 (단계 2 산출물), 로직을 축약/생략 없이 전체를 출력한다.

사용된 파일:
  - ob_provider.py (단일 파일; 본 파일만으로 단위 테스트 3건까지 수행 가능)

함수 목록 + In/Out:
  - find_pivots(highs, lows, w, i_min, i_max) -> Tuple[List[int], List[int]]
      In:  highs (np.ndarray float64), lows (np.ndarray float64),
           w (int, pivot 한쪽 윈도우 크기), i_min (int), i_max (int)
      Out: (high_pivot_indices: List[int], low_pivot_indices: List[int])
      기능: i ∈ [i_min, i_max] 범위에서 high[i]==max(window) 또는 low[i]==min(window) 인 i 수집

  - build_ob(i, highs, lows) -> OB
      In:  i (int), highs/lows (np.ndarray)
      Out: OB(top, bottom, mean, i)
      기능: i번째 봉의 high/low를 OB 데이터로 포장

  - merge_overlapping(obs) -> List[OB]
      In:  obs (List[OB]) — 가까운 순으로 정렬됨
      Out: List[OB] — 인접 쌍 1회 패스로 겹치는 쌍을 평균 머지
      기능: 가격 범위 겹치는 인접 OB를 [top·bottom 평균]으로 합침

  - _to_arrays(ohlc) -> Tuple[np.ndarray, np.ndarray]
      In:  ohlc (pd.DataFrame['high','low'] 또는 dict-like)
      Out: (highs, lows) np.ndarray
      기능: 입력 형식 정규화 (DataFrame/dict 모두 허용)

  - get_levels_above(t, current_price, n, ohlc_1h, w) -> List[OB]
      In:  t (int, 진입 시점 봉 인덱스),
           current_price (float, 진입가 또는 현재가),
           n (int, 반환할 최대 OB 수),
           ohlc_1h (pd.DataFrame/dict, OHLC 데이터),
           w (int, pivot 윈도우; 그리드 {2,5,7})
      Out: List[OB] — 위쪽 OB 최대 n개, bottom 오름차순(가까운 것 먼저)
      기능: 룩어헤드 가드 i ≤ t-w-1 적용. high pivot 중 top > current_price 만 통과.
            가까운 순 정렬 → 머지 1회 패스 → 상위 n개 반환.

  - get_levels_below(t, current_price, n, ohlc_1h, w) -> List[OB]
      In:  동일 (t, current_price, n, ohlc_1h, w)
      Out: List[OB] — 아래쪽 OB 최대 n개, top 내림차순(가까운 것 먼저)
      기능: low pivot 중 bottom < current_price 만 통과. 그 외 above와 대칭.

변수 목록 + 의미:
  - t            : 현재 1h봉 인덱스 (진입 시점). 이 t에서 t+1봉 시가에 진입한다는 전제.
  - current_price: 진입가 또는 현재가 (안전거리 게이트/대기 재체크 시점에 가변)
  - n            : 반환할 OB 최대 개수 (그리드 {3,5,8})
  - ohlc_1h      : pd.DataFrame ['open','high','low','close'] 또는 dict 의 동일 키
  - w            : pivot 한쪽 윈도우 크기. high[i]==max(high[i-w:i+w+1]) 정의에 사용
  - i_max        : 룩어헤드 가드 상한. t - w - 1.
  - OB.top       : pivot 봉의 high (저항 OB는 상단 가격, 깬 후 SL 후보)
  - OB.bottom    : pivot 봉의 low (저항 OB는 하단, SL Ratchet 시 사용)
  - OB.mean      : (top+bottom)/2 — 본 단계에선 사용 안 함(다음 단계에서 안전거리 일부 식에 사용)
  - OB.i         : pivot 봉 인덱스 (디버깅/머지 추적용)

룩어헤드 보장:
  - 모든 진입 의사결정에서 사용되는 OB는 i ≤ t - w - 1 (확정된 OB만).
  - w=2 → 3봉 전까지, w=5 → 6봉 전까지, w=7 → 8봉 전까지.
"""

from typing import List, Tuple, NamedTuple, Union
import numpy as np
import pandas as pd


# ============================================================
# 데이터 구조
# ============================================================
class OB(NamedTuple):
    top: float
    bottom: float
    mean: float
    i: int  # pivot 봉 인덱스


# ============================================================
# 핵심 함수
# ============================================================
def find_pivots(highs: np.ndarray,
                lows: np.ndarray,
                w: int,
                i_min: int,
                i_max: int) -> Tuple[List[int], List[int]]:
    """
    In:
      highs/lows: np.ndarray (float64)
      w: pivot 한쪽 윈도우 크기 (양수)
      i_min: 검사 시작 인덱스 (포함)
      i_max: 검사 종료 인덱스 (포함)
    Out:
      (high_pivots, low_pivots): 두 개의 List[int]
    """
    n = len(highs)
    if n != len(lows):
        raise ValueError(f"highs/lows 길이 불일치: {n} vs {len(lows)}")
    if w < 1:
        raise ValueError(f"w는 1 이상: w={w}")

    # 유효 범위: [max(w, i_min), min(n-w-1, i_max)]
    lo = max(w, i_min)
    hi = min(n - w - 1, i_max)

    high_pivots: List[int] = []
    low_pivots: List[int] = []

    if hi < lo:
        return high_pivots, low_pivots

    for i in range(lo, hi + 1):
        window_high = highs[i - w: i + w + 1]
        window_low = lows[i - w: i + w + 1]
        if highs[i] == window_high.max():
            high_pivots.append(i)
        if lows[i] == window_low.min():
            low_pivots.append(i)

    return high_pivots, low_pivots


def build_ob(i: int, highs: np.ndarray, lows: np.ndarray) -> OB:
    """
    In: i (int), highs/lows (np.ndarray)
    Out: OB
    """
    top = float(highs[i])
    bottom = float(lows[i])
    return OB(top=top, bottom=bottom, mean=(top + bottom) / 2.0, i=i)


def merge_overlapping(obs: List[OB]) -> List[OB]:
    """
    In: obs — *가까운 순으로 정렬된* OB 리스트
    Out: 인접 쌍 1회 패스로 겹치는 쌍을 평균 머지한 OB 리스트

    겹침 판정: 두 OB의 [bottom, top] 가격 구간이 겹치면 머지.
        min(top_a, top_b) > max(bottom_a, bottom_b)  ⇒ 겹침
    머지 결과: top·bottom 각각 평균.
    i는 가까운 쪽(첫 번째)을 유지.
    """
    if len(obs) <= 1:
        return list(obs)

    merged: List[OB] = [obs[0]]
    for ob in obs[1:]:
        last = merged[-1]
        if min(last.top, ob.top) > max(last.bottom, ob.bottom):
            # 겹침 — 평균 머지
            new_top = (last.top + ob.top) / 2.0
            new_bottom = (last.bottom + ob.bottom) / 2.0
            merged[-1] = OB(
                top=new_top,
                bottom=new_bottom,
                mean=(new_top + new_bottom) / 2.0,
                i=last.i,  # 가까운 쪽 보존
            )
        else:
            merged.append(ob)
    return merged


def _to_arrays(ohlc) -> Tuple[np.ndarray, np.ndarray]:
    """ohlc(DataFrame/dict)에서 (highs, lows) np.ndarray 추출."""
    if isinstance(ohlc, pd.DataFrame):
        return ohlc['high'].values.astype(np.float64), ohlc['low'].values.astype(np.float64)
    elif isinstance(ohlc, dict):
        return np.asarray(ohlc['high'], dtype=np.float64), np.asarray(ohlc['low'], dtype=np.float64)
    else:
        raise TypeError(f"지원하지 않는 ohlc 타입: {type(ohlc)}")


def get_levels_above(t: int,
                     current_price: float,
                     n: int,
                     ohlc_1h,
                     w: int) -> List[OB]:
    """
    위쪽(저항) OB 최대 n개 반환. 가까운 순 (bottom 오름차순).
    룩어헤드 가드 i ≤ t-w-1 적용.
    """
    highs, lows = _to_arrays(ohlc_1h)
    i_max = t - w - 1
    if i_max < w:
        return []

    high_pivots, _ = find_pivots(highs, lows, w, i_min=w, i_max=i_max)

    # 위쪽 OB만 (표준 b 룰): bottom > current_price — OB 전체가 진입가 위에 있어야 함
    # 진입가를 가로지르는 OB는 above에서 제외 (가로지름 OB 진입은 단계 2.5에서 별도 처리)
    obs_above: List[OB] = []
    for i in high_pivots:
        ob = build_ob(i, highs, lows)
        if ob.bottom > current_price:
            obs_above.append(ob)

    # 정렬: bottom 오름차순 (가까운 것 먼저)
    obs_above.sort(key=lambda o: o.bottom)

    # 머지 1회 패스
    obs_above = merge_overlapping(obs_above)

    return obs_above[:n]


def get_levels_below(t: int,
                     current_price: float,
                     n: int,
                     ohlc_1h,
                     w: int) -> List[OB]:
    """
    아래쪽(지지) OB 최대 n개 반환. 가까운 순 (top 내림차순).
    룩어헤드 가드 i ≤ t-w-1 적용.
    """
    highs, lows = _to_arrays(ohlc_1h)
    i_max = t - w - 1
    if i_max < w:
        return []

    _, low_pivots = find_pivots(highs, lows, w, i_min=w, i_max=i_max)

    # 아래쪽 OB만 (표준 b 룰): top < current_price — OB 전체가 진입가 아래에 있어야 함
    # 진입가를 가로지르는 OB는 below에서 제외 (가로지름 OB 진입은 단계 2.5에서 별도 처리)
    obs_below: List[OB] = []
    for i in low_pivots:
        ob = build_ob(i, highs, lows)
        if ob.top < current_price:
            obs_below.append(ob)

    # 정렬: top 내림차순 (가까운 것 먼저)
    obs_below.sort(key=lambda o: o.top, reverse=True)

    # 머지 1회 패스
    obs_below = merge_overlapping(obs_below)

    return obs_below[:n]


# ============================================================
# 단위 테스트 3건
# ============================================================
def test_T1_lookahead_guard() -> None:
    """
    T1: 룩어헤드 가드.
    t=100, w=5에서 i=95~99의 OB는 *반환 안 됨*.
    i_max = t - w - 1 = 94. i=97에 high pivot을 강제로 만들고 차단되는지 확인.
    """
    n_bars = 200
    np.random.seed(42)
    # 평탄(낮은) 배경 — 노이즈 작게
    highs = np.random.uniform(45.0, 50.0, n_bars)
    lows = np.random.uniform(35.0, 40.0, n_bars)

    # i=97에 high pivot 강제 (w=5 윈도우 안에서 i=97의 high가 max)
    for k in range(92, 103):
        highs[k] = min(highs[k], 50.0)
    highs[97] = 120.0
    lows[97] = 100.0

    ohlc = pd.DataFrame({
        'open': lows.copy(),
        'high': highs,
        'low': lows,
        'close': highs.copy(),
    })

    obs = get_levels_above(t=100, current_price=80.0, n=10, ohlc_1h=ohlc, w=5)
    pivot_indices = [ob.i for ob in obs]

    # i=97은 t-w-1=94 < 97 이므로 가드로 차단되어야 함
    assert 97 not in pivot_indices, \
        f"룩어헤드 가드 실패: i=97이 반환됨 (pivot_indices={pivot_indices})"
    assert all(i <= 94 for i in pivot_indices), \
        f"가드 위반 인덱스 발견: {pivot_indices}"
    print(f"  T1 PASS — 룩어헤드 가드 동작 확인 (반환된 i={pivot_indices})")


def test_T2_merge() -> None:
    """
    T2: 머지 동작.
    가격 겹치는 high pivot 3개 → 인접 쌍 1회 패스로 1개로 머지.
    OB 위치: i=20 [bot=100,top=110], i=30 [99,109], i=40 [98,108]
    정렬(bottom 오름차순) 후 인접 쌍 머지:
      [98,108] ⊕ [99,109] → [98.5, 108.5]
      [98.5, 108.5] ⊕ [100, 110] → [99.25, 109.25]
    """
    n_bars = 100
    np.random.seed(123)
    highs = np.random.uniform(45.0, 50.0, n_bars)
    lows = np.random.uniform(35.0, 40.0, n_bars)

    # 3개 OB 강제 — 양옆 w=2 윈도우는 50 이하로 유지하여 i가 high pivot이 되게
    setups = [(20, 100.0, 110.0), (30, 99.0, 109.0), (40, 98.0, 108.0)]
    for idx, bot, top in setups:
        for k in range(idx - 2, idx + 3):
            highs[k] = min(highs[k], 50.0)
            lows[k] = max(lows[k], 35.0)
        highs[idx] = top
        lows[idx] = bot

    ohlc = pd.DataFrame({
        'open': lows.copy(),
        'high': highs,
        'low': lows,
        'close': highs.copy(),
    })

    # t=80, current_price=80, w=2: 평탄 부분 OB (top<50)는 current_price 필터로 제외됨
    obs = get_levels_above(t=80, current_price=80.0, n=10, ohlc_1h=ohlc, w=2)

    assert len(obs) == 1, \
        f"머지 실패: {len(obs)}개 반환 (기대=1). 결과={[(o.top, o.bottom, o.i) for o in obs]}"

    # 인접 쌍 1회 패스 기대값:
    # step1: ((108+109)/2, (98+99)/2) = (108.5, 98.5)
    # step2: ((108.5+110)/2, (98.5+100)/2) = (109.25, 99.25)
    expected_top = 109.25
    expected_bottom = 99.25
    assert abs(obs[0].top - expected_top) < 1e-9, \
        f"top 불일치: {obs[0].top} vs 기대 {expected_top}"
    assert abs(obs[0].bottom - expected_bottom) < 1e-9, \
        f"bottom 불일치: {obs[0].bottom} vs 기대 {expected_bottom}"
    print(f"  T2 PASS — 머지 결과 1개: top={obs[0].top:.4f}, bottom={obs[0].bottom:.4f}")


def test_T3_direction_and_sort() -> None:
    """
    T3: 방향성·정렬 (표준 b 룰).
    above 결과: 모든 OB의 bottom > current_price, bottom 오름차순.
    below 결과: 모든 OB의 top < current_price, top 내림차순.
    OB 전체가 진입가의 해당 쪽에 완전히 있어야 분류됨. 진입가 가로지름은 제외.
    """
    n_bars = 100
    np.random.seed(7)
    # 평탄 배경: highs~80, lows~70 (노이즈 큼). 진입가 80을 가로지르는 노이즈 봉이 섞이게 의도.
    highs = np.full(n_bars, 80.0) + np.random.uniform(-0.5, 0.5, n_bars)
    lows = np.full(n_bars, 70.0) + np.random.uniform(-0.5, 0.5, n_bars)

    # 위쪽 OB 3개 (bottom > 80): i=10 [105,110], i=20 [115,120], i=30 [125,130]
    above_setups = [(10, 105.0, 110.0), (20, 115.0, 120.0), (30, 125.0, 130.0)]
    # 아래쪽 OB 3개 (top < 80): i=40 [40,45], i=50 [30,35], i=60 [20,25]
    below_setups = [(40, 40.0, 45.0), (50, 30.0, 35.0), (60, 20.0, 25.0)]

    for idx, bot, top in above_setups:
        for k in range(idx - 2, idx + 3):
            highs[k] = min(highs[k], 80.5)
        highs[idx] = top
        lows[idx] = bot

    for idx, bot, top in below_setups:
        for k in range(idx - 2, idx + 3):
            lows[k] = max(lows[k], 69.5)
        highs[idx] = top
        lows[idx] = bot

    ohlc = pd.DataFrame({
        'open': lows.copy(),
        'high': highs,
        'low': lows,
        'close': highs.copy(),
    })

    above = get_levels_above(t=80, current_price=80.0, n=10, ohlc_1h=ohlc, w=2)
    below = get_levels_below(t=80, current_price=80.0, n=10, ohlc_1h=ohlc, w=2)

    # above 검증 — 표준 (b): 모든 ob.bottom > current_price
    assert len(above) >= 3, f"above OB 부족: {len(above)}개"
    assert all(ob.bottom > 80.0 for ob in above), \
        f"표준(b) 위반 — above에 가로지름 OB 포함: {[(o.bottom, o.top) for o in above]}"
    bottoms = [ob.bottom for ob in above]
    assert bottoms == sorted(bottoms), f"above 오름차순 위반: {bottoms}"

    # below 검증 — 표준 (b): 모든 ob.top < current_price
    assert len(below) >= 3, f"below OB 부족: {len(below)}개"
    assert all(ob.top < 80.0 for ob in below), \
        f"표준(b) 위반 — below에 가로지름 OB 포함: {[(o.bottom, o.top) for o in below]}"
    tops = [ob.top for ob in below]
    assert tops == sorted(tops, reverse=True), f"below 내림차순 위반: {tops}"

    # 이중 분류 차단 검증 — above와 below에 같은 i가 없어야 함
    above_i = {ob.i for ob in above}
    below_i = {ob.i for ob in below}
    assert above_i.isdisjoint(below_i), \
        f"이중 분류 발생 — 같은 OB이 above·below 둘 다 들어감: {above_i & below_i}"

    print(f"  T3 PASS — above {len(above)}개 (bottoms={bottoms[:3]}...), "
          f"below {len(below)}개 (tops={tops[:3]}...), 이중분류=0")


# ============================================================
# 실행 진입점
# ============================================================
if __name__ == "__main__":
    print("=" * 64)
    print("OB Provider v0.1 — 단위 테스트 (3건)")
    print("=" * 64)
    test_T1_lookahead_guard()
    test_T2_merge()
    test_T3_direction_and_sort()
    print("=" * 64)
    print("ALL 3 TESTS PASSED ✓")
    print("=" * 64)
