# [파일명] liquidation_model.py
# 코드길이: 약 180줄, 내부버전명: v2_2026-05-14, 로직 축약/생략 없이 전체를 출력
#
# === 목적 ===
# 바이낸스 USDⓈ-M Cross 마진 청산 모델.
# 봉 t의 high/low가 청산 가격에 도달하면 청산 (SL hit보다 우선 처리).
# 사이징 100% 가정 (Cross + capital = position_margin)으로 청산 *임계* 계산.
# 사후 사이징 X% 환산에서 청산 회피 여부 재계산 가능.
#
# === 사용자 결정 채택 ===
# F-3: Tier 1 MMR 0.4% 추정 (BTCUSDT Notional ≤ 50K USDT 영역)
# Maintenance Amount = 0 (Tier 1)
# 자본 $10,000, Lev 1~20 범위에서 사이징 100% 가정 시 명목 $10K ~ $200K
#   → 사용자 자본 규모에선 *Tier 1 안에 머묾* (50K 초과 영역은 사이징 25% × Lev 20)
#
# === 청산 공식 (Cross 마진) ===
# Long:
#   청산 조건: WalletBalance + UnrealizedPnL ≤ MaintenanceMargin
#   WalletBalance = capital (= position_margin / lev × ... 복잡)
#   사이징 100% 단순화: capital = position_margin (전체 자본을 마진으로 사용)
#                       position_notional = capital × lev
#
#   UnrealizedPnL = position_notional × (mark_price - entry_price) / entry_price
#   MM = position_notional × MMR
#
#   청산 조건:
#     capital + capital × lev × (Δ%) ≤ capital × lev × MMR
#     1 + lev × Δ% ≤ lev × MMR
#     Δ% ≤ MMR - 1/lev
#
#   Long 청산 가격: entry × (1 + MMR - 1/lev)
#   Short 청산 가격: entry × (1 - MMR + 1/lev) = entry × (1 + 1/lev - MMR)
#
# 예시 (Lev 20, MMR 0.4%):
#   Long 청산: entry × (1 + 0.004 - 0.05) = entry × 0.954 → -4.6% 가격 변동에 청산
#   Short 청산: entry × 1.046 → +4.6% 가격 변동에 청산
#
# === Lookahead Bias 점검 (작업지침 5번) ===
# - 청산 검출은 봉 t의 high/low만 사용 (진입 봉 + 이후 봉들 monitoring)
# - 봉 안에서 SL vs 청산 동시 도달 시 — 청산이 더 멀리 있으므로 SL 먼저 hit
#   (현재 시뮬 grid의 sl_acct 1.32~3.85% 모두 청산 -4.6% 전에 발생)
# - 그러나 *intrabar*에서 가격이 SL을 *통과해서* 청산까지 갈 가능성 존재
#   → 본 모델은 봉 high/low가 청산 가격에 도달했는지만 보고 청산 우선 처리
#
# === In/Out 명세 ===
# compute_liquidation_price(entry_price, side, lev, mmr=0.004) -> float
#   In: 진입가, 'long'/'short', lev, mmr
#   Out: 청산 가격 (스칼라)
#
# compute_liquidation_price_vec(entry_price_arr, side, lev, mmr=0.004) -> np.ndarray
#   In: 진입가 배열, 방향, lev, mmr
#   Out: 청산 가격 배열 (사이징 100% 기준)
#
# check_liquidation_hit(h_window, l_window, liq_price, side) -> (sl_hit_mask, first_hit_idx)
#   In: holding 윈도우의 high/low 행렬 (N, holding_bars), 청산 가격 배열 (N,), 방향
#   Out: 청산 hit mask, 첫 hit 봉 인덱스
# ============================================================

import numpy as np


# 사용자 결정 채택
BINANCE_BTCUSDT_TIER1_MMR = 0.004  # 0.4% (F-3 추정값)
BINANCE_BTCUSDT_TIER1_MA = 0.0     # Tier 1은 Maintenance Amount = 0


def compute_liquidation_price(entry_price, side, lev, mmr=BINANCE_BTCUSDT_TIER1_MMR):
    """
    Cross 마진 청산 가격 (사이징 100% 가정).

    Args:
        entry_price: float. 진입가
        side: 'long' or 'short'
        lev: int or float. 레버리지
        mmr: float. Maintenance Margin Rate (기본 Tier 1 0.4%)
    Returns:
        float. 청산 가격
    """
    if side == 'long':
        # Long 청산 가격 = entry × (1 + MMR - 1/lev)
        return entry_price * (1.0 + mmr - 1.0 / lev)
    elif side == 'short':
        # Short 청산 가격 = entry × (1 - MMR + 1/lev)
        return entry_price * (1.0 - mmr + 1.0 / lev)
    else:
        raise ValueError(f"side must be 'long' or 'short', got {side}")


