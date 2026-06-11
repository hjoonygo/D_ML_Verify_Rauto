# [파일명] tf_aggregator.py
# 코드길이: 약 130줄, 내부버전명: v0_2026-05-14, 로직 축약/생략 없이 전체 출력.
#
# === 목적 ===
# 1분봉 OHLCV DataFrame을 5분/15분/30분/1시간봉으로 변환한다.
# TradingView 표준 봉 경계 사용 (UTC 기준).
# Lookahead bias 방지: 각 봉은 *닫힌 후*에만 사용 가능.
#
# === 입력 명세 ===
# - timestamp 컬럼: ISO 문자열 (예: 2023-05-01T00:00:00+00:00) 또는 pandas datetime
# - OHLC 컬럼: open, high, low, close
# - volume 컬럼: volume (선택)
#
# === 출력 명세 ===
# - timestamp: 새 TF 봉의 *시작 시각* (UTC)
# - open: 첫 1분봉 open
# - high: 모든 1분봉 high의 max
# - low: 모든 1분봉 low의 min
# - close: 마지막 1분봉 close
# - volume: 모든 1분봉 volume의 sum
# - n_minutes: 이 봉이 포함한 1분봉 수 (정합성 점검용)
#
# === 함수 In/Out ===
# aggregate_ohlcv(df_1m: pd.DataFrame, tf_minutes: int) -> pd.DataFrame
#   In: 1분봉 DataFrame, 새 TF 분(5/15/30/60)
#   Out: 변환된 DataFrame
#
# === 점프 짚기 ===
# - pandas resample은 봉 경계가 *왼쪽 정렬* (label='left'). 이게 TradingView 표준
# - 시작 봉이 정확히 TF 경계와 정렬되지 않으면 첫 봉이 *부분*. 본 함수는 그 경우 첫 봉 제거
# - 마지막 봉이 완전하지 않으면 (n_minutes < tf_minutes) 마지막 봉도 제거
# ============================================================

import pandas as pd
import numpy as np


def aggregate_ohlcv(df_1m, tf_minutes):
    """
    1분봉을 더 큰 TF로 변환.

    Args:
        df_1m: pd.DataFrame. 컬럼: timestamp, open, high, low, close, [volume].
               timestamp는 datetime64[ns, UTC] 또는 ISO 문자열.
        tf_minutes: int. 5, 15, 30, 60 중 하나.

    Returns:
        pd.DataFrame. 같은 컬럼 + n_minutes (정합성 점검).
    """
    if tf_minutes not in (5, 15, 30, 60):
        raise ValueError(f"tf_minutes={tf_minutes} 미지원. 5/15/30/60 사용.")

    df = df_1m.copy()

    # timestamp를 datetime으로 정규화 (pandas 2.x 호환: dtype은 str/object/datetime 가능)
    if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    elif df["timestamp"].dt.tz is None:
        df["timestamp"] = df["timestamp"].dt.tz_localize("UTC")

    df = df.set_index("timestamp").sort_index()

    # 정합성: 1분 단위 균일성 점검
    diffs = df.index.to_series().diff().dt.total_seconds()
    median_diff = diffs.median()
    if median_diff != 60.0:
        print(
            f"[WARN] median 시간 간격 = {median_diff}초 (1분=60초 기대). "
            f"1분봉 데이터인지 확인 필요."
        )

    # resample: 'left' label = 봉 시작 시각, closed='left' = [t, t+TF) 구간
    rule = f"{tf_minutes}min"
    agg_dict = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
    }
    if "volume" in df.columns:
        agg_dict["volume"] = "sum"

    resampled = df.resample(rule, label="left", closed="left").agg(agg_dict)

    # n_minutes 컬럼 추가
    resampled["n_minutes"] = df.resample(rule, label="left", closed="left").size()

    # 완전 봉만 유지 (n_minutes == tf_minutes)
    full_bars = resampled[resampled["n_minutes"] == tf_minutes].copy()

    if len(full_bars) < len(resampled):
        n_dropped = len(resampled) - len(full_bars)
        print(
            f"[INFO] TF {tf_minutes}m: 불완전 봉 {n_dropped}개 제거 "
            f"(시작/종료 경계 또는 결측). 잔여 {len(full_bars)}봉."
        )

    full_bars = full_bars.reset_index()
    return full_bars


if __name__ == "__main__":
    # 단위 테스트 — 합성 1분봉으로 동작 확인
    print("[단위 테스트] tf_aggregator.py")

    # 100개 1분봉 (2023-05-01 00:00:00부터)
    n_test = 100
    timestamps = pd.date_range(
        "2023-05-01 00:00:00", periods=n_test, freq="1min", tz="UTC"
    )
    rng = np.random.default_rng(42)
    closes = 100 + np.cumsum(rng.normal(0, 0.1, n_test))
    df_1m = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": closes,
            "high": closes + 0.1,
            "low": closes - 0.1,
            "close": closes,
            "volume": rng.uniform(1, 10, n_test),
        }
    )

    for tf in (5, 15, 30, 60):
        result = aggregate_ohlcv(df_1m, tf)
        expected_bars = n_test // tf
        actual_bars = len(result)
        print(
            f"  TF {tf}m: {actual_bars}봉 (기대 ≈ {expected_bars}). "
            f"첫 봉 timestamp = {result['timestamp'].iloc[0]}"
        )
        # 정합성: 모든 봉 n_minutes == tf
        assert (result["n_minutes"] == tf).all(), f"TF {tf}m 봉 길이 불일치"

    print("  통과")
