# -*- coding: utf-8 -*-
# [파일명] dauto_loader.py — Dauto 일자별 CSV 공용 로더 (캡틴 지시 2026-06-12: 로더 모듈 1개로 통일)
# 코드길이: 약 30줄 | 내부버전: dauto_loader_v1
# [역할] C:\BinanceData\BTCUSDT_1m_YYYYMMDD.csv 전체를 concat → UTC ts 정렬 → 중복ts 가드.
#        oi_zscore_adapter / atr_ratio_adapter 공용(코드패스 단일화).
import glob
import os
import pandas as pd

DAUTO_DIR = r"C:\BinanceData"
PATTERN = "BTCUSDT_1m_*.csv"


def load_dauto(usecols, data_dir=DAUTO_DIR, pattern=PATTERN, parse_ts=True):
    """usecols: 'ts_utc' 포함 컬럼 리스트. 반환: ts 오름차순·중복제거된 DataFrame."""
    if 'ts_utc' not in usecols:
        usecols = ['ts_utc'] + list(usecols)
    files = sorted(glob.glob(os.path.join(data_dir, pattern)))
    if not files:
        raise FileNotFoundError(f"Dauto CSV 없음: {data_dir}\\{pattern}")
    dd = pd.concat([pd.read_csv(f, usecols=usecols) for f in files])
    if parse_ts:
        dd['ts_utc'] = pd.to_datetime(dd['ts_utc'])
    dd = dd.drop_duplicates('ts_utc').sort_values('ts_utc').reset_index(drop=True)
    return dd
