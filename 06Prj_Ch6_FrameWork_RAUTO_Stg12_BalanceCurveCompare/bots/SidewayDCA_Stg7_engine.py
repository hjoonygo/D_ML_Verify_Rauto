# -*- coding: utf-8 -*-
# [파일명] test_05Prj_Ch1_Stg7_SidewayDCA_AlphaUp.py
# 코드길이: 약 700줄 | 내부버전: SidewayDCA_AlphaUp_05_Ch1_Stg7 (regime롱 차등sl 측정+익절추적) | 로직 축약/생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명]
#   stg1~3(정직화·왕복비용·펀딩전체·손절깊이sl_mult)을 계승하고, stg7에서 두 가지를 추가한다.
#   유지: ①1분봉경로청산 ②실펀딩(부호반영) ④왕복비용 ⑤펀딩전체본(ISO8601) ⑥sl_deep 손절깊이 sl_mult
#   신규(stg7):
#     ⑦ sl_mult 1.8 확정 : stg3 실데이터에서 1.8이 WFE80.8%(최고)+MDD-13.4%. 인접 1.7/1.9도 함께 돌려 '고원'인지 확인.
#                          기준선(base)을 stg3의 1.5에서 1.8로 변경. 스윕 그리드=1.2/1.5/1.7/1.8/1.9/2.2/2.6.
#     ⑧ 정밀 진입필터   : stg7 데이터분석 결과 — regime_shift 장세에서 '변동압축(atr_ratio<0.9)'일 때 거래가 망함
#                          (승률 33%, 수익률 -4.95%). 단순 전체차단은 clean_range 알짜까지 죽이므로,
#                          'regime_shift 장세 AND atr_ratio<0.9'만 콕 집어 진입 차단(precise).
#                          atr_ratio = 데이터 feat_ 컬럼(그 시점 과거기반). scen = 봇이 그 시점 계산하는 라벨.
#                          둘 다 진입결정 시점에 알 수 있음 → 미래참조 없음.
#   검증스윕(E): 필터 off / precise / both_ends(압축<0.9 또는 과열>=1.3) / precise+숏0.7배 를 비교 출력.
#   ★안전장치: 데이터에 atr_ratio 컬럼이 없으면 필터 자동 비활성 + summary에 '필터불가' 경고. (추정으로 돌지 않음)
#
# [★사용명칭 정의]  ※추정 방지 위해 명시
#   sl_mult = 'POC 기준 sl_mult×ATR 벗어나면 깊은손절(sl_deep)' 손절깊이 배수(진입 dist_max=1.5와 분리).
#   진입조건 dist_max(1.5)와 분리된 별개 값. 1분봉 경로에서 이 레벨에 닿는 즉시 그 가격으로 청산(종가청산 아님).
#
# [미래참조 차단]
#   - 진입/피보트레일/DCA/시간손절 '결정'은 전부 닫힌 8시간봉 기준, 체결은 다음 8시간봉 시가.
#   - 1분봉 경로는 보유 중 '실제 가격이 지나간 길'만 사용(미래봉 안 봄). 첫 닿는 순간 청산 후 멈춤.
#   - 피벗은 right=1봉 뒤 확정값(과거가격)만 사용. ATR/ADX/POC 과거봉만. shift(-) 없음.
#   - 펀딩은 보유기간에 실제 정산된 과거 펀딩만 합산.
#
# [PATH] 실행: D:\ML\verify\05Prj_Ch1_Stg7_SidewayDCA_AlphaUp\ . 데이터/펀딩: 상위 D:\ML\verify\ .
# [DATA] 상위 Merged_Data_with_Regime_Features.csv (없으면 merged_data.csv). volume 자동감지.
#        펀딩 funding_history_8h.csv (없으면 고정 0.0001 폴백 + 경고표시).
# [OUTPUT] (실행폴더) sdca_summary.csv + sdca_trades.csv + sdca_scenarios.csv -> check.py 정리.
# [SPEED] 8h신호 1회 사전계산 + 1분봉→8시간봉 슬라이스맵 1회. 캡9개는 고정 best파라미터로만 11회 실행.
#         보유 중에만 1분봉 슬라이스를 numpy로 스캔(거래가 짧아 가볍다).
#
# [사용 파일]
#   IN : (상위) Merged_Data_with_Regime_Features.csv / merged_data.csv  (1분봉 OHLCV)
#        (상위) funding_history_8h.csv  (실펀딩; 없으면 폴백)
#   OUT: (실행폴더) sdca_summary.csv / sdca_trades.csv / sdca_scenarios.csv
#
# [함수 In->Out]
#   find_data()                         (없음) -> 데이터 csv 경로
#   find_funding()                      (없음) -> 펀딩 csv 경로 또는 None
#   load_1m(path)                       csv경로 -> 1분봉 DataFrame(+has_vol)
#   load_funding(path)                  csv경로 -> (시각 int64 ns 배열, 펀딩률 배열)
#   resample_tf(df1m,tf)                1분봉,분 -> 8시간봉 OHLCV
#   compute_atr/adx/poc(...)            지표 배열 (stg9 재사용, 변경없음)
#   precompute(df8)                     8시간봉 -> 신호dict(피벗/atr/adx/poc 등)
#   build_1m_map(df1m,df8)              1분봉,8시간봉 -> (slice_start[], slice_end[]) 각 8h봉의 1분봉 구간
#   scen_label(...)                     사후 8시나리오 라벨 (stg9 재사용)
#   funding_sum(ft,fr,a_ns,b_ns)        펀딩시각/률,구간 -> 구간 합산 펀딩률
#   run_bot_legacy(df8,sig,par)         OLD 8h집계 엔진(낙관) -> trades  [정직화 전 비교용]
#   run_bot_honest(df8,sig,par,...,ft,fr,sl_mult) 1분봉경로 정직엔진(왕복비용 고정, sl_deep깊이=sl_mult) -> (trades, ambig_n, held_n)
#   agg(trades,label,years)             거래 -> PF/누적R/MDD/거래수/승률 (stg9 재사용)
#   scen_breakdown(trades,years)        거래 -> 8시나리오별 손익 (stg9 재사용)
#   main()                              전체 실행 + 캡스윕 + CSV 3종
#
# [상태변수] pos(수량비율) avg(평단) side(+1롱/-1숏) entry_fill_bar nfilled pb trailSL poc_t scen0
# ==============================================================================

import os, sys, itertools
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)

# ── CFG (stg9 계승) ──
COST_SIDE   = 0.0005 + 0.0002      # 편도 비용(수수료0.05%+슬리피지0.02%). 거래당 왕복=COST_SIDE*2 차감.
FUND_8H     = 0.0001               # 펀딩 폴백 고정값(실데이터 없을 때만)
NOTIONAL_CAP= 2.5                  # 명목 2.5배 상한(폭주 방지) - agg 복리에 반영
START_CAP   = 10000.0
LEFT, RIGHT = 4, 1
ATR_PERIOD  = 14
ADX_N       = 14
ATR_SMA_N   = 50
ATR_COMP_K  = 0.8
POC_LOOKBACK= 60
POC_BINS    = 50
TIME_STOP   = 40
TRAIN_YEARS = [2023, 2024]
TEST_YEARS  = [2025, 2026]
SHORT_SIZE  = 0.5

# ── stg7 설정: 펀딩 전체본 + sl_deep 손절깊이 스윕(캡 방식 폐기) ──
TF_MIN   = 8 * 60                  # stg9 VERDICT 채택 = 8h 고정
BEST_PAR = {'dist_max': 1.5, 'adx_hi': 22, 'a': 0.3, 'd': 0.1, 'short_on': 1, 'nDCA': 1}  # stg9 VERDICT
# 손절깊이 sl_mult: 'POC에서 sl_mult×ATR 벗어나면 sl_deep'. 진입은 dist_max=1.5 고정.
#   stg4 실데이터: 필터ON일 때 1.8이 WFE116%. stg7는 필터ON 상태에서 1.7/1.8/1.9 재확인(고원).
SL_MULT_GRID = [1.2, 1.5, 1.7, 1.8, 1.9, 2.2, 2.6]
DEFAULT_SLMULT = 1.8               # stg4 확정 기준선

