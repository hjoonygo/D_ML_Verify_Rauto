# [파일명] single_pos_filter.py
# 코드길이: 약 130줄, 내부버전명: v2_2026-05-14, 로직 축약/생략 없이 전체를 출력
#
# === 목적 ===
# 사용자 ML 적용 룰 ①: "기존 거래가 종료된 후에만 신규 진입 가능"
# 롱·숏 무관 단일 포지션 운영.
#
# === 알고리즘 ===
# 1) Long 신호 indices + Short 신호 indices를 시간 순으로 통합
# 2) 시계열 순회. 진행 중 거래 있으면 새 신호 건너뜀
# 3) 거래 종료 시점은 (lev, sl_acct, tp_ratio, holding_bars) 조합마다 다르므로
#    *조합별로 별도 시뮬레이션* 필요
# 4) 본 함수는 입력으로 *exit_idx 시계열을 알고 있는 trade 후보 list*를 받아서
#    단일 포지션 룰을 적용한 *survived trades*를 출력
#
# === Lookahead Bias 점검 (작업지침 5번) ===
# - "기존 거래 종료 시점"은 시뮬레이션 결과 (entry_idx, exit_idx)를 봉 시계열에서 추적
# - 봉 t에서 "진행 중 거래"는 entry < t < exit인 거래
# - 새 신호 봉 sig_idx >= in_position_until 만 허용 (진입 봉 = sig_idx + 1 ≥ exit_idx + 1)
# - 즉 거래 종료 봉 *직후 봉부터* 신규 진입 가능 (실거래 가능)
#
# === In/Out 명세 ===
# apply_single_position_filter(candidates_df) -> pd.DataFrame
#   In:  DataFrame with columns [entry_idx, exit_idx, side, ...].
#        entry_idx로 정렬되어 있어야 함 (또는 함수 내부에서 정렬).
#   Out: 단일 포지션 룰 적용 후 살아남은 거래만 (subset of In)
# ============================================================

import numpy as np
import pandas as pd


def apply_single_position_filter(candidates_df):
    """
    단일 포지션 룰 적용.

    Args:
        candidates_df: DataFrame. 컬럼 필수 = ['entry_idx', 'exit_idx', 'side', ...]
            - entry_idx: 신호 봉 인덱스 (정수)
            - exit_idx: 청산 봉 인덱스 (정수, -1이면 NoData)
            - side: 'long' or 'short'
            - 그 외 컬럼 보존됨
    Returns:
        DataFrame. 단일 포지션 룰 통과한 거래만. 시간 순 정렬.
    """
    if len(candidates_df) == 0:
        return candidates_df.copy()

    # 시간 순 정렬 (entry_idx 기준)
    df = candidates_df.sort_values('entry_idx').reset_index(drop=True)

    survived_mask = np.zeros(len(df), dtype=bool)
    # in_position_until: 현재 보유 중인 거래의 exit_idx (없으면 -1)
    in_position_until = -1

    for i in range(len(df)):
        entry_idx = int(df.iloc[i]['entry_idx'])
        exit_idx = int(df.iloc[i]['exit_idx'])

        # NoData (exit_idx == -1) 거래는 건너뜀 — 시뮬 실패
        if exit_idx < 0:
            continue

        # 진입 봉 = entry_idx + 1 (다음 봉 시가 진입, lookahead 회피)
        # 진입 가능 조건: entry_idx + 1 > in_position_until
        # 즉 entry_idx >= in_position_until
        # 더 엄밀히: 이전 거래의 exit 봉에 청산 → 다음 봉부터 신규 진입 가능
        # → entry_idx + 1 > in_position_until   ⇔   entry_idx >= in_position_until
        if entry_idx < in_position_until:
            # 진행 중 거래 있음 → 신호 건너뜀
            continue

        # 진입 가능
        survived_mask[i] = True
        in_position_until = exit_idx

    return df[survived_mask].reset_index(drop=True)


