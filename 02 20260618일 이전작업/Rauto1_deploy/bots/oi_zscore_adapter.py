# -*- coding: utf-8 -*-
# [파일명] oi_zscore_adapter.py — Dauto CSV(open_interest) → oi_zscore_24h 라이브 aux 공급원
# 코드길이: 약 75줄 | 내부버전: dauto_ch2_stg13_adapter_v2 (캡틴 계보결정 ① 반영)
# [수식 — REPAIRED 계보 확정(캡틴 2026-06-12, 분석 202606121121)]
#   oi_zscore_24h = clip( zscore_self_window(x, 1440, min_periods=720, ddof=1).shift(1), ±10 )
#   = '직전 봉의 z(자기 봉 포함 24h 창)'를 현재 행에 부착. Merged_Data.csv(=REPAIRED 05-11)와
#   전수 0불일치·NaN패턴 완전일치로 핀포인트된 수식. 원본 v2(Derived 05-07용)와 다름 —
#   LINEAGE_WARNING_oi_zscore.txt 참조.
# [입력 정책 — 캡틴 확정 2026-06-12 v2]
#   oi_src=live/hist → 값 사용(hist는 5m ffill = 'z 뭉툭화' — oi_blunt=1 플래그 병기)
#   oi_src=na       → NaN 전파(창에 섞이면 z=NaN → 신호봇 무덤필터 통과 관성 유지)
import os
import sys

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
from dauto_loader import load_dauto      # 공용 로더(캡틴 2026-06-12: 모듈 1개로 통일)

REPAIRED_PARAMS = dict(win=1440, ddof=1, minp=720, shift=1, clip=10.0)


def compute_oi_zscore(x, win, ddof, minp, shift, clip=None):
    """x: pd.Series(원시 OI, 제외구간은 NaN). clip=±상한(예 10.0) 또는 None. 반환: z Series."""
    if shift:
        x = x.shift(1)
    mu = x.rolling(win, min_periods=minp).mean()
    sd = x.rolling(win, min_periods=minp).std(ddof=ddof)
    z = (x - mu) / sd
    return z.clip(-clip, clip) if clip is not None else z


def load_dauto_oi(data_dir=None, pattern=None):
    """공용 로더 경유 (ts, oi_use, oi_src) 반환. oi_use = live/hist 값 사용, na만 NaN(캡틴 v2)."""
    kw = {}
    if data_dir is not None:
        kw['data_dir'] = data_dir
    if pattern is not None:
        kw['pattern'] = pattern
    dd = load_dauto(['open_interest', 'oi_src'], **kw)
    oi_use = dd['open_interest'].astype(float).where(dd['oi_src'].isin(['live', 'hist']))
    return dd['ts_utc'], oi_use, dd['oi_src']


def build_aux(params=None, data_dir=None, out_csv=None):
    """market.aux용 (ts_utc, oi_zscore_24h, oi_src, oi_blunt) DataFrame 생성.
    oi_blunt=1: z 계산창(직전 1440행, shift 포함)에 hist(5m ffill) 행이 섞임 — 'z 뭉툭화'."""
    P = dict(REPAIRED_PARAMS)
    if params:
        P.update(params)
    ts, oi_use, src = load_dauto_oi(data_dir)
    z = compute_oi_zscore(oi_use, **P)
    hist_ind = (src == 'hist').astype(float)
    blunt = (hist_ind.shift(1).rolling(P['win'], min_periods=1).max() > 0).astype(int)
    aux = pd.DataFrame({'ts_utc': ts, 'oi_zscore_24h': z.values,
                        'oi_src': src, 'oi_blunt': blunt.values})
    if out_csv:
        aux.to_csv(out_csv, index=False, encoding='utf-8-sig')
    return aux
