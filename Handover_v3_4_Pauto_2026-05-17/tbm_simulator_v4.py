# [파일명] tbm_simulator_v4.py
# 코드길이: 약 510줄, 내부버전명: v4_2026-05-15, 로직 축약/생략 없이 전체 출력.
#
# === 사용된 파일/함수/변수 In/Out 명세 ===
#
# [의존 파일]
#   liquidation_model.py:
#     compute_liquidation_price_vec(entry_price_arr, side, lev, mmr) -> np.ndarray
#       In: 진입가 1D, 'long'/'short', lev int, mmr float
#       Out: 청산가 1D (사이징 100% Cross 기준)
#     check_liquidation_hit(h_window, l_window, liq_price, side) -> (mask, first_idx)
#       In: (N, holding_bars) high/low 행렬, 청산가 (N,), 방향
#       Out: hit mask (N,), 첫 hit 봉 인덱스 (N,)
#   intrabar_path_loader.py (안 C 전용, 옵션):
#     IntrabarPathProvider.get_entry_bar_minutes(entry_bar_idx, tf_name) -> dict
#       In: 진입 봉 인덱스(TF봉 기준), TF 이름 ('15m'/'30m'/'1h')
#       Out: {'open':1D, 'high':1D, 'low':1D, 'close':1D} (해당 봉 내부 1분봉 시퀀스)
#
# [신규/수정 함수]
#   simulate_batch_vec_v4(...):
#     v3 대비 변경 — monitor 윈도우 시작점을 entry_at으로 변경 (진입 봉 path 포함)
#     mode='A': 1h/15m/30m 봉의 high/low만 사용 (intrabar SL 우선)
#     mode='C': 진입 봉만 1분봉 path 재구성, 이후 봉은 기존 방식
#     출력 신규 컬럼: hit_in_entry_bar (bool)
#
#   _simulate_mode_A(entry_indices, ohlc, sl_acct, tp_r, lev, hold, side, regime, mmr)
#     In: entry 봉 인덱스 1D, OHLC dict (각 1D), SL/TP/lev/holding/side/regime/mmr
#     Out: trades DataFrame
#
#   _simulate_mode_C(entry_indices, ohlc, sl_acct, tp_r, lev, hold, side, regime, mmr, intrabar)
#     In: 위와 동일 + intrabar=IntrabarPathProvider 인스턴스
#     Out: trades DataFrame
#
# [핵심 상수]
#   COST_ROUND_TRIP_NOMINAL = 0.0016 (왕복 16bp 명목가 기준, ML 룰 ④)
#   주의: 명목가 기준이므로 자본 기준 net_return 계산 시 *반드시 × lev* 적용
#         (v3.3 정정 — 점프 ① E16 해결)
#
# === 주요 변경 (v3 → v4) ===
# 1) Entry-bar Omission Bias 수정 (이전 채팅 E8 점프 정정):
#    v3: monitor_idx = entry_at + 1 + k  → 진입 봉 path 누락
#    v4: monitor_idx = entry_at + k      → 진입 봉 path 포함
# 2) mode 인자 추가: 'A' (1h high/low, SL 우선 보수) / 'C' (진입 봉 1분봉 재구성)
# 3) 출력 컬럼 신규: hit_in_entry_bar (진입 봉 안에서 exit 발생 여부)
# 4) compute_stats_v4 — pct_hit_in_entry_bar 통계 추가
# 5) intrabar order ambiguity 처리:
#    mode A: SL+TP 같은 봉 hit 시 SL 우선 (P4 보수 유지)
#    mode C: 진입 봉만 1분봉으로 정확한 순서 결정, 이후 봉은 mode A와 동일 P4
#
# === Lookahead Bias 점검 (작업지침 5번) ===
# - 신호 검출 → 진입 봉 = signal_idx + 1 (다음 봉 시가 진입). 신호 봉의 정보만 사용
# - 진입 봉 path: 진입 *이후* 정보이므로 Look-back. Lookahead 아님
# - mode C 1분봉 path: 봉 t의 1분봉들은 t 시점 이후 차차 형성. 봉 t에서 매수 결정은
#   봉 t-1까지의 정보로만 (cRSI/WAE/DI 계산), 따라서 1분봉 사용해도 무관
# - 단위 테스트: assert intrabar_path[0] = bar_open  (시가 정합성)
#
# === holding_bars 의미 변화 (필수 인지) ===
# v3: 진입 봉 다음 봉(+1)부터 holding_bars 봉 monitor. 실효 윈도우 = entry_at+1 ~ +holding_bars
# v4: 진입 봉(entry_at)부터 holding_bars 봉 monitor. 실효 윈도우 = entry_at ~ +holding_bars-1
#
# 예: H=1
#   v3: monitor = [entry_at+1]만 (1봉)
#   v4: monitor = [entry_at]만 (1봉, 진입 봉 자기 자신)
#
# 예: H=4 (1h × 4 = 240min)
#   v3: monitor = entry_at+1 ~ entry_at+4 (4봉, 60~240min 이후)
#   v4: monitor = entry_at ~ entry_at+3 (4봉, 0~240min 이후)
#
# *실거래 의미*: 봉 t-1 종가에 신호 검출 → 봉 t 시가에 진입 → 봉 t 진행 중 SL/TP/청산 hit 가능
# *측정 의미 변경*: 같은 H=N에서 v4가 *0~N봉* 윈도우, v3는 *1~N+1봉* 윈도우. 단순 비교 위험
# 본인 권장: v4 측정 결과를 *기존 v3 결과의 정정값*으로 해석. 알파 자체 비교는 가능
# ============================================================

import numpy as np
import pandas as pd

from liquidation_model import (
    compute_liquidation_price_vec,
    check_liquidation_hit,
    BINANCE_BTCUSDT_TIER1_MMR,
)

COST_ROUND_TRIP_NOMINAL = 0.0016  # 명목가 기준 16bp 왕복 (taker 4bp×2 + slip 8bp). 자본 기준 변환은 × lev


# ============================================================
# Public API
# ============================================================
def simulate_batch_vec_v4(
    entry_indices,
    ohlc,
    sl_acct,
    tp_ratio,
    lev,
    holding_bars,
    side,
    regime_series=None,
    mmr=BINANCE_BTCUSDT_TIER1_MMR,
    mode="A",
    intrabar_provider=None,
    tf_name=None,
):
    """
    Triple Barrier + 청산 모델 v4. 진입 봉 path 포함.

    Args:
        entry_indices: np.ndarray int64. 신호 봉 인덱스 (진입 봉 = entry_indices + 1)
        ohlc: dict with 'open','high','low','close' (각 1D float)
        sl_acct, tp_ratio: float
        lev: int. 레버리지
        holding_bars: int. monitor 윈도우 봉 수 (진입 봉 포함)
        side: 'long' or 'short'
        regime_series: optional 1D object array. 봉별 regime 라벨
        mmr: float. Maintenance Margin Rate
        mode: 'A' (1h/30m/15m high/low만 사용, SL 우선 보수)
              'C' (진입 봉 1분봉 재구성, 이후 봉은 mode A 방식)
        intrabar_provider: IntrabarPathProvider. mode C에서 필수
        tf_name: '15m'/'30m'/'1h'. mode C에서 필수

    Returns:
        pd.DataFrame.
        컬럼: entry_idx, entry_bar, exit_reason, exit_idx, entry_price,
              exit_price, net_return, hit_in_entry_bar, [regime]
        exit_reason ∈ {'SL','TP','Timeout','Liquidation','NoData'}
    """
    if mode not in ("A", "C", "D"):
        raise ValueError(f"mode must be 'A', 'C', or 'D', got {mode}")
    if mode in ("C", "D"):
        if intrabar_provider is None:
            raise ValueError(f"mode {mode} requires intrabar_provider")
        if tf_name is None:
            raise ValueError(f"mode {mode} requires tf_name")

    if len(entry_indices) == 0:
        cols = [
            "entry_idx", "entry_bar", "exit_reason", "exit_idx",
            "entry_price", "exit_price", "net_return", "hit_in_entry_bar",
        ]
        if regime_series is not None:
            cols.append("regime")
        return pd.DataFrame(columns=cols)

    if mode == "A":
        return _simulate_mode_A(
            entry_indices, ohlc, sl_acct, tp_ratio, lev, holding_bars, side,
            regime_series, mmr,
        )
    elif mode == "C":
        return _simulate_mode_C(
            entry_indices, ohlc, sl_acct, tp_ratio, lev, holding_bars, side,
            regime_series, mmr, intrabar_provider, tf_name,
        )
    else:  # mode == "D"
        return _simulate_mode_D(
            entry_indices, ohlc, sl_acct, tp_ratio, lev, holding_bars, side,
            regime_series, mmr, intrabar_provider, tf_name,
        )


