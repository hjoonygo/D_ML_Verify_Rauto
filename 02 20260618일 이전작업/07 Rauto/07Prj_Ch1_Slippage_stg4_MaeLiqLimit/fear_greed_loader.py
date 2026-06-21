# -*- coding: utf-8 -*-
# [파일명] fear_greed_loader.py
# 코드길이: 약 90줄 | 내부버전: fng_loader_v1 | 로직 전체 출력(축약/생략 없음)
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일] 공포탐욕지수(FNG) 파일을 '어떤 형식이든' 읽어, 7시간봉 각각에
#   '전날(D-1) 확정 FNG값'을 매핑한 배열로 돌려준다. ★전날값 사용 = 미래참조 차단.
#   지원 형식: ①JSON껍데기+CSV본문+DD-MM-YYYY(+\r)  ②순수 timestamp,value,... CSV  ③JSON
# [In] path(FNG파일), tf_index(7h봉 DatetimeIndex)
# [Out] (fng_arr: 각 7h봉의 전날 FNG값 float배열, NaN=데이터없는 봉) , (covered: 커버한 봉 비율)
# [사용함수] _parse_any / map_to_bars
# ==============================================================================
import os, re, json
import numpy as np, pandas as pd


def _parse_any(path):
    # 어떤 형식이든 (date_or_ts, value) 시계열로 파싱해 일자별 FNG의 pandas Series(index=날짜) 반환
    txt = open(path, encoding="utf-8", errors="replace").read()
    recs = []  # (datetime, value)

    # 시도1: DD-MM-YYYY,값,분류  본문 라인 (JSON껍데기 섞여도 라인단위로 골라냄)
    for ln in txt.splitlines():
        ln = ln.replace("\r", "").replace("\t", "").strip()
        m = re.match(r'^(\d{2})-(\d{2})-(\d{4}),(\d+),', ln)
        if m:
            dd, mm, yy, val = m.group(1), m.group(2), m.group(3), m.group(4)
            recs.append((pd.Timestamp(f"{yy}-{mm}-{dd}"), int(val)))
    if recs:
        s = pd.Series({d: v for d, v in recs}).sort_index()
        return s

    # 시도2: 순수 CSV (timestamp,value,...) — 유닉스초
    try:
        df = pd.read_csv(path, comment="#")
        df.columns = [c.strip() for c in df.columns]
        if "timestamp" in df.columns and "value" in df.columns:
            ts = df["timestamp"].astype(int)
            dt = pd.to_datetime(ts, unit="s").dt.normalize()
            s = pd.Series(df["value"].astype(int).values, index=dt).sort_index()
            s = s[~s.index.duplicated(keep="last")]
            return s
    except Exception:
        pass

    # 시도3: JSON ({"data":[{value,timestamp},...]})
    try:
        j = json.loads(txt)
        data = j["data"] if isinstance(j, dict) else j
        recs = [(pd.to_datetime(int(e["timestamp"]), unit="s").normalize(), int(e["value"])) for e in data]
        s = pd.Series({d: v for d, v in recs}).sort_index()
        return s
    except Exception:
        pass

    return pd.Series(dtype=float)


def map_to_bars(path, tf_index):
    # 7h봉 각각에 '그 봉 날짜의 전날(D-1)' FNG값을 매핑. 전날값 = 진입시점에 이미 확정(미래참조X).
    s = _parse_any(path)
    if len(s) == 0:
        return np.full(len(tf_index), np.nan), 0.0
    # 일자 인덱스로 정규화, 하루씩 미뤄 '전날값'을 그날에 배정
    s = s.sort_index()
    s_shift = s.copy()
    s_shift.index = s_shift.index + pd.Timedelta(days=1)   # D의 값을 D+1에 배정 = D+1봉은 D값(전날) 사용
    # 7h봉 날짜
    bar_dates = pd.DatetimeIndex(tf_index).normalize()
    # 각 봉 날짜에 해당하는 전날기준 FNG (없으면 직전 유효값으로 ffill — 주말·결측 대비, 단 미래 안씀)
    daily = s_shift.reindex(pd.date_range(s_shift.index.min(), max(s_shift.index.max(), bar_dates.max()), freq="D")).ffill()
    fng_arr = daily.reindex(bar_dates).values.astype("float64")
    covered = float(np.mean(np.isfinite(fng_arr)))
    return fng_arr, covered


if __name__ == "__main__":
    # 단독 점검용
    import sys
    p = sys.argv[1] if len(sys.argv) > 1 else "../Fear_Greed_Index_4Years.csv"
    s = _parse_any(p)
    print(f"파싱 {len(s)}일 | {s.index.min().date()} ~ {s.index.max().date()} | 값 {s.min()}~{s.max()}")
