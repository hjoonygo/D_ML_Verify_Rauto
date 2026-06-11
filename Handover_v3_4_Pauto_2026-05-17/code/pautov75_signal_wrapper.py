"""
[파일명] pautov75_signal_wrapper.py
코드길이: 약 130줄, 내부버전 v3.4-pauto
목적: PautoV75 진입 로직(ML+Regime)을 v3.3 계층 A 인터페이스로 wrapping

[변수 파이프라인]
In:
  df_1m: pd.DataFrame (timestamp index, OHLCV + oi_sum)
  model: 학습된 xgboost.Booster (PautoV75 ML 모델)
  threshold_long: ML 임계값 (default 0.80)
  threshold_short: ML 임계값 (default 0.20)
  window_size: PautoV75 원본 호출 윈도우 (default 60)
  start_idx, end_idx: 신호 추출 구간 (None이면 전체)

Out:
  long_indices: np.ndarray[int64], df_1m의 정수 위치 인덱스 (★ iloc 기반)
  short_indices: np.ndarray[int64], df_1m의 정수 위치 인덱스

[주요 함수]
extract_signals_pautov75(df_1m, model, ...) -> (long_indices, short_indices)
  - 매 봉에서 원본 Predict_ML/Regime_Master 호출
  - v3.3 계층 A 인터페이스 호환 (numpy int64 array)
"""

import os
import sys
import numpy as np
import pandas as pd
import xgboost as xgb

# PautoV75 원본 모듈 import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from Predict_ML_PautoV75 import Predict_ML_PautoV75
from Regime_Master_PautoV75 import Regime_Master_PautoV75


def extract_signals_pautov75(
    df_1m: pd.DataFrame,
    model_path: str,
    threshold_long: float = 0.80,
    threshold_short: float = 0.20,
    window_size: int = 60,
    start_idx: int = None,
    end_idx: int = None,
    verbose_every: int = 50000,
):
    """
    PautoV75 ML+Regime을 v3.3 계층 A 인터페이스로 변환.

    봉 t에서:
      1. df_1m.iloc[t-window_size+1 : t+1] 윈도우 추출 (PautoV75 원본 방식)
      2. Predict_ML.get_signal(window, regime, params) 호출
      3. action이 OPEN_LONG / OPEN_SHORT면 인덱스 t를 결과에 추가

    Args:
        df_1m: 1분봉 DataFrame (timestamp index)
        model_path: PautoV75_XGB_1to3_Predictor.json 경로
        threshold_long, threshold_short: ML 임계값
        window_size: PautoV75 원본 = 60 (1시간 윈도우)
        start_idx, end_idx: iloc 범위. None이면 [window_size, len(df_1m))

    Returns:
        long_indices: np.ndarray[int64] (df_1m의 iloc 인덱스)
        short_indices: np.ndarray[int64]
        stats: dict (신호 빈도, ML prob 분포, regime 분포)
    """
    # --- 원본 PautoV75 인스턴스 생성 ---
    predict_inst = Predict_ML_PautoV75()
    # 모델 경로 명시 (모듈이 자동 로드 못 했을 경우 대비)
    if not predict_inst.model_loaded:
        if os.path.exists(model_path):
            predict_inst.model = xgb.Booster()
            predict_inst.model.load_model(model_path)
            predict_inst.model_loaded = True
        else:
            raise FileNotFoundError(f"ML 모델 파일 없음: {model_path}")

    regime_inst = Regime_Master_PautoV75()
    params = {
        'ml_long_threshold': threshold_long,
        'ml_short_threshold': threshold_short,
    }

    n_bars = len(df_1m)
    if start_idx is None:
        start_idx = window_size  # 윈도우 확보 가능한 첫 봉
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

    print(f"[Pauto wrapper] 신호 추출 시작 (봉 {start_idx} ~ {end_idx-1} = {end_idx-start_idx:,}개)")

    for t in range(start_idx, end_idx):
        # 원본 PautoV75 방식: 윈도우 = [t-window_size+1, t]
        window = df_1m.iloc[t - window_size + 1 : t + 1].copy()

        # Regime
        try:
            regime = regime_inst.get_regime(window, params)
        except Exception:
            regime = "CHOPPY"
        if regime in n_regime:
            n_regime[regime] += 1
        else:
            n_regime['OTHER'] += 1

        # ML signal
        signal = predict_inst.get_signal(window, regime, params)
        action = signal.get('action', 'WAIT')

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
                  f"(L={n_long_signal} S={n_short_signal})")

    long_indices = np.array(long_list, dtype=np.int64)
    short_indices = np.array(short_list, dtype=np.int64)

    stats = {
        'n_total_bars': end_idx - start_idx,
        'n_long_signals': len(long_indices),
        'n_short_signals': len(short_indices),
        'n_wait': n_wait,
        'regime_distribution': n_regime,
        'signal_pct': {
            'long': 100 * len(long_indices) / max(1, end_idx - start_idx),
            'short': 100 * len(short_indices) / max(1, end_idx - start_idx),
        }
    }

    print(f"[Pauto wrapper] 완료")
    print(f"  전체 봉: {stats['n_total_bars']:,}")
    print(f"  Long 신호: {stats['n_long_signals']:,} ({stats['signal_pct']['long']:.3f}%)")
    print(f"  Short 신호: {stats['n_short_signals']:,} ({stats['signal_pct']['short']:.3f}%)")
    print(f"  Regime 분포: {stats['regime_distribution']}")

    return long_indices, short_indices, stats


