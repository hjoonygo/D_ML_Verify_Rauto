"""
[파일명] stage1_signal_wrapper.py
코드길이: 약 280줄, 내부버전 v3.4-stage1
목적: Stage 1 정정 4건 동시 적용한 신호 추출
       S1 (window 60→100) + ⓟ-6 (3-class) + ⓟ-11 (look-ahead 정정 모델) + ⓟ-12 (ATR 3항)

[변경 핵심]
1. window_size=100 (Regime_Master len<100 가드 통과)
2. ML 모델 = 3-class multi:softprob (predict_proba → [stay, long, short])
3. 진입 임계: long_prob ≥ 0.50 OR short_prob ≥ 0.50 (교차 임계)
4. Predict_ML 모듈 통째 임포트 안 함 — 본인이 직접 feature 계산 (ATR 3항 정확히)
5. Regime은 Regime_Master 그대로 사용 (window 100 = 가드 통과)
6. TF aggregate: 15m/1h를 1m에서 직접 계산

[변수 파이프라인]
In:
  df_1m: 1m OHLCV+oi_sum DataFrame
  model_path: PautoV75_XGB_3class_v3.json
  tf_minutes: 15 또는 60 (Stage 1 두 TF)
  threshold_long, threshold_short: 둘 다 0.50
  window_size: 100 (★ Regime 가드 통과)

Out:
  long_indices, short_indices: 1m 봉 인덱스 (단 신호는 TF봉 마감 시점에 발생)
  stats: 빈도 + regime 분포
"""

import os
import sys
import numpy as np
import pandas as pd
import xgboost as xgb

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from Regime_Master_PautoV75 import Regime_Master_PautoV75


def aggregate_to_tf(df_1m: pd.DataFrame, tf_minutes: int) -> pd.DataFrame:
    """1m → tf_minutes 봉 aggregate. OHLCV + oi_sum 모두 포함."""
    # 1m 인덱스가 timestamp tz-aware라 가정
    rule = f'{tf_minutes}min'
    agg = df_1m.resample(rule, label='right', closed='right').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum',
    })
    # oi_sum은 봉 마지막 값
    if 'oi_sum' in df_1m.columns:
        agg['oi_sum'] = df_1m['oi_sum'].resample(rule, label='right', closed='right').last()
    agg = agg.dropna()
    return agg


def calculate_features_3term(closed_df: pd.DataFrame) -> dict:
    """
    [v7.7 정정 ⓟ-12] 학습 모듈과 *정확히 동일한* feature 계산.
    학습-추론 정합성 보장.
    
    closed_df: 마감 봉만 (Predict_ML 원본은 iloc[:-1] 사용)
    Returns: dict (9 feature) 또는 None (NaN 발생 시)
    """
    # RSI 14
    delta = closed_df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rsi_series = 100 - (100 / (1 + gain / (loss + 1e-12)))
    
    # EMA dist
    ema_20 = closed_df['close'].ewm(span=20, adjust=False).mean()
    ema_50 = closed_df['close'].ewm(span=50, adjust=False).mean()
    ema_dist_series = (ema_20 - ema_50) / ema_50 * 100
    
    # ATR 14 (★ 3항)
    high_low = closed_df['high'] - closed_df['low']
    high_close = np.abs(closed_df['high'] - closed_df['close'].shift())
    low_close = np.abs(closed_df['low'] - closed_df['close'].shift())
    true_range = np.max(pd.concat([high_low, high_close, low_close], axis=1), axis=1)
    atr_series = true_range.rolling(14).mean()
    
    # FVG
    fvg_bull = (closed_df['low'] > closed_df['high'].shift(2)).astype(int)
    fvg_bear = (closed_df['high'] < closed_df['low'].shift(2)).astype(int)
    
    # OI delta (oi_sum 우선)
    if 'open_interest' in closed_df.columns:
        oi_col = 'open_interest'
    elif 'oi_sum' in closed_df.columns:
        oi_col = 'oi_sum'
    elif 'oi_value' in closed_df.columns:
        oi_col = 'oi_value'
    else:
        oi_col = None
    
    if oi_col:
        oi_delta_series = closed_df[oi_col].pct_change(periods=3).fillna(0) * 100
    else:
        oi_delta_series = pd.Series(0.0, index=closed_df.index)
    
    # RVOL + vol accel
    rvol_series = closed_df['volume'] / (closed_df['volume'].rolling(window=20).mean() + 1e-8)
    vol_accel_series = closed_df['volume'].pct_change().fillna(0).replace([np.inf, -np.inf], 0)
    
    # Delta streak
    buy_pressure = (closed_df['close'] - closed_df['low']) / (closed_df['high'] - closed_df['low'] + 1e-8)
    order_delta = closed_df['volume'] * (buy_pressure * 2 - 1)
    delta_sign = np.sign(order_delta)
    delta_streak_series = delta_sign.groupby((delta_sign != delta_sign.shift()).cumsum()).cumsum()
    
    # 마지막 봉의 feature
    features = {
        'rsi_14': rsi_series.iloc[-1],
        'ema_dist': ema_dist_series.iloc[-1],
        'atr_14': atr_series.iloc[-1],
        'fvg_bull': fvg_bull.iloc[-1],
        'fvg_bear': fvg_bear.iloc[-1],
        'oi_delta': oi_delta_series.iloc[-1],
        'rvol_20': rvol_series.iloc[-1],
        'vol_accel': vol_accel_series.iloc[-1],
        'delta_streak': delta_streak_series.iloc[-1],
    }
    
    # NaN 체크
    if pd.isna(list(features.values())).any():
        return None
    return features


FEATURE_ORDER = ['rsi_14', 'ema_dist', 'atr_14', 'fvg_bull', 'fvg_bear',
                 'oi_delta', 'rvol_20', 'vol_accel', 'delta_streak']