# ── 정밀 진입필터 (stg4 확정: regime_shift & 변동압축 차단) ──
#   위험은 '변동확대'가 아니라 '변동압축(atr_ratio<0.9)'. 장세(regime_shift)와 결합해야 알짜를 안 죽인다.
#   atr_ratio=데이터 feat_(과거기반), scen=봇이 그 시점 계산. 둘 다 진입시점에 알 수 있음 → 미래참조 없음.
FILTER_MODE      = 'precise'
ATR_LO           = 0.9
ATR_HI           = 1.3
FILTER_SCENS     = ('regime_shift',)

# ── stg7 OI 2차필터 (요소E: regime_shift 잔여손실을 OI급증으로 추가 차단) ──
#   stg7 데이터분석: regime_shift에서 oi_zscore_24h>0(OI 비정상 급증)이면 승률 36→17%로 폭락, 수익률 음수.
#   '남들이 우르르 포지션 늘릴 때 역추세 진입하면 깨진다'는 미시구조 논리. 1차필터(atr) 통과분을 OI로 재차단.
#   oi_zscore_24h = merged_data 컬럼(그 시점 과거 24h 기준). 진입시점에 알 수 있음 → 미래참조 없음.
OI_FILTER_ON     = True            # OI 2차필터 사용(데이터 없으면 자동 비활성)
OI_Z_HI          = 0.0             # oi_zscore_24h 이 값 이상이면 regime_shift 진입 차단
OI_FILTER_SCENS  = ('regime_shift',)
OI_Z_GRID        = [-0.5, 0.0, 0.5, 1.0]   # stg7 임계 고원 확인(과최적화 점검 — stg5 교훈)
# 두 파일 자동병합: 데이터 파일에 oi_zscore_24h 없으면, merged_data.csv를 찾아 timestamp로 붙임.
MERGED_OI_CANDS  = ["Merged_Data.csv", "merged_data.csv", "merged_data_sample.csv"]

# ── 안정성 스윕(stg5 계승): 인접값 고원인지 = 과최적화 점검 ──
ATR_LO_GRID      = [0.80, 0.85, 0.90, 0.95, 1.00]
SHORT_MULT_GRID  = [1.0, 1.2, 1.4, 1.6]
SLMULT_ON_GRID   = [1.7, 1.8, 1.9]

# ── stg7 ② regime_shift 롱 차등 sl_mult (측정) ──
#   stg6 분석: sl_deep 손실은 'regime_shift & 롱'에 집중(9건 -5.73%). 숏/clean_range는 멀쩡.
#   → regime_shift 롱만 손절을 얕게(빨리 자름) 했을 때 효과를 '실제 재백테스트'로 측정.
#   기본은 0(차등 안 함). 스윕으로 1.2/1.3/1.5/1.8(=차등없음) 비교.
SLMULT_REGIME_LONG_GRID = [1.2, 1.3, 1.5, 1.8]   # regime_shift 롱 전용 sl_mult (1.8=차등없음과 동일)

# ── stg7 ③ tp_poc 익절 후 가격추적 (측정 전용, 봇 로직 아님) ──
#   부분익절 판단 근거: POC 익절 후 N봉 동안 가격이 익절가 대비 얼마나 더 유리하게 갔나.
#   ★measure용 미래참조(청산 후 가격)는 분석에만 쓰고 봇 진입/청산엔 절대 차용 안 함.
TP_TRACK_BARS    = [1, 2, 3, 5]                  # 익절 후 몇 봉 추적

SCEN = ['clean_range','break_up','break_down','fake_break',
        'v_reversal','low_vol_range','strong_trend','regime_shift']


def find_data():
    cands = ["Merged_Data_with_Regime_Features.csv", "merged_data.csv"]
    for d in [PARENT, HERE, r"D:\ML\verify", r"D:\ML\Verify"]:
        for c in cands:
            p = os.path.join(d, c)
            if os.path.exists(p):
                return p
    raise FileNotFoundError("상위 D:\\ML\\verify 에 데이터 csv 필요")


def find_funding():
    # 전체본(BTCUSDT_/funding_history) 우선, 샘플(sample_)은 맨 마지막 폴백
    cands = ["BTCUSDT_funding_history_8h.csv", "funding_history_8h.csv",
             "sample_BTCUSDT_funding_history_8h.csv"]
    for d in [PARENT, HERE, r"D:\ML\verify", r"D:\ML\Verify"]:
        for c in cands:
            p = os.path.join(d, c)
            if os.path.exists(p):
                return p
    return None


def find_oi(exclude_path=None):
    # OI(oi_zscore_24h) 들어있는 merged_data 파일 탐색. 메인데이터와 다른 파일일 수 있음.
    for d in [PARENT, HERE, r"D:\ML\verify", r"D:\ML\Verify"]:
        for c in MERGED_OI_CANDS:
            p = os.path.join(d, c)
            if os.path.exists(p) and (exclude_path is None or os.path.abspath(p) != os.path.abspath(exclude_path)):
                try:
                    h = pd.read_csv(p, nrows=1)
                    if 'oi_zscore_24h' in h.columns:
                        return p
                except Exception:
                    pass
    return None


def load_1m(path):
    head = pd.read_csv(path, nrows=1)
    cols = ['timestamp', 'open', 'high', 'low', 'close']
    has_vol = 'volume' in head.columns
    if has_vol:
        cols.append('volume')
    # stg4: 정밀필터용 atr_ratio(feat_ 컬럼) 있으면 함께 읽음. 없으면 1차필터 자동 비활성.
    has_atrr = 'atr_ratio' in head.columns
    if has_atrr:
        cols.append('atr_ratio')
    # stg7: OI 2차필터용 oi_zscore_24h 가 같은 파일에 있으면 함께 읽음.
    has_oi_same = 'oi_zscore_24h' in head.columns
    if has_oi_same:
        cols.append('oi_zscore_24h')
    df = pd.read_csv(path, usecols=cols, index_col='timestamp', parse_dates=True)
    if getattr(df.index, 'tz', None) is not None:
        df.index = df.index.tz_localize(None)
    df = df.sort_index()
    df.attrs['has_vol'] = has_vol
    df.attrs['has_atrr'] = has_atrr

    # stg7 자동병합: oi_zscore_24h 가 메인 파일에 없으면 별도 merged_data 파일에서 timestamp로 붙임.
    has_oi = has_oi_same
    if not has_oi_same:
        oip = find_oi(exclude_path=path)
        if oip is not None:
            try:
                oi = pd.read_csv(oip, usecols=['timestamp', 'oi_zscore_24h'],
                                 index_col='timestamp', parse_dates=True)
                if getattr(oi.index, 'tz', None) is not None:
                    oi.index = oi.index.tz_localize(None)
                oi = oi.sort_index()
                # 동일 1분봉 인덱스 정렬해 reindex(메인에 맞춤). 시각 일치라 그대로 매칭.
                df['oi_zscore_24h'] = oi['oi_zscore_24h'].reindex(df.index)
                has_oi = True
                df.attrs['oi_source'] = os.path.basename(oip)
            except Exception as e:
                df.attrs['oi_source'] = f"병합실패:{e}"
    else:
        df.attrs['oi_source'] = "메인파일내장"
    df.attrs['has_oi'] = has_oi
    return df


def load_funding(path):
    # 컬럼 유연 처리 + 포맷 견고화: 바이낸스 펀딩의 밀리초+TZ 혼재(예 '...00.004000+00:00')를
    # errors='coerce'로 두면 일부가 NaT로 누락된다(stg2 버그). format='ISO8601'로 강제 파싱.
    df = pd.read_csv(path)
    tcol = next((c for c in df.columns if 'time' in c.lower()), df.columns[0])
    rcol = next((c for c in df.columns if 'rate' in c.lower()), df.columns[1])
    try:
        t = pd.to_datetime(df[tcol], format='ISO8601', utc=True)
    except Exception:
        t = pd.to_datetime(df[tcol], utc=True, errors='coerce')   # 최후 폴백
    t = t.dt.tz_localize(None)
    r = pd.to_numeric(df[rcol], errors='coerce')
    ok = t.notna() & r.notna()
    n_drop = int((~ok).sum())
    t = t[ok].values.astype('datetime64[ns]').astype('int64')
    r = r[ok].values.astype('float64')
    order = np.argsort(t)
    t, r = t[order], r[order]
    # 로드 진단을 attrs 대신 모듈 전역에 기록(검증·VERDICT 표기용)
    load_funding.n_loaded = len(t)
    load_funding.n_dropped = n_drop
    return t, r