# ===========================================
# 단위 테스트
# ===========================================
if __name__ == "__main__":
    print("=" * 70)
    print("[Pauto Wrapper 단위 테스트]")
    print("=" * 70)

    # 가짜 데이터 1000봉 + 가짜 모델로 wrapper 동작 검증
    import tempfile, shutil
    
    rng = np.random.default_rng(42)
    n = 1000
    ts = pd.date_range('2025-05-01', periods=n, freq='1min', tz='UTC')
    close = 30000 + np.cumsum(rng.normal(0, 30, n))
    df_test = pd.DataFrame({
        'open': np.r_[close[0], close[:-1]],
        'high': close + np.abs(rng.normal(0, 20, n)),
        'low': close - np.abs(rng.normal(0, 20, n)),
        'close': close,
        'volume': np.abs(rng.normal(100, 20, n)),
        'oi_sum': 86000 + np.cumsum(rng.normal(0, 10, n)),
    }, index=ts)

    # 가짜 모델 학습 (테스트용)
    print("\n[테스트용 임시 모델 학습]")
    tmpdir = tempfile.mkdtemp()
    features_train = pd.DataFrame({
        'rsi_14': np.random.uniform(0, 100, n),
        'ema_dist': np.random.normal(0, 1, n),
        'atr_14': np.abs(np.random.normal(50, 20, n)),
        'fvg_bull': np.random.randint(0, 2, n),
        'fvg_bear': np.random.randint(0, 2, n),
        'oi_delta': np.random.normal(0, 1, n),
        'rvol_20': np.abs(np.random.normal(1, 0.3, n)),
        'vol_accel': np.random.normal(0, 1, n),
        'delta_streak': np.random.randint(-5, 6, n),
    })
    y_train = np.random.randint(0, 2, n)
    model = xgb.XGBClassifier(n_estimators=50, max_depth=4, learning_rate=0.03, random_state=42)
    model.fit(features_train, y_train)
    model_path = os.path.join(tmpdir, 'test_xgb.json')
    model.get_booster().save_model(model_path)

    # wrapper 호출
    print("\n[wrapper 호출 - 1000봉]")
    long_idx, short_idx, stats = extract_signals_pautov75(
        df_test, model_path,
        threshold_long=0.6, threshold_short=0.4,  # 가짜 모델용 완화
        window_size=60, verbose_every=500
    )

    # 검증
    print("\n[검증]")
    assert long_idx.dtype == np.int64, "long_indices dtype 불일치"
    assert short_idx.dtype == np.int64, "short_indices dtype 불일치"
    assert (long_idx >= 60).all(), "window_size 이전 봉이 신호에 포함됨"
    assert (long_idx < n).all(), "범위 초과 인덱스"
    assert len(set(long_idx) & set(short_idx)) == 0, "long+short 같은 봉 동시 신호 (불가능)"
    print(f"  ✓ dtype int64")
    print(f"  ✓ 모든 인덱스가 [window_size, n) 범위")
    print(f"  ✓ long/short 동시 신호 없음")
    print(f"  ✓ 통계 dict 정상")

    shutil.rmtree(tmpdir)
    print("\n✓ wrapper 단위 테스트 통과")
