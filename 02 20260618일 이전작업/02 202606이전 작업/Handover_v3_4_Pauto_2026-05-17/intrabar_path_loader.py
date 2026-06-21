# [파일명] intrabar_path_loader.py
# 코드길이: 약 250줄, 내부버전명: v0_2026-05-15, 로직 축약/생략 없이 전체 출력.
#
# === 사용된 파일/함수/변수 In/Out 명세 ===
#
# [목적]
#   안 C (mode C) 측정에서 *진입 봉 안 1분봉 path*를 정확히 재구성한다.
#   tbm_simulator_v4.py의 _simulate_mode_C에서 호출되어 진입 봉 SL/TP/청산 첫 hit 1분봉을 결정.
#
# [핵심 동작]
#   IntrabarPathProvider 클래스가 1분봉 DataFrame을 보유하고
#   bar_idx(TF봉 인덱스)와 tf_name('15m'/'30m'/'1h')을 받아 해당 봉 안의 1분봉 시퀀스를 반환.
#
# [Class API]
#   IntrabarPathProvider(df_1m, tf_aggregated_dict):
#     In:
#       df_1m: 1분봉 DataFrame (timestamp, open, high, low, close 컬럼 필수)
#       tf_aggregated_dict: dict
#         {'15m': df_15m, '30m': df_30m, '1h': df_1h} TF별 aggregated DataFrame
#         각 df는 measure_pf_v2/v3의 aggregate_ohlcv 결과
#         (timestamp 컬럼 — TF봉 시작 시각)
#     Out: 인스턴스. 내부 dict로 (tf_name, bar_idx) → 1분봉 시퀀스 매핑 사전 인덱싱
#
#   get_entry_bar_minutes(bar_idx, tf_name) -> dict or None
#     In:
#       bar_idx: int. TF봉 인덱스 (aggregated DataFrame의 행 인덱스)
#       tf_name: '15m'/'30m'/'1h'
#     Out:
#       dict {'open': 1D np.ndarray, 'high': 1D, 'low': 1D, 'close': 1D, 'timestamps': 1D datetime}
#       1분봉 시퀀스. 길이 = TF봉의 n_minutes (15/30/60).
#       만약 봉이 결측이거나 데이터 부족 시 None 반환 (mode C에서 fallback 처리)
#
# [Lookahead Bias 점검 (작업지침 5번)]
# - 1분봉 path는 *진입 *이후* 시점*의 가격 형성. Look-back, Lookahead 아님
# - 신호 검출은 TF봉 종가까지의 정보만 사용 (cRSI/WAE/DI). 1분봉은 exit 검출용으로만 사용
# - 단위 테스트: assert minutes[0].open == TF봉.open  (시가 정합성)
#                assert minutes[-1].close == TF봉.close (종가 정합성)
#                assert max(minutes.high) == TF봉.high (high 정합성)
#                assert min(minutes.low) == TF봉.low (low 정합성)
#
# [성능 고려]
# - df_1m을 timestamp index로 sort_index() → O(log n) 검색
# - TF봉 timestamp를 시작 시각으로 가짐 → 1분봉 [bar_ts, bar_ts + tf_minutes) 범위 추출
# - 36개월 1.58M 1m봉 → 사전 인덱싱으로 검색 가속 (TF별로 위치 캐싱)
# ============================================================

import numpy as np
import pandas as pd


# TF별 1분봉 개수
TF_MINUTES = {"15m": 15, "30m": 30, "1h": 60}


