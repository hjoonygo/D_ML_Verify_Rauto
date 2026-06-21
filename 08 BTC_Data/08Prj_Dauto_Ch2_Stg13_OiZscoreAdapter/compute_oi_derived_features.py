# ==============================================================================
# [파일명] compute_oi_derived_features.py
# [코드길이] 약 530줄 / 내부버전 compute_oi_derived_features_v2
# [모듈 종류] Merged_36mo_With_OI.csv → 8개 OI 파생 피처 산출 (휩소 깊이 분석용)
# ==============================================================================
# [v2 패치 — 2026-05-07]
#   v1 36mo 실데이터 산출 결과로 발견된 데이터 위생 문제 수정:
#     · oi_change_*_pct에서 1,490 inf 발생 (이전 봉 OI=0)
#     · oi_zscore_24h min=-264.9 (정규분포 비정상 outlier)
#     · L/S 비율의 81/47/38건 NaN (Binance 결측)
#
#   v2 핵심 변경 (선장님 본 채팅 결정 = 표준 패치 b):
#     · 패치 1: compute_pct_change — 분모 0/NaN 처리 (NaN 반환)
#     · 패치 2: compute_zscore_rolling — |z| > Z_CLIP_LIMIT 클리핑 (기본 10)
#     · 패치 3: compute_oi_drop_after_spike — inf 입력 안전화
#     · 패치 4: L/S NaN forward fill (한도 30분 = 6봉)
#     · 패치 5: 8 피처별 inf/clip/ffill 카운트 로그 보고
#
#   v2 보존 (변경 없음):
#     · 8 파생 피처 정의 그대로
#     · Lookahead 안전 정책 (rolling().shift(1))
#     · 함수 In/Out signature
# ==============================================================================
#
# [작업 목적]
#   1m봉에 정합된 OI raw 6피처에서 ML 학습용 파생 피처 8개 산출.
#   선장님 의도 "휩소가 얼만큼 깊이로 들어가는지" 정량화 핵심 모듈.
#
# [선장님 결정 (본 채팅)]
#   · Q3 = ㄷ: raw 합본은 별도, 파생은 본 모듈에서 일괄 산출
#   · Q1 (v2 패치) = α: 패치 진행
#   · Q2 (v2 패치 범위) = b: 표준 패치 (inf + clip + ffill)
#   · OI 데이터 = Heatmap 대체 — SL선 근처 유동성 사냥 분석
#
# [파생 피처 8개 (휩소 깊이 분석 핵심)]
#   ┌───────────────────────────────────────────────────────────────────────┐
#   │ #1  oi_change_5m_pct      : 직전 봉 대비 OI 변화율 (%)                │
#   │     의미: OI 급변동 = 청산 또는 대량 진입                              │
#   │                                                                        │
#   │ #2  oi_change_15m_pct     : 3봉 (15분) 전 대비 OI 변화율 (%)          │
#   │     의미: 중기 OI 흐름 (휩소 직후 청산 빈도)                          │
#   │                                                                        │
#   │ #3  oi_change_1h_pct      : 12봉 (1시간) 전 대비 OI 변화율 (%)        │
#   │     의미: 거시적 OI 흐름                                              │
#   │                                                                        │
#   │ #4  oi_zscore_24h         : 24시간 (288봉) 평균 대비 z-score          │
#   │     의미: OI 비정상 검출 (큰손 진입/청산 신호)                        │
#   │                                                                        │
#   │ #5  taker_imbalance_5m_avg: Taker L/S 5봉 (25분) 평균                 │
#   │     의미: 능동적 진입 편향 지속성                                     │
#   │                                                                        │
#   │ #6  top_retail_divergence : 큰손 L/S - 개미 L/S                       │
#   │     의미: smart money 신호 (개미 반대 방향 = 휩소 위험)               │
#   │                                                                        │
#   │ #7  oi_drop_after_spike   : OI 급증 → 급락 패턴 점수 ★ 휩소 직접      │
#   │     산출: 직전 6봉(30분) 안에 OI z>+1.5 도달 후 현재 봉 OI 변화율 < 0 │
#   │     의미: 개미 진입 직후 청산 = 전형적 휩소 직격                      │
#   │                                                                        │
#   │ #8  taker_flip_15m        : 15분 (3봉) 내 Taker 비율 부호 반전 횟수  │
#   │     산출: count(taker_LS>1 → taker_LS<1 또는 역) in 3봉              │
#   │     의미: Taker 매수/매도 빠른 전환 = 휩소 본질 신호                  │
#   └───────────────────────────────────────────────────────────────────────┘
#
# [Lookahead 안전 — 모든 피처]
#   · #1~#3: 과거 봉 차분 (현재 ↔ N봉 전) — 미래 미참조
#   · #4: 24시간 rolling mean/std — 현재 봉 포함 (단, mean/std는 과거 누적)
#         완전 안전을 위해 shift(1) 적용 → 직전 봉까지의 24h 통계 사용
#   · #5: 5봉 rolling mean — shift(1) 적용으로 직전 5봉 평균
#   · #6: 동시점 raw 차이 — 미래 미참조
#   · #7: 직전 6봉 z-score 검사 + 현재 변화율 — 모두 과거+현재만
#   · #8: 직전 3봉 부호 반전 카운트 — 과거만
#
# [📥 IN]
#   --input <path>  : 정합된 1m+OI CSV (기본 ./Merged_36mo_With_OI.csv)
#   --output <path> : 출력 CSV (기본 ./Merged_36mo_With_OI_Derived.csv)
#
# [📤 OUT]
#   <output>.csv : 입력 컬럼 + 8개 파생 피처
#   <output>.log : 산출 통계 + Lookahead 검증 로그
#
# [예상 실행 시간]
#   1.578M봉 산출: 약 30~60초 (rolling 연산 위주)
# ==============================================================================
#
# [상수]
#   · OI_RAW_COLS = ['oi_sum', 'oi_value', 'top_count_ls', 'top_sum_ls',
#                     'count_ls', 'taker_vol_ls']
#   · OI_DERIVED_COLS = 8개 (위 명세)
#   · WINDOW_5M = 1봉 (1m봉)
#   · WINDOW_15M = 15
#   · WINDOW_1H = 60
#   · WINDOW_24H = 1440 (1m봉 기준 24시간)
#   · OI_SPIKE_ZTHR = 1.5 (z-score 임계)
#   · OI_SPIKE_LOOKBACK = 30 (분 = 30봉 = 30분 직전 검사)
#   · TAKER_FLIP_LOOKBACK = 15 (분 = 15봉)
#
# [함수]
#   · setup_logging(output_path) → logger
#   · load_aligned_csv(input_path, logger) → pd.DataFrame
#   · compute_pct_change(series, periods, fill_zero) → pd.Series
#       📥 IN: series, periods (lookback)
#       📤 OUT: pct change Series (NaN if insufficient)
#   · compute_zscore_rolling(series, window) → pd.Series
#       📥 IN: series, window (mean/std lookback)
#       📤 OUT: z-score (shift(1) 적용 — Lookahead-safe)
#   · compute_oi_drop_after_spike(oi_zscore, oi_change_5m, lookback, z_thr) → pd.Series
#       📥 IN: z-score series, change_5m series, lookback bars, z threshold
#       📤 OUT: 0 또는 oi_change_5m 절댓값 (spike 후 drop만 점수)
#   · compute_taker_flip_count(taker_ratio, lookback) → pd.Series
#       📥 IN: taker ratio series, lookback bars
#       📤 OUT: 부호 반전 횟수 in lookback 봉
#   · compute_all_derived_features(df, logger) → pd.DataFrame
#       📥 IN: aligned df (timestamp + OI raw 6 + 1m OHLCV)
#       📤 OUT: df + 8 derived columns
#   · main()
# ==============================================================================