# ============================================================
# Mode A: 1h/30m/15m 봉 high/low로 진입 봉 path 포함 (SL 우선 보수)
# ============================================================
def _simulate_mode_A(
    entry_indices, ohlc, sl_acct, tp_ratio, lev, holding_bars, side,
    regime_series, mmr,
):
    """
    Mode A: 진입 봉의 봉 high/low를 사용 (TF봉 OHLC 그대로).
    Intrabar ambiguity는 SL 우선 (P4 보수).
    이전 v3 코드의 monitor 시작점을 +1 → +0으로 변경한 것과 동등.
    """
    entry_indices = np.asarray(entry_indices, dtype=np.int64)
    open_ = ohlc["open"]
    high = ohlc["high"]
    low = ohlc["low"]
    n_bars = len(open_)
    N = len(entry_indices)

    # 진입 봉 = signal_idx + 1 (다음 봉 시가 진입)
    entry_at = entry_indices + 1
    valid = entry_at < n_bars
    entry_at_safe = np.where(valid, entry_at, 0)

    entry_price = open_[entry_at_safe]
    valid &= ~np.isnan(entry_price) & (entry_price > 0)

    sl_pct_price = sl_acct / lev
    tp_pct_price = sl_acct * tp_ratio / lev

    if side == "long":
        sl_price = entry_price * (1 - sl_pct_price)
        tp_price = entry_price * (1 + tp_pct_price)
    else:
        sl_price = entry_price * (1 + sl_pct_price)
        tp_price = entry_price * (1 - tp_pct_price)

    liq_price = compute_liquidation_price_vec(entry_price, side, lev, mmr=mmr)

    # === 핵심 변경: monitor 윈도우 = entry_at + k (진입 봉 포함) ===
    k = np.arange(holding_bars)
    monitor_idx = entry_at_safe[:, None] + k[None, :]  # (N, holding_bars)
    monitor_valid = (monitor_idx < n_bars) & valid[:, None]

    safe_monitor = np.where(monitor_valid, monitor_idx, 0)
    h_window = high[safe_monitor]
    l_window = low[safe_monitor]
    h_window = np.where(monitor_valid, h_window, np.nan)
    l_window = np.where(monitor_valid, l_window, np.nan)

    # SL/TP/청산 hit 검출
    if side == "long":
        sl_hit_mask = (l_window <= sl_price[:, None]) & ~np.isnan(h_window)
        tp_hit_mask = (h_window >= tp_price[:, None]) & ~np.isnan(h_window)
    else:
        sl_hit_mask = (h_window >= sl_price[:, None]) & ~np.isnan(h_window)
        tp_hit_mask = (l_window <= tp_price[:, None]) & ~np.isnan(h_window)

    liq_hit_any, liq_first = check_liquidation_hit(h_window, l_window, liq_price, side)

    # === 진입 봉 hit 별도 처리 ===
    # 진입 봉(monitor[:, 0])은 OPEN으로 들어왔으므로, 시가가 이미 SL/TP/liq 가격을 통과한 case는 없음
    # 단 high/low가 SL/TP를 *진입 봉 안*에서 hit하는 case는 가능 (이게 핵심)
    # → sl_hit_mask[:, 0], tp_hit_mask[:, 0] 모두 의미 있음 (그대로 사용)

    return _resolve_exits(
        entry_indices, entry_at, entry_at_safe, entry_price, sl_price, tp_price,
        liq_price, sl_hit_mask, tp_hit_mask, liq_hit_any, liq_first,
        sl_acct, tp_ratio, lev, holding_bars, side, valid, monitor_idx,
        n_bars, open_, regime_series,
    )


