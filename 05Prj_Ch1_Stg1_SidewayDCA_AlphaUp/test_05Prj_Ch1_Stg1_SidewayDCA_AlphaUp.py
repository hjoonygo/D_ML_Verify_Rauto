# -*- coding: utf-8 -*-
# [파일명] test_05Prj_Ch1_Stg1_SidewayDCA_AlphaUp.py
# 코드길이: 약 470줄 | 내부버전: SidewayDCA_AlphaUp_05_Ch1_Stg1 (측정정직화) | 로직 축약/생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명]
#   stg9 봇(얕은 POC 되돌림 + S_TREND 게이트 + 피보청산)의 "성과가 거짓이 아닌지" 다시 잰다(측정 정직화).
#   알파를 새로 더하지 않는다. 세 군데만 정직하게 고친다:
#     ① 1분봉 경로 청산  : 8시간봉 1개의 고저만 보고 "이익이 먼저 닿았다"고 낙관하던 것을,
#                          그 8시간 속 1분봉을 순서대로 밟아 '진짜 먼저 닿은' 익절/손절로 청산.
#                          (같은 1분봉 안에서 둘 다 닿으면 보수적으로 손절 우선 = 더 정직)
#     ② 실펀딩           : 펀딩을 고정 0.0001에서 funding_history_8h.csv 실제값(음수 포함)으로.
#                          롱은 펀딩 음수면 받고, 숏은 펀딩 양수면 받는다(부호 반영).
#     ③ 손실 하드캡 스윕 : 거래당 최대 손실(진입가 대비 %)을 -1.2 ~ -2.0% 9단계로 각각 테스트.
#                          1분봉 경로에서 그 캡 가격에 닿으면 즉시 강제청산(sl_cap).
#   비교용으로 OLD(낙관) 엔진과 2-side 비용(참고) 행도 함께 내서 '정직화 전/후' 차이를 보여준다.
#
# [★사용명칭 정의 — 손실캡 R의 뜻]  ※추정 방지 위해 명시
#   여기서 캡 값(1.2~2.0)은 '거래당 최대 가격손실 %(진입가 대비)'다.
#   예) 1.5 = 진입가에서 1.5% 역행하면 강제청산. (사장님이 R을 ATR배수로 의도하셨다면 알려주시면 재정의)
#   사장님이 이전에 본 sdca_trades.csv의 R_pct(가격수익률%) 단위와 동일선상이라 직관적으로 맞춤.
#
# [미래참조 차단]
#   - 진입/피보트레일/DCA/시간손절 '결정'은 전부 닫힌 8시간봉 기준, 체결은 다음 8시간봉 시가.
#   - 1분봉 경로는 보유 중 '실제 가격이 지나간 길'만 사용(미래봉 안 봄). 첫 닿는 순간 청산 후 멈춤.
#   - 피벗은 right=1봉 뒤 확정값(과거가격)만 사용. ATR/ADX/POC 과거봉만. shift(-) 없음.
#   - 펀딩은 보유기간에 실제 정산된 과거 펀딩만 합산.
#
# [PATH] 실행: D:\ML\verify\05Prj_Ch1_Stg1_SidewayDCA_AlphaUp\ . 데이터/펀딩: 상위 D:\ML\verify\ .
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
#   run_bot_honest(df8,sig,par,mO,mH,mL,mT,ss,se,ft,fr,cap_pct,cost_sides) 1분봉경로 정직엔진 -> (trades, ambig_n, held_n)
#   agg(trades,label,years)             거래 -> PF/누적R/MDD/거래수/승률 (stg9 재사용)
#   scen_breakdown(trades,years)        거래 -> 8시나리오별 손익 (stg9 재사용)
#   main()                              전체 실행 + 캡스윕 + CSV 3종
#
# [상태변수] pos(수량비율) avg(평단) side(+1롱/-1숏) entry_fill_bar nfilled pb trailSL poc_t cap_px scen0
# ==============================================================================