import argparse
import logging
import os
import sys
import time

import numpy as np
import pandas as pd


# ==============================================================================
# 상수
# ==============================================================================
OI_RAW_COLS = ['oi_sum', 'oi_value', 'top_count_ls', 'top_sum_ls',
                'count_ls', 'taker_vol_ls']

OI_DERIVED_COLS = [
    'oi_change_5m_pct',
    'oi_change_15m_pct',
    'oi_change_1h_pct',
    'oi_zscore_24h',
    'taker_imbalance_5m_avg',
    'top_retail_divergence',
    'oi_drop_after_spike',
    'taker_flip_15m',
]

WINDOW_5M = 1     # 1m봉 직전
WINDOW_15M = 15
WINDOW_1H = 60
WINDOW_24H = 1440  # 24시간 (1m봉 기준)

OI_SPIKE_ZTHR = 1.5
OI_SPIKE_LOOKBACK = 30  # 30분 직전 검사
TAKER_FLIP_LOOKBACK = 15  # 15분

# v2 패치 신규 상수
Z_CLIP_LIMIT = 10.0      # |z| 이 값 초과 시 클리핑 (정규분포 양극단)
LS_FFILL_LIMIT = 6       # L/S 비율 NaN forward fill 한도 (6봉 = 30분)
LS_RATIO_COLS = ['top_count_ls', 'top_sum_ls', 'count_ls', 'taker_vol_ls']


