# [파일명] pautov75_signal_wrapper_v2.py
# 코드길이: 약 165줄, 내부버전명: v2.0 (v3.4_fib), 로직 축약/생략 없이 전체 출력
#
# [목적] PautoV75 진입 로직 v2를 v3.3 계층 A 인터페이스로 wrapping
#
# [변경 사항 vs v1]
#  - Predict_ML_v2 + Regime_Master_v2 사용 (3-class + window 120)
#  - 임계값 prob_long ≥ 0.35 / prob_short ≥ 0.35
#  - window_size = 120 (S1 버그 정정)
#
# [In/Out]
#  extract_signals_v2(df_1m, model_path, threshold_long, threshold_short, window_size, ...)
#    -> (long_indices, short_indices, stats)

import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from Predict_ML_v2 import Predict_ML_v2
from Regime_Master_v2 import Regime_Master_v2


def extract_signals_v2(
    df_1m: pd.DataFrame,
    threshold_long: float = 0.35,
    threshold_short: float = 0.35,
    window_size: int = 120,
    start_idx: int = None,
    end_idx: int = None,
    verbose_every: int = 50000,
):
    """
    PautoV75 v2 (3-class) ML+Regime을 v3.3 계층 A 인터페이스로 변환.

    IN:
      df_1m: 1m DataFrame (timestamp idx, OHLCV + oi_*)
      threshold_long, threshold_short: 임계 (기본 0.35)
      window_size: 호출 윈도우 (기본 120 — S1 버그 정정)
      start_idx, end_idx: iloc 범위
    OUT:
      long_indices, short_indices, stats
    """
    predict_inst = Predict_ML_v2()
    regime_inst = Regime_Master_v2()

    if not predict_inst.model_loaded:
        raise FileNotFoundError(
            f"3-class 모델 로드 실패. ML_Predictor_Pipeline_v2.py 먼저 실행 필요"
        )

    params = {
        'ml_long_threshold': threshold_long,
        'ml_short_threshold': threshold_short,
    }

    n_bars = len(df_1m)
    if start_idx is None:
        start_idx = window_size
    if end_idx is None:
        end_idx = n_bars

    if start_idx < window_size:
        print(f"⚠️ start_idx={start_idx} < window_size={window_size}. 자동 조정")
        start_idx = window_size

    long_list = []
    short_list = []
    n_long_signal = 0
    n_short_signal = 0
    n_regime = {'BULLISH_EXPANSION': 0, 'BEARISH_EXPANSION': 0, 'CHOPPY': 0, 'OTHER': 0}
    n_wait = 0
    prob_long_sum = 0.0
    prob_short_sum = 0.0

    print(f"[wrapper_v2] 신호 추출 (봉 {start_idx}~{end_idx-1} = {end_idx-start_idx:,}개, window={window_size})")

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

        if action == 'OPEN_LONG':
            long_list.append(t)
            n_long_signal += 1
        elif action == 'OPEN_SHORT':
            short_list.append(t)
            n_short_signal += 1
        else:
            n_wait += 1

        if verbose_every > 0 and (t - start_idx + 1) % verbose_every == 0:
            print(f"  진행: {t - start_idx + 1:,}/{end_idx - start_idx:,} (L={n_long_signal} S={n_short_signal})")

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
    }

    print(f"[wrapper_v2] 완료")
    print(f"  Long 신호: {stats['n_long_signals']:,} ({stats['signal_pct']['long']:.3f}%)")
    print(f"  Short 신호: {stats['n_short_signals']:,} ({stats['signal_pct']['short']:.3f}%)")
    print(f"  평균 prob_long: {stats['avg_prob_long']:.4f}")
    print(f"  평균 prob_short: {stats['avg_prob_short']:.4f}")
    print(f"  Regime 분포: {stats['regime_distribution']}")

    return long_indices, short_indices, stats


if __name__ == "__main__":
    # 단위 테스트
    print("[wrapper_v2 단위 테스트]")
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

    long_idx, short_idx, stats = extract_signals_v2(
        df_test, threshold_long=0.35, threshold_short=0.35,
        window_size=120, verbose_every=200
    )
    print(f"  ✓ long {len(long_idx)} / short {len(short_idx)} 추출")
    print(f"  ✓ avg prob_long {stats['avg_prob_long']:.3f}, prob_short {stats['avg_prob_short']:.3f}")