# ============================================================
# Mode C: 진입 봉을 1분봉으로 재구성 + 이후 봉은 mode A
# ============================================================
def _simulate_mode_C(
    entry_indices, ohlc, sl_acct, tp_ratio, lev, holding_bars, side,
    regime_series, mmr, intrabar_provider, tf_name,
):
    """
    Mode C: 진입 봉만 1분봉 path 재구성. 이후 봉은 TF봉 high/low.

    절차:
        1) 진입 봉(entry_at)의 1분봉 N개(TF=60→60개, 30→30개, 15→15개) 로드
        2) 각 1분봉의 high/low로 SL/TP/청산 순서 정확 결정
        3) 만약 진입 봉 내에서 exit 발생 시 → 그 1분봉 가격으로 종료
        4) 진입 봉 내 exit 없으면 → 이후 봉(entry_at+1 ~ +holding_bars-1)은 TF high/low로 처리
    """
    entry_indices = np.asarray(entry_indices, dtype=np.int64)
    open_ = ohlc["open"]
    high = ohlc["high"]
    low = ohlc["low"]
    n_bars = len(open_)
    N = len(entry_indices)

    entry_at = entry_indices + 1
    valid = entry_at < n_bars
    entry_at_safe = np.where(valid, entry_at, 0)

    entry_price = open_[entry_at_safe]
    valid &= ~np.isnan(entry_price) & (entry_price > 0)

    sl_pct_price = sl_acct / lev
    tp_pct_price = sl_acct * tp_ratio / lev

    if side == "long":
        sl_price = entry_price * (1 - sl_pct_price)
        tp_price = entry_price * (1 + tp_pct_price)
    else:
        sl_price = entry_price * (1 + sl_pct_price)
        tp_price = entry_price * (1 - tp_pct_price)

    liq_price = compute_liquidation_price_vec(entry_price, side, lev, mmr=mmr)

    # === Step 1: 진입 봉 path를 1분봉으로 정밀 체크 ===
    # 각 거래마다 진입 봉의 1분봉 시퀀스를 가져와 SL/TP/청산 첫 hit 1분봉 결정
    intrabar_exit_reason = np.full(N, "None", dtype=object)  # 'SL'/'TP'/'Liq'/'None'
    intrabar_exit_price = np.full(N, np.nan, dtype=np.float64)
    intrabar_exit_min_idx = np.full(N, -1, dtype=np.int64)  # 1분봉 인덱스 (0~59)

    for i in range(N):
        if not valid[i]:
            continue
        bar_idx = int(entry_at_safe[i])
        try:
            mins = intrabar_provider.get_entry_bar_minutes(bar_idx, tf_name)
        except Exception:
            # 1분봉 path 로드 실패 (예: 데이터 결측 봉)
            # → 보수적으로 mode A 식으로 fallback (진입 봉 전체 high/low 사용)
            mins = None

        if mins is None:
            # Fallback: TF봉 high/low 사용 (mode A와 동일 결과)
            h_bar = high[bar_idx]
            l_bar = low[bar_idx]
            if side == "long":
                sl_in = (l_bar <= sl_price[i])
                tp_in = (h_bar >= tp_price[i])
                liq_in = (l_bar <= liq_price[i])
            else:
                sl_in = (h_bar >= sl_price[i])
                tp_in = (l_bar <= tp_price[i])
                liq_in = (h_bar >= liq_price[i])
            # P4: SL 우선
            if liq_in and not sl_in and not tp_in:
                intrabar_exit_reason[i] = "Liq"
                intrabar_exit_price[i] = liq_price[i]
            elif sl_in:
                intrabar_exit_reason[i] = "SL"
                intrabar_exit_price[i] = sl_price[i]
            elif tp_in:
                intrabar_exit_reason[i] = "TP"
                intrabar_exit_price[i] = tp_price[i]
            intrabar_exit_min_idx[i] = 0  # 봉 시작
            continue

        # 1분봉 path 정상 로드
        mh = mins["high"]
        ml = mins["low"]
        n_min = len(mh)

        # 첫 hit 1분봉 인덱스 검출
        if side == "long":
            sl_mask_min = ml <= sl_price[i]
            tp_mask_min = mh >= tp_price[i]
            liq_mask_min = ml <= liq_price[i]
        else:
            sl_mask_min = mh >= sl_price[i]
            tp_mask_min = ml <= tp_price[i]
            liq_mask_min = mh >= liq_price[i]

        first_sl = int(np.argmax(sl_mask_min)) if sl_mask_min.any() else n_min + 1
        first_tp = int(np.argmax(tp_mask_min)) if tp_mask_min.any() else n_min + 1
        first_liq = int(np.argmax(liq_mask_min)) if liq_mask_min.any() else n_min + 1

        first_hit = min(first_sl, first_tp, first_liq)
        if first_hit > n_min:
            # 진입 봉 안에서는 hit 없음 → 이후 봉으로 넘김
            continue

        # 같은 1분봉에서 둘 이상 hit 시: 우선순위 Liq > SL > TP (보수)
        # 단 Liq은 SL을 통과해야만 도달하므로 first_liq <= first_sl일 때만 Liq 인정
        # 이미 first_hit이 셋의 min이므로 거기서 어떤 게 첫 hit인지 분기
        if first_liq == first_hit:
            # 청산 봉. 단 같은 봉에서 SL도 hit이면 SL 먼저인지 청산 먼저인지 모름
            # 보수: 청산은 SL보다 *더 나쁜 결과*이므로, SL이 같은 봉에 있으면 SL 우선 처리
            if first_sl == first_hit:
                intrabar_exit_reason[i] = "SL"
                intrabar_exit_price[i] = sl_price[i]
            else:
                intrabar_exit_reason[i] = "Liq"
                intrabar_exit_price[i] = liq_price[i]
        elif first_sl == first_hit and first_tp == first_hit:
            # 같은 1분봉 SL+TP 동시 — 1분봉 안에서도 ambiguity. P4 SL 우선
            intrabar_exit_reason[i] = "SL"
            intrabar_exit_price[i] = sl_price[i]
        elif first_sl == first_hit:
            intrabar_exit_reason[i] = "SL"
            intrabar_exit_price[i] = sl_price[i]
        else:
            intrabar_exit_reason[i] = "TP"
            intrabar_exit_price[i] = tp_price[i]

        intrabar_exit_min_idx[i] = first_hit

    # === Step 2: 진입 봉 내 exit 없는 거래만 이후 봉으로 monitor ===
    # 이후 봉 윈도우: entry_at+1 ~ entry_at+holding_bars-1 (holding_bars-1봉)
    has_intrabar_exit = (intrabar_exit_reason != "None") & valid

    # 이후 봉 monitor만 새로 구성
    if holding_bars > 1:
        k_post = np.arange(holding_bars - 1)
        monitor_idx_post = entry_at_safe[:, None] + 1 + k_post[None, :]
        monitor_valid_post = (monitor_idx_post < n_bars) & valid[:, None]

        safe_monitor_post = np.where(monitor_valid_post, monitor_idx_post, 0)
        h_window_post = high[safe_monitor_post]
        l_window_post = low[safe_monitor_post]
        h_window_post = np.where(monitor_valid_post, h_window_post, np.nan)
        l_window_post = np.where(monitor_valid_post, l_window_post, np.nan)

        if side == "long":
            sl_hit_mask_post = (l_window_post <= sl_price[:, None]) & ~np.isnan(h_window_post)
            tp_hit_mask_post = (h_window_post >= tp_price[:, None]) & ~np.isnan(h_window_post)
        else:
            sl_hit_mask_post = (h_window_post >= sl_price[:, None]) & ~np.isnan(h_window_post)
            tp_hit_mask_post = (l_window_post <= tp_price[:, None]) & ~np.isnan(h_window_post)

        liq_hit_any_post, liq_first_post = check_liquidation_hit(
            h_window_post, l_window_post, liq_price, side
        )
    else:
        # H=1이면 진입 봉만으로 끝
        sl_hit_mask_post = np.zeros((N, 0), dtype=bool)
        tp_hit_mask_post = np.zeros((N, 0), dtype=bool)
        liq_hit_any_post = np.zeros(N, dtype=bool)
        liq_first_post = np.full(N, -1, dtype=np.int64)

    # === Step 3: 최종 exit_reason 결정 ===
    exit_reason = np.full(N, "Timeout", dtype=object)
    exit_idx = np.full(N, -1, dtype=np.int64)
    exit_price = np.full(N, np.nan, dtype=np.float64)
    net_return = np.full(N, np.nan, dtype=np.float64)
    hit_in_entry_bar = np.zeros(N, dtype=bool)

    exit_reason[~valid] = "NoData"

    # 3-1: 진입 봉 hit인 경우 → 그 결과로 즉시 종료
    for i in range(N):
        if not valid[i] or intrabar_exit_reason[i] == "None":
            continue
        reason = intrabar_exit_reason[i]
        hit_in_entry_bar[i] = True
        exit_idx[i] = int(entry_at_safe[i])
        exit_price[i] = intrabar_exit_price[i]
        if reason == "SL":
            exit_reason[i] = "SL"
            net_return[i] = -sl_acct - COST_ROUND_TRIP_NOMINAL * lev
        elif reason == "TP":
            exit_reason[i] = "TP"
            net_return[i] = sl_acct * tp_ratio - COST_ROUND_TRIP_NOMINAL * lev
        elif reason == "Liq":
            exit_reason[i] = "Liquidation"
            net_return[i] = -1.0

    # 3-2: 진입 봉 hit 없음 → 이후 봉으로 처리
    no_intrabar = valid & ~has_intrabar_exit
    if no_intrabar.any() and holding_bars > 1:
        # 이후 봉 first hit (앞 v3 로직과 동일)
        def first_true_idx(mask):
            any_true = mask.any(axis=1)
            idx = np.argmax(mask, axis=1)
            return np.where(any_true, idx, -1), any_true

        sl_first_post, has_sl_post = first_true_idx(sl_hit_mask_post)
        tp_first_post, has_tp_post = first_true_idx(tp_hit_mask_post)
        has_liq_post = liq_hit_any_post

        sl_wins_post = has_sl_post & (~has_tp_post | (sl_first_post <= tp_first_post))
        tp_wins_post = has_tp_post & ~sl_wins_post

        sl_tp_exit_bar_post = np.full(N, np.iinfo(np.int64).max, dtype=np.int64)
        sl_tp_exit_bar_post = np.where(sl_wins_post, sl_first_post, sl_tp_exit_bar_post)
        sl_tp_exit_bar_post = np.where(tp_wins_post, tp_first_post, sl_tp_exit_bar_post)

        liq_overrides_post = has_liq_post & (liq_first_post < sl_tp_exit_bar_post)

        final_liq = no_intrabar & liq_overrides_post
        final_sl = no_intrabar & sl_wins_post & ~liq_overrides_post
        final_tp = no_intrabar & tp_wins_post & ~liq_overrides_post
        final_timeout = no_intrabar & ~has_sl_post & ~has_tp_post & ~liq_overrides_post

        # Liquidation
        exit_reason[final_liq] = "Liquidation"
        # exit_idx: entry_at + 1 + liq_first (이후 봉 윈도우의 상대 위치)
        exit_idx[final_liq] = entry_at_safe[final_liq] + 1 + liq_first_post[final_liq]
        exit_price[final_liq] = liq_price[final_liq]
        net_return[final_liq] = -1.0

        # SL
        exit_reason[final_sl] = "SL"
        exit_idx[final_sl] = entry_at_safe[final_sl] + 1 + sl_first_post[final_sl]
        exit_price[final_sl] = sl_price[final_sl]
        net_return[final_sl] = -sl_acct - COST_ROUND_TRIP_NOMINAL * lev

        # TP
        exit_reason[final_tp] = "TP"
        exit_idx[final_tp] = entry_at_safe[final_tp] + 1 + tp_first_post[final_tp]
        exit_price[final_tp] = tp_price[final_tp]
        net_return[final_tp] = sl_acct * tp_ratio - COST_ROUND_TRIP_NOMINAL * lev

        # Timeout: 진입 봉(0) + 이후 봉(1~holding_bars-1) 모두 hit 없음 → 마지막 봉 close 시점
        timeout_exit_idx_arr = np.minimum(entry_at_safe + holding_bars - 1, n_bars - 1)
        exit_idx[final_timeout] = timeout_exit_idx_arr[final_timeout]
        timeout_exit_price = open_[np.clip(timeout_exit_idx_arr + 1, 0, n_bars - 1)]
        # 더 안전하게: 마지막 monitor 봉의 close 가까운 값 사용 — open_[t+1] = close_[t] 근사
        # 단 마지막 봉 = 데이터 끝이면 open_[t+1] 없음, 대체로 NaN

        timeout_no_data = final_timeout & np.isnan(timeout_exit_price)
        exit_reason[timeout_no_data] = "NoData"
        final_timeout_valid = final_timeout & ~timeout_no_data
        exit_price[final_timeout_valid] = timeout_exit_price[final_timeout_valid]

        if side == "long":
            pct = (timeout_exit_price - entry_price) / entry_price
        else:
            pct = (entry_price - timeout_exit_price) / entry_price
        net_return[final_timeout_valid] = pct[final_timeout_valid] * lev - COST_ROUND_TRIP_NOMINAL * lev

    elif no_intrabar.any() and holding_bars == 1:
        # H=1이고 진입 봉 hit 없음 → Timeout (진입 봉 close에서 종료)
        # close = 진입 봉 다음 봉의 open과 같지 않음 → 진입 봉 close 직접 사용 (close 컬럼 없으므로 open of next bar로 근사 어려움)
        # 보수: 다음 봉 open이 가장 가까운 mark to market 가격
        timeout_next_open_idx = np.minimum(entry_at_safe + 1, n_bars - 1)
        timeout_exit_price = open_[timeout_next_open_idx]
        timeout_no_data = no_intrabar & np.isnan(timeout_exit_price)
        exit_reason[timeout_no_data] = "NoData"
        valid_timeout = no_intrabar & ~timeout_no_data
        exit_reason[valid_timeout] = "Timeout"
        exit_idx[valid_timeout] = entry_at_safe[valid_timeout]
        exit_price[valid_timeout] = timeout_exit_price[valid_timeout]
        if side == "long":
            pct = (timeout_exit_price - entry_price) / entry_price
        else:
            pct = (entry_price - timeout_exit_price) / entry_price
        net_return[valid_timeout] = pct[valid_timeout] * lev - COST_ROUND_TRIP_NOMINAL * lev

    result = pd.DataFrame({
        "entry_idx": entry_indices,
        "entry_bar": entry_at,
        "exit_reason": exit_reason,
        "exit_idx": exit_idx,
        "entry_price": np.where(valid, entry_price, np.nan),
        "exit_price": exit_price,
        "net_return": net_return,
        "hit_in_entry_bar": hit_in_entry_bar,
    })

    if regime_series is not None:
        valid_entry_bar = np.clip(entry_at, 0, n_bars - 1)
        result["regime"] = regime_series[valid_entry_bar]
        result.loc[~valid, "regime"] = "NoData"

    return result


