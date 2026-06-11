# [파일명] tf_aggregator_v2.py
# 코드길이: 약 110줄, 내부버전명: v2.0 (v3.4_fib), 로직 축약/생략 없이 전체 출력
#
# [목적] tf_aggregator v1 + 2h봉(120m) 지원 추가
#
# [변경 사항]
#  - 지원 TF: 5/15/30/60 → 5/15/30/60/120 (2h 추가)
#  - 1분봉 → 2h봉 변환 가능 (Regime_Master_v2 get_regime_2h 입력용)
#
# [함수 In/Out]
#  aggregate_ohlcv(df_1m, tf_minutes) -> pd.DataFrame
#    IN: 1분봉 df, TF 분 (5/15/30/60/120 중 하나)
#    OUT: 변환된 OHLCV + n_minutes

import pandas as pd
import numpy as np


SUPPORTED_TFS = (5, 15, 30, 60, 120)


def aggregate_ohlcv(df_1m, tf_minutes):
    """
    1분봉을 더 큰 TF로 변환. 2h(120m) 지원 추가.

    IN:
      df_1m: pd.DataFrame. 컬럼 timestamp, open, high, low, close, [volume]
      tf_minutes: int. 5/15/30/60/120
    OUT:
      pd.DataFrame. 같은 컬럼 + n_minutes
    """
    if tf_minutes not in SUPPORTED_TFS:
        raise ValueError(f"tf_minutes={tf_minutes} 미지원. {SUPPORTED_TFS} 사용.")

    df = df_1m.copy()

    if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    elif df["timestamp"].dt.tz is None:
        df["timestamp"] = df["timestamp"].dt.tz_localize("UTC")

    df = df.set_index("timestamp").sort_index()

    # 정합성: 1분 단위 점검
    diffs = df.index.to_series().diff().dt.total_seconds()
    median_diff = diffs.median()
    if median_diff != 60.0:
        print(f"[WARN] median 시간 간격 = {median_diff}초 (1분=60초 기대).")

    rule = f"{tf_minutes}min"
    agg_dict = {"open": "first", "high": "max", "low": "min", "close": "last"}
    if "volume" in df.columns:
        agg_dict["volume"] = "sum"

    resampled = df.resample(rule, label="left", closed="left").agg(agg_dict)
    resampled["n_minutes"] = df.resample(rule, label="left", closed="left").size()
    full_bars = resampled[resampled["n_minutes"] == tf_minutes].copy()

    if len(full_bars) < len(resampled):
        n_dropped = len(resampled) - len(full_bars)
        print(f"[INFO] TF {tf_minutes}m: 불완전 봉 {n_dropped}개 제거. 잔여 {len(full_bars)}봉.")

    full_bars = full_bars.reset_index()
    return full_bars


if __name__ == "__main__":
    # 단위 테스트
    print("[단위 테스트] tf_aggregator_v2.py")
    n_test = 7200  # 5일 분량 — 2h 봉 60개 가능
    timestamps = pd.date_range("2023-05-01 00:00:00", periods=n_test, freq="1min", tz="UTC")
    rng = np.random.default_rng(42)
    closes = 100 + np.cumsum(rng.normal(0, 0.1, n_test))
    df_1m = pd.DataFrame({
        "timestamp": timestamps, "open": closes,
        "high": closes + 0.1, "low": closes - 0.1, "close": closes,
        "volume": rng.uniform(1, 10, n_test),
    })

    for tf in SUPPORTED_TFS:
        result = aggregate_ohlcv(df_1m, tf)
        expected = n_test // tf
        print(f"  TF {tf}m: {len(result)}봉 (기대 ≈ {expected})")
        assert (result["n_minutes"] == tf).all(), f"TF {tf}m 길이 불일치"
        assert len(result) >= expected - 1, f"TF {tf}m 봉 수 부족"

    print("  ✓ 통과")