# ==============================================================================
# 로깅
# ==============================================================================
def setup_logging(output_path: str):
    log_path = output_path.replace('.csv', '.log')
    logger = logging.getLogger('compute_oi_derived_features')
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
    fh = logging.FileHandler(log_path, mode='w', encoding='utf-8')
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    return logger


# ==============================================================================
# 입력 로드
# ==============================================================================
def load_aligned_csv(input_path: str, logger) -> pd.DataFrame:
    logger.info(f"  로드: {input_path}")
    df = pd.read_csv(input_path)
    logger.info(f"  봉수: {len(df):,}")

    # 컬럼 검증
    missing = [c for c in OI_RAW_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"OI raw 컬럼 누락: {missing}")

    # timestamp 변환
    if 'timestamp' in df.columns:
        df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)

    return df


# ==============================================================================
# 변화율 산출 (★ v2 패치 1 — inf 처리)
# ==============================================================================
def compute_pct_change(series: pd.Series, periods: int) -> pd.Series:
    """
    📥 IN: series (oi_sum 등), periods (lookback bars)
    📤 OUT: pct change (앞 periods 봉 NaN, 분모 0/NaN인 봉도 NaN)

    Lookahead 안전: pandas pct_change(periods)는 (curr - prev_n) / prev_n
                     curr는 현재 봉, prev_n은 N봉 전 — 미래 미참조

    [v2 패치] pandas pct_change()가 분모(prev_n)=0 시 inf 반환.
    inf/-inf를 NaN으로 변환 (학습 시 자연스럽게 제외됨).
    """
    raw = series.pct_change(periods=periods) * 100
    # inf/-inf → NaN 변환
    raw = raw.replace([np.inf, -np.inf], np.nan)
    return raw


