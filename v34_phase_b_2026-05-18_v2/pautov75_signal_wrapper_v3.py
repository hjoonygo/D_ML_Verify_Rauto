# [파일명] pautov75_signal_wrapper_v3.py
# 코드길이: 약 250줄, 내부버전명: v3.0 (phase_a), 로직 축약/생략 없이 전체 출력
#
# [목적] v2 + 안 D (Rolling 14일 percentile 변동성 임계 진입 필터)
#
# [v2 → v3 변경 사항]
#   ★ 새 인자: filter_mode ('off' / 'p20_p80' / 'p10_p90')
#   ★ 새 인자: atr_15m_pct_per_1m (1m봉별 15m ATR_pct 사전 계산값)
#   ★ 새 인자: rolling_lookback_minutes (14일 = 20160분)
#   ★ 추가: 진입 신호마다 Rolling 14일 ATR_pct percentile 계산
#   ★ 추가: 필터 통과/거부 카운트 + 거부 사유
#   ★ 출력: stats에 filter_stats 추가
#
# [Rolling Percentile 메커니즘]
#   진입 후보 시점 t에서:
#     window = atr_15m_pct_per_1m[t-20160 : t]   (직전 14일)
#     p_low = np.percentile(window, p_low_value)  (예: 20)
#     p_high = np.percentile(window, p_high_value)  (예: 80)
#     current = atr_15m_pct_per_1m[t]
#     
#   필터 통과 = (current >= p_low) AND (current <= p_high)
#   lookahead 없음: window가 항상 t 이전 데이터만 사용
#
# [사용된 파일]
#   Predict_ML_v2.py — 3-class 추론 (그대로)
#   Regime_Master_v2.py — 장세 판독 (그대로)
#
# [In/Out]
#   compute_atr_15m_pct_per_1m(df_1m) -> np.ndarray
#     IN: df_1m (1m봉 DataFrame)
#     OUT: 1m봉별 15m ATR_pct 배열 (길이=len(df_1m))
#
#   extract_signals_v3(df_1m, threshold_long, threshold_short, window_size,
#                      atr_15m_pct_per_1m, filter_mode, rolling_lookback_minutes,
#                      start_idx, end_idx, verbose_every) 
#     -> (long_indices, short_indices, stats)

import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from Predict_ML_v2 import Predict_ML_v2
from Regime_Master_v2 import Regime_Master_v2

# 필터 모드별 percentile
FILTER_MODES = {
    'off':        (None, None),
    'p20_p80':    (20, 80),
    'p10_p90':    (10, 90),
}

ROLLING_LOOKBACK_MINUTES_DEFAULT = 14 * 1440  # 14일 = 20,160분


def compute_atr_15m_pct_per_1m(df_1m: pd.DataFrame, atr_period: int = 14) -> np.ndarray:
    """
    1m봉 전체에 대해 *15m TF ATR_pct*를 사전 계산.
    
    수식:
      1. 1m봉 → 15m봉 aggregate
      2. 15m ATR(period=14) 계산 (Wilder 3항)
      3. 15m ATR_pct = ATR / close
      4. 각 1m봉 t에 해당하는 15m봉 인덱스 찾아 매핑
      5. 길이=len(df_1m) 배열 반환
    
    IN: df_1m (timestamp idx, OHLC)
    OUT: np.ndarray (길이=len(df_1m), 1m봉별 15m ATR_pct)
    """
    # 15m aggregate
    df_15m = df_1m.resample('15min').agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last',
    }).dropna()
    
    # 15m ATR (Wilder 3항)
    high = df_15m['high'].values
    low = df_15m['low'].values
    close = df_15m['close'].values
    n_15 = len(close)
    
    tr = np.zeros(n_15, dtype=np.float64)
    tr[0] = high[0] - low[0]
    for i in range(1, n_15):
        h_l = high[i] - low[i]
        h_pc = abs(high[i] - close[i-1])
        l_pc = abs(low[i] - close[i-1])
        tr[i] = max(h_l, h_pc, l_pc)
    
    atr = np.full(n_15, np.nan, dtype=np.float64)
    if n_15 >= atr_period:
        atr[atr_period-1] = tr[:atr_period].mean()
        for i in range(atr_period, n_15):
            atr[i] = (atr[i-1] * (atr_period-1) + tr[i]) / atr_period
    
    atr_pct_15m = atr / close  # 가격 대비 비율
    
    # 1m봉 → 15m봉 매핑
    # 1m봉 t의 timestamp → 해당 15m봉의 인덱스
    df_15m_resampled = df_15m.copy()
    df_15m_resampled['atr_pct'] = atr_pct_15m
    
    # 1m봉마다 직전 15m봉의 atr_pct 사용 (lookahead 방지)
    # asof 사용: 1m봉 t 시점에 이미 마감된 15m봉의 ATR
    atr_per_1m = np.full(len(df_1m), 0.004, dtype=np.float64)  # default 0.4%
    
    # 더 정밀한 매핑: 1m index를 floor 15min → asof
    for i, ts_1m in enumerate(df_1m.index):
        # 15m봉의 *이전* 마감 봉 검색 (lookahead 방지)
        # ts_1m이 14:23이면 floor=14:15 → idx_15m이 14:15 봉
        # 단, 14:15 봉은 14:29까지 모든 정보 포함 → 14:15 봉 자체는 14:30에 마감
        # 즉 1m봉 14:23의 ATR을 알려면 14:15 마감(=이전 15m봉) ATR을 봐야
        # 14:15에 해당하는 15m봉 idx는 14:00 봉 (14:00-14:14 마감)
        # 즉 floor((ts_1m - 1m) to 15min)
        ts_lookup = ts_1m - pd.Timedelta(minutes=1)
        loc = df_15m_resampled.index.searchsorted(ts_lookup, side='right') - 1
        if 0 <= loc < n_15:
            v = atr_pct_15m[loc]
            if np.isfinite(v) and v > 0:
                atr_per_1m[i] = v
    
    return atr_per_1m