class IntrabarPathProvider:
    """
    진입 봉의 1분봉 path를 제공하는 클래스.

    Attributes:
        df_1m: 1분봉 DataFrame (timestamp index)
        tf_aggregated_dict: TF별 aggregated DataFrame dict
        _idx_cache: {(tf_name, bar_idx): (start_1m_idx, end_1m_idx)} 위치 캐시
    """

    def __init__(self, df_1m, tf_aggregated_dict):
        """
        Args:
            df_1m: pd.DataFrame. timestamp/open/high/low/close 컬럼 필수.
                   timestamp는 datetime64[ns, UTC] 권장.
            tf_aggregated_dict: dict. 키 = '15m'/'30m'/'1h'. 값 = TF DataFrame.
        """
        # df_1m timestamp 정규화 + sort + index 설정
        df = df_1m.copy()
        if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        elif df["timestamp"].dt.tz is None:
            df["timestamp"] = df["timestamp"].dt.tz_localize("UTC")
        df = df.set_index("timestamp").sort_index()
        self.df_1m = df

        # 1분봉 데이터를 numpy 배열로 미리 추출 (속도)
        self._ts_1m = df.index.values.astype("datetime64[ns]")
        self._open_1m = df["open"].values.astype(np.float64)
        self._high_1m = df["high"].values.astype(np.float64)
        self._low_1m = df["low"].values.astype(np.float64)
        self._close_1m = df["close"].values.astype(np.float64)

        # TF별 aggregated DataFrame 저장 (timestamp 컬럼 사용)
        self.tf_aggregated = {}
        for tf_name, df_tf in tf_aggregated_dict.items():
            df_tf_copy = df_tf.copy()
            if not pd.api.types.is_datetime64_any_dtype(df_tf_copy["timestamp"]):
                df_tf_copy["timestamp"] = pd.to_datetime(df_tf_copy["timestamp"], utc=True)
            elif df_tf_copy["timestamp"].dt.tz is None:
                df_tf_copy["timestamp"] = df_tf_copy["timestamp"].dt.tz_localize("UTC")
            self.tf_aggregated[tf_name] = df_tf_copy.reset_index(drop=True)

        # 위치 캐시 (lazy init)
        self._idx_cache = {}

    def _build_index_cache(self, tf_name):
        """
        TF별 사전 인덱스: TF봉 인덱스 → (start_1m_idx, end_1m_idx)
        searchsorted로 빠른 검색. 처음 호출 시 1회만 구축.
        """
        df_tf = self.tf_aggregated[tf_name]
        tf_min = TF_MINUTES[tf_name]
        n_tf = len(df_tf)

        # TF봉 시작 시각 배열
        bar_starts = df_tf["timestamp"].values.astype("datetime64[ns]")
        bar_ends = bar_starts + np.timedelta64(tf_min, "m")

        # searchsorted로 각 TF봉의 1분봉 범위 결정
        # 1분봉 timestamp[i] ∈ [bar_start, bar_end) → 그 봉에 속함
        start_1m = np.searchsorted(self._ts_1m, bar_starts, side="left")
        end_1m = np.searchsorted(self._ts_1m, bar_ends, side="left")

        self._idx_cache[tf_name] = (start_1m, end_1m)

    def get_entry_bar_minutes(self, bar_idx, tf_name):
        """
        진입 봉의 1분봉 시퀀스 반환.

        Args:
            bar_idx: int. TF봉 인덱스 (tf_aggregated[tf_name] 행 인덱스).
            tf_name: '15m'/'30m'/'1h'.
        Returns:
            dict {'open','high','low','close','timestamps'} 또는 None
        """
        if tf_name not in TF_MINUTES:
            return None
        if tf_name not in self._idx_cache:
            self._build_index_cache(tf_name)

        start_arr, end_arr = self._idx_cache[tf_name]
        if bar_idx < 0 or bar_idx >= len(start_arr):
            return None

        s = int(start_arr[bar_idx])
        e = int(end_arr[bar_idx])
        if e <= s:
            return None

        n = e - s
        expected_n = TF_MINUTES[tf_name]
        # 완전 봉이 아니면 (n != expected_n) → 데이터 결측 가능, None 반환
        if n != expected_n:
            return None

        return {
            "open": self._open_1m[s:e],
            "high": self._high_1m[s:e],
            "low": self._low_1m[s:e],
            "close": self._close_1m[s:e],
            "timestamps": self._ts_1m[s:e],
        }

    def get_multi_bar_minutes(self, start_bar_idx, n_bars, tf_name):
        """
        진입 봉부터 n_bars개 연속 TF봉의 1분봉 시퀀스 반환 (Mode D 전용).

        Args:
            start_bar_idx: int. 시작 TF봉 인덱스 (= 진입 봉 = entry_at)
            n_bars: int. 추출할 TF봉 수 (= holding_bars)
            tf_name: '15m'/'30m'/'1h'

        Returns:
            dict {'open','high','low','close','timestamps','bar_starts'} 또는 None
            - open/high/low/close: 1D np.ndarray. 총 n_bars × TF_MINUTES[tf_name] 길이
            - timestamps: 각 1분봉 시각
            - bar_starts: 각 TF봉 시작에 해당하는 1분봉 *상대* 인덱스 (n_bars+1 길이, 마지막은 전체 길이)
              예: 1h × 2봉 → bar_starts = [0, 60, 120]
                  → bar 0의 1분봉 = [0:60], bar 1의 1분봉 = [60:120]

            연속 봉 중 *하나라도* 결측되면 None 반환 (보수 처리).
        """
        if tf_name not in TF_MINUTES:
            return None
        if tf_name not in self._idx_cache:
            self._build_index_cache(tf_name)

        start_arr, end_arr = self._idx_cache[tf_name]
        n_tf = len(start_arr)

        # 범위 체크
        if start_bar_idx < 0:
            return None
        end_bar_idx = start_bar_idx + n_bars  # exclusive
        if end_bar_idx > n_tf:
            return None  # 데이터 끝 초과

        expected_per_bar = TF_MINUTES[tf_name]

        # 각 봉 길이 검증 + 연속성 검증
        bar_starts = [0]
        cumulative = 0
        for b in range(start_bar_idx, end_bar_idx):
            s = int(start_arr[b])
            e = int(end_arr[b])
            n = e - s
            if n != expected_per_bar:
                return None  # 결측 봉 발견

            # 연속성: 이전 봉의 end와 현재 봉의 start가 같아야 함
            if b > start_bar_idx:
                prev_e = int(end_arr[b - 1])
                if prev_e != s:
                    return None  # 1분봉 시퀀스에 gap

            cumulative += n
            bar_starts.append(cumulative)

        # 전체 슬라이스 (연속 + 결측 없음 확인됨)
        s_total = int(start_arr[start_bar_idx])
        e_total = int(end_arr[end_bar_idx - 1])

        return {
            "open": self._open_1m[s_total:e_total],
            "high": self._high_1m[s_total:e_total],
            "low": self._low_1m[s_total:e_total],
            "close": self._close_1m[s_total:e_total],
            "timestamps": self._ts_1m[s_total:e_total],
            "bar_starts": np.array(bar_starts, dtype=np.int64),
        }


