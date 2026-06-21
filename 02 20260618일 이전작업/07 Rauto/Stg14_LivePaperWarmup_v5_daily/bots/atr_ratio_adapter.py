# -*- coding: utf-8 -*-
# [파일명] atr_ratio_adapter.py — Dauto CSV(1m OHLC) → atr_ratio 라이브 aux 공급원
# 코드길이: 약 70줄 | 내부버전: dauto_ch2_stg15_adapter_v1
# [수식 출처] regime_feature_extractor.py(c3ace85e, 동봉 원본 무수정 import) —
#   compute_continuous_metrics의 atr_ratio 경로만 사용:
#   4H right/right 리샘플 → TR ewm(alpha=1/14, adjust=False) → norm_atr=atr/close*100
#   → avg=rolling(60).mean() → ratio → 1m 매핑 shift(1)+ffill (build 132~133줄과 동일).
# [워밍업 — atr_warm 플래그] EWM ATR은 전 역사 의존 → 짧은 출생지에선 수렴 전 오차.
#   test ②가 실측한 N_WARM_4H(오차<1e-3 수렴 4H봉수)을 기본값으로 박제. 수렴 전 1m행은
#   atr_warm=1 병기(필터는 NaN/플래그 정책으로 보수 처리).
# [na 행] Dauto oi_src=na 행도 가격(OHLC) 컬럼은 무결 → atr 계산 영향 0 (test ③에서 확인).
import os
import sys

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import regime_feature_extractor as RF      # 원본(c3ace85e) 무수정 import
from dauto_loader import load_dauto

N_WARM_4H_DEFAULT = 137                    # test ② 실측 박제: 오차<1e-3 수렴 N(컷 30/45/60일 최대 133/130/137)


def atr_ratio_4h_from_1m(df_1m):
    """df_1m: index=ts, open/high/low/close(+volume). 원본 build 117~119줄과 동일 경로."""
    ohlc = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}
    if 'volume' not in df_1m.columns:
        df_1m = df_1m.assign(volume=0.0)
    d4 = df_1m.resample(RF.TF, label='right', closed='right').agg(ohlc).dropna()
    d4.columns = [c.lower() for c in d4.columns]
    d4 = RF.compute_continuous_metrics(d4)
    return d4


def map_4h_to_1m(d4_series, idx_1m):
    """원본 build 130~133줄 1:1 — shift(1) 안전판 + ffill."""
    s = d4_series.shift(1)
    return s.reindex(idx_1m.union(s.index)).ffill().reindex(idx_1m)


def build_aux(data_dir=None, out_csv=None, n_warm_4h=N_WARM_4H_DEFAULT):
    """market.aux용 (ts_utc, atr_ratio, atr_warm) DataFrame 생성."""
    kw = {} if data_dir is None else {'data_dir': data_dir}
    dd = load_dauto(['open', 'high', 'low', 'close', 'volume'], **kw)
    df = dd.set_index('ts_utc')
    d4 = atr_ratio_4h_from_1m(df)
    ar_1m = map_4h_to_1m(d4['atr_ratio'], df.index)
    # 워밍업 플래그: 스트림 출생 후 n_warm_4h 번째 4H봉이 '확정·매핑'되기 전까지 atr_warm=1
    if len(d4) > n_warm_4h:
        warm_end = d4.index[n_warm_4h]     # shift(1) 매핑이라 이 봉 시각부터 수렴값 공급
        warm = (df.index < warm_end).astype(int)
    else:
        warm = pd.Series(1, index=df.index).values
    aux = pd.DataFrame({'ts_utc': df.index, 'atr_ratio': ar_1m.values, 'atr_warm': warm})
    if out_csv:
        aux.to_csv(out_csv, index=False, encoding='utf-8-sig')
    return aux