import os, sys, itertools
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)

# ── CFG (stg9 계승) ──
COST_SIDE   = 0.0005 + 0.0002      # 편도 비용(수수료0.05%+슬리피지0.02%)
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

# ── stg1 측정정직화 설정 ──
TF_MIN   = 8 * 60                  # stg9 VERDICT 채택 = 8h 고정 (stg1은 이 한 구성을 정직하게 재측정)
BEST_PAR = {'dist_max': 1.5, 'adx_hi': 22, 'a': 0.3, 'd': 0.1, 'short_on': 1, 'nDCA': 1}  # stg9 VERDICT
CAP_GRID = [1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0]   # 거래당 최대손실 %(진입가 대비) 스윕
NO_CAP   = 999.0                   # 캡 미적용 sentinel(거의 안 닿음)

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
    cands = ["funding_history_8h.csv", "sample_BTCUSDT_funding_history_8h.csv",
             "BTCUSDT_funding_history_8h.csv"]
    for d in [PARENT, HERE, r"D:\ML\verify", r"D:\ML\Verify"]:
        for c in cands:
            p = os.path.join(d, c)
            if os.path.exists(p):
                return p
    return None


def load_1m(path):
    head = pd.read_csv(path, nrows=1)
    cols = ['timestamp', 'open', 'high', 'low', 'close']
    has_vol = 'volume' in head.columns
    if has_vol:
        cols.append('volume')
    df = pd.read_csv(path, usecols=cols, index_col='timestamp', parse_dates=True)
    if getattr(df.index, 'tz', None) is not None:
        df.index = df.index.tz_localize(None)
    df = df.sort_index()
    df.attrs['has_vol'] = has_vol
    return df


def load_funding(path):
    # 컬럼 유연 처리: fundingTime/fundingRate (대소문자/이름 변형 허용)
    df = pd.read_csv(path)
    tcol = next((c for c in df.columns if 'time' in c.lower()), df.columns[0])
    rcol = next((c for c in df.columns if 'rate' in c.lower()), df.columns[1])
    t = pd.to_datetime(df[tcol], utc=True, errors='coerce').dt.tz_localize(None)
    r = pd.to_numeric(df[rcol], errors='coerce')
    ok = t.notna() & r.notna()
    t = t[ok].values.astype('datetime64[ns]').astype('int64')
    r = r[ok].values.astype('float64')
    order = np.argsort(t)
    return t[order], r[order]


def resample_tf(df1m, tf_min):
    rule = f"{tf_min}min"
    agg = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}
    if df1m.attrs.get('has_vol', False):
        agg['volume'] = 'sum'
    out = df1m.resample(rule, label='left', closed='left').agg(agg).dropna()
    out.attrs['has_vol'] = df1m.attrs.get('has_vol', False)
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
    return {'high': high, 'low': low, 'close': close, 'open': df['open'].values, 'n': n,
            'ph_conf': ph_conf, 'pl_conf': pl_conf, 'atr': atr, 'adx': adx,
            'atrcmp': atrcmp, 'poc': poc, 'years': years, 'eh': eh}


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
                R -= COST_SIDE * pos + fund(entry_i, i)
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