# ==============================================================================
# z-score (Lookahead-safe) (★ v2 패치 2 — outlier 클리핑)
# ==============================================================================
def compute_zscore_rolling(series: pd.Series, window: int,
                            clip_limit: float = Z_CLIP_LIMIT,
                            return_clip_count: bool = False):
    """
    📥 IN: series, window, clip_limit (기본 10), return_clip_count
    📤 OUT: z-score Series (또는 (z, n_clipped) tuple if return_clip_count)
            = (curr - mean[t-window-1, t-1]) / std[t-window-1, t-1]
            |z| > clip_limit 면 ±clip_limit로 클리핑

    Lookahead 안전: rolling().mean().shift(1) — 현재 봉 t에서 사용하는
                     mean/std는 [t-window, t-1]까지의 통계 (현재 봉 미포함)

    [v2 패치] outlier 클리핑:
      36mo 실데이터에서 oi_zscore_24h min=-264.9 발견 (정규분포 비정상).
      |z| > 10 (정규분포 양극단)을 ±10으로 클리핑하여 ML 학습 안정화.
      단, NaN은 NaN 유지 (학습 시 자연스럽게 제외).
    """
    rolling_mean = series.rolling(window=window, min_periods=window).mean().shift(1)
    rolling_std = series.rolling(window=window, min_periods=window).std().shift(1)
    # std=0이면 결과 inf — NaN으로 처리
    z_raw = (series - rolling_mean) / rolling_std
    z_raw = z_raw.replace([np.inf, -np.inf], np.nan)

    # 클리핑 카운트 (NaN 제외)
    n_clipped_lo = int(((z_raw < -clip_limit) & z_raw.notna()).sum())
    n_clipped_hi = int(((z_raw > clip_limit) & z_raw.notna()).sum())

    z_clipped = z_raw.clip(lower=-clip_limit, upper=clip_limit)

    if return_clip_count:
        return z_clipped, {'low': n_clipped_lo, 'high': n_clipped_hi}
    return z_clipped


# ==============================================================================
# OI 급증 후 급락 점수
# ==============================================================================
def compute_oi_drop_after_spike(oi_zscore: pd.Series,
                                  oi_change_5m: pd.Series,
                                  lookback: int = OI_SPIKE_LOOKBACK,
                                  z_thr: float = OI_SPIKE_ZTHR) -> pd.Series:
    """
    OI 급증 후 급락 패턴 점수 — 휩소 직접 신호.

    산출 규칙:
      현재 봉 t에서:
        recent_max_z = max(z[t-lookback, t-1])  ← 직전 N봉의 z 최댓값
        if recent_max_z >= z_thr 그리고 oi_change_5m[t] < 0:
            score = abs(oi_change_5m[t])  ← 급락 폭 (양수 점수)
        else:
            score = 0

    Lookahead 안전: 직전 lookback 봉 + 현재 봉의 OI 변화율 — 미래 미참조

    [v2 패치] 입력 inf 안전화 — z-score 또는 change_5m이 inf면 NaN 처리

    📥 IN: oi_zscore (Series), oi_change_5m (Series), lookback, z_thr
    📤 OUT: pd.Series (NaN if insufficient lookback)
    """
    # [v2 패치] 입력 inf/-inf 안전화 (이미 v2 compute_pct_change/zscore에서 NaN으로
    # 변환되지만, 이중 안전을 위해 본 함수에서도 명시 처리)
    oi_zscore_safe = oi_zscore.replace([np.inf, -np.inf], np.nan)
    oi_change_5m_safe = oi_change_5m.replace([np.inf, -np.inf], np.nan)

    # 직전 lookback 봉의 z 최댓값 (현재 봉 미포함)
    recent_max_z = oi_zscore_safe.rolling(window=lookback, min_periods=lookback).max().shift(1)

    spike_recent = (recent_max_z >= z_thr)
    drop_now = (oi_change_5m_safe < 0)

    score = pd.Series(0.0, index=oi_zscore.index)
    mask = spike_recent & drop_now
    score[mask] = oi_change_5m_safe[mask].abs()
    # 입력 둘 다 NaN이면 score도 NaN
    score[recent_max_z.isna() | oi_change_5m_safe.isna()] = np.nan

    return score