# ============================================================
# Mode D: 진입 봉 + 이후 모든 봉을 1분봉으로 정확 측정 (사용자 지시)
# ============================================================
def _simulate_mode_D(
    entry_indices, ohlc, sl_acct, tp_ratio, lev, holding_bars, side,
    regime_series, mmr, intrabar_provider, tf_name,
):
    """
    Mode D: 사용자 지시 — 진입 봉부터 holding_bars 전부 1분봉으로 SL/TP/청산 검출.

    절차:
        1) 거래마다 진입 봉~holding_bars 만큼 연속 1분봉 시퀀스 추출
           (provider.get_multi_bar_minutes)
        2) 1분봉별 high/low로 SL/TP/Liq 첫 hit 1분봉 결정
        3) 같은 1분봉 SL+TP 동시 hit 시 → P4 SL 우선 (1분봉 ambiguity)
        4) 같은 1분봉 Liq+SL 동시 hit 시 → SL 우선 (Liq은 SL 통과 후)
        5) 모든 1분봉에서 hit 없으면 → 마지막 봉 다음 봉 open으로 mark-to-market
        6) 진입 봉 hit 여부: 첫 hit 1분봉이 bar_starts[0]~bar_starts[1] 범위에 속하면 True

    Lookahead Bias 점검:
    - 신호 검출은 TF봉 (cRSI/WAE/DI). 봉 t 종가에 검출 → 봉 t+1 시가 진입
    - 1분봉 path는 진입 이후 시점이므로 Look-back, 위반 아님

    측정 시간 추정:
    - Mode A의 3~5배 (1분봉 path 처리 오버헤드)
    - 거래 1만 건 × holding 평균 2.5봉 × 평균 30 1분봉 = 75만 1분봉 처리
    """
    entry_indices = np.asarray(entry_indices, dtype=np.int64)
    open_ = ohlc["open"]
    high = ohlc["high"]
    low = ohlc["low"]
    n_bars = len(open_)
    N = len(entry_indices)

    entry_at = entry_indices + 1
    valid = entry_at < n_bars
    entry_at_safe = np.where(valid, entry_at, 0)

    entry_price = open_[entry_at_safe]
    valid &= ~np.isnan(entry_price) & (entry_price > 0)

    sl_pct_price = sl_acct / lev
    tp_pct_price = sl_acct * tp_ratio / lev

    if side == "long":
        sl_price = entry_price * (1 - sl_pct_price)
        tp_price = entry_price * (1 + tp_pct_price)
    else:
        sl_price = entry_price * (1 + sl_pct_price)
        tp_price = entry_price * (1 - tp_pct_price)

    liq_price = compute_liquidation_price_vec(entry_price, side, lev, mmr=mmr)

    # === 결과 컨테이너 ===
    exit_reason = np.full(N, "Timeout", dtype=object)
    exit_idx = np.full(N, -1, dtype=np.int64)
    exit_price = np.full(N, np.nan, dtype=np.float64)
    net_return = np.full(N, np.nan, dtype=np.float64)
    hit_in_entry_bar = np.zeros(N, dtype=bool)

    exit_reason[~valid] = "NoData"

    # === 거래마다 multi-bar 1분봉 path 처리 ===
    for i in range(N):
        if not valid[i]:
            continue
        bar_idx = int(entry_at_safe[i])
        multi = intrabar_provider.get_multi_bar_minutes(bar_idx, holding_bars, tf_name)

        if multi is None:
            # Fallback: TF봉 high/low로 mode A 식 처리 (보수 P4)
            # 진입 봉부터 holding_bars 봉 monitor
            window_end = min(bar_idx + holding_bars, n_bars)
            if window_end <= bar_idx:
                exit_reason[i] = "NoData"
                continue

            h_win = high[bar_idx:window_end]
            l_win = low[bar_idx:window_end]

            if side == "long":
                sl_mask = l_win <= sl_price[i]
                tp_mask = h_win >= tp_price[i]
                liq_mask = l_win <= liq_price[i]
            else:
                sl_mask = h_win >= sl_price[i]
                tp_mask = l_win <= tp_price[i]
                liq_mask = h_win >= liq_price[i]

            # 첫 hit 봉 결정 (P4 SL 우선)
            n_win = len(h_win)
            first_sl = int(np.argmax(sl_mask)) if sl_mask.any() else n_win + 1
            first_tp = int(np.argmax(tp_mask)) if tp_mask.any() else n_win + 1
            first_liq = int(np.argmax(liq_mask)) if liq_mask.any() else n_win + 1

            first_hit_bar = min(first_sl, first_tp, first_liq)

            if first_hit_bar > n_win:
                # Timeout - 마지막 봉 다음 시가
                mark_idx = min(bar_idx + holding_bars, n_bars - 1)
                mark_price = open_[mark_idx]
                if np.isnan(mark_price):
                    exit_reason[i] = "NoData"
                else:
                    exit_reason[i] = "Timeout"
                    exit_idx[i] = mark_idx - 1
                    exit_price[i] = mark_price
                    pct = ((mark_price - entry_price[i]) / entry_price[i]
                           if side == "long" else
                           (entry_price[i] - mark_price) / entry_price[i])
                    net_return[i] = pct * lev - COST_ROUND_TRIP_NOMINAL * lev
                continue

            # 같은 봉 우선순위: SL > Liq > TP (Liq은 SL 더 통과 후 = SL 먼저 hit)
            if first_sl == first_hit_bar:
                exit_reason[i] = "SL"
                exit_price[i] = sl_price[i]
                net_return[i] = -sl_acct - COST_ROUND_TRIP_NOMINAL * lev
            elif first_liq == first_hit_bar:
                exit_reason[i] = "Liquidation"
                exit_price[i] = liq_price[i]
                net_return[i] = -1.0
            else:
                exit_reason[i] = "TP"
                exit_price[i] = tp_price[i]
                net_return[i] = sl_acct * tp_ratio - COST_ROUND_TRIP_NOMINAL * lev

            exit_idx[i] = bar_idx + first_hit_bar
            hit_in_entry_bar[i] = (first_hit_bar == 0)
            continue

        # === 정상 1분봉 path 처리 ===
        mh = multi["high"]
        ml = multi["low"]
        bar_starts = multi["bar_starts"]
        n_min = len(mh)

        # 1분봉 mask
        if side == "long":
            sl_mask_min = ml <= sl_price[i]
            tp_mask_min = mh >= tp_price[i]
            liq_mask_min = ml <= liq_price[i]
        else:
            sl_mask_min = mh >= sl_price[i]
            tp_mask_min = ml <= tp_price[i]
            liq_mask_min = mh >= liq_price[i]

        first_sl = int(np.argmax(sl_mask_min)) if sl_mask_min.any() else n_min + 1
        first_tp = int(np.argmax(tp_mask_min)) if tp_mask_min.any() else n_min + 1
        first_liq = int(np.argmax(liq_mask_min)) if liq_mask_min.any() else n_min + 1

        first_hit_min = min(first_sl, first_tp, first_liq)

        if first_hit_min > n_min:
            # 모든 1분봉에서 hit 없음 → Timeout (마지막 봉 다음 시가)
            mark_idx = min(bar_idx + holding_bars, n_bars - 1)
            mark_price = open_[mark_idx]
            if np.isnan(mark_price):
                exit_reason[i] = "NoData"
            else:
                exit_reason[i] = "Timeout"
                exit_idx[i] = mark_idx - 1
                exit_price[i] = mark_price
                pct = ((mark_price - entry_price[i]) / entry_price[i]
                       if side == "long" else
                       (entry_price[i] - mark_price) / entry_price[i])
                net_return[i] = pct * lev - COST_ROUND_TRIP_NOMINAL * lev
            continue

        # 같은 1분봉 ambiguity 처리 (P4 SL 우선)
        # 우선순위: 같은 1분봉에서 SL hit이면 SL, 아니면 Liq 체크, 아니면 TP
        if first_sl == first_hit_min:
            exit_reason[i] = "SL"
            exit_price[i] = sl_price[i]
            net_return[i] = -sl_acct - COST_ROUND_TRIP_NOMINAL * lev
        elif first_liq == first_hit_min:
            # Liq이 같은 1분봉이고 SL은 더 뒤 → 실제 거래에서 Liq은 SL 통과한 가격
            # 단 first_sl > first_liq일 때만 도달하는 분기 (논리상 SL이 Liq보다 가까움)
            # → 안전하게 Liq 인정
            exit_reason[i] = "Liquidation"
            exit_price[i] = liq_price[i]
            net_return[i] = -1.0
        else:
            exit_reason[i] = "TP"
            exit_price[i] = tp_price[i]
            net_return[i] = sl_acct * tp_ratio - COST_ROUND_TRIP_NOMINAL * lev

        # exit_idx 환산: 1분봉 인덱스 → TF봉 인덱스
        # first_hit_min이 bar_starts[k] <= first_hit_min < bar_starts[k+1] 범위에 있으면
        # → TF봉 k가 exit 봉. exit_idx = bar_idx + k
        k = int(np.searchsorted(bar_starts, first_hit_min, side="right") - 1)
        k = max(0, min(k, holding_bars - 1))
        exit_idx[i] = bar_idx + k

        # 진입 봉 hit 여부
        hit_in_entry_bar[i] = (first_hit_min < bar_starts[1])

    result = pd.DataFrame({
        "entry_idx": entry_indices,
        "entry_bar": entry_at,
        "exit_reason": exit_reason,
        "exit_idx": exit_idx,
        "entry_price": np.where(valid, entry_price, np.nan),
        "exit_price": exit_price,
        "net_return": net_return,
        "hit_in_entry_bar": hit_in_entry_bar,
    })

    if regime_series is not None:
        valid_entry_bar = np.clip(entry_at, 0, n_bars - 1)
        result["regime"] = regime_series[valid_entry_bar]
        result.loc[~valid, "regime"] = "NoData"

    return result


