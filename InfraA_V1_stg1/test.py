# -*- coding: utf-8 -*-
# [파일명] test.py  (InfraA_V1_stg1 — OB 크기 실측 리포트)
# 코드길이: 약 200줄, 내부버전명: obsize_v1, 로직 축약/생략 없이 전체 출력
#
# [목적] 새 설계(SL=1H OB중간, TP=5분 OB) 게이트값을 추정 말고 '숫자로' 확정하기 위해,
#   하락장 매 1시간봉 시점에서 5분 OB와 60분 OB가 진입가에서 몇 bp 떨어졌는지(top/mean/bottom)
#   와 OB 두께(bp), 실제 달러를 전수 측정해 분포로 정리한다. (★거래·손익 시뮬 아님 — 순수 측정)
#
# [속도가속] (1)pivot은 5분·60분 각각 전구간 1회 사전계산(sliding_window_view 벡터화).
#   (2)pivot은 '확정시각' 오름차순이라, 매 시점 searchsorted로 활성 슬라이스만 본다.
#   (3)측정점은 하락장 '1시간봉 시점'만(빈구간·분단위 점프).
#
# [미래참조 가드] ob_mtf.py 원본 그대로 인라인: pivot 확정시각 = (center+w)봉 마감시각.
#   그 시각 <= 측정시각 인 OB만 사용(미완성 상위TF봉 배제).
#
# [경로] 이 파일은 D:\ML\verify\InfraA_V1_stg1\ 에서 실행. 데이터는 상위 D:\ML\verify\ 에 있다.
#   결과 CSV(obsize_samples.csv, obsize_summary.csv)는 '이 하위폴더'에 저장(check.py가 검사).
#
# [사용 파일] 본 파일 단독(필요한 ob_mtf 함수는 아래에 인라인). 외부 import 없음.
# [입력 데이터] 상위폴더 Merged_Data_with_Regime_Features.csv (timestamp,open,high,low,close,feat_struct_8)
# [출력] obsize_samples.csv(시점별 원자료) + obsize_summary.csv(분포요약) — 전량 파일, 화면복붙 불필요.
#
# [함수 In/Out]
#   find_data()                         -> 데이터 경로(str)
#   load_data(path)                     -> df(DatetimeIndex, OHLC + feat_struct_8)
#   resample_tf(df1m, tf_min)           -> df_tf (OHLC, index=봉시작시각)            [ob_mtf 인라인]
#   precompute_tf_pivots(df_tf,w,tf_min)-> (hp_conf,lp_conf,hp_top,hp_bot,lp_top,lp_bot) [ob_mtf 인라인]
#   nearest_above(price,ts,...)         -> (top,bottom) or None  저항OB(SL용)         [ob_mtf 인라인]
#   nearest_below(price,ts,...)         -> (top,bottom) or None  지지OB(TP용)         [ob_mtf 인라인]
#   measure_tf(tf, df, sample_idx, ...) -> list[dict] 시점별 측정행
#   summarize(rows)                     -> list[dict] (TF·방향·엣지별 분포)
# ==============================================================================

import os, sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
REGIME_COL = 'feat_struct_8'
W_TF = 3                       # pivot 한쪽 윈도우(원본 ob_mtf와 동일)
TF_LIST = [5, 60]              # 측정할 상위TF: 5분(=새 TP 후보), 60분(=현행/새 SL 후보)
PCTS = [10, 50, 90]            # 분포 백분위


def find_data():
    for d in [PARENT, HERE, r"D:\ML\verify", r"D:\ML\Verify"]:
        for n in ["Merged_Data_with_Regime_Features.csv", "Merged_Data.csv"]:
            p = os.path.join(d, n)
            if os.path.exists(p):
                return p
    raise FileNotFoundError("상위 D:\\ML\\verify 에 Merged_Data_with_Regime_Features.csv 필요")


def load_data(path):
    head = pd.read_csv(path, nrows=1)
    if REGIME_COL not in head.columns:
        raise KeyError(f"{REGIME_COL} 컬럼 없음. 가진 컬럼: {list(head.columns)[:12]}")
    cols = ['timestamp', 'open', 'high', 'low', 'close', REGIME_COL]
    df = pd.read_csv(path, usecols=cols, index_col='timestamp', parse_dates=True)
    if getattr(df.index, 'tz', None) is not None:
        df.index = df.index.tz_localize(None)
    return df.sort_index()