# ==============================================================================
# Taker 비율 부호 반전 카운트
# ==============================================================================
def compute_taker_flip_count(taker_ratio: pd.Series,
                              lookback: int = TAKER_FLIP_LOOKBACK) -> pd.Series:
    """
    Taker 비율 1.0 기준 부호 반전 (>1 → <1 또는 역) 횟수 — 휩소 본질 신호.

    산출 규칙:
      현재 봉 t에서:
        직전 lookback 봉의 (taker_ratio > 1) bool 시퀀스
        인접 봉 간 변화 횟수 = 부호 반전 횟수

    Lookahead 안전: 직전 lookback 봉만 검사 — 현재/미래 미참조

    📥 IN: taker_ratio Series, lookback bars
    📤 OUT: pd.Series (NaN if insufficient lookback)
    """
    # bool: > 1 인지
    above = (taker_ratio > 1.0).astype(int)
    # 인접 차분 절댓값 (1이면 부호 반전, 0이면 같음)
    flip = above.diff().abs().fillna(0)
    # rolling sum (현재 봉 포함, 단 현재 봉의 flip은 t-1↔t 변화)
    # 현재 봉 시점에 사용하는 flip[t]는 t-1↔t 차이 → 이미 과거+현재 정보
    # 안전을 위해 shift(1) 적용 → 직전 lookback 봉만의 flip 합
    flip_count = flip.rolling(window=lookback, min_periods=lookback).sum().shift(1)

    return flip_count


# ==============================================================================
# ★ v2 패치 4 — L/S 비율 NaN forward fill
# ==============================================================================
def fill_ls_ratio_nan(df: pd.DataFrame, ls_cols: list = LS_RATIO_COLS,
                       limit: int = LS_FFILL_LIMIT, logger=None) -> tuple:
    """
    L/S 비율 컬럼의 NaN을 직전 봉 값으로 forward fill (한도 limit봉).

    합리성: Binance OI 결측은 짧은 시간 (수 분) 발생. 직전 값 사용이
    가장 합리적. 한도 초과 시 NaN 유지 (학습에서 자연스럽게 제외).

    📥 IN: df, ls_cols, limit (봉수), logger
    📤 OUT: (df_filled, fill_stats: dict)
      fill_stats = {col: {before_nan: int, after_nan: int, filled: int}}
    """
    out = df.copy()
    fill_stats = {}

    for c in ls_cols:
        if c not in out.columns:
            continue
        before_nan = int(out[c].isna().sum())
        out[c] = out[c].ffill(limit=limit)
        after_nan = int(out[c].isna().sum())
        filled = before_nan - after_nan
        fill_stats[c] = {
            'before_nan': before_nan,
            'after_nan': after_nan,
            'filled': filled,
        }
        if logger and before_nan > 0:
            logger.info(f"    {c:<14} ffill: {before_nan:>5} → {after_nan:>5} (채움 {filled:>5}, 한도 초과 {after_nan})")

    return out, fill_stats