load_funding.n_loaded = 0
load_funding.n_dropped = 0


def resample_tf(df1m, tf_min):
    rule = f"{tf_min}min"
    agg = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}
    if df1m.attrs.get('has_vol', False):
        agg['volume'] = 'sum'
    has_atrr = df1m.attrs.get('has_atrr', False)
    if has_atrr:
        agg['atr_ratio'] = 'last'   # 8h봉 닫히는 시점의 atr_ratio(그 시점 알 수 있는 값)
    has_oi = df1m.attrs.get('has_oi', False)
    if has_oi:
        agg['oi_zscore_24h'] = 'last'   # 8h봉 닫히는 시점의 oi_zscore(과거 24h 기준, 알 수 있는 값)
    res = df1m.resample(rule, label='left', closed='left').agg(agg)
    # OHLC가 있는 봉만 유지(atr_ratio/oi NaN이라고 봉을 버리지 않음 — 필터는 NaN시 통과시킴)
    out = res.dropna(subset=['open', 'high', 'low', 'close'])
    out.attrs['has_vol'] = df1m.attrs.get('has_vol', False)
    out.attrs['has_atrr'] = has_atrr
    out.attrs['has_oi'] = has_oi
    return out


def compute_atr(high, low, close, Pd):
    n = len(close); tr = np.zeros(n)
    tr[1:] = np.maximum.reduce([high[1:] - low[1:],
                                np.abs(high[1:] - close[:-1]),
                                np.abs(low[1:] - close[:-1])])
    atr = np.zeros(n)
    if n > Pd:
        atr[Pd] = tr[1:Pd + 1].mean()
        for i in range(Pd + 1, n):
            atr[i] = (atr[i - 1] * (Pd - 1) + tr[i]) / Pd
    return atr


def compute_adx(high, low, close, n):
    N = len(close)
    tr = np.zeros(N); pdm = np.zeros(N); ndm = np.zeros(N)
    up = high[1:] - high[:-1]; dn = low[:-1] - low[1:]
    pdm[1:] = np.where((up > dn) & (up > 0), up, 0.0)
    ndm[1:] = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr[1:] = np.maximum.reduce([high[1:] - low[1:],
                                np.abs(high[1:] - close[:-1]),
                                np.abs(low[1:] - close[:-1])])
    atrw = np.zeros(N); pdmw = np.zeros(N); ndmw = np.zeros(N); adx = np.zeros(N)
    if N <= n + 1:
        return adx
    atrw[n] = tr[1:n + 1].sum(); pdmw[n] = pdm[1:n + 1].sum(); ndmw[n] = ndm[1:n + 1].sum()
    dx = np.zeros(N)
    for i in range(n + 1, N):
        atrw[i] = atrw[i - 1] - atrw[i - 1] / n + tr[i]
        pdmw[i] = pdmw[i - 1] - pdmw[i - 1] / n + pdm[i]
        ndmw[i] = ndmw[i - 1] - ndmw[i - 1] / n + ndm[i]
        if atrw[i] > 0:
            pdi = 100 * pdmw[i] / atrw[i]; ndi = 100 * ndmw[i] / atrw[i]
            dx[i] = 100 * abs(pdi - ndi) / (pdi + ndi) if (pdi + ndi) > 0 else 0
    start = 2 * n
    if N > start:
        adx[start] = dx[n + 1:start + 1].mean()
        for i in range(start + 1, N):
            adx[i] = (adx[i - 1] * (n - 1) + dx[i]) / n
    return adx


def compute_poc(df, lookback, bins):
    high = df['high'].values; low = df['low'].values; close = df['close'].values
    n = len(close)
    has_vol = df.attrs.get('has_vol', False)
    vol = df['volume'].values if has_vol else np.ones(n)
    poc = np.full(n, np.nan); midall = (high + low) / 2.0
    for i in range(lookback, n):
        s = i - lookback
        lo = low[s:i].min(); hi = high[s:i].max()
        if hi <= lo:
            poc[i] = close[i - 1]; continue
        edges = np.linspace(lo, hi, bins + 1)
        idxb = np.clip(np.digitize(midall[s:i], edges) - 1, 0, bins - 1)
        hist = np.zeros(bins); np.add.at(hist, idxb, vol[s:i])
        kmax = int(hist.argmax())
        poc[i] = (edges[kmax] + edges[kmax + 1]) / 2.0
    return poc


def precompute(df):
    high = df['high'].values; low = df['low'].values; close = df['close'].values
    n = len(close)
    from numpy.lib.stride_tricks import sliding_window_view
    ph_conf = {}; pl_conf = {}
    win = LEFT + RIGHT + 1
    if n >= win:
        hwin = sliding_window_view(high, win); lwin = sliding_window_view(low, win)
        centers = np.arange(LEFT, n - RIGHT)
        hmax = hwin.max(axis=1); lmin = lwin.min(axis=1)
        hc = high[LEFT:n - RIGHT]; lc = low[LEFT:n - RIGHT]
        is_ph = (hc == hmax) & ((hwin == hmax[:, None]).sum(axis=1) == 1)
        is_pl = (lc == lmin) & ((lwin == lmin[:, None]).sum(axis=1) == 1)
        for k in np.where(is_ph)[0]:
            ph_conf[centers[k] + RIGHT] = float(high[centers[k]])
        for k in np.where(is_pl)[0]:
            pl_conf[centers[k] + RIGHT] = float(low[centers[k]])
    atr = compute_atr(high, low, close, ATR_PERIOD)
    adx = compute_adx(high, low, close, ADX_N)
    atr_sma = pd.Series(atr).rolling(ATR_SMA_N, min_periods=1).mean().values
    atrcmp = (atr < atr_sma * ATR_COMP_K)
    poc = compute_poc(df, POC_LOOKBACK, POC_BINS)
    years = df.index.year.values
    eh = ((df.index - pd.Timestamp('1970-01-01')) / pd.Timedelta(hours=1)).values.astype('float64')
    # stg4: atr_ratio(feat_) 8h배열. 컬럼 없으면 전부 NaN(필터 자동 통과).
    if df.attrs.get('has_atrr', False) and 'atr_ratio' in df.columns:
        atr_ratio = df['atr_ratio'].values.astype('float64')
    else:
        atr_ratio = np.full(n, np.nan)
    # stg7: oi_zscore_24h 8h배열. 컬럼 없으면 전부 NaN(2차필터 자동 통과).
    if df.attrs.get('has_oi', False) and 'oi_zscore_24h' in df.columns:
        oi_z = df['oi_zscore_24h'].values.astype('float64')
    else:
        oi_z = np.full(n, np.nan)
    return {'high': high, 'low': low, 'close': close, 'open': df['open'].values, 'n': n,
            'ph_conf': ph_conf, 'pl_conf': pl_conf, 'atr': atr, 'adx': adx,
            'atrcmp': atrcmp, 'poc': poc, 'years': years, 'eh': eh,
            'atr_ratio': atr_ratio, 'oi_z': oi_z}


def build_1m_map(df1m, df8):
    # 각 8시간봉 j 의 1분봉 구간 [slice_start[j], slice_end[j]) 을 미리 계산(좌측라벨/좌폐 구간 일치)
    m_ns = df1m.index.values.astype('datetime64[ns]').astype('int64')
    b_ns = df8.index.values.astype('datetime64[ns]').astype('int64')
    step = int(TF_MIN) * 60 * 1_000_000_000  # 8h in ns
    ss = np.searchsorted(m_ns, b_ns, side='left')
    se = np.searchsorted(m_ns, b_ns + step, side='left')
    return ss.astype(np.int64), se.astype(np.int64)