def merge_long_short_signals(long_indices, short_indices):
    """
    Long·Short 신호 인덱스를 통합해서 (idx, side) 시간 순 정렬 리스트 생성.
    같은 봉에서 둘 다 발생 시 — 본 시뮬에서는 둘 다 후보로 보존 (시뮬 후 단일 포지션 필터로 처리).

    Args:
        long_indices, short_indices: 1D int array
    Returns:
        list of (idx, side) tuples, sorted by idx
    """
    merged = [(int(i), 'long') for i in long_indices] + [(int(i), 'short') for i in short_indices]
    merged.sort(key=lambda x: x[0])
    return merged


if __name__ == "__main__":
    print("[단위 테스트] single_pos_filter.py")

    # 케이스 1: 거래 중첩 없음 — 모두 살아남음
    df1 = pd.DataFrame({
        'entry_idx': [10, 30, 50, 70],
        'exit_idx': [15, 35, 55, 75],
        'side': ['long', 'short', 'long', 'short'],
    })
    out1 = apply_single_position_filter(df1)
    assert len(out1) == 4, f"케이스1: 4개 살아남아야, 실측 {len(out1)}"
    print(f"  케이스1 (중첩 없음): {len(out1)}/4 통과")

    # 케이스 2: 거래 중첩 — 첫 거래 끝나기 전 신호 무시
    df2 = pd.DataFrame({
        'entry_idx': [10, 12, 18, 30],
        'exit_idx': [20, 25, 28, 40],
        'side': ['long', 'short', 'long', 'short'],
    })
    out2 = apply_single_position_filter(df2)
    # 진입 10 → exit 20. 다음 신호 12 (<20) 건너뜀, 18 (<20) 건너뜀, 30 (≥20) 진입
    assert len(out2) == 2, f"케이스2: 2개 살아남아야, 실측 {len(out2)}"
    assert list(out2['entry_idx']) == [10, 30]
    print(f"  케이스2 (중첩 발생): {len(out2)}/4 통과 — entry_idx {list(out2['entry_idx'])}")

    # 케이스 3: 거래 종료 봉과 다음 신호 봉이 같은 idx — 경계 조건
    df3 = pd.DataFrame({
        'entry_idx': [10, 20, 25],
        'exit_idx': [20, 30, 35],
        'side': ['long', 'long', 'short'],
    })
    out3 = apply_single_position_filter(df3)
    # 진입 10 → exit 20. 다음 신호 20 (=in_position_until 20)
    # entry_idx 20 >= in_position_until 20 → 진입 OK
    # 진입 20 → exit 30. 다음 신호 25 (<30) 건너뜀
    assert len(out3) == 2, f"케이스3: 2개 살아남아야, 실측 {len(out3)}"
    assert list(out3['entry_idx']) == [10, 20]
    print(f"  케이스3 (경계 조건 entry==prev_exit): {len(out3)}/3 통과 — entry_idx {list(out3['entry_idx'])}")

    # 케이스 4: NoData 거래 (exit_idx = -1) 건너뜀
    df4 = pd.DataFrame({
        'entry_idx': [10, 20, 30],
        'exit_idx': [-1, 25, 35],  # 첫 거래 NoData
        'side': ['long', 'short', 'long'],
    })
    out4 = apply_single_position_filter(df4)
    # 첫 거래 NoData → 건너뜀 (포지션 X)
    # 두번째 entry 20 → 진입, exit 25
    # 세번째 entry 30 >= 25 → 진입
    assert len(out4) == 2, f"케이스4: 2개 살아남아야, 실측 {len(out4)}"
    print(f"  케이스4 (NoData 건너뜀): {len(out4)}/3 통과 — entry_idx {list(out4['entry_idx'])}")

    # 케이스 5: 빈 입력
    df5 = pd.DataFrame(columns=['entry_idx', 'exit_idx', 'side'])
    out5 = apply_single_position_filter(df5)
    assert len(out5) == 0
    print(f"  케이스5 (빈 입력): 통과")

    print("  통과")