# ==============================================================================
# 8개 파생 피처 일괄 산출 (★ v2 — ffill + 클리핑 보고 통합)
# ==============================================================================
def compute_all_derived_features(df: pd.DataFrame, logger) -> pd.DataFrame:
    """
    📥 IN: df (timestamp + OI raw 6 + 1m OHLCV 등)
    📤 OUT: df + 8 derived columns

    [v2 변경]
      · 패치 4: L/S NaN forward fill (top_count_ls/top_sum_ls/count_ls/taker_vol_ls)
      · 패치 5: inf/clip/ffill 카운트 명시 보고
    """
    n = len(df)

    # ===== 패치 4: L/S 비율 NaN ffill (산출 전 데이터 위생) =====
    logger.info(f"  [v2 패치 4] L/S 비율 NaN forward fill (한도 {LS_FFILL_LIMIT}봉 = {LS_FFILL_LIMIT*5}분)")
    out, ffill_stats = fill_ls_ratio_nan(df, LS_RATIO_COLS, LS_FFILL_LIMIT, logger)

    logger.info(f"\n  파생 피처 8개 산출 중...")
    t0 = time.time()

    # 클리핑/inf 카운트 추적용
    inf_counts = {}
    clip_counts = {}

    # ---- #1 oi_change_5m_pct ----
    raw_5m = out['oi_sum'].pct_change(periods=WINDOW_5M) * 100
    inf_counts['oi_change_5m_pct'] = int(np.isinf(raw_5m).sum())
    out['oi_change_5m_pct'] = compute_pct_change(out['oi_sum'], periods=WINDOW_5M)

    # ---- #2 oi_change_15m_pct ----
    raw_15m = out['oi_sum'].pct_change(periods=WINDOW_15M) * 100
    inf_counts['oi_change_15m_pct'] = int(np.isinf(raw_15m).sum())
    out['oi_change_15m_pct'] = compute_pct_change(out['oi_sum'], periods=WINDOW_15M)

    # ---- #3 oi_change_1h_pct ----
    raw_1h = out['oi_sum'].pct_change(periods=WINDOW_1H) * 100
    inf_counts['oi_change_1h_pct'] = int(np.isinf(raw_1h).sum())
    out['oi_change_1h_pct'] = compute_pct_change(out['oi_sum'], periods=WINDOW_1H)

    # ---- #4 oi_zscore_24h (Lookahead-safe + 클리핑) ----
    z_24h, clip_stats = compute_zscore_rolling(
        out['oi_sum'], window=WINDOW_24H,
        clip_limit=Z_CLIP_LIMIT, return_clip_count=True,
    )
    out['oi_zscore_24h'] = z_24h
    clip_counts['oi_zscore_24h'] = clip_stats

    # ---- #5 taker_imbalance_5m_avg (5봉 평균, Lookahead-safe) ----
    out['taker_imbalance_5m_avg'] = (
        out['taker_vol_ls']
        .rolling(window=5, min_periods=5).mean().shift(1)
    )

    # ---- #6 top_retail_divergence (동시점 차이) ----
    out['top_retail_divergence'] = out['top_sum_ls'] - out['count_ls']

    # ---- #7 oi_drop_after_spike ----
    out['oi_drop_after_spike'] = compute_oi_drop_after_spike(
        out['oi_zscore_24h'],
        out['oi_change_5m_pct'],
        lookback=OI_SPIKE_LOOKBACK,
        z_thr=OI_SPIKE_ZTHR,
    )

    # ---- #8 taker_flip_15m ----
    out['taker_flip_15m'] = compute_taker_flip_count(
        out['taker_vol_ls'],
        lookback=TAKER_FLIP_LOOKBACK,
    )

    logger.info(f"  산출 완료 ({time.time()-t0:.1f}s)")

    # ===== 패치 5: 데이터 위생 카운트 보고 =====
    logger.info(f"\n  [v2 패치 5] 데이터 위생 처리 카운트:")
    logger.info(f"  {'피처':<28} {'inf→NaN':>10} {'clip(low)':>10} {'clip(high)':>11}")
    logger.info(f"  " + "-" * 65)
    for c in ['oi_change_5m_pct', 'oi_change_15m_pct', 'oi_change_1h_pct']:
        n_inf = inf_counts.get(c, 0)
        logger.info(f"  {c:<28} {n_inf:>10,} {'—':>10} {'—':>11}")
    cs = clip_counts.get('oi_zscore_24h', {'low': 0, 'high': 0})
    logger.info(f"  {'oi_zscore_24h':<28} {'—':>10} {cs['low']:>10,} {cs['high']:>11,}")

    # ===== 8 피처 통계 보고 =====
    logger.info(f"\n  파생 피처 NaN 비율 + 통계 (v2 — inf 제거됨):")
    logger.info(f"  {'컬럼':<28} {'NaN':>10} {'NaN%':>8} {'mean':>10} {'std':>10} {'min':>10} {'max':>10}")
    logger.info(f"  " + "-" * 95)
    for c in OI_DERIVED_COLS:
        s = out[c]
        n_nan = int(s.isna().sum())
        nan_pct = n_nan / n * 100
        if s.notna().any():
            stats = (s.mean(), s.std(), s.min(), s.max())
        else:
            stats = (np.nan, np.nan, np.nan, np.nan)
        logger.info(
            f"  {c:<28} {n_nan:>10,} {nan_pct:>7.2f}% "
            f"{stats[0]:>10.3f} {stats[1]:>10.3f} {stats[2]:>10.3f} {stats[3]:>10.3f}"
        )

    # 패치 산출 통계 객체에 ffill_stats 추가 (반환은 단일 df 유지, attrs 활용)
    out.attrs['v2_inf_counts'] = inf_counts
    out.attrs['v2_clip_counts'] = clip_counts
    out.attrs['v2_ffill_stats'] = ffill_stats

    return out