def scen_label(adx_i, dev, atrcmp_i, adx_hi):
    strong = adx_i >= adx_hi
    if strong and dev < 0:  return 'break_down'
    if strong and dev > 0:  return 'break_up'
    if strong:              return 'strong_trend'
    if atrcmp_i:            return 'low_vol_range'
    if abs(dev) < 0.5:      return 'clean_range'
    return 'regime_shift'


def funding_sum(ft, fr, a_ns, b_ns):
    # (a_ns, b_ns] 구간에 정산된 펀딩률 합. ft/fr 는 시각오름차순.
    if ft is None or len(ft) == 0 or b_ns <= a_ns:
        return None
    lo = np.searchsorted(ft, a_ns, side='right')
    hi = np.searchsorted(ft, b_ns, side='right')
    if hi <= lo:
        return 0.0
    return float(fr[lo:hi].sum())


# ── OLD 엔진(정직화 전, 8h집계·낙관·고정펀딩·무캡) — 비교 참고용. stg9 run_bot 그대로 ──
def run_bot_legacy(df, sig, par):
    high = sig['high']; low = sig['low']; close = sig['close']; open_ = sig['open']; n = sig['n']
    ph_conf = sig['ph_conf']; pl_conf = sig['pl_conf']
    atr = sig['atr']; adx = sig['adx']; poc = sig['poc']; atrcmp = sig['atrcmp']
    years = sig['years']; eh = sig['eh']
    dist_max = par['dist_max']; adx_hi = par['adx_hi']; a = par['a']; d = par['d']
    short_on = par['short_on']; nDCA = par['nDCA']
    raw = np.arange(1, nDCA + 1, dtype=float); weights = raw / raw.sum()

    def fund(a_i, b_i):
        return FUND_8H * int(np.floor(eh[b_i] / 8.0) - np.floor(eh[a_i] / 8.0))

    lastPH = np.nan; lastPL = np.nan
    pos = 0.0; side = 0; avg = np.nan; entry_i = -1; nfilled = 0
    pb = 0; trailSL = np.nan; poc_t = np.nan; scen0 = None
    trades = []; i = 0
    while i < n:
        new_ph = i in ph_conf; new_pl = i in pl_conf
        if new_ph: lastPH = ph_conf[i]
        if new_pl: lastPL = pl_conf[i]
        A = atr[i]; P = poc[i]
        strong = adx[i] >= adx_hi
        dev = (close[i] - P) / A if (not np.isnan(P) and not np.isnan(A) and A > 0) else np.nan
        if pos != 0:
            if side == 1 and new_ph and not np.isnan(lastPL):
                pb += 1; ratio = min(a + d * (pb - 1), 0.95)
                cand = lastPH - ratio * (lastPH - lastPL)
                trailSL = cand if np.isnan(trailSL) else max(trailSL, cand)
            elif side == -1 and new_pl and not np.isnan(lastPH):
                pb += 1; ratio = min(a + d * (pb - 1), 0.95)
                cand = lastPL + ratio * (lastPH - lastPL)
                trailSL = cand if np.isnan(trailSL) else min(trailSL, cand)
            if (nfilled < nDCA and not np.isnan(dev) and not strong):
                addable = ((side == 1 and dev < 0 and abs(dev) <= dist_max and new_pl) or
                           (side == -1 and dev > 0 and abs(dev) <= dist_max and new_ph))
                if addable:
                    px = open_[i + 1] if i + 1 < n else close[i]
                    w = weights[nfilled] * (SHORT_SIZE if side == -1 else 1.0)
                    newp = pos + w; avg = (avg * pos + px * w) / newp
                    pos = newp; nfilled += 1
            exit_px = np.nan; reason = None
            if side == 1:
                if not np.isnan(poc_t) and high[i] >= poc_t: exit_px = poc_t; reason = 'tp_poc'
                elif not np.isnan(dev) and dev < -dist_max:  exit_px = close[i]; reason = 'sl_deep'
                elif not np.isnan(trailSL) and low[i] <= trailSL: exit_px = trailSL; reason = 'sl_trail'
                elif (i - entry_i) >= TIME_STOP: exit_px = close[i]; reason = 'time'
            else:
                if not np.isnan(poc_t) and low[i] <= poc_t: exit_px = poc_t; reason = 'tp_poc'
                elif not np.isnan(dev) and dev > dist_max:   exit_px = close[i]; reason = 'sl_deep'
                elif not np.isnan(trailSL) and high[i] >= trailSL: exit_px = trailSL; reason = 'sl_trail'
                elif (i - entry_i) >= TIME_STOP: exit_px = close[i]; reason = 'time'
            if reason is not None:
                R = side * (exit_px - avg) / avg * pos
                R -= COST_SIDE * 2 * pos + fund(entry_i, i)   # 왕복(진입+청산) 2배 비용
                trades.append({'entry_t': df.index[entry_i], 'exit_t': df.index[i], 'side': side,
                               'entry': avg, 'exit': exit_px, 'R': R, 'reason': reason,
                               'bars': i - entry_i, 'scen': scen0, 'year': years[i], 'nfilled': nfilled})
                pos = 0.0; side = 0; avg = np.nan; nfilled = 0; pb = 0
                trailSL = np.nan; poc_t = np.nan
            i += 1; continue
        if not np.isnan(dev) and not np.isnan(A) and not strong:
            if new_pl and dev < 0 and abs(dev) <= dist_max:
                px = open_[i + 1] if i + 1 < n else close[i]
                pos = weights[0]; side = 1; avg = px; nfilled = 1; entry_i = i
                pb = 0; trailSL = px - dist_max * A; poc_t = P
                scen0 = scen_label(adx[i], dev, bool(atrcmp[i]), adx_hi)
            elif short_on and new_ph and dev > 0 and abs(dev) <= dist_max:
                px = open_[i + 1] if i + 1 < n else close[i]
                pos = weights[0] * SHORT_SIZE; side = -1; avg = px; nfilled = 1; entry_i = i
                pb = 0; trailSL = px + dist_max * A; poc_t = P
                scen0 = scen_label(adx[i], dev, bool(atrcmp[i]), adx_hi)
        i += 1
    return trades


