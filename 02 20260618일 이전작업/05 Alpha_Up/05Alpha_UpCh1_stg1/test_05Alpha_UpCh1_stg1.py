# -*- coding: utf-8 -*-
# [FILE] test_05Alpha_UpCh1_stg1.py
# 코드길이: 약 470줄 | 내부버전명: 05Alpha_Up_Ch1_SLfibAB_stg1 | 전체 출력, 축약/생략 없음
# ==============================================================================
# [목적] stg9(SideWayDCA_Alpha) 봇에서 '피보 트레일링 SL 공식' 단 한 가지만 A안/B안으로
#        바꿔, 같은 데이터·같은 파라미터 그리드로 동시에 돌려 어느 쪽이 알파가 큰지 직접 비교한다.
#        그 외 로직(진입·장세게이트·사이징·청산판정·시간손절)은 stg9 원본 그대로 보존한다(한 로직만 수정).
#
# [A안 vs B안 — 이번 비교의 전부]
#   A안 'HIGH_BASE' (stg9 원본 그대로):
#       롱: cand = lastPH - ratio*(lastPH-lastPL) ; SL=max(SL,cand)  (고점 기준)
#       숏: cand = lastPL + ratio*(lastPH-lastPL) ; SL=min(SL,cand)  (저점 기준)
#       → ratio가 커질수록 cand가 가격에서 멀어져, max/min 때문에 첫 단계값에 사실상 고정(고점 갱신 의존).
#   B안 'LOW_BASE' (사장님 설계 의도: 눌림목 기준, 단계마다 타이트화):
#       롱: cand = lastPL + ratio*(lastPH-lastPL) ; SL=max(SL,cand)  (눌림목 기준, 위로 또박또박)
#       숏: cand = lastPH - ratio*(lastPH-lastPL) ; SL=min(SL,cand)  (반등고점 기준, 아래로 또박또박)
#       → 단계가 오를수록 SL이 가격 쪽으로 붙어 이익을 점점 잠근다(동결 없음).
#   * A와 B는 롱/숏에서 공식이 정확히 swap 관계. ratio=0.5에서만 두 안이 우연히 일치.
#
# [롱·숏] 사장님 지시 '테스트니까 숏롱 둘다' → GRID_short=[0,1] 유지, 결과를 방향별(롱PF/숏PF)로 분해 기록.
#
# [진입] (stg9 원본 보존) POC 아래 얕은 이탈(<=dist_max ATR)+새저점 → 롱. POC 위 얕은+새고점 → 숏(0.5배).
#        S_TREND(ADX>=adx_hi)면 신규진입 OFF(지뢰밭 회피). 얕은영역 내 1회 추가분할(균등, 깊은DCA 아님).
# [청산] (stg9 원본 보존) (1)POC익절 tp_poc (2)|dev|>dist_max 깊어짐 sl_deep (3)피보트레일 sl_trail (4)시간.
# [사이징] (stg9 원본 보존) 1.5% 리스크예산 손절폭 역산 + 명목 2.5배 캡.
# [비용] 수수료0.05%+슬리피지0.02%(편도) + 펀딩0.01%/8h. 결정=닫힌봉, 체결=다음봉시가.
# [미래참조 차단] 피벗 r봉 뒤 확정. ATR/ADX/POC 과거봉만. shift(-) 없음. 진입 px=open_[i+1].
# [PATH] 실행: D:\ML\verify\05Alpha_UpCh1_stg1\ . 데이터: 상위 D:\ML\verify\ (자동탐색).
# [DATA] 상위 Merged_Data_with_Regime_Features.csv (없으면 merged_data.csv). volume 자동감지.
# [OUTPUT] (실행폴더) sdca_summary.csv + sdca_trades.csv + sdca_scenarios.csv → check.py가 정리.
# [SPEED] TF별 신호(피벗/ATR/ADX/POC) 1회 사전계산 후 캐시. 그리드(768런)는 가벼운 거래루프만 재실행.
#
# [FUNCTIONS]
#   find_data()              In:(없음)            Out: 데이터 csv 경로            데이터 자동탐색
#   load_1m(path)            In: csv경로          Out: 1분봉 DataFrame(+vol감지)  로드/정렬/tz제거
#   resample_tf(df,tf_min)   In: 1분봉,분         Out: TF봉 OHLCV                 리샘플
#   compute_atr(h,l,c,P)     In: 고저종,기간      Out: ATR배열                    변동성
#   compute_adx(h,l,c,n)     In: 고저종,기간      Out: ADX배열                    추세강도
#   compute_poc(df,N,B)      In: df,룩백,빈수     Out: POC배열                    거래량 최다가격대
#   precompute(df)           In: TF df            Out: 신호 dict                  TF별 1회 사전계산
#   fib_cand(mode,side,...)  In: 모드,방향,피벗   Out: SL 후보가 cand            ★A/B 분기 핵심
#   scen_label(...)          In: adx,dev,압축,임계 Out: 시나리오명                8시나리오 사후라벨
#   run_bot(df,sig,par)      In: TFdf,sig,파라미터 Out: trades 리스트             ★진입/청산 엔진
#   agg(trades,label,yrs,sf) In: 거래,라벨,연도,방향필터 Out: PF/누적R/MDD/승률  성과집계(방향분해 지원)
#   scen_breakdown(...)      In: 거래,연도        Out: 시나리오별 손익            8시나리오 분해
#   main()                   In:(없음)            Out: CSV 3종                    그리드+A/B비교+WFE
# [변수] pos(수량비율) side(+1롱/-1숏) avg(평단) entry_i nfilled pb trailSL poc_t dev dist_max sl_mode
# ==============================================================================