# ==============================================================================
# Lookahead 단순 검증 (NaN 패턴)
# ==============================================================================
def verify_lookahead_pattern(out: pd.DataFrame, logger):
    """
    Lookahead 안전성 패턴 검사 (NaN 패턴 기준):
      · oi_change_5m_pct: 첫 1봉 NaN 기대
      · oi_change_15m_pct: 첫 15봉 NaN 기대
      · oi_change_1h_pct: 첫 60봉 NaN 기대
      · oi_zscore_24h: 첫 1440+1봉 NaN 기대 (window+shift)
      · taker_imbalance_5m_avg: 첫 6봉 NaN 기대
      · top_retail_divergence: NaN 패턴 없음 (동시점 차이)
      · oi_drop_after_spike: 첫 1440+30봉 NaN 기대
      · taker_flip_15m: 첫 16봉 NaN 기대
    """
    expected_first_nan = {
        'oi_change_5m_pct': 1,
        'oi_change_15m_pct': WINDOW_15M,
        'oi_change_1h_pct': WINDOW_1H,
        'oi_zscore_24h': WINDOW_24H,
        'taker_imbalance_5m_avg': 5,
        'taker_flip_15m': TAKER_FLIP_LOOKBACK,
    }

    logger.info(f"\n  Lookahead 패턴 검증 (앞부분 NaN 패턴):")
    for c, expected in expected_first_nan.items():
        first_n_isna = out[c].iloc[:expected].isna().all()
        next_isna = out[c].iloc[expected] if len(out) > expected else np.nan
        status = "✓" if first_n_isna else "⚠"
        logger.info(f"    {status} {c:<28} 첫 {expected}봉 NaN 기대 (실제 NaN: {first_n_isna})")


# ==============================================================================
# main
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(
        description='OI raw 6 → 파생 8 피처 (휩소 깊이 분석용)'
    )
    parser.add_argument('--input', type=str, default='./Merged_36mo_With_OI.csv')
    parser.add_argument('--output', type=str, default='./Merged_36mo_With_OI_Derived.csv')
    args = parser.parse_args()

    args.input = os.path.abspath(args.input)
    args.output = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(args.output), exist_ok=True)

    logger = setup_logging(args.output)
    t_start = time.time()

    logger.info("=" * 78)
    logger.info("compute_oi_derived_features v1 — OI 파생 8 피처 산출")
    logger.info("=" * 78)
    logger.info(f"  input:  {args.input}")
    logger.info(f"  output: {args.output}")

    if not os.path.exists(args.input):
        logger.error(f"  입력 CSV 없음: {args.input}")
        return 1

    # 로드
    logger.info(f"\n[1/3] 정합 CSV 로드")
    df = load_aligned_csv(args.input, logger)

    # 산출
    logger.info(f"\n[2/3] 파생 피처 산출")
    out = compute_all_derived_features(df, logger)

    # Lookahead 패턴 검증
    logger.info(f"\n[3/3] Lookahead 패턴 검증")
    verify_lookahead_pattern(out, logger)

    # 저장
    logger.info(f"\n  저장 중: {args.output}")
    t0 = time.time()
    out.to_csv(args.output, index=False)
    logger.info(f"  저장 완료 ({time.time()-t0:.1f}s)")

    logger.info("=" * 78)
    logger.info("[산출 완료]")
    logger.info("=" * 78)
    logger.info(f"  최종 봉수: {len(out):,}")
    logger.info(f"  최종 컬럼 수: {len(out.columns)}")
    logger.info(f"  ✓ 출력: {args.output}")
    logger.info(f"[총 시간] {time.time()-t_start:.1f}s")

    return 0


if __name__ == '__main__':
    sys.exit(main())