# ── 정직 엔진(1분봉 경로 청산 + 실펀딩 + sl_deep 손절깊이 + 1·2차필터 + stg7 차등sl/익절추적) ──
def run_bot_honest(df, sig, par, mO, mH, mL, mT, ss, se, ft, fr, sl_mult,
                   filter_mode='off', atr_lo=0.9, atr_hi=1.3, filter_scens=('regime_shift',),
                   oi_filter=False, oi_z_hi=0.0, oi_filter_scens=('regime_shift',),
                   sl_mult_regime_long=None, track_tp=False):
    high = sig['high']; low = sig['low']; close = sig['close']; open_ = sig['open']; n = sig['n']
    ph_conf = sig['ph_conf']; pl_conf = sig['pl_conf']
    atr = sig['atr']; adx = sig['adx']; poc = sig['poc']; atrcmp = sig['atrcmp']
    years = sig['years']; atr_ratio = sig['atr_ratio']; oi_z = sig['oi_z']
    dist_max = par['dist_max']; adx_hi = par['adx_hi']; a = par['a']; d = par['d']
    short_on = par['short_on']; nDCA = par['nDCA']
    raw = np.arange(1, nDCA + 1, dtype=float); weights = raw / raw.sum()
    fscen = set(filter_scens); oi_fscen = set(oi_filter_scens)
    tp_track = []   # stg7 ③ 익절후 가격추적 기록 [(side, exit_px, {bars:future_px})]

    def cur_sl_mult(scen_now, sd):
        # stg7 ② 거래별 sl_mult: regime_shift & 롱이면 차등값(있으면), 아니면 기본.
        if sl_mult_regime_long is not None and scen_now == 'regime_shift' and sd == 1:
            return sl_mult_regime_long
        return sl_mult

    def blocked(scen_now, ar, oz):
        # 진입 차단 판정. ar=atr_ratio(1차), oz=oi_zscore(2차). 각 NaN이면 그 필터는 통과(안전).
        if filter_mode != 'off' and scen_now in fscen and not np.isnan(ar):
            if filter_mode == 'precise' and ar < atr_lo:
                return True
            if filter_mode == 'both_ends' and ((ar < atr_lo) or (ar >= atr_hi)):
                return True
        if oi_filter and scen_now in oi_fscen and not np.isnan(oz):
            if oz >= oi_z_hi:
                return True
        return False

    lastPH = np.nan; lastPL = np.nan
    pos = 0.0; side = 0; avg = np.nan; entry_fill_bar = -1; nfilled = 0
    pb = 0; trailSL = np.nan; poc_t = np.nan; scen0 = None
    trades = []
    ambig_n = 0; held_n = 0   # 인트라바 모호도 측정용(OLD가 추측해야 했을 봉 비율)
    blocked_n = 0             # stg7: 필터가 차단한 진입 수
    j = 0
    while j < n:
        new_ph = j in ph_conf; new_pl = j in pl_conf
        if new_ph: lastPH = ph_conf[j]
        if new_pl: lastPL = pl_conf[j]
        A = atr[j]; P = poc[j]
        strong = adx[j] >= adx_hi
        dev = (close[j] - P) / A if (not np.isnan(P) and not np.isnan(A) and A > 0) else np.nan

        if pos != 0:
            # (1) 피보 스텝업 트레일 — 확정 피벗(과거가)으로 bar j 시작 전 알 수 있는 값만
            if side == 1 and new_ph and not np.isnan(lastPL):
                pb += 1; ratio = min(a + d * (pb - 1), 0.95)
                cand = lastPH - ratio * (lastPH - lastPL)
                trailSL = cand if np.isnan(trailSL) else max(trailSL, cand)
            elif side == -1 and new_pl and not np.isnan(lastPH):
                pb += 1; ratio = min(a + d * (pb - 1), 0.95)
                cand = lastPL + ratio * (lastPH - lastPL)
                trailSL = cand if np.isnan(trailSL) else min(trailSL, cand)

            # (2) bar j 의 청산 레벨 확정
            #     DEEP = sl_deep 레벨: POC에서 sl_mult×ATR 이탈한 가격(8h봉 j 값, 과거기반 known)
            #     stg7: 거래별 차등 sl_mult — regime_shift 롱이면 얕은값(설정 시), 아니면 기본.
            this_sl = cur_sl_mult(scen0, side)
            deep = (P - this_sl * A) if side == 1 else (P + this_sl * A)
            tp = poc_t
            # 스톱 후보(가격). 롱: 가장 높은 스톱이 먼저 닿음 / 숏: 가장 낮은 스톱이 먼저 닿음
            stops = []
            if not np.isnan(trailSL): stops.append((trailSL, 'sl_trail'))
            if not np.isnan(deep):    stops.append((deep, 'sl_deep'))

            # 인트라바 모호도: 8h봉 [low,high] 안에 tp와 스톱이 둘 다 들어오면 OLD는 추측해야 했음
            held_n += 1
            s0, s1 = int(ss[j]), int(se[j])
            if s1 > s0:
                bl = float(mL[s0:s1].min()); bh = float(mH[s0:s1].max())
                eff_stop_amb = (max(v for v, _ in stops) if (side == 1 and stops) else
                                (min(v for v, _ in stops) if stops else np.nan))
                tp_in = (not np.isnan(tp)) and (bl <= tp <= bh)
                st_in = (not np.isnan(eff_stop_amb)) and (bl <= eff_stop_amb <= bh)
                if tp_in and st_in:
                    ambig_n += 1

            # (3) 1분봉 경로로 '먼저 닿은' 출구 탐색 (같은 1분봉서 둘 다면 손절 우선=보수적)
            exit_px = np.nan; reason = None
            if s1 > s0:
                seg_h = mH[s0:s1]; seg_l = mL[s0:s1]
                if side == 1:
                    eff_stop = max((v for v, _ in stops), default=np.nan)
                    stop_reason = next((r for v, r in sorted(stops, reverse=True)), None) if stops else None
                    stop_hit = (seg_l <= eff_stop) if not np.isnan(eff_stop) else np.zeros(len(seg_l), bool)
                    tp_hit = (seg_h >= tp) if not np.isnan(tp) else np.zeros(len(seg_h), bool)
                else:
                    eff_stop = min((v for v, _ in stops), default=np.nan)
                    stop_reason = next((r for v, r in sorted(stops)), None) if stops else None
                    stop_hit = (seg_h >= eff_stop) if not np.isnan(eff_stop) else np.zeros(len(seg_h), bool)
                    tp_hit = (seg_l <= tp) if not np.isnan(tp) else np.zeros(len(seg_l), bool)
                si = int(np.argmax(stop_hit)) if stop_hit.any() else 10**9
                ti = int(np.argmax(tp_hit)) if tp_hit.any() else 10**9
                if si <= ti and si < 10**9:
                    exit_px = eff_stop; reason = stop_reason            # 보수적: 동타이밍이면 손절
                elif ti < 10**9:
                    exit_px = tp; reason = 'tp_poc'

            # (4) 출구 없으면: 시간손절(닫힌봉 종가) → 그래도 없으면 얕은영역 추가분할 결정(다음봉 체결)
            if reason is None and (j - entry_fill_bar) >= TIME_STOP:
                exit_px = close[j]; reason = 'time'
            if reason is None and (nfilled < nDCA and not np.isnan(dev) and not strong):
                addable = ((side == 1 and dev < 0 and abs(dev) <= dist_max and new_pl) or
                           (side == -1 and dev > 0 and abs(dev) <= dist_max and new_ph))
                if addable and (j + 1 < n):
                    px = open_[j + 1]
                    w = weights[nfilled] * (SHORT_SIZE if side == -1 else 1.0)
                    newp = pos + w; avg = (avg * pos + px * w) / newp
                    pos = newp; nfilled += 1

            if reason is not None:
                a_ns = int(mT[int(ss[entry_fill_bar])]) if se[entry_fill_bar] > ss[entry_fill_bar] else int(df.index.values[entry_fill_bar].astype('datetime64[ns]').astype('int64'))
                b_ns = int(df.index.values[j].astype('datetime64[ns]').astype('int64'))
                fsum = funding_sum(ft, fr, a_ns, b_ns)
                if fsum is None:
                    eh_a = a_ns / 3.6e12; eh_b = b_ns / 3.6e12
                    fund_cost = FUND_8H * int(np.floor(eh_b / 8.0) - np.floor(eh_a / 8.0))  # 폴백
                else:
                    fund_cost = side * fsum                      # 부호반영: 롱 양수펀딩=지불, 숏 양수=수취
                R = side * (exit_px - avg) / avg * pos
                R -= COST_SIDE * 2 * pos + fund_cost * pos   # 왕복(진입+청산) 2배 비용
                trades.append({'entry_t': df.index[entry_fill_bar], 'exit_t': df.index[j], 'side': side,
                               'entry': avg, 'exit': exit_px, 'R': R, 'reason': reason,
                               'bars': j - entry_fill_bar, 'scen': scen0, 'year': years[j], 'nfilled': nfilled})
                # stg7 ③ 익절후 가격추적(측정 전용): tp_poc일 때 이후 N봉이 익절가 대비 얼마나 더 갔나.
                #   롱은 더 오르면 +, 숏은 더 내리면 +(= side*(future-exit)/exit). ★봇 로직 아님(분석만).
                if track_tp and reason == 'tp_poc':
                    rec = {'side': side, 'exit_px': exit_px}
                    for nb in TP_TRACK_BARS:
                        fj = j + nb
                        if fj < n:
                            fpx = close[fj]
                            rec[nb] = side * (fpx - exit_px) / exit_px * 100.0  # % 추가이동(유리=+)
                        else:
                            rec[nb] = np.nan
                    tp_track.append(rec)
                pos = 0.0; side = 0; avg = np.nan; nfilled = 0; pb = 0
                trailSL = np.nan; poc_t = np.nan
            j += 1; continue

        # 미보유: 진입 결정(닫힌봉 j) → 체결 다음봉 시가(j+1)
        if not np.isnan(dev) and not np.isnan(A) and not strong and (j + 1 < n):
            if new_pl and dev < 0 and abs(dev) <= dist_max:
                scen_now = scen_label(adx[j], dev, bool(atrcmp[j]), adx_hi)
                if blocked(scen_now, atr_ratio[j], oi_z[j]):  # stg7: 1차(atr)+2차(OI) 진입 차단
                    blocked_n += 1
                else:
                    px = open_[j + 1]
                    pos = weights[0]; side = 1; avg = px; nfilled = 1; entry_fill_bar = j + 1
                    pb = 0; trailSL = px - dist_max * A; poc_t = P
                    scen0 = scen_now
            elif short_on and new_ph and dev > 0 and abs(dev) <= dist_max:
                scen_now = scen_label(adx[j], dev, bool(atrcmp[j]), adx_hi)
                if blocked(scen_now, atr_ratio[j], oi_z[j]):
                    blocked_n += 1
                else:
                    px = open_[j + 1]
                    pos = weights[0] * SHORT_SIZE; side = -1; avg = px; nfilled = 1; entry_fill_bar = j + 1
                    pb = 0; trailSL = px + dist_max * A; poc_t = P
                    scen0 = scen_now
        j += 1
    run_bot_honest.last_tp_track = tp_track   # stg7 ③ 익절추적 결과(함수속성, 호출부 변경 없이 회수)
    return trades, ambig_n, held_n, blocked_n