import os, sys, itertools
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)

# ── CFG (stg9 원본 동일) ──
COST_SIDE   = 0.0005 + 0.0002
FUND_8H     = 0.0001
RISK_BUDGET = 0.015
NOTIONAL_CAP= 2.5
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

# ── 탐색 그리드 (stg9 원본 전체) ──
GRID_TF      = [4*60, 6*60, 8*60, 12*60]
GRID_distmax = [1.0, 1.5]
GRID_adxhi   = [22, 25, 28]
GRID_a       = [0.3, 0.5]
GRID_d       = [0.1, 0.2]
GRID_short   = [0, 1]
GRID_nDCA    = [1, 2]
SHORT_SIZE   = 0.5
# ★이번 추가: SL 공식 A/B 스위치. 이것만 늘려 비교(384런 x 2 = 768런)
GRID_SLMODE  = ['HIGH_BASE', 'LOW_BASE']   # A안=HIGH_BASE(원본), B안=LOW_BASE(설계)

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


def resample_tf(df1m, tf_min):
    rule = f"{tf_min}min"
    agg_map = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}
    if df1m.attrs.get('has_vol', False):
        agg_map['volume'] = 'sum'
    out = df1m.resample(rule, label='left', closed='left').agg(agg_map).dropna()
    out.attrs['has_vol'] = df1m.attrs.get('has_vol', False)
    return out


def compute_atr(high, low, close, Pd):
    n = len(close); tr = np.zeros(n)
    if n < 2:
        return np.zeros(n)
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
    if N < 2:
        return np.zeros(N)
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


def fib_cand(sl_mode, side, ratio, lastPH, lastPL):
    # ★A/B 분기의 전부. 이 함수 하나만 stg9 원본과 다르다.
    #   A안(HIGH_BASE): 롱=고점기준, 숏=저점기준  (stg9 원본 287/245행과 동일)
    #   B안(LOW_BASE) : 롱=눌림목기준, 숏=반등고점기준 (사장님 설계: 단계마다 타이트화)
    span = lastPH - lastPL
    if sl_mode == 'HIGH_BASE':
        return (lastPH - ratio * span) if side == 1 else (lastPL + ratio * span)
    else:  # LOW_BASE
        return (lastPL + ratio * span) if side == 1 else (lastPH - ratio * span)


def scen_label(adx_i, dev, atrcmp_i, adx_hi):
    strong = adx_i >= adx_hi
    if strong and dev < 0:  return 'break_down'
    if strong and dev > 0:  return 'break_up'
    if strong:              return 'strong_trend'
    if atrcmp_i:            return 'low_vol_range'
    if abs(dev) < 0.5:      return 'clean_range'
    return 'regime_shift'