# ── 정직 엔진(1분봉 경로 청산 + 실펀딩 + 손실캡) ──
def run_bot_honest(df, sig, par, mO, mH, mL, mT, ss, se, ft, fr, cap_pct, cost_sides):
    high = sig['high']; low = sig['low']; close = sig['close']; open_ = sig['open']; n = sig['n']
    ph_conf = sig['ph_conf']; pl_conf = sig['pl_conf']
    atr = sig['atr']; adx = sig['adx']; poc = sig['poc']; atrcmp = sig['atrcmp']
    years = sig['years']
    dist_max = par['dist_max']; adx_hi = par['adx_hi']; a = par['a']; d = par['d']
    short_on = par['short_on']; nDCA = par['nDCA']
    raw = np.arange(1, nDCA + 1, dtype=float); weights = raw / raw.sum()

    lastPH = np.nan; lastPL = np.nan
    pos = 0.0; side = 0; avg = np.nan; entry_fill_bar = -1; nfilled = 0
    pb = 0; trailSL = np.nan; poc_t = np.nan; cap_px = np.nan; scen0 = None
    trades = []
    ambig_n = 0; held_n = 0   # 인트라바 모호도 측정용(OLD가 추측해야 했을 봉 비율)
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
            #     DEEP = sl_deep 레벨화: POC에서 dist_max ATR 이탈한 가격(8h봉 j 값, 과거기반 known)
            deep = (P - dist_max * A) if side == 1 else (P + dist_max * A)
            tp = poc_t
            # 스톱 후보(가격). 롱: 가장 높은 스톱이 먼저 닿음 / 숏: 가장 낮은 스톱이 먼저 닿음
            stops = []
            if not np.isnan(trailSL): stops.append((trailSL, 'sl_trail'))
            if not np.isnan(deep):    stops.append((deep, 'sl_deep'))
            if not np.isnan(cap_px):  stops.append((cap_px, 'sl_cap'))

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
                    cap_px = (avg * (1 - cap_pct / 100.0) if side == 1
                              else avg * (1 + cap_pct / 100.0)) if cap_pct < NO_CAP else np.nan

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
                R -= COST_SIDE * cost_sides * pos + fund_cost * pos
                trades.append({'entry_t': df.index[entry_fill_bar], 'exit_t': df.index[j], 'side': side,
                               'entry': avg, 'exit': exit_px, 'R': R, 'reason': reason,
                               'bars': j - entry_fill_bar, 'scen': scen0, 'year': years[j], 'nfilled': nfilled})
                pos = 0.0; side = 0; avg = np.nan; nfilled = 0; pb = 0
                trailSL = np.nan; poc_t = np.nan; cap_px = np.nan
            j += 1; continue

        # 미보유: 진입 결정(닫힌봉 j) → 체결 다음봉 시가(j+1)
        if not np.isnan(dev) and not np.isnan(A) and not strong and (j + 1 < n):
            if new_pl and dev < 0 and abs(dev) <= dist_max:
                px = open_[j + 1]
                pos = weights[0]; side = 1; avg = px; nfilled = 1; entry_fill_bar = j + 1
                pb = 0; trailSL = px - dist_max * A; poc_t = P
                cap_px = avg * (1 - cap_pct / 100.0) if cap_pct < NO_CAP else np.nan
                scen0 = scen_label(adx[j], dev, bool(atrcmp[j]), adx_hi)
            elif short_on and new_ph and dev > 0 and abs(dev) <= dist_max:
                px = open_[j + 1]
                pos = weights[0] * SHORT_SIZE; side = -1; avg = px; nfilled = 1; entry_fill_bar = j + 1
                pb = 0; trailSL = px + dist_max * A; poc_t = P
                cap_px = avg * (1 + cap_pct / 100.0) if cap_pct < NO_CAP else np.nan
                scen0 = scen_label(adx[j], dev, bool(atrcmp[j]), adx_hi)
        j += 1
    return trades, ambig_n, held_n


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


def cap_hits(trades):
    return sum(1 for t in trades if t['reason'] == 'sl_cap')