run_bot_honest.last_tp_track = []


def agg(trades, label, years=None):
    if years is not None:
        trades = [t for t in trades if t['year'] in years]
    if not trades:
        return {'cell': label, 'trades': 0, 'win_pct': 0, 'cumR_pct': 0, 'PF': 0, 'MDD_pct': 0, 'final_cap': START_CAP}
    R = np.array([t['R'] for t in trades])
    wins = R[R > 0]; losses = R[R < 0]
    gp = wins.sum(); gl = -losses.sum()
    pf = (gp / gl) if gl > 0 else 999.0
    cap = START_CAP; caps = [cap]
    for r in R:
        cap *= (1 + r * NOTIONAL_CAP); caps.append(cap)
    caps = np.array(caps); peak = -1e18; mdd = 0.0
    for c in caps:
        peak = max(peak, c)
        if peak > 0: mdd = min(mdd, (c - peak) / peak)
    return {'cell': label, 'trades': len(trades),
            'win_pct': round(len(wins) / len(trades) * 100, 1),
            'cumR_pct': round(R.sum() * 100, 2), 'PF': round(pf, 3),
            'MDD_pct': round(mdd * 100, 1), 'final_cap': round(float(caps[-1]), 0)}


def scen_breakdown(trades, years):
    out = {}
    for s in SCEN:
        rs = [t['R'] for t in trades if t['scen'] == s and t['year'] in years]
        out[s] = (len(rs), round(float(np.sum(rs)) * 100, 2) if rs else 0.0)
    return out