def extract_signals_stage1(
    df_1m: pd.DataFrame,
    model_path: str,
    tf_minutes: int = 15,
    threshold_long: float = 0.50,
    threshold_short: float = 0.50,
    window_size: int = 100,
    verbose_every: int = 5000,
):
    """
    Stage 1 신호 추출. 1m → TF aggregate → 봉별 추론 → 신호 TF봉 인덱스로 변환 후 
    1m 인덱스로 매핑 (TF봉 마감 시점의 *다음 1m 봉*에 진입)
    
    Returns:
        long_indices_1m: np.ndarray[int64] (1m 봉 iloc)
        short_indices_1m: np.ndarray[int64]
        stats: dict
    """
    # 모델 로드 (3-class)
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"모델 없음: {model_path}")
    model = xgb.XGBClassifier()
    model.load_model(model_path)
    
    # TF aggregate
    print(f"[Stage 1 wrapper] TF {tf_minutes}m aggregate...")
    df_tf = aggregate_to_tf(df_1m, tf_minutes)
    n_tf = len(df_tf)
    print(f"  1m: {len(df_1m):,}봉 → {tf_minutes}m: {n_tf:,}봉")
    
    # Regime 인스턴스
    regime_inst = Regime_Master_PautoV75()
    params = {
        'ml_long_threshold': threshold_long,
        'ml_short_threshold': threshold_short,
    }
    
    long_tf = []
    short_tf = []
    n_long = 0
    n_short = 0
    n_wait = 0
    n_regime = {'BULLISH_EXPANSION': 0, 'BEARISH_EXPANSION': 0, 'CHOPPY': 0, 'OTHER': 0}
    
    print(f"[Stage 1 wrapper] 신호 추출 (TF봉 {window_size} ~ {n_tf - 1}, window_size={window_size})")
    
    # TF봉 인덱스 t에서 윈도우 = [t-window+1, t]
    # closed_df = window.iloc[:-1] (Predict_ML 원본 방식, 마감봉만)
    for t in range(window_size, n_tf):
        window = df_tf.iloc[t - window_size + 1 : t + 1].copy()
        
        # Regime (window 100봉 → len(df)>=100 → 가드 통과)
        try:
            regime = regime_inst.get_regime(window, params)
        except Exception:
            regime = "CHOPPY"
        if regime in n_regime:
            n_regime[regime] += 1
        else:
            n_regime['OTHER'] += 1
        
        # Feature 계산 (closed_df = iloc[:-1] 원본 방식)
        closed_df = window.iloc[:-1]
        feats = calculate_features_3term(closed_df)
        if feats is None:
            n_wait += 1
            continue
        
        # ML 추론 (3-class predict_proba)
        feat_array = np.array([[feats[k] for k in FEATURE_ORDER]])
        prob_array = model.predict_proba(feat_array)[0]
        # [stay_prob, long_prob, short_prob]
        long_prob = prob_array[1]
        short_prob = prob_array[2]
        
        # 진입 판단 — 교차 임계 (둘 다 ≥ 0.50)
        # Regime 필터 — PautoV75 원본 그대로
        if long_prob >= threshold_long and regime in ["BULLISH_EXPANSION", "CHOPPY"]:
            long_tf.append(t)
            n_long += 1
        elif short_prob >= threshold_short and regime in ["BEARISH_EXPANSION", "CHOPPY"]:
            short_tf.append(t)
            n_short += 1
        else:
            n_wait += 1
        
        if verbose_every > 0 and (t - window_size + 1) % verbose_every == 0:
            print(f"  진행 {t - window_size + 1:,}/{n_tf - window_size:,} (L={n_long} S={n_short})")
    
    # TF봉 인덱스 → 1m 봉 인덱스 변환
    # TF봉 t의 마감 시점 = df_tf.index[t]. 진입은 *다음 1m 봉*
    long_indices_1m = []
    short_indices_1m = []
    
    df_1m_idx_array = df_1m.index.values
    for t_tf in long_tf:
        tf_close_ts = df_tf.index[t_tf]
        # 다음 1m 봉 찾기 (tf_close_ts 다음 첫 봉)
        next_1m_pos = df_1m.index.searchsorted(tf_close_ts, side='right')
        if next_1m_pos < len(df_1m):
            long_indices_1m.append(next_1m_pos)
    for t_tf in short_tf:
        tf_close_ts = df_tf.index[t_tf]
        next_1m_pos = df_1m.index.searchsorted(tf_close_ts, side='right')
        if next_1m_pos < len(df_1m):
            short_indices_1m.append(next_1m_pos)
    
    long_indices_1m = np.array(long_indices_1m, dtype=np.int64)
    short_indices_1m = np.array(short_indices_1m, dtype=np.int64)
    
    stats = {
        'tf_minutes': tf_minutes,
        'window_size': window_size,
        'n_tf_bars': n_tf - window_size,
        'n_long_signals': len(long_indices_1m),
        'n_short_signals': len(short_indices_1m),
        'n_wait': n_wait,
        'regime_distribution': n_regime,
        'signal_pct': {
            'long': 100 * n_long / max(1, n_tf - window_size),
            'short': 100 * n_short / max(1, n_tf - window_size),
        }
    }
    
    print(f"\n[Stage 1 wrapper] 완료 (TF {tf_minutes}m)")
    print(f"  TF봉: {stats['n_tf_bars']:,}")
    print(f"  Long: {stats['n_long_signals']:,} ({stats['signal_pct']['long']:.2f}%)")
    print(f"  Short: {stats['n_short_signals']:,} ({stats['signal_pct']['short']:.2f}%)")
    print(f"  Regime 분포: {stats['regime_distribution']}")
    
    return long_indices_1m, short_indices_1m, stats