def extract_signals_v3(
    df_1m: pd.DataFrame,
    atr_15m_pct_per_1m: np.ndarray,
    threshold_long: float = 0.35,
    threshold_short: float = 0.35,
    window_size: int = 120,
    filter_mode: str = 'off',
    rolling_lookback_minutes: int = ROLLING_LOOKBACK_MINUTES_DEFAULT,
    start_idx: int = None,
    end_idx: int = None,
    verbose_every: int = 50000,
):
    """
    v3 — PautoV75 ML + Regime 신호 추출 + Rolling 14일 ATR_pct 필터.

    IN:
      df_1m: 1m DataFrame
      atr_15m_pct_per_1m: 1m봉별 15m ATR_pct (사전 계산)
      threshold_long, threshold_short: ML 임계 (기본 0.35)
      window_size: 호출 윈도우 (기본 120)
      filter_mode: 'off' / 'p20_p80' / 'p10_p90'
      rolling_lookback_minutes: 필터 lookback 기간 (기본 14일)
      start_idx, end_idx: iloc 범위
    OUT:
      long_indices, short_indices, stats
    """
    if filter_mode not in FILTER_MODES:
        raise ValueError(f"filter_mode 부정확: {filter_mode}. 가능: {list(FILTER_MODES.keys())}")
    p_low_val, p_high_val = FILTER_MODES[filter_mode]
    
    predict_inst = Predict_ML_v2()
    regime_inst = Regime_Master_v2()

    if not predict_inst.model_loaded:
        raise FileNotFoundError(
            "3-class 모델 로드 실패. ML_Predictor_Pipeline_v2.py 먼저 실행 필요"
        )

    params = {
        'ml_long_threshold': threshold_long,
        'ml_short_threshold': threshold_short,
    }

    n_bars = len(df_1m)
    if start_idx is None:
        start_idx = max(window_size, rolling_lookback_minutes)  # 필터 lookback 보장
    if end_idx is None:
        end_idx = n_bars

    if start_idx < max(window_size, rolling_lookback_minutes):
        print(f"⚠️ start_idx={start_idx} 너무 작음. 자동 조정")
        start_idx = max(window_size, rolling_lookback_minutes)

    long_list = []
    short_list = []
    n_long_signal = 0
    n_short_signal = 0
    n_regime = {'BULLISH_EXPANSION': 0, 'BEARISH_EXPANSION': 0, 'CHOPPY': 0, 'OTHER': 0}
    n_wait = 0
    n_filter_rejected_low = 0  # 너무 낮은 변동성
    n_filter_rejected_high = 0  # 너무 높은 변동성
    n_filter_passed = 0
    prob_long_sum = 0.0
    prob_short_sum = 0.0

    print(f"[wrapper_v3] 신호 추출 (봉 {start_idx}~{end_idx-1} = {end_idx-start_idx:,}개)")
    print(f"  window_size={window_size}, filter_mode={filter_mode}")

    for t in range(start_idx, end_idx):
        window = df_1m.iloc[t - window_size + 1 : t + 1].copy()

        try:
            regime = regime_inst.get_regime(window)
        except Exception:
            regime = "CHOPPY"
        if regime in n_regime:
            n_regime[regime] += 1
        else:
            n_regime['OTHER'] += 1

        signal = predict_inst.get_signal(window, regime, params)
        action = signal.get('action', 'WAIT')
        prob_long_sum += signal.get('prob_long', 0.0)
        prob_short_sum += signal.get('prob_short', 0.0)

        # ML이 진입 신호를 낸 경우에만 필터 적용
        if action in ('OPEN_LONG', 'OPEN_SHORT'):
            # ★ Rolling 14일 percentile 계산
            if filter_mode != 'off':
                lookback_start = max(0, t - rolling_lookback_minutes)
                lookback_window = atr_15m_pct_per_1m[lookback_start:t]
                # NaN 제거
                clean_window = lookback_window[np.isfinite(lookback_window) & (lookback_window > 0)]
                
                if len(clean_window) < 100:  # 데이터 부족
                    # filter 적용 안함
                    pass
                else:
                    p_low = np.percentile(clean_window, p_low_val)
                    p_high = np.percentile(clean_window, p_high_val)
                    current = atr_15m_pct_per_1m[t]
                    
                    if current < p_low:
                        # 너무 낮은 변동성 - 죽은 시장
                        n_filter_rejected_low += 1
                        action = 'WAIT'
                    elif current > p_high:
                        # 너무 높은 변동성 - 학살 구간
                        n_filter_rejected_high += 1
                        action = 'WAIT'
                    else:
                        n_filter_passed += 1
            else:
                n_filter_passed += 1

        if action == 'OPEN_LONG':
            long_list.append(t)
            n_long_signal += 1
        elif action == 'OPEN_SHORT':
            short_list.append(t)
            n_short_signal += 1
        else:
            n_wait += 1

        if verbose_every > 0 and (t - start_idx + 1) % verbose_every == 0:
            print(f"  진행: {t - start_idx + 1:,}/{end_idx - start_idx:,} "
                  f"(L={n_long_signal} S={n_short_signal} F_rej_lo={n_filter_rejected_low} F_rej_hi={n_filter_rejected_high})")

    long_indices = np.array(long_list, dtype=np.int64)
    short_indices = np.array(short_list, dtype=np.int64)

    n_processed = max(1, end_idx - start_idx)
    stats = {
        'n_total_bars': end_idx - start_idx,
        'n_long_signals': len(long_indices),
        'n_short_signals': len(short_indices),
        'n_wait': n_wait,
        'regime_distribution': n_regime,
        'signal_pct': {
            'long': 100 * len(long_indices) / n_processed,
            'short': 100 * len(short_indices) / n_processed,
        },
        'avg_prob_long': prob_long_sum / n_processed,
        'avg_prob_short': prob_short_sum / n_processed,
        'threshold_long': threshold_long,
        'threshold_short': threshold_short,
        'window_size': window_size,
        # ★ 필터 통계
        'filter_mode': filter_mode,
        'rolling_lookback_minutes': rolling_lookback_minutes,
        'filter_stats': {
            'rejected_low_vol': n_filter_rejected_low,
            'rejected_high_vol': n_filter_rejected_high,
            'passed': n_filter_passed,
            'total_pre_filter_signals': n_filter_rejected_low + n_filter_rejected_high + n_filter_passed,
            'rejection_rate_pct': 100 * (n_filter_rejected_low + n_filter_rejected_high) / max(1, n_filter_rejected_low + n_filter_rejected_high + n_filter_passed),
        }
    }

    print(f"[wrapper_v3] 완료")
    print(f"  Long: {stats['n_long_signals']:,} ({stats['signal_pct']['long']:.3f}%)")
    print(f"  Short: {stats['n_short_signals']:,} ({stats['signal_pct']['short']:.3f}%)")
    print(f"  필터 거부 (저변동): {n_filter_rejected_low}")
    print(f"  필터 거부 (고변동): {n_filter_rejected_high}")
    print(f"  필터 통과: {n_filter_passed}")

    return long_indices, short_indices, stats


if __name__ == "__main__":
    # 단위 테스트
    print("[wrapper_v3 단위 테스트]")
    n = 500
    ts = pd.date_range('2025-05-01', periods=n, freq='1min', tz='UTC')
    rng = np.random.default_rng(42)
    close = 50000 + np.cumsum(rng.normal(0, 30, n))
    df_test = pd.DataFrame({
        'open': np.r_[close[0], close[:-1]],
        'high': close + np.abs(rng.normal(0, 20, n)),
        'low': close - np.abs(rng.normal(0, 20, n)),
        'close': close,
        'volume': np.abs(rng.normal(100, 20, n)),
        'oi_sum': 86000 + np.cumsum(rng.normal(0, 10, n)),
    }, index=ts)

    atr_pct = compute_atr_15m_pct_per_1m(df_test)
    print(f"  ATR_pct shape: {atr_pct.shape}, mean: {np.nanmean(atr_pct):.4%}")