# ----- ob_mtf.py 인라인(검증된 원본 그대로) -------------------------------------
def resample_tf(df1m, tf_min):
    rule = f"{tf_min}min"
    agg = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}
    return df1m[['open', 'high', 'low', 'close']].resample(rule, label='left', closed='left').agg(agg).dropna()


def precompute_tf_pivots(df_tf, w, tf_min):
    high = df_tf['high'].values; low = df_tf['low'].values
    starts = df_tf.index.values
    n = len(high)
    if n < 2 * w + 1:
        z = np.array([], dtype='datetime64[ns]'); f = np.array([], dtype=float)
        return z, z, f, f, f, f
    from numpy.lib.stride_tricks import sliding_window_view
    win = 2 * w + 1
    hmax = sliding_window_view(high, win).max(axis=1)
    lmin = sliding_window_view(low, win).min(axis=1)
    centers = np.arange(w, n - w)
    hp_c = centers[high[w:n - w] == hmax]
    lp_c = centers[low[w:n - w] == lmin]
    tf_delta = np.timedelta64(tf_min, 'm')
    hp_confirm = starts[hp_c + w] + tf_delta          # 확정시각=우측 w봉 마감
    lp_confirm = starts[lp_c + w] + tf_delta
    return (hp_confirm, lp_confirm, high[hp_c], low[hp_c], high[lp_c], low[lp_c])


def nearest_above(price, ts, hp_confirm, hp_top, hp_bot):
    """저항 OB(SL용): 확정시각<=ts 중 bottom>price 인 것에서 bottom 최소(가까운 것)."""
    k = np.searchsorted(hp_confirm, np.datetime64(ts), side='right')   # 활성 슬라이스
    if k == 0:
        return None
    bots = hp_bot[:k]; tops = hp_top[:k]
    cand = bots > price
    if not cand.any():
        return None
    bb = bots[cand]; tt = tops[cand]
    j = np.argmin(bb)
    return (float(tt[j]), float(bb[j]))


def nearest_below(price, ts, lp_confirm, lp_top, lp_bot):
    """지지 OB(TP용): 확정시각<=ts 중 top<price 인 것에서 top 최대(가까운 것)."""
    k = np.searchsorted(lp_confirm, np.datetime64(ts), side='right')
    if k == 0:
        return None
    tops = lp_top[:k]; bots = lp_bot[:k]
    cand = tops < price
    if not cand.any():
        return None
    tt = tops[cand]; bb = bots[cand]
    j = np.argmax(tt)
    return (float(tt[j]), float(bb[j]))
# -------------------------------------------------------------------------------


def measure_tf(tf, df, sample_idx, idx, c):
    """tf분 OB를 하락장 시점마다 측정. 반환: 시점별 dict 리스트."""
    df_tf = resample_tf(df, tf)
    hpc, lpc, hpt, hpb, lpt, lpb = precompute_tf_pivots(df_tf, W_TF, tf)
    rows = []
    for t0 in sample_idx:
        price = c[t0]; ts = idx[t0]
        ab = nearest_above(price, ts, hpc, hpt, hpb)   # 저항(SL)
        bl = nearest_below(price, ts, lpc, lpt, lpb)   # 지지(TP)
        r = {'시각': ts.strftime('%Y-%m-%d %H:%M'), '연도': ts.year, 'TF': tf, '진입가': round(price, 2)}
        # 저항(위) OB: SL 후보. top이 멀고 bottom이 가깝다. mean은 그 중간.
        if ab is None:
            r.update(저항_있나='없음', SLtop_bp='', SLmean_bp='', SLbot_bp='', 저항두께_bp='', SLmean_달러='')
        else:
            top, bot = ab; mean = (top + bot) / 2.0
            r.update(저항_있나='있음',
                     SLtop_bp=round((top - price) / price * 1e4, 1),
                     SLmean_bp=round((mean - price) / price * 1e4, 1),
                     SLbot_bp=round((bot - price) / price * 1e4, 1),
                     저항두께_bp=round((top - bot) / price * 1e4, 1),
                     SLmean_달러=round(mean - price, 2))
        # 지지(아래) OB: TP 후보. top이 가깝다(=tp_price). bottom이 멀다.
        if bl is None:
            r.update(지지_있나='없음', TPtop_bp='', TPmean_bp='', TPbot_bp='', 지지두께_bp='', TPtop_달러='')
        else:
            top, bot = bl; mean = (top + bot) / 2.0
            r.update(지지_있나='있음',
                     TPtop_bp=round((price - top) / price * 1e4, 1),
                     TPmean_bp=round((price - mean) / price * 1e4, 1),
                     TPbot_bp=round((price - bot) / price * 1e4, 1),
                     지지두께_bp=round((top - bot) / price * 1e4, 1),
                     TPtop_달러=round(price - top, 2))
        rows.append(r)
    return rows