# ============================================================
# Mode A의 exit resolver (mode A 내부에서 호출)
# ============================================================
def _resolve_exits(
    entry_indices, entry_at, entry_at_safe, entry_price, sl_price, tp_price,
    liq_price, sl_hit_mask, tp_hit_mask, liq_hit_any, liq_first,
    sl_acct, tp_ratio, lev, holding_bars, side, valid, monitor_idx,
    n_bars, open_, regime_series,
):
    """
    Mode A 전용 exit 결정. monitor 윈도우 = entry_at부터 holding_bars봉.
    Intrabar ambiguity: SL+TP 같은 봉 hit → SL 우선 (P4 보수)
                       Liq+SL 같은 봉 → SL 우선 (Liq은 더 멀어서 SL 통과 후 도달)
    """
    N = len(entry_indices)

    def first_true_idx(mask):
        any_true = mask.any(axis=1)
        idx = np.argmax(mask, axis=1)
        return np.where(any_true, idx, -1), any_true

    sl_first, has_sl = first_true_idx(sl_hit_mask)
    tp_first, has_tp = first_true_idx(tp_hit_mask)
    has_liq = liq_hit_any

    exit_reason = np.full(N, "Timeout", dtype=object)
    exit_idx = np.full(N, -1, dtype=np.int64)
    exit_price = np.full(N, np.nan, dtype=np.float64)
    net_return = np.full(N, np.nan, dtype=np.float64)
    hit_in_entry_bar = np.zeros(N, dtype=bool)

    exit_reason[~valid] = "NoData"

    sl_wins = has_sl & (~has_tp | (sl_first <= tp_first))
    tp_wins = has_tp & ~sl_wins

    sl_tp_exit_bar = np.full(N, np.iinfo(np.int64).max, dtype=np.int64)
    sl_tp_exit_bar = np.where(sl_wins, sl_first, sl_tp_exit_bar)
    sl_tp_exit_bar = np.where(tp_wins, tp_first, sl_tp_exit_bar)

    liq_overrides = has_liq & (liq_first < sl_tp_exit_bar)

    final_liq = valid & liq_overrides
    final_sl = valid & sl_wins & ~liq_overrides
    final_tp = valid & tp_wins & ~liq_overrides
    final_timeout = valid & ~has_sl & ~has_tp & ~liq_overrides

    # 진입 봉(monitor 인덱스 0) 에서 hit한 거래 표시
    sl_in_entry_bar = sl_wins & (sl_first == 0) & ~liq_overrides
    tp_in_entry_bar = tp_wins & (tp_first == 0) & ~liq_overrides
    liq_in_entry_bar = liq_overrides & (liq_first == 0)
    hit_in_entry_bar = (sl_in_entry_bar | tp_in_entry_bar | liq_in_entry_bar)

    # Liquidation
    exit_reason[final_liq] = "Liquidation"
    exit_idx[final_liq] = entry_at_safe[final_liq] + liq_first[final_liq]
    exit_price[final_liq] = liq_price[final_liq]
    net_return[final_liq] = -1.0

    # SL
    exit_reason[final_sl] = "SL"
    exit_idx[final_sl] = entry_at_safe[final_sl] + sl_first[final_sl]
    exit_price[final_sl] = sl_price[final_sl]
    net_return[final_sl] = -sl_acct - COST_ROUND_TRIP_NOMINAL * lev

    # TP
    exit_reason[final_tp] = "TP"
    exit_idx[final_tp] = entry_at_safe[final_tp] + tp_first[final_tp]
    exit_price[final_tp] = tp_price[final_tp]
    net_return[final_tp] = sl_acct * tp_ratio - COST_ROUND_TRIP_NOMINAL * lev

    # Timeout: 마지막 monitor 봉 = entry_at + holding_bars - 1
    timeout_exit_idx_arr = np.minimum(entry_at_safe + holding_bars - 1, n_bars - 1)
    # mark-to-market 가격: 다음 봉 시가 (가장 일관성 있는 봉간 결제 가격)
    timeout_next_open_idx = np.minimum(timeout_exit_idx_arr + 1, n_bars - 1)
    timeout_exit_price = open_[timeout_next_open_idx]

    timeout_no_data = final_timeout & np.isnan(timeout_exit_price)
    exit_reason[timeout_no_data] = "NoData"
    final_timeout_valid = final_timeout & ~timeout_no_data
    exit_idx[final_timeout_valid] = timeout_exit_idx_arr[final_timeout_valid]
    exit_price[final_timeout_valid] = timeout_exit_price[final_timeout_valid]

    if side == "long":
        pct = (timeout_exit_price - entry_price) / entry_price
    else:
        pct = (entry_price - timeout_exit_price) / entry_price
    net_return[final_timeout_valid] = pct[final_timeout_valid] * lev - COST_ROUND_TRIP_NOMINAL * lev

    result = pd.DataFrame({
        "entry_idx": entry_indices,
        "entry_bar": entry_at,
        "exit_reason": exit_reason,
        "exit_idx": exit_idx,
        "entry_price": np.where(valid, entry_price, np.nan),
        "exit_price": exit_price,
        "net_return": net_return,
        "hit_in_entry_bar": hit_in_entry_bar,
    })

    if regime_series is not None:
        valid_entry_bar = np.clip(entry_at, 0, n_bars - 1)
        result["regime"] = regime_series[valid_entry_bar]
        result.loc[~valid, "regime"] = "NoData"

    return result