# ============================================================
# 단위 테스트
# ============================================================
if __name__ == "__main__":
    print("[단위 테스트] intrabar_path_loader.py")

    # --- 합성 1분봉 데이터 생성 (60분 × 5봉 1h = 300개 1분봉) ---
    n_1m = 60 * 5  # 5개 1h봉 분량
    ts = pd.date_range("2024-01-01 00:00:00", periods=n_1m, freq="1min", tz="UTC")
    rng = np.random.default_rng(42)
    close = 80000 + np.cumsum(rng.normal(0, 10, n_1m))
    high = close + np.abs(rng.normal(0, 5, n_1m))
    low = close - np.abs(rng.normal(0, 5, n_1m))
    open_ = np.r_[close[0], close[:-1]]
    df_1m = pd.DataFrame({
        "timestamp": ts,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
    })

    # --- 1h aggregated ---
    # Manual aggregate (tf_aggregator.py와 동일 로직)
    df_1m_idx = df_1m.set_index("timestamp")
    df_1h = df_1m_idx.resample("60min", label="left", closed="left").agg({
        "open": "first", "high": "max", "low": "min", "close": "last"
    }).reset_index()
    df_1h["n_minutes"] = df_1m_idx.resample("60min", label="left", closed="left").size().values
    df_1h = df_1h[df_1h["n_minutes"] == 60].reset_index(drop=True)

    # --- 30m aggregated ---
    df_30 = df_1m_idx.resample("30min", label="left", closed="left").agg({
        "open": "first", "high": "max", "low": "min", "close": "last"
    }).reset_index()
    df_30["n_minutes"] = df_1m_idx.resample("30min", label="left", closed="left").size().values
    df_30 = df_30[df_30["n_minutes"] == 30].reset_index(drop=True)

    # --- 15m aggregated ---
    df_15 = df_1m_idx.resample("15min", label="left", closed="left").agg({
        "open": "first", "high": "max", "low": "min", "close": "last"
    }).reset_index()
    df_15["n_minutes"] = df_1m_idx.resample("15min", label="left", closed="left").size().values
    df_15 = df_15[df_15["n_minutes"] == 15].reset_index(drop=True)

    print(f"  1m: {len(df_1m)}개, 15m: {len(df_15)}개, 30m: {len(df_30)}개, 1h: {len(df_1h)}개")

    provider = IntrabarPathProvider(
        df_1m,
        {"15m": df_15, "30m": df_30, "1h": df_1h}
    )

    # --- 케이스 1: 1h 첫 봉의 1분봉 path 검증 ---
    mins = provider.get_entry_bar_minutes(0, "1h")
    assert mins is not None, "케이스1: 1h 첫 봉 path 로드 실패"
    assert len(mins["open"]) == 60, f"케이스1: 1h 60개 1분봉 기대, 실측 {len(mins['open'])}"

    # 시가 정합성: 1분봉 첫 open = TF봉 open
    tf_open = df_1h["open"].iloc[0]
    assert abs(mins["open"][0] - tf_open) < 1e-6, f"케이스1 시가 불일치: {mins['open'][0]} vs {tf_open}"

    # 종가 정합성: 1분봉 마지막 close = TF봉 close
    tf_close = df_1h["close"].iloc[0]
    assert abs(mins["close"][-1] - tf_close) < 1e-6, f"케이스1 종가 불일치"

    # high 정합성: 1분봉 high.max() = TF봉 high
    tf_high = df_1h["high"].iloc[0]
    assert abs(mins["high"].max() - tf_high) < 1e-6, f"케이스1 high 불일치"

    # low 정합성
    tf_low = df_1h["low"].iloc[0]
    assert abs(mins["low"].min() - tf_low) < 1e-6, f"케이스1 low 불일치"

    print(f"  케이스1 (1h 첫 봉 1분봉 path 정합성): 통과")
    print(f"    open={mins['open'][0]:.2f}=tf_open, close={mins['close'][-1]:.2f}=tf_close, max(high)={mins['high'].max():.2f}=tf_high, min(low)={mins['low'].min():.2f}=tf_low")

    # --- 케이스 2: 30m 두번째 봉 ---
    mins_30 = provider.get_entry_bar_minutes(1, "30m")
    assert mins_30 is not None and len(mins_30["open"]) == 30, f"케이스2: 30m 30개 기대"
    tf_open_30 = df_30["open"].iloc[1]
    assert abs(mins_30["open"][0] - tf_open_30) < 1e-6, "케이스2 시가 불일치"
    print(f"  케이스2 (30m bar_idx=1 path): 통과, n_min={len(mins_30['open'])}")

    # --- 케이스 3: 15m 세번째 봉 ---
    mins_15 = provider.get_entry_bar_minutes(2, "15m")
    assert mins_15 is not None and len(mins_15["open"]) == 15
    print(f"  케이스3 (15m bar_idx=2 path): 통과, n_min={len(mins_15['open'])}")

    # --- 케이스 4: 범위 밖 봉 → None ---
    mins_oob = provider.get_entry_bar_minutes(999, "1h")
    assert mins_oob is None, "케이스4: 범위 밖 → None 기대"
    print(f"  케이스4 (범위 밖 → None): 통과")

    # --- 케이스 5: 잘못된 tf_name → None ---
    mins_bad = provider.get_entry_bar_minutes(0, "5m")
    assert mins_bad is None, "케이스5: 잘못된 tf → None 기대"
    print(f"  케이스5 (잘못된 tf_name → None): 통과")

    # --- 케이스 6: 1분봉 결측 (gap) 봉은 None 처리 ---
    df_1m_gap = df_1m.copy()
    df_1m_gap = df_1m_gap.drop(index=30).reset_index(drop=True)  # 30번째 1분봉 누락
    df_1h_gap = df_1h.copy()
    provider_gap = IntrabarPathProvider(df_1m_gap, {"1h": df_1h_gap, "15m": df_15, "30m": df_30})
    # 첫 1h봉은 0~59 분이 필요한데 30번이 빠짐 → 59개만 → None 반환되어야
    mins_gap = provider_gap.get_entry_bar_minutes(0, "1h")
    assert mins_gap is None, f"케이스6: 결측 봉 → None 기대, 실측 {mins_gap}"
    print(f"  케이스6 (1분봉 결측 봉 → None fallback): 통과")

    # --- 케이스 7: 모든 1h봉 로드 가능 여부 (배치 검증) ---
    n_loaded = 0
    n_total = len(df_1h)
    for i in range(n_total):
        m = provider.get_entry_bar_minutes(i, "1h")
        if m is not None:
            n_loaded += 1
    print(f"  케이스7 (전체 1h봉 path 로드율): {n_loaded}/{n_total} = {n_loaded/n_total*100:.1f}%")
    assert n_loaded == n_total, f"전체 1h봉 로드 실패: {n_loaded}/{n_total}"

    # --- 케이스 8: Mode D 다중 봉 추출 (1h × 2봉 = 120 1분봉) ---
    multi = provider.get_multi_bar_minutes(0, 2, "1h")
    assert multi is not None, "케이스8: 1h 2봉 multi 로드 실패"
    assert len(multi["open"]) == 120, f"케이스8: 120 1분봉 기대, 실측 {len(multi['open'])}"
    assert len(multi["bar_starts"]) == 3, "bar_starts 길이 3 기대 (시작 + 봉 사이 + 끝)"
    assert multi["bar_starts"].tolist() == [0, 60, 120], f"bar_starts = {multi['bar_starts']}"
    # 시가 정합성: multi의 첫 1분봉 = df_1h 봉 0의 open
    assert abs(multi["open"][0] - df_1h["open"].iloc[0]) < 1e-6
    # 두 번째 봉 시가 = multi[60] = df_1h 봉 1의 open
    assert abs(multi["open"][60] - df_1h["open"].iloc[1]) < 1e-6
    # high 정합성 — 봉 0의 1분봉 max = df_1h 봉 0의 high
    assert abs(multi["high"][0:60].max() - df_1h["high"].iloc[0]) < 1e-6
    assert abs(multi["high"][60:120].max() - df_1h["high"].iloc[1]) < 1e-6
    print(f"  케이스8 (Mode D 1h × 2봉 = 120 1분봉): 통과")

    # --- 케이스 9: Mode D 30m × 4봉 = 120 1분봉 ---
    multi30 = provider.get_multi_bar_minutes(0, 4, "30m")
    assert multi30 is not None
    assert len(multi30["open"]) == 120
    assert multi30["bar_starts"].tolist() == [0, 30, 60, 90, 120]
    print(f"  케이스9 (Mode D 30m × 4봉 = 120 1분봉): 통과")

    # --- 케이스 10: Mode D 범위 밖 → None ---
    multi_oob = provider.get_multi_bar_minutes(len(df_1h) - 1, 5, "1h")  # 마지막 봉부터 5봉 = 범위 초과
    assert multi_oob is None, "케이스10: 범위 밖 → None 기대"
    print(f"  케이스10 (Mode D 범위 밖 → None): 통과")

    # --- 케이스 11: Mode D 1분봉 결측 시 None fallback ---
    df_1m_gap = df_1m.copy().drop(index=80).reset_index(drop=True)  # 80번째 1분봉 누락 (1h봉 1에 속함)
    provider_gap = IntrabarPathProvider(df_1m_gap, {"1h": df_1h, "15m": df_15, "30m": df_30})
    multi_gap_0 = provider_gap.get_multi_bar_minutes(0, 2, "1h")  # 봉 0~1, 봉 1에 결측
    assert multi_gap_0 is None, "케이스11: 1봉 결측 → None 기대"
    multi_gap_2 = provider_gap.get_multi_bar_minutes(2, 2, "1h")  # 봉 2~3, 결측 없음
    assert multi_gap_2 is not None, "케이스11: 결측 없는 범위 → 정상 기대"
    print(f"  케이스11 (Mode D 1분봉 결측 → None fallback): 통과")

    print("\n  모든 케이스 통과")