def main():
    print("[SidewayDCA_AlphaUp_05_Ch1_Stg1] 측정정직화: 1분봉경로청산 + 실펀딩 + 손실캡스윕")
    open(os.path.join(HERE, ".run_start"), 'w').close()
    data = find_data(); print(f"[data] {data}")
    df1m = load_1m(data)
    print(f"[load] {len(df1m):,}rows | vol={df1m.attrs['has_vol']} | "
          f"{df1m.index.min().date()}~{df1m.index.max().date()}")

    fpath = find_funding(); ft = fr = None; fund_note = "FALLBACK(고정0.0001)"
    if fpath is not None:
        try:
            ft, fr = load_funding(fpath)
            fund_note = f"REAL({os.path.basename(fpath)}, {len(ft)}건)"
        except Exception as e:
            fund_note = f"FALLBACK(로드실패:{e})"
    print(f"[funding] {fund_note}")

    df8 = resample_tf(df1m, TF_MIN); sig = precompute(df8)
    ss, se = build_1m_map(df1m, df8)
    mO = df1m['open'].values; mH = df1m['high'].values; mL = df1m['low'].values
    mT = df1m.index.values.astype('datetime64[ns]').astype('int64')
    print(f"[tf 8h] {len(df8)} bars precomputed | 1m map ok")

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

    # (B) 정직 엔진 무캡 (베이스라인) + 인트라바 모호도 측정
    tr_h0, ambig_n, held_n = run_bot_honest(df8, sig, BEST_PAR, mO, mH, mL, mT, ss, se, ft, fr, NO_CAP, 1)
    ambig_pct = round(100.0 * ambig_n / held_n, 1) if held_n else 0.0
    a_h0 = agg(tr_h0, "HONEST_nocap")
    a_h0_tr = agg(tr_h0, "HONEST_train", TRAIN_YEARS); a_h0_te = agg(tr_h0, "HONEST_test", TEST_YEARS)
    wfe_h0 = round((a_h0_te['PF'] / a_h0_tr['PF']) * 100, 1) if a_h0_tr['PF'] > 0 else 0
    rows.append({'cell': 'HONEST_nocap(1m경로·실펀딩·무캡)', 'cap_pct': 'none', 'full_trades': a_h0['trades'],
                 'full_PF': a_h0['PF'], 'full_cumR': a_h0['cumR_pct'], 'full_MDD': a_h0['MDD_pct'],
                 'full_win': a_h0['win_pct'], 'tr_PF': a_h0_tr['PF'], 'te_PF': a_h0_te['PF'],
                 'te_cumR': a_h0_te['cumR_pct'], 'WFE': wfe_h0, 'sl_cap_hits': 0, 'ambig_pct': ambig_pct})

    # (C) 손실캡 스윕 1.2 ~ 2.0
    for cp in CAP_GRID:
        tr_c, _, _ = run_bot_honest(df8, sig, BEST_PAR, mO, mH, mL, mT, ss, se, ft, fr, cp, 1)
        ac = agg(tr_c, f"HONEST_cap{cp}")
        ac_tr = agg(tr_c, "tr", TRAIN_YEARS); ac_te = agg(tr_c, "te", TEST_YEARS)
        wfe_c = round((ac_te['PF'] / ac_tr['PF']) * 100, 1) if ac_tr['PF'] > 0 else 0
        rows.append({'cell': f'HONEST_cap_{cp}%', 'cap_pct': cp, 'full_trades': ac['trades'],
                     'full_PF': ac['PF'], 'full_cumR': ac['cumR_pct'], 'full_MDD': ac['MDD_pct'],
                     'full_win': ac['win_pct'], 'tr_PF': ac_tr['PF'], 'te_PF': ac_te['PF'],
                     'te_cumR': ac_te['cumR_pct'], 'WFE': wfe_c, 'sl_cap_hits': cap_hits(tr_c), 'ambig_pct': ''})

    # (D) 참고행: 정직엔진 무캡 + 왕복비용(2-side) — 비용 과소차감 의심건 영향 가늠(★승인필요, 베이스 아님)
    tr_2s, _, _ = run_bot_honest(df8, sig, BEST_PAR, mO, mH, mL, mT, ss, se, ft, fr, NO_CAP, 2)
    a_2s = agg(tr_2s, "REF_2sideCost")
    rows.append({'cell': 'REF_왕복비용2배(참고·승인필요)', 'cap_pct': 'none', 'full_trades': a_2s['trades'],
                 'full_PF': a_2s['PF'], 'full_cumR': a_2s['cumR_pct'], 'full_MDD': a_2s['MDD_pct'],
                 'full_win': a_2s['win_pct'], 'tr_PF': '', 'te_PF': '', 'te_cumR': '', 'WFE': '',
                 'sl_cap_hits': 0, 'ambig_pct': ''})

    # 캡 추천(메타): MDD를 폭주선 -15% 안으로 들이면서 full_cumR 손실이 가장 적은 캡
    best_cap = None
    for r in rows:
        if isinstance(r['cap_pct'], (int, float)) and r['full_MDD'] > -15.0:
            if best_cap is None or r['full_cumR'] > best_cap[1]:
                best_cap = (r['cap_pct'], r['full_cumR'], r['full_MDD'])
    cap_msg = (f"cap {best_cap[0]}% (MDD {best_cap[2]}%, cumR {best_cap[1]}%)"
               if best_cap else "MDD를 -15% 안으로 넣는 캡 없음(추가검토)")

    verdict = (f"VERDICT stg1 정직화 | OLD PF={a_old['PF']} cumR={a_old['cumR_pct']}% MDD={a_old['MDD_pct']}% "
               f"-> HONEST(무캡) PF={a_h0['PF']} cumR={a_h0['cumR_pct']}% MDD={a_h0['MDD_pct']}% WFE={wfe_h0}% "
               f"| 인트라바모호도={ambig_pct}% | 펀딩={fund_note} | 캡추천={cap_msg}")
    print("[verdict] " + verdict)

    # ── 저장 ──
    out = [{'cell': verdict}] + rows
    pd.DataFrame(out).to_csv(os.path.join(HERE, "sdca_summary.csv"), index=False, encoding='utf-8-sig')

    # trades = HONEST 무캡 베이스라인(정직화 후 거래원장)
    td = [{'entry_t': t['entry_t'].strftime('%Y-%m-%d %H:%M'), 'exit_t': t['exit_t'].strftime('%Y-%m-%d %H:%M'),
           'side': t['side'], 'year': t['year'], 'entry': round(t['entry'], 2), 'exit': round(t['exit'], 2),
           'R_pct': round(t['R'] * 100, 4), 'reason': t['reason'], 'bars': t['bars'],
           'scen': t['scen'], 'nfilled': t['nfilled']} for t in tr_h0]
    if not td:
        pd.DataFrame(columns=['entry_t','exit_t','side','year','entry','exit','R_pct','reason','bars','scen','nfilled'])\
            .to_csv(os.path.join(HERE, "sdca_trades.csv"), index=False, encoding='utf-8-sig')
    else:
        pd.DataFrame(td).to_csv(os.path.join(HERE, "sdca_trades.csv"), index=False, encoding='utf-8-sig')

    # scenarios = HONEST 무캡 8시나리오(train/test)
    sb_tr = scen_breakdown(tr_h0, TRAIN_YEARS); sb_te = scen_breakdown(tr_h0, TEST_YEARS)
    pd.DataFrame([{'cell': f'SCEN_{s}', 'train_n': sb_tr[s][0], 'train_cumR': sb_tr[s][1],
                   'test_n': sb_te[s][0], 'test_cumR': sb_te[s][1]} for s in SCEN])\
        .to_csv(os.path.join(HERE, "sdca_scenarios.csv"), index=False, encoding='utf-8-sig')

    # check.py 가 읽을 인트라바 모호도 메트릭(별도 1줄 파일)
    with open(os.path.join(HERE, ".intrabar_metric"), "w", encoding="utf-8") as f:
        f.write(f"ambig_pct={ambig_pct}\nheld_bars={held_n}\nambig_bars={ambig_n}\n")

    print("[save] sdca_summary.csv + sdca_trades.csv + sdca_scenarios.csv")


if __name__ == "__main__":
    main()