def _pct(series):
    s = pd.to_numeric(series, errors='coerce').dropna()
    if len(s) == 0:
        return {f'p{p}': '' for p in PCTS}
    return {f'p{p}': round(float(np.percentile(s, p)), 1) for p in PCTS}


def summarize(rows):
    d = pd.DataFrame(rows)
    out = []
    for tf in TF_LIST:
        sub = d[d['TF'] == tf]
        n = len(sub)
        # 저항(SL) 분포
        has_sl = (sub['저항_있나'] == '있음')
        for metric, col in [('SL_top', 'SLtop_bp'), ('SL_mean', 'SLmean_bp'), ('SL_bottom', 'SLbot_bp'), ('저항_두께', '저항두께_bp')]:
            row = {'TF': tf, '대상': metric, '측정수': n, 'OB없음pct': round((~has_sl).mean() * 100, 1)}
            row.update(_pct(sub.loc[has_sl, col])); out.append(row)
        # 지지(TP) 분포
        has_tp = (sub['지지_있나'] == '있음')
        for metric, col in [('TP_top', 'TPtop_bp'), ('TP_mean', 'TPmean_bp'), ('TP_bottom', 'TPbot_bp'), ('지지_두께', '지지두께_bp')]:
            row = {'TF': tf, '대상': metric, '측정수': n, 'OB없음pct': round((~has_tp).mean() * 100, 1)}
            row.update(_pct(sub.loc[has_tp, col])); out.append(row)
    return out


def main():
    print("[InfraA_V1_stg1] OB 크기 실측 — 하락장 1시간봉 시점, 5분/60분 OB의 top/mean/bottom·두께(bp)")
    open(os.path.join(HERE, ".run_start"), 'w').close()   # check.py가 '이번 실행 이후 생성' 판정용
    data = find_data(); print(f"[데이터] {data}")
    df = load_data(data)
    o = df['open'].values; h = df['high'].values; l = df['low'].values; c = df['close'].values
    idx = df.index
    regime = df[REGIME_COL].astype(str).values
    # 측정점: 하락장 + '정시(분==0)' 1분봉 (= 1시간봉 시점, 속도가속 표본)
    minute0 = (idx.minute.values == 0)
    sample_idx = np.where((regime == 'downtrend') & minute0)[0]
    print(f"[로드] {len(df):,}행. 하락장 정시 측정점 {len(sample_idx):,}개. TF {TF_LIST} 측정...\n")

    all_rows = []
    for tf in TF_LIST:
        rows = measure_tf(tf, df, sample_idx, idx, c)
        all_rows.extend(rows)
        sl_med = pd.to_numeric(pd.DataFrame(rows).get('SLtop_bp'), errors='coerce').median()
        tp_med = pd.to_numeric(pd.DataFrame(rows).get('TPtop_bp'), errors='coerce').median()
        print(f"  [TF{tf}분] 측정 {len(rows)}개 | SLtop중앙 {sl_med:.1f}bp | TPtop중앙 {tp_med:.1f}bp")

    pd.DataFrame(all_rows).to_csv(os.path.join(HERE, "obsize_samples.csv"), index=False, encoding='utf-8-sig')
    pd.DataFrame(summarize(all_rows)).to_csv(os.path.join(HERE, "obsize_summary.csv"), index=False, encoding='utf-8-sig')
    print("\n[저장] obsize_samples.csv + obsize_summary.csv (이 하위폴더) — 전량 파일, 복붙 불필요")


if __name__ == "__main__":
    main()