def run_bot(df, sig, par):
    high = sig['high']; low = sig['low']; close = sig['close']; open_ = sig['open']; n = sig['n']
    ph_conf = sig['ph_conf']; pl_conf = sig['pl_conf']
    atr = sig['atr']; adx = sig['adx']; atrcmp = sig['atrcmp']; poc = sig['poc']
    years = sig['years']; eh = sig['eh']
    dist_max = par['dist_max']; adx_hi = par['adx_hi']; a = par['a']; d = par['d']
    short_on = par['short_on']; nDCA = par['nDCA']; sl_mode = par['sl_mode']

    raw = np.arange(1, nDCA + 1, dtype=float); weights = raw / raw.sum()

    def fund(a_i, b_i):
        return FUND_8H * int(np.floor(eh[b_i] / 8.0) - np.floor(eh[a_i] / 8.0))

    lastPH = np.nan; lastPL = np.nan
    pos = 0.0; side = 0; avg = np.nan; entry_i = -1; nfilled = 0
    pb = 0; trailSL = np.nan; poc_t = np.nan; scen0 = None
    trades = []
    i = 0
    while i < n:
        new_ph = i in ph_conf; new_pl = i in pl_conf
        if new_ph: lastPH = ph_conf[i]
        if new_pl: lastPL = pl_conf[i]
        A = atr[i]; P = poc[i]
        strong = adx[i] >= adx_hi
        dev = (close[i] - P) / A if (not np.isnan(P) and not np.isnan(A) and A > 0) else np.nan

        if pos != 0:
            # 피보 스텝업 SL (롱: 새고점 / 숏: 새저점) — A/B는 fib_cand 안에서만 갈림
            if side == 1 and new_ph and not np.isnan(lastPL):
                pb += 1; ratio = min(a + d * (pb - 1), 0.95)
                cand = fib_cand(sl_mode, 1, ratio, lastPH, lastPL)
                trailSL = cand if np.isnan(trailSL) else max(trailSL, cand)
            elif side == -1 and new_pl and not np.isnan(lastPH):
                pb += 1; ratio = min(a + d * (pb - 1), 0.95)
                cand = fib_cand(sl_mode, -1, ratio, lastPH, lastPL)
                trailSL = cand if np.isnan(trailSL) else min(trailSL, cand)
            # 얕은영역 내 추가 분할(균등, 깊은DCA 아님)
            if (nfilled < nDCA and not np.isnan(dev) and not strong):
                addable = ((side == 1 and dev < 0 and abs(dev) <= dist_max and new_pl) or
                           (side == -1 and dev > 0 and abs(dev) <= dist_max and new_ph))
                if addable:
                    px = open_[i + 1] if i + 1 < n else close[i]
                    w = weights[nfilled] * (SHORT_SIZE if side == -1 else 1.0)
                    newp = pos + w; avg = (avg * pos + px * w) / newp
                    pos = newp; nfilled += 1
            # 청산 판정 (stg9 원본 보존)
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

        # 미보유: 1차 진입 (얕은 이탈 + S_TREND 아님) — stg9 원본 보존
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


def agg(trades, label, years=None, side_filter=None):
    if years is not None:
        trades = [t for t in trades if t['year'] in years]
    if side_filter is not None:
        trades = [t for t in trades if t['side'] == side_filter]
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


def pick_best(summary_runs, sl_mode):
    # 해당 sl_mode 런 중 train PF 최고(거래>=15) 셀을 고른다
    best = None
    for row in summary_runs:
        if row['sl_mode'] != sl_mode:
            continue
        if row['tr_trades'] >= 15 and (best is None or row['tr_PF'] > best['tr_PF']):
            best = row
    return best


