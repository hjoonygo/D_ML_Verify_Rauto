# -*- coding: utf-8 -*-
# [파일명] po3_common.py
# 코드길이: 약 80줄 | 내부버전: po3_common_v1
# [목적] M1(POC자석)/M2(스윕반전) 측정의 공통 유틸만 모음. H1/H2 측정 로직은
#        각 measure_*.py 에 분리(지시문 원칙4: 한 스크립트 한 로직).
# [함수 In/Out]
#   find_data()        -> str  : Merged_Data_with_Regime_Features.csv 경로 자동탐색
#   load_1m(path=None) -> DataFrame : ts(UTC) + ohlcv + 레짐라벨6 + year
#   atr_1m(df, n=14)   -> np.ndarray : 1분봉 Wilder ATR(인과적·과거 close만)
# [비용] COST_ONEWAY = 0.0007 (수수료 0.05% + 슬립 0.02%)  편도
# [lookahead] 이 파일에 shift(-)·미래 인덱싱 없음. atr는 ewm(adjust=False)=인과적.
import os, sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd

COST_ONEWAY = 0.0007
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(os.path.dirname(HERE), "00WorkHstr")   # 산출물 = 본진\00WorkHstr
REGIME_COLS = ["label_smc_5", "label_smc_8", "label_smc_12",
               "feat_struct_5", "feat_struct_8", "feat_struct_12"]


def find_data():
    name = "Merged_Data_with_Regime_Features.csv"
    for d in [os.path.dirname(HERE), HERE, r"D:\ML\verify"]:
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    raise FileNotFoundError(f"{name} 못 찾음 (상위 D:\\ML\\verify 확인)")


def load_1m(path=None, nrows=None):
    p = path or find_data()
    usecols = ["timestamp", "open", "high", "low", "close", "volume"] + REGIME_COLS
    df = pd.read_csv(p, encoding="utf-8-sig", usecols=usecols, nrows=nrows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    df["year"] = df["timestamp"].dt.year.astype("int32")
    # 레짐 라벨 결측(예열 240행)은 'na' 문자열로 — 측정에서 표본부족 셀로 식별됨
    for c in REGIME_COLS:
        df[c] = df[c].astype("object").where(df[c].notna(), "na")
    return df


def atr_1m(df, n=14):
    """1분봉 Wilder ATR. TR = max(h-l, |h-pc|, |l-pc|), pc=직전 close(과거만)."""
    h = df["high"].to_numpy(float)
    l = df["low"].to_numpy(float)
    c = df["close"].to_numpy(float)
    pc = np.empty_like(c)
    pc[0] = c[0]
    pc[1:] = c[:-1]
    tr = np.maximum.reduce([h - l, np.abs(h - pc), np.abs(l - pc)])
    atr = pd.Series(tr).ewm(alpha=1.0 / n, adjust=False).mean().to_numpy()
    return atr


def ensure_out():
    if not os.path.isdir(OUT_DIR):
        try:
            os.makedirs(OUT_DIR, exist_ok=True)
        except Exception:
            return HERE   # fallback: 자기폴더
    return OUT_DIR