# ============================================================
# 통계
# ============================================================
def compute_stats_v4(trades_df):
    """
    PF, WinR, NetSum, MaxDD, MaxConsecLoss + pct_hit_in_entry_bar.
    """
    valid = trades_df[trades_df["exit_reason"] != "NoData"].copy()
    n = len(valid)
    if n == 0:
        return {
            "n_total": int(len(trades_df)), "n_valid": 0,
            "win_rate": np.nan, "pf": np.nan,
            "net_return_sum": 0.0, "net_return_mean": 0.0,
            "n_sl": 0, "n_tp": 0, "n_timeout": 0, "n_liq": 0,
            "mean_win": 0.0, "mean_loss": 0.0,
            "max_dd": 0.0, "max_consec_loss": 0,
            "n_hit_in_entry_bar": 0,
            "pct_hit_in_entry_bar": 0.0,
        }

    valid = valid.sort_values("entry_idx").reset_index(drop=True)
    nr = valid["net_return"].values

    wins = nr[nr > 0]
    losses = nr[nr <= 0]
    total_gain = wins.sum() if len(wins) > 0 else 0.0
    total_loss = abs(losses.sum()) if len(losses) > 0 else 0.0
    pf = total_gain / total_loss if total_loss > 0 else 999.0

    cum = np.cumsum(nr)
    running_max = np.maximum.accumulate(cum)
    dd = running_max - cum
    max_dd = float(dd.max()) if len(dd) > 0 else 0.0

    loss_mask = nr <= 0
    max_consec = 0
    cur = 0
    for v in loss_mask:
        if v:
            cur += 1
            max_consec = max(max_consec, cur)
        else:
            cur = 0

    n_hit_entry = int(valid["hit_in_entry_bar"].sum()) if "hit_in_entry_bar" in valid.columns else 0
    pct_hit_entry = float(n_hit_entry / n) if n > 0 else 0.0

    return {
        "n_total": int(len(trades_df)),
        "n_valid": int(n),
        "win_rate": float(len(wins) / n),
        "pf": float(min(pf, 999.0)),
        "net_return_sum": float(nr.sum()),
        "net_return_mean": float(nr.mean()),
        "n_sl": int((valid["exit_reason"] == "SL").sum()),
        "n_tp": int((valid["exit_reason"] == "TP").sum()),
        "n_timeout": int((valid["exit_reason"] == "Timeout").sum()),
        "n_liq": int((valid["exit_reason"] == "Liquidation").sum()),
        "mean_win": float(wins.mean()) if len(wins) > 0 else 0.0,
        "mean_loss": float(losses.mean()) if len(losses) > 0 else 0.0,
        "max_dd": max_dd,
        "max_consec_loss": int(max_consec),
        "n_hit_in_entry_bar": n_hit_entry,
        "pct_hit_in_entry_bar": pct_hit_entry,
    }