def main():
    print("[05Alpha_Up_Ch1_SLfibAB_stg1] A(HIGH_BASE) vs B(LOW_BASE) 피보 SL 공식 비교")
    open(os.path.join(HERE, ".run_start"), 'w').close()
    data = find_data(); print(f"[data] {data}")
    df1m = load_1m(data)
    print(f"[load] {len(df1m):,}rows | vol={df1m.attrs['has_vol']} | "
          f"{df1m.index.min().date()}~{df1m.index.max().date()}")

    tf_df = {}; tf_sig = {}
    for tf in GRID_TF:
        dd = resample_tf(df1m, tf); tf_df[tf] = dd; tf_sig[tf] = precompute(dd)
        print(f"[tf {tf//60}h] {len(dd)} bars precomputed")

    base_combos = list(itertools.product(GRID_distmax, GRID_adxhi, GRID_a, GRID_d, GRID_short, GRID_nDCA))
    total = len(GRID_TF) * len(base_combos) * len(GRID_SLMODE)
    print(f"[grid] TF{len(GRID_TF)} x params{len(base_combos)} x SL{len(GRID_SLMODE)} = {total} runs")

    summary_runs = []
    trades_by_cell = {}   # (sl_mode, cell) -> trades  (best 추출용 저장)
    done = 0
    for tf in GRID_TF:
        df = tf_df[tf]; sig = tf_sig[tf]
        for sl_mode in GRID_SLMODE:
            for (dm, axh, a, d, sh, nd) in base_combos:
                par = {'dist_max': dm, 'adx_hi': axh, 'a': a, 'd': d,
                       'short_on': sh, 'nDCA': nd, 'sl_mode': sl_mode}
                trades = run_bot(df, sig, par)
                lab = f"TF{tf//60}h_dm{dm}_adx{axh}_a{a}_d{d}_sh{sh}_n{nd}"
                mTr = agg(trades, lab + "_train", TRAIN_YEARS)
                mTe = agg(trades, lab + "_test", TEST_YEARS)
                summary_runs.append({'sl_mode': sl_mode, 'cell': lab, 'TF_h': tf // 60,
                                     'dist_max': dm, 'adx_hi': axh, 'a': a, 'd': d, 'short_on': sh, 'nDCA': nd,
                                     'tr_trades': mTr['trades'], 'tr_PF': mTr['PF'], 'tr_cumR': mTr['cumR_pct'], 'tr_MDD': mTr['MDD_pct'],
                                     'te_trades': mTe['trades'], 'te_PF': mTe['PF'], 'te_cumR': mTe['cumR_pct'], 'te_MDD': mTe['MDD_pct']})
                trades_by_cell[(sl_mode, lab)] = trades
                done += 1
        print(f"[progress] TF{tf//60}h done ({done}/{total})")

    # ── A안/B안 각각 best 선정 + WFE + 방향분해 ──
    verdict_lines = []
    scen_rows = []
    best_meta = {}
    for sl_mode in GRID_SLMODE:
        b = pick_best(summary_runs, sl_mode)
        tag = 'A_HIGH_BASE' if sl_mode == 'HIGH_BASE' else 'B_LOW_BASE'
        if b is None:
            verdict_lines.append(f"{tag}: 거래 표본부족(train<15)")
            best_meta[sl_mode] = None
            for s in SCEN:
                scen_rows.append({'sl_mode': sl_mode, 'cell': f'SCEN_{s}', 'train_n': 0, 'train_cumR': 0, 'test_n': 0, 'test_cumR': 0})
            continue
        btr = trades_by_cell[(sl_mode, b['cell'])]
        m_tr = agg(btr, tag + "_train", TRAIN_YEARS); m_te = agg(btr, tag + "_test", TEST_YEARS)
        wfe = round((m_te['PF'] / m_tr['PF']) * 100, 1) if m_tr['PF'] > 0 else 0
        # 방향 분해 (롱=+1 / 숏=-1)
        L = agg(btr, tag + "_long", None, side_filter=1)
        S = agg(btr, tag + "_short", None, side_filter=-1)
        verdict_lines.append(
            f"{tag} BEST {b['cell']} | train PF={m_tr['PF']} cumR={m_tr['cumR_pct']}% MDD={m_tr['MDD_pct']}% "
            f"| test PF={m_te['PF']} cumR={m_te['cumR_pct']}% MDD={m_te['MDD_pct']}% | WFE={wfe}% "
            f"| LONG PF={L['PF']} n{L['trades']} cumR{L['cumR_pct']}% / SHORT PF={S['PF']} n{S['trades']} cumR{S['cumR_pct']}%")
        best_meta[sl_mode] = {'b': b, 'tr': m_tr, 'te': m_te, 'wfe': wfe, 'L': L, 'S': S, 'btr': btr}
        sb_tr = scen_breakdown(btr, TRAIN_YEARS); sb_te = scen_breakdown(btr, TEST_YEARS)
        for s in SCEN:
            scen_rows.append({'sl_mode': sl_mode, 'cell': f'SCEN_{s}',
                              'train_n': sb_tr[s][0], 'train_cumR': sb_tr[s][1],
                              'test_n': sb_te[s][0], 'test_cumR': sb_te[s][1]})

    # ── 최종 A vs B 결론 ──
    a_meta = best_meta.get('HIGH_BASE'); b_meta = best_meta.get('LOW_BASE')
    if a_meta and b_meta:
        a_te = a_meta['te']['PF']; b_te = b_meta['te']['PF']
        if b_te > a_te:
            concl = f"결론: B(LOW_BASE 설계대로)가 우위 (test PF {b_te} > {a_te}) -> 알파상승"
        elif a_te > b_te:
            concl = f"결론: A(HIGH_BASE 원본)가 우위 (test PF {a_te} > {b_te}) -> 설계수정 불필요"
        else:
            concl = f"결론: A=B 동률 (test PF {a_te})"
    else:
        concl = "결론: 한쪽 이상 표본부족 - 데이터/그리드 점검 필요"
    verdict = "VERDICT: " + concl + " || " + " || ".join(verdict_lines)
    print("[verdict] " + verdict)

    # ── CSV 저장 (전량 파일로만) ──
    out = [{'cell': verdict}] + summary_runs
    pd.DataFrame(out).to_csv(os.path.join(HERE, "sdca_summary.csv"), index=False, encoding='utf-8-sig')

    # trades: A best + B best 합본 (sl_mode 컬럼으로 구분)
    all_td = []
    for sl_mode in GRID_SLMODE:
        meta = best_meta.get(sl_mode)
        if not meta:
            continue
        tag = 'A_HIGH_BASE' if sl_mode == 'HIGH_BASE' else 'B_LOW_BASE'
        for t in meta['btr']:
            all_td.append({'sl_mode': tag,
                           'entry_t': t['entry_t'].strftime('%Y-%m-%d %H:%M'),
                           'exit_t': t['exit_t'].strftime('%Y-%m-%d %H:%M'),
                           'side': t['side'], 'year': t['year'],
                           'entry': round(t['entry'], 2), 'exit': round(t['exit'], 2),
                           'R_pct': round(t['R'] * 100, 4), 'reason': t['reason'],
                           'bars': t['bars'], 'scen': t['scen'], 'nfilled': t['nfilled']})
    if all_td:
        pd.DataFrame(all_td).to_csv(os.path.join(HERE, "sdca_trades.csv"), index=False, encoding='utf-8-sig')
    else:
        pd.DataFrame(columns=['sl_mode', 'entry_t', 'exit_t', 'side', 'year', 'entry', 'exit',
                              'R_pct', 'reason', 'bars', 'scen', 'nfilled']).to_csv(
            os.path.join(HERE, "sdca_trades.csv"), index=False, encoding='utf-8-sig')

    # scenarios: A 8행 + B 8행 = 16행 (sl_mode 컬럼)
    if not scen_rows:
        scen_rows = [{'sl_mode': m, 'cell': f'SCEN_{s}', 'train_n': 0, 'train_cumR': 0, 'test_n': 0, 'test_cumR': 0}
                     for m in GRID_SLMODE for s in SCEN]
    pd.DataFrame(scen_rows).to_csv(os.path.join(HERE, "sdca_scenarios.csv"), index=False, encoding='utf-8-sig')
    print("[save] sdca_summary.csv + sdca_trades.csv + sdca_scenarios.csv")


if __name__ == "__main__":
    main()