def compute_liquidation_price_vec(entry_price_arr, side, lev, mmr=BINANCE_BTCUSDT_TIER1_MMR):
    """벡터화 청산 가격 계산."""
    if side == 'long':
        return entry_price_arr * (1.0 + mmr - 1.0 / lev)
    elif side == 'short':
        return entry_price_arr * (1.0 - mmr + 1.0 / lev)
    else:
        raise ValueError(f"side must be 'long' or 'short', got {side}")


def check_liquidation_hit(h_window, l_window, liq_price, side):
    """
    holding 윈도우에서 청산 hit 봉 검출 (벡터화).

    Args:
        h_window: (N, holding_bars) high 행렬
        l_window: (N, holding_bars) low 행렬
        liq_price: (N,) 청산 가격 배열
        side: 'long' or 'short'
    Returns:
        (liq_hit_mask, first_liq_idx)
        liq_hit_mask: (N,) bool. 해당 거래에서 청산 발생 여부
        first_liq_idx: (N,) int. 첫 청산 봉 인덱스 (윈도우 내 상대 위치, 없으면 -1)
    """
    if side == 'long':
        # Long: low가 청산 가격에 도달 (아래 방향)
        liq_mask = l_window <= liq_price[:, None]
    elif side == 'short':
        # Short: high가 청산 가격에 도달 (위 방향)
        liq_mask = h_window >= liq_price[:, None]
    else:
        raise ValueError(f"side must be 'long' or 'short', got {side}")

    # NaN 봉 제외
    liq_mask &= ~np.isnan(h_window)

    any_hit = liq_mask.any(axis=1)
    first_idx = np.argmax(liq_mask, axis=1)  # 첫 True 위치
    first_idx = np.where(any_hit, first_idx, -1)

    return any_hit, first_idx


if __name__ == "__main__":
    print("[단위 테스트] liquidation_model.py")

    # 케이스 1: Lev 20, MMR 0.4% — 청산 가격 검증
    entry = 80000.0
    liq_long_20x = compute_liquidation_price(entry, 'long', 20)
    liq_short_20x = compute_liquidation_price(entry, 'short', 20)
    expected_long = entry * (1 + 0.004 - 0.05)  # 0.954
    expected_short = entry * (1 - 0.004 + 0.05)  # 1.046
    print(f"  Lev 20 Long 청산: {liq_long_20x:.1f} (기대 {expected_long:.1f}) - 차이 {liq_long_20x - expected_long:.4f}")
    print(f"  Lev 20 Short 청산: {liq_short_20x:.1f} (기대 {expected_short:.1f}) - 차이 {liq_short_20x - expected_short:.4f}")
    pct_long = (liq_long_20x - entry) / entry * 100
    pct_short = (liq_short_20x - entry) / entry * 100
    print(f"  Lev 20 Long 청산 임계: {pct_long:+.2f}% (기대 -4.60%)")
    print(f"  Lev 20 Short 청산 임계: {pct_short:+.2f}% (기대 +4.60%)")

    # 케이스 2: Lev 10 청산 가격
    liq_long_10x = compute_liquidation_price(entry, 'long', 10)
    pct_long_10x = (liq_long_10x - entry) / entry * 100
    print(f"  Lev 10 Long 청산 임계: {pct_long_10x:+.2f}% (기대 -9.60%)")

    # 케이스 3: 청산 hit 검출 벡터화
    N = 5
    holding_bars = 4
    entries = np.array([80000.0, 80000.0, 80000.0, 80000.0, 80000.0])
    liq_prices = compute_liquidation_price_vec(entries, 'long', 20)

    # 5개 거래 시뮬:
    # 0: 정상 (high, low가 청산 가격 안 닿음)
    # 1: 봉 2에서 low가 청산 가격 hit
    # 2: 봉 0에서 즉시 hit
    # 3: 봉 3에서 hit (마지막)
    # 4: 끝까지 hit 없음
    h_win = np.array([
        [80100, 80200, 80300, 80100],
        [80000, 79500, 79000, 78500],   # 봉 1에서 low 76,320 도달
        [79000, 78000, 77000, 76000],   # 봉 0에서 즉시
        [80500, 80400, 80300, 80100],
        [80200, 80300, 80400, 80500],
    ], dtype=np.float64)
    l_win = np.array([
        [79800, 79700, 79600, 79900],
        [79900, 76000, 79000, 78500],   # 봉 1에서 76,000 (< 76,320 청산)
        [76000, 78000, 77000, 76000],
        [80100, 80000, 76000, 80000],   # 봉 2에서 hit
        [79800, 79900, 80000, 80100],
    ], dtype=np.float64)

    liq_hit, liq_first = check_liquidation_hit(h_win, l_win, liq_prices, 'long')
    expected_hit = np.array([False, True, True, True, False])
    expected_first = np.array([-1, 1, 0, 2, -1])
    print(f"  청산 hit: {liq_hit} (기대 {expected_hit})")
    print(f"  첫 청산 봉: {liq_first} (기대 {expected_first})")
    assert np.array_equal(liq_hit, expected_hit), "청산 hit 불일치"
    assert np.array_equal(liq_first, expected_first), "첫 청산 봉 불일치"

    print("  통과")