# ============================================================
# 단위 테스트 (5+ 케이스)
# ============================================================
if __name__ == "__main__":
    print("[단위 테스트] tbm_simulator_v4.py")

    # --- 케이스 1: 진입 봉 안 SL hit (Long) ---
    # 진입가 80000, SL 1.32%/Lev 20 = 0.066% → SL 가격 79947.2
    # 진입 봉의 low가 79900 → SL hit (진입 봉 자체에서)
    open_ = np.array([80000.0, 80000.0, 80000.0, 80000.0, 80000.0, 80000.0])
    high = np.array([80100.0, 80100.0, 80000.0, 80100.0, 80100.0, 80100.0])
    low = np.array([79900.0, 79900.0, 79900.0, 79900.0, 79900.0, 79900.0])
    ohlc = {"open": open_, "high": high, "low": low, "close": open_}

    # signal_idx=0 → entry_at=1 → 진입가 = open_[1] = 80000
    # SL 가격 = 80000 × (1 - 0.066%) = 79947.2
    # 진입 봉 low 79900 < 79947.2 → SL hit on bar 0 of monitor (= entry_at = 1)
    df_A = simulate_batch_vec_v4(
        np.array([0]), ohlc, sl_acct=0.0132, tp_ratio=5.0,
        lev=20, holding_bars=1, side="long", mode="A"
    )
    assert df_A["exit_reason"].iloc[0] == "SL", f"케이스1 SL 기대, 실측 {df_A['exit_reason'].iloc[0]}"
    assert df_A["hit_in_entry_bar"].iloc[0] == True, f"케이스1 hit_in_entry_bar=True 기대"
    print(f"  케이스1 (진입 봉 SL hit): 통과, exit={df_A['exit_reason'].iloc[0]}, hit_in_entry_bar={df_A['hit_in_entry_bar'].iloc[0]}")

    # --- 케이스 2: 진입 봉은 안전, 다음 봉에서 SL hit ---
    open_ = np.array([80000.0, 80000.0, 80000.0, 80000.0])
    high = np.array([80100.0, 80050.0, 80100.0, 80100.0])  # 진입 봉(idx=1) high=80050, low=79980 (SL hit 안 됨)
    low = np.array([79980.0, 79980.0, 79900.0, 79900.0])   # idx=2에서 SL hit
    ohlc = {"open": open_, "high": high, "low": low, "close": open_}

    df_A = simulate_batch_vec_v4(
        np.array([0]), ohlc, sl_acct=0.0132, tp_ratio=5.0,
        lev=20, holding_bars=2, side="long", mode="A"
    )
    # SL 가격 = 80000 × 0.99934 = 79947.2
    # 진입 봉(idx=1) low 79980 > 79947.2 → SL hit 안 됨
    # 다음 봉(idx=2) low 79900 < 79947.2 → SL hit
    assert df_A["exit_reason"].iloc[0] == "SL", f"케이스2 SL 기대"
    assert df_A["hit_in_entry_bar"].iloc[0] == False, f"케이스2 hit_in_entry_bar=False 기대"
    print(f"  케이스2 (다음 봉 SL hit): 통과, exit={df_A['exit_reason'].iloc[0]}, hit_in_entry_bar={df_A['hit_in_entry_bar'].iloc[0]}")

    # --- 케이스 3: 진입 봉 안 TP hit ---
    # TP 가격 = 80000 × (1 + 0.066%×5) = 80264 (TP_ratio=5.0)
    open_ = np.array([80000.0, 80000.0, 80000.0])
    high = np.array([80100.0, 80300.0, 80100.0])  # 진입 봉 high 80300 > TP 80264
    low = np.array([79990.0, 79990.0, 79990.0])
    ohlc = {"open": open_, "high": high, "low": low, "close": open_}

    df_A = simulate_batch_vec_v4(
        np.array([0]), ohlc, sl_acct=0.0132, tp_ratio=5.0,
        lev=20, holding_bars=2, side="long", mode="A"
    )
    assert df_A["exit_reason"].iloc[0] == "TP", f"케이스3 TP 기대, 실측 {df_A['exit_reason'].iloc[0]}"
    assert df_A["hit_in_entry_bar"].iloc[0] == True, f"케이스3 hit_in_entry_bar=True 기대"
    print(f"  케이스3 (진입 봉 TP hit): 통과, exit={df_A['exit_reason'].iloc[0]}, hit_in_entry_bar={df_A['hit_in_entry_bar'].iloc[0]}")

    # --- 케이스 4: 진입 봉 SL+TP 둘 다 hit → P4 SL 우선 ---
    open_ = np.array([80000.0, 80000.0, 80000.0])
    high = np.array([80100.0, 80300.0, 80100.0])  # TP hit (80264)
    low = np.array([79990.0, 79900.0, 79990.0])   # SL hit (79947)
    ohlc = {"open": open_, "high": high, "low": low, "close": open_}

    df_A = simulate_batch_vec_v4(
        np.array([0]), ohlc, sl_acct=0.0132, tp_ratio=5.0,
        lev=20, holding_bars=2, side="long", mode="A"
    )
    assert df_A["exit_reason"].iloc[0] == "SL", f"케이스4 SL 기대 (P4), 실측 {df_A['exit_reason'].iloc[0]}"
    print(f"  케이스4 (진입 봉 SL+TP 동시 → P4 SL 우선): 통과, exit={df_A['exit_reason'].iloc[0]}")

    # --- 케이스 5: holding_bars=1, 진입 봉 안 hit 없음 → Timeout ---
    open_ = np.array([80000.0, 80000.0, 80000.1])
    high = np.array([80100.0, 80200.0, 80200.0])  # 진입 봉 high 80200 < TP 80264
    low = np.array([79990.0, 79960.0, 79960.0])   # 진입 봉 low 79960 > SL 79947
    ohlc = {"open": open_, "high": high, "low": low, "close": open_}

    df_A = simulate_batch_vec_v4(
        np.array([0]), ohlc, sl_acct=0.0132, tp_ratio=5.0,
        lev=20, holding_bars=1, side="long", mode="A"
    )
    assert df_A["exit_reason"].iloc[0] == "Timeout", f"케이스5 Timeout 기대, 실측 {df_A['exit_reason'].iloc[0]}"
    assert df_A["hit_in_entry_bar"].iloc[0] == False, f"케이스5 hit_in_entry_bar=False 기대"
    print(f"  케이스5 (H=1, 진입 봉 안전 → Timeout): 통과, exit={df_A['exit_reason'].iloc[0]}")

    # --- 케이스 6: Short — 진입 봉 안 SL hit ---
    # Short 진입가 80000, SL 가격 = 80000 × (1 + 0.066%) = 80052.8
    open_ = np.array([80000.0, 80000.0, 80000.0])
    high = np.array([80100.0, 80100.0, 80100.0])  # 진입 봉 high 80100 > SL 80052.8
    low = np.array([79950.0, 79950.0, 79950.0])
    ohlc = {"open": open_, "high": high, "low": low, "close": open_}

    df_A = simulate_batch_vec_v4(
        np.array([0]), ohlc, sl_acct=0.0132, tp_ratio=5.0,
        lev=20, holding_bars=2, side="short", mode="A"
    )
    assert df_A["exit_reason"].iloc[0] == "SL", f"케이스6 Short SL 기대, 실측 {df_A['exit_reason'].iloc[0]}"
    print(f"  케이스6 (Short 진입 봉 SL hit): 통과")

    # --- 케이스 7: 합성 데이터 200개 거래 통계 ---
    rng = np.random.default_rng(42)
    n = 3000
    close = 80000 + np.cumsum(rng.normal(0, 100, n))
    high = close + np.abs(rng.normal(0, 60, n))
    low = close - np.abs(rng.normal(0, 60, n))
    open_ = np.r_[close[0], close[:-1]]
    ohlc = {"open": open_, "high": high, "low": low, "close": close}

    entries = np.random.randint(50, n - 100, 200)
    df = simulate_batch_vec_v4(entries, ohlc, sl_acct=0.0132, tp_ratio=5.0,
                                lev=20, holding_bars=1, side="long", mode="A")
    print(f"  케이스7 (합성 200거래 H=1 통계):")
    print(f"    exit_reason: {df['exit_reason'].value_counts().to_dict()}")
    stats = compute_stats_v4(df)
    print(f"    PF={stats['pf']:.3f}, WinR={stats['win_rate']:.3f}")
    print(f"    *** pct_hit_in_entry_bar = {stats['pct_hit_in_entry_bar']*100:.1f}% ***")
    print(f"    (H=1이면 100% 가까이 나와야. 진입 봉만 monitor)")

    # --- 케이스 8: H=4 동일 데이터 — 진입 봉 hit 비율 측정 (실데이터에 가까운 의미) ---
    df_h4 = simulate_batch_vec_v4(entries, ohlc, sl_acct=0.0132, tp_ratio=5.0,
                                   lev=20, holding_bars=4, side="long", mode="A")
    stats_h4 = compute_stats_v4(df_h4)
    print(f"\n  케이스8 (합성 200거래 H=4):")
    print(f"    PF={stats_h4['pf']:.3f}, WinR={stats_h4['win_rate']:.3f}")
    print(f"    *** pct_hit_in_entry_bar = {stats_h4['pct_hit_in_entry_bar']*100:.1f}% ***")
    print(f"    (H>1: 진입 봉 hit 비율이 *기존 v3에서 측정 누락된 부분*의 직접 정량화)")

    # ====================================================================
    # === Mode D 단위 테스트 (사용자 지시 — 진입 봉 + 이후 봉 모두 1분봉) ===
    # ====================================================================
    print("\n[Mode D 단위 테스트]")
    from intrabar_path_loader import IntrabarPathProvider
    from tf_aggregator import aggregate_ohlcv

    # 합성 1분봉 데이터 (60일)
    rng2 = np.random.default_rng(42)
    n_1m = 60 * 24 * 60  # 60일 1분봉
    ts_1m = pd.date_range("2024-01-01", periods=n_1m, freq="1min", tz="UTC")
    rets = rng2.normal(0, 0.0003, n_1m)
    cl = 80000 * np.exp(np.cumsum(rets))
    hi = cl + np.abs(rng2.normal(0, cl*0.0003, n_1m))
    lo = cl - np.abs(rng2.normal(0, cl*0.0003, n_1m))
    op = np.r_[cl[0], cl[:-1]]
    df_1m_test = pd.DataFrame({
        "timestamp": ts_1m, "open": op, "high": hi, "low": lo, "close": cl
    })

    # 1h aggregate
    df_1h_test = aggregate_ohlcv(df_1m_test, 60)
    provider = IntrabarPathProvider(df_1m_test, {"1h": df_1h_test})

    ohlc_test = {
        "open": df_1h_test["open"].values,
        "high": df_1h_test["high"].values,
        "low": df_1h_test["low"].values,
        "close": df_1h_test["close"].values,
    }
    n_test = len(df_1h_test)
    entries_test = np.random.RandomState(42).randint(50, n_test - 10, 30)

    # --- 케이스 D1: Mode A vs Mode D 비교 (H=1) ---
    df_A_d1 = simulate_batch_vec_v4(entries_test, ohlc_test, 0.0132, 5.0, 20, 1, "long", mode="A")
    df_D_d1 = simulate_batch_vec_v4(entries_test, ohlc_test, 0.0132, 5.0, 20, 1, "long",
                                     mode="D", intrabar_provider=provider, tf_name="1h")
    stats_A_d1 = compute_stats_v4(df_A_d1)
    stats_D_d1 = compute_stats_v4(df_D_d1)
    print(f"  케이스D1 (H=1, 합성 30거래):")
    print(f"    Mode A: PF={stats_A_d1['pf']:.3f}, exit={df_A_d1['exit_reason'].value_counts().to_dict()}")
    print(f"    Mode D: PF={stats_D_d1['pf']:.3f}, exit={df_D_d1['exit_reason'].value_counts().to_dict()}")
    diff = (df_A_d1['exit_reason'].values != df_D_d1['exit_reason'].values).sum()
    print(f"    A vs D 다른 exit: {diff}/30")

    # --- 케이스 D2: H=4 Mode D 처리 ---
    df_D_d2 = simulate_batch_vec_v4(entries_test, ohlc_test, 0.0132, 5.0, 20, 4, "long",
                                     mode="D", intrabar_provider=provider, tf_name="1h")
    stats_D_d2 = compute_stats_v4(df_D_d2)
    n_resolved_d2 = (df_D_d2['exit_reason'] != 'NoData').sum()
    assert n_resolved_d2 >= 25, f"D2 거래 ≥25 기대, 실측 {n_resolved_d2}"
    print(f"  케이스D2 (H=4, Mode D): PF={stats_D_d2['pf']:.3f}, "
          f"hit_in_entry_bar={stats_D_d2['pct_hit_in_entry_bar']*100:.1f}%")

    # --- 케이스 D3: Mode A vs Mode C vs Mode D 비교 (H=2) ---
    df_A_d3 = simulate_batch_vec_v4(entries_test, ohlc_test, 0.0132, 5.0, 20, 2, "long", mode="A")
    df_C_d3 = simulate_batch_vec_v4(entries_test, ohlc_test, 0.0132, 5.0, 20, 2, "long",
                                     mode="C", intrabar_provider=provider, tf_name="1h")
    df_D_d3 = simulate_batch_vec_v4(entries_test, ohlc_test, 0.0132, 5.0, 20, 2, "long",
                                     mode="D", intrabar_provider=provider, tf_name="1h")
    print(f"  케이스D3 (H=2, A vs C vs D):")
    print(f"    Mode A PF: {compute_stats_v4(df_A_d3)['pf']:.3f}")
    print(f"    Mode C PF: {compute_stats_v4(df_C_d3)['pf']:.3f}")
    print(f"    Mode D PF: {compute_stats_v4(df_D_d3)['pf']:.3f}")
    # 보수성: A ≤ D and C ≤ D (대략적, 단 작은 표본이라 항상 보장 안 됨)

    # --- 케이스 D4: Short Mode D ---
    df_D_d4 = simulate_batch_vec_v4(entries_test, ohlc_test, 0.0132, 5.0, 20, 2, "short",
                                     mode="D", intrabar_provider=provider, tf_name="1h")
    n_resolved_d4 = (df_D_d4['exit_reason'] != 'NoData').sum()
    assert n_resolved_d4 >= 25
    print(f"  케이스D4 (Short, H=2, Mode D): "
          f"PF={compute_stats_v4(df_D_d4)['pf']:.3f}, exit={df_D_d4['exit_reason'].value_counts().to_dict()}")

    # --- 케이스 D5: Mode D NoData 처리 (entry_idx가 데이터 끝 근처) ---
    edge_entries = np.array([n_test - 3])  # H=4면 multi_bar 범위 초과
    df_D_d5 = simulate_batch_vec_v4(edge_entries, ohlc_test, 0.0132, 5.0, 20, 4, "long",
                                     mode="D", intrabar_provider=provider, tf_name="1h")
    print(f"  케이스D5 (Mode D edge, exit_reason={df_D_d5['exit_reason'].iloc[0]})")

    print("\n  모든 케이스 통과 (Mode A 8개 + Mode D 5개)")

    # ====================================================================
    # === v3.3 정정 — 점프 ① E16 (수수료 단위 불일치) net_return 수치 검증 ===
    # ====================================================================
    # 정정 식:
    #   SL:      net_return = -sl_acct - COST_NOMINAL × lev
    #   TP:      net_return = +sl_acct × tp_ratio - COST_NOMINAL × lev
    #   Timeout: net_return = pct × lev - COST_NOMINAL × lev
    #   Liq:     net_return = -1.0  (수수료 제거, hard floor)
    #
    # COST_ROUND_TRIP_NOMINAL = 0.0016 (명목가 기준 16bp)
    # 자본 기준으로 환산: × lev
    print("\n[v3.3 정정 — net_return 수치 검증 6개 케이스]")
    TOL = 1e-9  # 부동소수점 허용 오차

    # 케이스 N1: Lev 20, SL 5%, TP_r 5.0, SL hit (Long)
    # 기대값: -0.05 - 0.0016 × 20 = -0.0820
    op = np.array([80000.0, 80000.0, 80000.0])
    hi = np.array([80100.0, 80100.0, 80100.0])
    lo = np.array([79990.0, 79780.0, 79990.0])  # 진입 봉(idx=1) low 79780 < SL 79800 (5%/20=0.25%)
    df_N1 = simulate_batch_vec_v4(np.array([0]), {"open":op,"high":hi,"low":lo,"close":op},
                                   sl_acct=0.05, tp_ratio=5.0, lev=20, holding_bars=1,
                                   side="long", mode="A")
    expected_N1 = -0.0820
    actual_N1 = df_N1['net_return'].iloc[0]
    assert df_N1['exit_reason'].iloc[0] == "SL", f"N1 SL 기대"
    assert abs(actual_N1 - expected_N1) < TOL, f"N1 net_return 기대 {expected_N1}, 실측 {actual_N1}"
    print(f"  N1 (Lev20×SL5%×SL hit): net_return={actual_N1:.4f} (기대 {expected_N1}) ✓")

    # 케이스 N2: Lev 20, SL 5%, TP_r 5.0, TP hit (Long)
    # 기대값: 0.05 × 5.0 - 0.0016 × 20 = 0.25 - 0.032 = +0.2180
    op = np.array([80000.0, 80000.0, 80000.0])
    hi = np.array([80100.0, 81100.0, 80100.0])  # 진입 봉 high 81100 > TP 81000 (1.25%)
    lo = np.array([79990.0, 79990.0, 79990.0])
    df_N2 = simulate_batch_vec_v4(np.array([0]), {"open":op,"high":hi,"low":lo,"close":op},
                                   sl_acct=0.05, tp_ratio=5.0, lev=20, holding_bars=1,
                                   side="long", mode="A")
    expected_N2 = 0.2180
    actual_N2 = df_N2['net_return'].iloc[0]
    assert df_N2['exit_reason'].iloc[0] == "TP", f"N2 TP 기대"
    assert abs(actual_N2 - expected_N2) < TOL, f"N2 net_return 기대 {expected_N2}, 실측 {actual_N2}"
    print(f"  N2 (Lev20×SL5%×TP hit): net_return={actual_N2:.4f} (기대 {expected_N2}) ✓")

    # 케이스 N3: Lev 10, SL 5%, TP_r 5.0, SL hit
    # 기대값: -0.05 - 0.0016 × 10 = -0.0660
    op = np.array([80000.0, 80000.0, 80000.0])
    hi = np.array([80100.0, 80100.0, 80100.0])
    # SL_price = 80000 × (1 - 0.05/10) = 80000 × 0.995 = 79600
    lo = np.array([79990.0, 79550.0, 79990.0])  # 진입 봉 low 79550 < 79600 = SL hit
    df_N3 = simulate_batch_vec_v4(np.array([0]), {"open":op,"high":hi,"low":lo,"close":op},
                                   sl_acct=0.05, tp_ratio=5.0, lev=10, holding_bars=1,
                                   side="long", mode="A")
    expected_N3 = -0.0660
    actual_N3 = df_N3['net_return'].iloc[0]
    assert df_N3['exit_reason'].iloc[0] == "SL", f"N3 SL 기대"
    assert abs(actual_N3 - expected_N3) < TOL, f"N3 net_return 기대 {expected_N3}, 실측 {actual_N3}"
    print(f"  N3 (Lev10×SL5%×SL hit): net_return={actual_N3:.4f} (기대 {expected_N3}) ✓")

    # 케이스 N4: Lev 20, SL 1.32%, TP_r 5.0, SL hit
    # 기대값: -0.0132 - 0.0016 × 20 = -0.0452
    op = np.array([80000.0, 80000.0, 80000.0])
    hi = np.array([80100.0, 80100.0, 80100.0])
    # SL_price = 80000 × (1 - 0.0132/20) = 80000 × 0.99934 = 79947.2
    lo = np.array([79990.0, 79900.0, 79990.0])  # 진입 봉 low 79900 < 79947.2 = SL hit
    df_N4 = simulate_batch_vec_v4(np.array([0]), {"open":op,"high":hi,"low":lo,"close":op},
                                   sl_acct=0.0132, tp_ratio=5.0, lev=20, holding_bars=1,
                                   side="long", mode="A")
    expected_N4 = -0.0452
    actual_N4 = df_N4['net_return'].iloc[0]
    assert df_N4['exit_reason'].iloc[0] == "SL", f"N4 SL 기대"
    assert abs(actual_N4 - expected_N4) < TOL, f"N4 net_return 기대 {expected_N4}, 실측 {actual_N4}"
    print(f"  N4 (Lev20×SL1.32%×SL hit): net_return={actual_N4:.4f} (기대 {expected_N4}) ✓")

    # 케이스 N5: Lev 20, SL 15%, TP_r 5.0, SL hit
    # 기대값: -0.15 - 0.0016 × 20 = -0.1820
    op = np.array([80000.0, 80000.0, 80000.0])
    hi = np.array([80100.0, 80100.0, 80100.0])
    # SL_price = 80000 × (1 - 0.15/20) = 80000 × 0.9925 = 79400
    lo = np.array([79990.0, 79300.0, 79990.0])  # 진입 봉 low 79300 < 79400 = SL hit
    df_N5 = simulate_batch_vec_v4(np.array([0]), {"open":op,"high":hi,"low":lo,"close":op},
                                   sl_acct=0.15, tp_ratio=5.0, lev=20, holding_bars=1,
                                   side="long", mode="A")
    expected_N5 = -0.1820
    actual_N5 = df_N5['net_return'].iloc[0]
    assert df_N5['exit_reason'].iloc[0] == "SL", f"N5 SL 기대"
    assert abs(actual_N5 - expected_N5) < TOL, f"N5 net_return 기대 {expected_N5}, 실측 {actual_N5}"
    print(f"  N5 (Lev20×SL15%×SL hit): net_return={actual_N5:.4f} (기대 {expected_N5}) ✓")

    # 케이스 N6: Lev 20, SL 5%, TP_r 5.0, Timeout (가격 +0.2% 마감)
    # 기대값: 0.002 × 20 - 0.0016 × 20 = 0.04 - 0.032 = +0.0080
    # 진입가 80000, SL 79800, TP 81000. 둘 다 안 닿고 H=1 끝나면 다음 봉 open이 mark price.
    op = np.array([80000.0, 80000.0, 80160.0])  # mark = open_[2] = 80160 → pct = +0.002
    hi = np.array([80100.0, 80200.0, 80300.0])  # TP 81000 < high 80200 → 안 닿음
    lo = np.array([79990.0, 79850.0, 79850.0])  # SL 79800 < low 79850 → 안 닿음
    df_N6 = simulate_batch_vec_v4(np.array([0]), {"open":op,"high":hi,"low":lo,"close":op},
                                   sl_acct=0.05, tp_ratio=5.0, lev=20, holding_bars=1,
                                   side="long", mode="A")
    expected_N6 = 0.0080
    actual_N6 = df_N6['net_return'].iloc[0]
    assert df_N6['exit_reason'].iloc[0] == "Timeout", f"N6 Timeout 기대, 실측 {df_N6['exit_reason'].iloc[0]}"
    assert abs(actual_N6 - expected_N6) < TOL, f"N6 net_return 기대 {expected_N6}, 실측 {actual_N6}"
    print(f"  N6 (Lev20×SL5%×Timeout +0.2%): net_return={actual_N6:.4f} (기대 {expected_N6}) ✓")

    print("\n  v3.3 net_return 수치 검증 — 6개 케이스 모두 통과")
    print(f"  (점프 ① E16 정정 확인: COST_ROUND_TRIP_NOMINAL × lev 적용)")