def main():
    print("[SidewayDCA_AlphaUp_05_Ch1_Stg7] ②regime롱 차등sl_mult 측정 + ③tp_poc 익절후 가격추적 측정")
    open(os.path.join(HERE, ".run_start"), 'w').close()
    data = find_data(); print(f"[data] {data}")
    df1m = load_1m(data)
    print(f"[load] {len(df1m):,}rows | vol={df1m.attrs['has_vol']} | "
          f"{df1m.index.min().date()}~{df1m.index.max().date()}")

    fpath = find_funding(); ft = fr = None; fund_note = "FALLBACK(고정0.0001)"
    if fpath is not None:
        try:
            ft, fr = load_funding(fpath)
            # 기간 대비 충분성 검사: 8h정산이면 (일수×3)건이 정상. 절반 미만이면 샘플/누락 경고.
            span_days = (df1m.index.max() - df1m.index.min()).days
            expect = max(1, span_days * 3)
            n = load_funding.n_loaded; ndrop = load_funding.n_dropped
            cover = 100.0 * n / expect
            warn = "" if cover >= 50 else "  ★경고:펀딩부족(샘플/누락 의심)"
            fund_note = f"REAL({os.path.basename(fpath)}, {n}건/예상{expect}, 커버{cover:.0f}%, 누락{ndrop}){warn}"
        except Exception as e:
            fund_note = f"FALLBACK(로드실패:{e})"
    print(f"[funding] {fund_note}")

    df8 = resample_tf(df1m, TF_MIN); sig = precompute(df8)
    ss, se = build_1m_map(df1m, df8)
    mO = df1m['open'].values; mH = df1m['high'].values; mL = df1m['low'].values
    mT = df1m.index.values.astype('datetime64[ns]').astype('int64')
    has_atrr = df1m.attrs.get('has_atrr', False)
    has_oi = df1m.attrs.get('has_oi', False)
    atrr_note = (f"atr_ratio 있음(1차필터 가동)" if has_atrr
                 else "★atr_ratio 없음 → 1차필터 비활성")
    oi_note = (f"oi_zscore 있음(2차필터 가동, src={df1m.attrs.get('oi_source','?')})" if has_oi
               else "★oi_zscore 없음 → 2차필터 비활성(merged_data 확인)")
    eff_filter = FILTER_MODE if has_atrr else 'off'
    print(f"[tf 8h] {len(df8)} bars | {atrr_note} | {oi_note}")

    rows = []

    # (A) OLD 낙관 엔진(8h집계, 고정펀딩, 무캡) — 정직화 전 기준
    tr_old = run_bot_legacy(df8, sig, BEST_PAR)
    a_old = agg(tr_old, "OLD_optimistic")
    a_old_tr = agg(tr_old, "OLD_train", TRAIN_YEARS); a_old_te = agg(tr_old, "OLD_test", TEST_YEARS)
    wfe_old = round((a_old_te['PF'] / a_old_tr['PF']) * 100, 1) if a_old_tr['PF'] > 0 else 0
    rows.append({'cell': 'OLD_optimistic(8h집계·고정펀딩·무캡)', 'cap_pct': '', 'full_trades': a_old['trades'],
                 'full_PF': a_old['PF'], 'full_cumR': a_old['cumR_pct'], 'full_MDD': a_old['MDD_pct'],
                 'full_win': a_old['win_pct'], 'tr_PF': a_old_tr['PF'], 'te_PF': a_old_te['PF'],
                 'te_cumR': a_old_te['cumR_pct'], 'WFE': wfe_old, 'sl_cap_hits': 0, 'ambig_pct': ''})

    # (B) 정직 엔진 기준선(sl_mult=1.8 확정, 필터OFF) + 인트라바 모호도 측정
    tr_h0, ambig_n, held_n, _ = run_bot_honest(df8, sig, BEST_PAR, mO, mH, mL, mT, ss, se, ft, fr, DEFAULT_SLMULT)
    ambig_pct = round(100.0 * ambig_n / held_n, 1) if held_n else 0.0
    a_h0 = agg(tr_h0, "HONEST_base")
    a_h0_tr = agg(tr_h0, "HONEST_train", TRAIN_YEARS); a_h0_te = agg(tr_h0, "HONEST_test", TEST_YEARS)
    wfe_h0 = round((a_h0_te['PF'] / a_h0_tr['PF']) * 100, 1) if a_h0_tr['PF'] > 0 else 0
    rows.append({'cell': f'HONEST_base(slmult={DEFAULT_SLMULT}·필터OFF)', 'cap_pct': DEFAULT_SLMULT,
                 'full_trades': a_h0['trades'],
                 'full_PF': a_h0['PF'], 'full_cumR': a_h0['cumR_pct'], 'full_MDD': a_h0['MDD_pct'],
                 'full_win': a_h0['win_pct'], 'tr_PF': a_h0_tr['PF'], 'te_PF': a_h0_te['PF'],
                 'te_cumR': a_h0_te['cumR_pct'], 'WFE': wfe_h0, 'sl_cap_hits': 0, 'ambig_pct': ambig_pct})

    # (C) sl_deep 손절깊이 sl_mult 스윕 (필터OFF, 1.7/1.8/1.9 고원 확인용)
    for sm in SL_MULT_GRID:
        tr_c, _, _, _ = run_bot_honest(df8, sig, BEST_PAR, mO, mH, mL, mT, ss, se, ft, fr, sm)
        ac = agg(tr_c, f"HONEST_slmult{sm}")
        ac_tr = agg(tr_c, "tr", TRAIN_YEARS); ac_te = agg(tr_c, "te", TEST_YEARS)
        wfe_c = round((ac_te['PF'] / ac_tr['PF']) * 100, 1) if ac_tr['PF'] > 0 else 0
        deep_hits = sum(1 for t in tr_c if t['reason'] == 'sl_deep')
        rows.append({'cell': f'HONEST_slmult_{sm}(필터OFF)', 'cap_pct': sm, 'full_trades': ac['trades'],
                     'full_PF': ac['PF'], 'full_cumR': ac['cumR_pct'], 'full_MDD': ac['MDD_pct'],
                     'full_win': ac['win_pct'], 'tr_PF': ac_tr['PF'], 'te_PF': ac_te['PF'],
                     'te_cumR': ac_te['cumR_pct'], 'WFE': wfe_c, 'sl_cap_hits': deep_hits, 'ambig_pct': ''})

    # (D) 비용은 OLD/HONEST 모두 왕복(2배)로 통일 적용됨 — 별도 참고행 없음.

    # (E) 정밀필터 검증 스윕 (sl_mult=1.8 고정, 필터 모드 비교) + 안정성 스윕 + stg7 OI 2차필터
    blk_report = {}
    def run_variant(label, fmode, short_sz_mult=1.0, atr_lo=ATR_LO, sl_mult=DEFAULT_SLMULT,
                    fscens=FILTER_SCENS, oi_filter=False, oi_z_hi=OI_Z_HI,
                    sl_rl=None, track_tp=False):
        global SHORT_SIZE
        old_ss = SHORT_SIZE
        SHORT_SIZE = old_ss * short_sz_mult
        tr, _, _, blk = run_bot_honest(df8, sig, BEST_PAR, mO, mH, mL, mT, ss, se, ft, fr,
                                       sl_mult, filter_mode=fmode,
                                       atr_lo=atr_lo, atr_hi=ATR_HI, filter_scens=fscens,
                                       oi_filter=oi_filter, oi_z_hi=oi_z_hi,
                                       oi_filter_scens=OI_FILTER_SCENS,
                                       sl_mult_regime_long=sl_rl, track_tp=track_tp)
        SHORT_SIZE = old_ss
        av = agg(tr, label); av_tr = agg(tr, "tr", TRAIN_YEARS); av_te = agg(tr, "te", TEST_YEARS)
        wfe = round((av_te['PF'] / av_tr['PF']) * 100, 1) if av_tr['PF'] > 0 else 0
        blk_report[label] = blk
        rows.append({'cell': label, 'cap_pct': sl_mult, 'full_trades': av['trades'],
                     'full_PF': av['PF'], 'full_cumR': av['cumR_pct'], 'full_MDD': av['MDD_pct'],
                     'full_win': av['win_pct'], 'tr_PF': av_tr['PF'], 'te_PF': av_te['PF'],
                     'te_cumR': av_te['cumR_pct'], 'WFE': wfe, 'sl_cap_hits': blk, 'ambig_pct': ''})
        return av

    if has_atrr:
        # 기준 비교
        run_variant('FILTER_off(slmult1.8)', 'off')
        run_variant('FILTER_precise(1차: atr<0.9,sl1.8,short0.5)', 'precise')
        run_variant('FILTER_both_ends(<0.9 or >=1.3)', 'both_ends')

        # ── 안정성 스윕(stg5 계승) ──
        for lo in ATR_LO_GRID:
            run_variant(f'STAB_atrLo_{lo}', 'precise', atr_lo=lo)
        for sm in SHORT_MULT_GRID:
            run_variant(f'STAB_short_{0.5*sm:.1f}x', 'precise', short_sz_mult=sm)
        run_variant('STAB_lowvol_KEEP(현행:regime만차단)', 'precise', fscens=('regime_shift',))
        run_variant('STAB_lowvol_BLOCK(regime+lowvol차단)', 'precise',
                    fscens=('regime_shift', 'low_vol_range'))
        for sl in SLMULT_ON_GRID:
            run_variant(f'STAB_slmultON_{sl}', 'precise', sl_mult=sl)

        # ── stg7 핵심: OI 2차필터 (1차 통과분을 OI급증으로 추가차단) ──
        if has_oi:
            run_variant('OI_1차만(precise)', 'precise', oi_filter=False)
            run_variant(f'OI_1차+2차(z>={OI_Z_HI})', 'precise', oi_filter=True, oi_z_hi=OI_Z_HI)
            # OI 임계 고원 확인(과최적화 점검)
            for z in OI_Z_GRID:
                run_variant(f'OI_z스윕_{z}', 'precise', oi_filter=True, oi_z_hi=z)
            # 최종 결합 후보: 1차+2차+숏0.7
            run_variant('OI_1차+2차+short0.7', 'precise', oi_filter=True, oi_z_hi=OI_Z_HI,
                        short_sz_mult=1.4)

            # ── stg7 ② regime_shift 롱 차등 sl_mult 측정 (1차+2차 기준, regime롱만 얕게) ──
            #   기준: OI 2차필터 적용(z>=OI_Z_HI). regime롱 sl_mult를 1.2/1.3/1.5/1.8로 흔들어 효과 측정.
            for srl in SLMULT_REGIME_LONG_GRID:
                tag = f'SL2_regimeLong_{srl}' + ('(=차등없음)' if srl == DEFAULT_SLMULT else '')
                run_variant(tag, 'precise', oi_filter=True, oi_z_hi=OI_Z_HI, sl_rl=srl)
        else:
            rows.append({'cell': '★OI_2차필터_불가(oi_zscore없음)', 'cap_pct': '', 'full_trades': '',
                         'full_PF': '', 'full_cumR': '', 'full_MDD': '', 'full_win': '',
                         'tr_PF': '', 'te_PF': '', 'te_cumR': '', 'WFE': '', 'sl_cap_hits': '', 'ambig_pct': ''})

        # ── stg7 ③ tp_poc 익절후 가격추적 측정 (최선 조합으로 1회 실행, 통계만) ──
        run_variant('TP_TRACK_run(측정용)', 'precise', oi_filter=has_oi, oi_z_hi=OI_Z_HI, track_tp=True)
        tp_track = run_bot_honest.last_tp_track
        if tp_track:
            tt = pd.DataFrame(tp_track)
            for nb in TP_TRACK_BARS:
                col = tt[nb].dropna()
                if len(col) > 0:
                    pos_ratio = 100.0 * (col > 0).mean()
                    rows.append({'cell': f'TPTRACK_+{nb}봉후', 'cap_pct': '',
                                 'full_trades': len(col), 'full_PF': round(col.mean(), 3),
                                 'full_cumR': round(col.median(), 3), 'full_MDD': round(col.max(), 2),
                                 'full_win': round(pos_ratio), 'tr_PF': round(col.min(), 2),
                                 'te_PF': '', 'te_cumR': '', 'WFE': '', 'sl_cap_hits': '', 'ambig_pct': ''})
            # TPTRACK 해석 메모: full_PF=평균추가이동%, full_cumR=중앙값%, full_win=더간거래비율%, full_MDD=최대, tr_PF=최소
    else:
        rows.append({'cell': '★FILTER_불가(atr_ratio 컬럼없음)', 'cap_pct': '', 'full_trades': '',
                     'full_PF': '', 'full_cumR': '', 'full_MDD': '', 'full_win': '',
                     'tr_PF': '', 'te_PF': '', 'te_cumR': '', 'WFE': '', 'sl_cap_hits': '', 'ambig_pct': ''})

    # 추천(메타): MDD를 폭주선 -15% 안으로 들이면서 full_cumR 최대인 sl_mult
    best_cap = None
    for r in rows:
        if isinstance(r['cap_pct'], (int, float)) and 'slmult_' in r['cell'] and r['full_MDD'] > -15.0:
            if best_cap is None or r['full_cumR'] > best_cap[1]:
                best_cap = (r['cap_pct'], r['full_cumR'], r['full_MDD'])
    cap_msg = (f"sl_mult {best_cap[0]} (MDD {best_cap[2]}%, cumR {best_cap[1]}%)"
               if best_cap else "MDD를 -15% 안으로 넣는 sl_mult 없음(추가검토)")

    # 필터 효과 + stg7 고원 판정
    def findrow(name_sub):
        for r in rows:
            if name_sub in str(r['cell']): return r
        return None
    def plateau(prefix, grid):
        # 같은 스윕군의 full_cumR 편차로 고원 여부 판정(편차 작으면 안정=고원)
        vals = [r['full_cumR'] for r in rows if str(r['cell']).startswith(prefix)
                and isinstance(r['full_cumR'], (int, float))]
        if len(vals) < 2: return "n/a"
        spread = max(vals) - min(vals)
        return f"편차{spread:.1f}%p({'고원' if spread < 6 else '뾰족-주의'})"

    filt_msg = "필터불가(atr_ratio없음)"
    if has_atrr:
        off = findrow('FILTER_off'); pre = findrow('FILTER_precise(1차')
        if off and pre:
            filt_msg = (f"OFF[PF{off['full_PF']} cumR{off['full_cumR']}% MDD{off['full_MDD']}% WFE{off['WFE']}%]"
                        f"->1차[PF{pre['full_PF']} cumR{pre['full_cumR']}% MDD{pre['full_MDD']}% WFE{pre['WFE']}%]")
        stab = (f"atrLo:{plateau('STAB_atrLo_', ATR_LO_GRID)} | "
                f"short:{plateau('STAB_short_', SHORT_MULT_GRID)} | "
                f"slmultON:{plateau('STAB_slmultON_', SLMULT_ON_GRID)}")
    else:
        stab = "안정성스윕 불가(atr_ratio없음)"

    # stg7 OI 2차필터 효과 + OI임계 고원
    oi_msg = "OI불가(oi_zscore없음)"
    if has_atrr and has_oi:
        o1 = findrow('OI_1차만'); o2 = findrow(f'OI_1차+2차(z>={OI_Z_HI})')
        if o1 and o2:
            oi_msg = (f"1차[PF{o1['full_PF']} cumR{o1['full_cumR']}% MDD{o1['full_MDD']}% WFE{o1['WFE']}%]"
                      f"->1차+2차[PF{o2['full_PF']} cumR{o2['full_cumR']}% MDD{o2['full_MDD']}% WFE{o2['WFE']}% 거래{o2['full_trades']}] "
                      f"| OI임계 {plateau('OI_z스윕_', OI_Z_GRID)}")

    # stg7 ② 차등 sl_mult 측정 요약 + ③ 익절추적 요약
    sl2_msg = ""
    base2 = findrow(f'OI_1차+2차(z>={OI_Z_HI})')
    best_srl = None
    for srl in SLMULT_REGIME_LONG_GRID:
        r = findrow(f'SL2_regimeLong_{srl}')
        if r and isinstance(r['full_cumR'], (int, float)):
            if best_srl is None or r['full_cumR'] > best_srl[1]:
                best_srl = (srl, r['full_cumR'], r['full_MDD'], r['full_PF'], r['WFE'])
    if base2 and best_srl:
        sl2_msg = (f"기준(차등없음)cumR{base2['full_cumR']}%MDD{base2['full_MDD']}% vs "
                   f"최선 regime롱sl={best_srl[0]}[cumR{best_srl[1]}% MDD{best_srl[2]}% PF{best_srl[3]} WFE{best_srl[4]}%]")
    tp_msg = ""
    tp1 = findrow('TPTRACK_+1봉후')
    if tp1:
        tp_msg = f"익절+1봉후 평균{tp1['full_PF']}% 더감, 더간거래 {tp1['full_win']}%"

    verdict = (f"VERDICT stg7 차등sl+익절추적 | ★OI: {oi_msg} | ②차등sl: {sl2_msg} | ③익절추적: {tp_msg} "
               f"| 고원 {stab} | atr_ratio={'O' if has_atrr else 'X'} oi={'O' if has_oi else 'X'}")
    print("[verdict] " + verdict)

    # ── 저장 ──
    out = [{'cell': verdict}] + rows
    pd.DataFrame(out).to_csv(os.path.join(HERE, "sdca_summary.csv"), index=False, encoding='utf-8-sig')

    # trades 저장용 거래원장: stg7 주력 = OI있으면 1차+2차, OI없고 atr만 있으면 1차, 둘다없으면 base
    if has_atrr and has_oi:
        save_tr, _, _, _ = run_bot_honest(df8, sig, BEST_PAR, mO, mH, mL, mT, ss, se, ft, fr,
                                          DEFAULT_SLMULT, filter_mode='precise',
                                          atr_lo=ATR_LO, atr_hi=ATR_HI, filter_scens=FILTER_SCENS,
                                          oi_filter=True, oi_z_hi=OI_Z_HI, oi_filter_scens=OI_FILTER_SCENS)
        trades_label = "FILTER_1차+2차(OI)"
    elif has_atrr:
        save_tr, _, _, _ = run_bot_honest(df8, sig, BEST_PAR, mO, mH, mL, mT, ss, se, ft, fr,
                                          DEFAULT_SLMULT, filter_mode='precise',
                                          atr_lo=ATR_LO, atr_hi=ATR_HI, filter_scens=FILTER_SCENS)
        trades_label = "FILTER_1차만"
    else:
        save_tr = tr_h0; trades_label = "base_slmult1.8"

    # trades = stg7 주력 거래원장(필터 가동시 precise)
    td = [{'entry_t': t['entry_t'].strftime('%Y-%m-%d %H:%M'), 'exit_t': t['exit_t'].strftime('%Y-%m-%d %H:%M'),
           'side': t['side'], 'year': t['year'], 'entry': round(t['entry'], 2), 'exit': round(t['exit'], 2),
           'R_pct': round(t['R'] * 100, 4), 'reason': t['reason'], 'bars': t['bars'],
           'scen': t['scen'], 'nfilled': t['nfilled']} for t in save_tr]
    if not td:
        pd.DataFrame(columns=['entry_t','exit_t','side','year','entry','exit','R_pct','reason','bars','scen','nfilled'])\
            .to_csv(os.path.join(HERE, "sdca_trades.csv"), index=False, encoding='utf-8-sig')
    else:
        pd.DataFrame(td).to_csv(os.path.join(HERE, "sdca_trades.csv"), index=False, encoding='utf-8-sig')

    # scenarios = stg7 주력 거래의 8시나리오(train/test)
    sb_tr = scen_breakdown(save_tr, TRAIN_YEARS); sb_te = scen_breakdown(save_tr, TEST_YEARS)
    pd.DataFrame([{'cell': f'SCEN_{s}', 'train_n': sb_tr[s][0], 'train_cumR': sb_tr[s][1],
                   'test_n': sb_te[s][0], 'test_cumR': sb_te[s][1]} for s in SCEN])\
        .to_csv(os.path.join(HERE, "sdca_scenarios.csv"), index=False, encoding='utf-8-sig')

    # check.py 가 읽을 메트릭(인트라바 모호도 + stg7 필터 거래라벨)
    with open(os.path.join(HERE, ".intrabar_metric"), "w", encoding="utf-8") as f:
        f.write(f"ambig_pct={ambig_pct}\nheld_bars={held_n}\nambig_bars={ambig_n}\ntrades_label={trades_label}\n")

    print(f"[save] sdca_summary.csv + sdca_trades.csv({trades_label}) + sdca_scenarios.csv")


if __name__ == "__main__":
    main()
