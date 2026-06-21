# -*- coding: utf-8 -*-
# [FILE] test_04All_IDEA4Concept_ch9_SideWayDCA_Alpha_stg10.py
# CODE LENGTH: approx 540 lines | INTERNAL VER: stg10 gate-relax + uptrend-shrink | full output, no omission
#
# [PURPOSE] 두 변경의 효과를 한 봇에서 분리 측정:
#   (Q1) 게이트 완화 ML: adxhi(임계) × gate_mode(strict/long_only/short_only/off) 그리드
#   (Q2) 상승장 사이즈 축소 ML: 실시간 상승장 판정 + trend_size 가중치 그리드
#
# [stg9 직전 분석 근거]
#   상승장 64건 중 sl_deep 45% (29건), 깊은손절 평균 -0.475%, 5건 합산 -9.24%
#   MDD 구간(24-12~25-02) 10건 중 7건 sl_deep, 양방향 5:5, 누적 -6.37%
#   사후 8시나리오: S3(상승장 30% 축소) 수익 31.7% MDD -7.4% 최우선
#
# [실시간 상승장 판정 — 사후 ±7% 라벨과 일치하는 단순규칙]
#   진입봉 i 직전 60일 가격변화율: (close[i]/close[i-look60] - 1)*100
#   ≥ +7%면 상승장 → trend_size 가중치 적용 (1.0/0.5/0.3/0.0)
#   가설 15%: 사후 라벨과 실시간 가격기준이 충분히 일치하는지 검증해야 함
#
# [게이트 4모드]
#   strict     = ADX>=adxhi면 양방향 OFF (현재 stg9 방식)
#   long_only  = ADX>=adxhi면 숏만 OFF (롱은 허용)
#   short_only = ADX>=adxhi면 롱만 OFF (숏만 허용)
#   off        = ADX 무시, 항상 진입 허용
#
# [그리드 압축] 기존 best(dist_max=1.5, a=0.3, d=0.1, short=1, nDCA=1) 고정.
#   변동: TF(4) × adxhi(4) × gate(4) × trend_size(4) = 256셀
#
# [best 선정 — 2종]
#   best_PF       = train PF 최고 (제약 없음)
#   best_PF_capped = train PF 최고 + MDD 한도(-15%) 안 + 거래 >=15건
#
# [기타] 기존 stg9 동일: 1m경로 추적, 실펀딩 csv 자동탐색, 인트라바 모호 계측, 비용 2배 스트레스
# [PATH] D:\ML\verify\ 본진. 데이터: 상위. 출력: 폴더 안 sdca_*.csv + 상위 00WorkHstr
# ==============================================================================

import os, sys, itertools
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)

# ── CFG (Basic_Trading_Environment_Setup.docx 준수) ──
COST_SIDE   = 0.0005 + 0.0002
FUND_8H_FALLBACK = 0.0001
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
MDD_CAP_PCT = -15.0      # 사장님 폭주 한도

# ── 그리드 ──
GRID_TF       = [4*60, 6*60, 8*60, 12*60]
GRID_distmax  = [1.5]                       # stg9 best 고정
GRID_a        = [0.3]                       # stg9 best 고정
GRID_d        = [0.1]                       # stg9 best 고정
GRID_short    = [1]                         # stg9 best 고정(숏ON 알파검증)
GRID_nDCA     = [1]                         # stg9 best 고정
GRID_adxhi    = [22, 28, 35, 99]            # ★Q1: 게이트 임계 완화
GRID_gate     = ['strict', 'long_only', 'short_only', 'off']   # ★Q1: 게이트 방향
GRID_trend_sz = [1.0, 0.5, 0.3, 0.0]        # ★Q2: 상승장 사이즈
TREND_LOOKBACK_DAYS = 60
TREND_PCT_THRESHOLD = 0.07                  # ±7% (사후라벨과 일치)
SHORT_SIZE    = 0.5

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
    """실펀딩 csv 자동탐색 (없으면 None → 고정값 fallback)."""
    cands = ["sample_BTCUSDT_funding_history_8h.csv", "BTCUSDT_funding.csv", "funding.csv"]
    for d in [PARENT, HERE, r"D:\ML\verify", r"D:\ML\Verify"]:
        for c in cands:
            p = os.path.join(d, c)
            if os.path.exists(p):
                return p
    return None


def load_funding(path):
    """8h 펀딩 csv → 시각→rate 딕셔너리. 컬럼 자동감지."""
    if path is None: return {}
    try:
        df = pd.read_csv(path)
        # 시각 컬럼 자동감지
        tcol = next((c for c in df.columns if 'time' in c.lower() or 'date' in c.lower()), df.columns[0])
        rcol = next((c for c in df.columns if 'rate' in c.lower() or 'fund' in c.lower()), df.columns[-1])
        df[tcol] = pd.to_datetime(df[tcol], errors='coerce')
        df = df.dropna(subset=[tcol])
        if getattr(df[tcol].dt, 'tz', None) is not None:
            df[tcol] = df[tcol].dt.tz_localize(None)
        return dict(zip(df[tcol], df[rcol].astype(float)))
    except Exception as e:
        print(f"[funding load warn] {e}, fallback 고정값")
        return {}


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


def precompute(df, tf_min):
    """TF별 신호 1회 사전계산. 상승장 판정 lookback도 TF별 봉수로 변환."""
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
    poc = compute_poc(df, POC_LOOKBACK, POC_BINS)
    years = df.index.year.values
    eh = ((df.index - pd.Timestamp('1970-01-01')) / pd.Timedelta(hours=1)).values.astype('float64')
    # 상승장 판정용: TF별 60일 봉수
    look60 = int((TREND_LOOKBACK_DAYS * 24 * 60) / tf_min)
    uptrend = np.zeros(n, dtype=bool)
    for i in range(look60, n):
        if close[i-look60] > 0 and (close[i]/close[i-look60] - 1) >= TREND_PCT_THRESHOLD:
            uptrend[i] = True
    return {'high': high, 'low': low, 'close': close, 'open': df['open'].values, 'n': n,
            'ph_conf': ph_conf, 'pl_conf': pl_conf, 'atr': atr, 'adx': adx,
            'poc': poc, 'years': years, 'eh': eh, 'uptrend': uptrend, 'index': df.index}


def scen_label(adx_i, dev, adx_hi):
    strong = adx_i >= adx_hi
    if strong and dev < 0:  return 'break_down'
    if strong and dev > 0:  return 'break_up'
    if strong:              return 'strong_trend'
    if abs(dev) < 0.5:      return 'clean_range'
    return 'regime_shift'


def funding_cost(funding_map, t_enter, t_exit):
    """보유기간 동안 8h 펀딩 누적. funding_map 없으면 고정값."""
    if not funding_map:
        # fallback 고정값
        hrs = (t_exit - t_enter).total_seconds()/3600
        return FUND_8H_FALLBACK * (hrs / 8.0)
    total = 0.0
    for ts, rate in funding_map.items():
        if t_enter < ts <= t_exit:
            total += rate
    return total


def run_bot(df, sig, par, funding_map):
    high = sig['high']; low = sig['low']; close = sig['close']; open_ = sig['open']; n = sig['n']
    ph_conf = sig['ph_conf']; pl_conf = sig['pl_conf']
    atr = sig['atr']; adx = sig['adx']; poc = sig['poc']
    uptrend = sig['uptrend']; idx = sig['index']
    years = sig['years']; eh = sig['eh']
    dist_max = par['dist_max']; adx_hi = par['adx_hi']; a = par['a']; d = par['d']
    short_on = par['short_on']; nDCA = par['nDCA']
    gate_mode = par['gate']; trend_sz = par['trend_sz']

    raw = np.arange(1, nDCA + 1, dtype=float); weights = raw / raw.sum()

    lastPH = np.nan; lastPL = np.nan
    pos = 0.0; side = 0; avg = np.nan; entry_i = -1; nfilled = 0
    pb = 0; trailSL = np.nan; poc_t = np.nan; scen0 = None; entry_uptrend = False
    trades = []
    i = 0
    while i < n:
        new_ph = i in ph_conf; new_pl = i in pl_conf
        if new_ph: lastPH = ph_conf[i]
        if new_pl: lastPL = pl_conf[i]
        A = atr[i]; P = poc[i]
        strong = adx[i] >= adx_hi
        # 게이트 4모드 적용
        if gate_mode == 'strict':
            block_long = strong; block_short = strong
        elif gate_mode == 'long_only':
            block_long = False; block_short = strong
        elif gate_mode == 'short_only':
            block_long = strong; block_short = False
        else:   # 'off'
            block_long = False; block_short = False
        dev = (close[i] - P) / A if (not np.isnan(P) and not np.isnan(A) and A > 0) else np.nan

        if pos != 0:
            # 피보 스텝업 SL
            if side == 1 and new_ph and not np.isnan(lastPL):
                pb += 1; ratio = min(a + d * (pb - 1), 0.95)
                cand = lastPH - ratio * (lastPH - lastPL)
                trailSL = cand if np.isnan(trailSL) else max(trailSL, cand)
            elif side == -1 and new_pl and not np.isnan(lastPH):
                pb += 1; ratio = min(a + d * (pb - 1), 0.95)
                cand = lastPL + ratio * (lastPH - lastPL)
                trailSL = cand if np.isnan(trailSL) else min(trailSL, cand)
            # 추가 분할(얕은영역내)
            if (nfilled < nDCA and not np.isnan(dev)):
                addable = False
                if side == 1 and dev < 0 and abs(dev) <= dist_max and new_pl and not block_long:
                    addable = True
                elif side == -1 and dev > 0 and abs(dev) <= dist_max and new_ph and not block_short:
                    addable = True
                if addable:
                    px = open_[i + 1] if i + 1 < n else close[i]
                    # ★상승장 가중치(진입 시점의 uptrend 기준 유지)
                    sz_mult = trend_sz if entry_uptrend else 1.0
                    w = weights[nfilled] * (SHORT_SIZE if side == -1 else 1.0) * sz_mult
                    if w > 0:   # trend_sz=0이면 추가 안함
                        newp = pos + w; avg = (avg * pos + px * w) / newp
                        pos = newp; nfilled += 1
            # 청산
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
                R -= COST_SIDE * pos + funding_cost(funding_map, idx[entry_i], idx[i]) * pos
                trades.append({'entry_t': idx[entry_i], 'exit_t': idx[i], 'side': side,
                               'entry': avg, 'exit': exit_px, 'R': R, 'reason': reason,
                               'bars': i - entry_i, 'scen': scen0, 'year': years[i], 'nfilled': nfilled,
                               'uptrend': int(entry_uptrend)})
                pos = 0.0; side = 0; avg = np.nan; nfilled = 0; pb = 0
                trailSL = np.nan; poc_t = np.nan; entry_uptrend = False
            i += 1; continue

        # 미보유: 1차 진입
        if not np.isnan(dev) and not np.isnan(A):
            cur_uptrend = bool(uptrend[i])
            sz_mult = trend_sz if cur_uptrend else 1.0
            if sz_mult > 0:   # trend_sz=0이고 상승장이면 진입 안 함
                # 롱
                if not block_long and new_pl and dev < 0 and abs(dev) <= dist_max:
                    px = open_[i + 1] if i + 1 < n else close[i]
                    pos = weights[0] * sz_mult; side = 1; avg = px; nfilled = 1; entry_i = i
                    pb = 0; trailSL = px - dist_max * A; poc_t = P
                    scen0 = scen_label(adx[i], dev, adx_hi); entry_uptrend = cur_uptrend
                # 숏
                elif short_on and not block_short and new_ph and dev > 0 and abs(dev) <= dist_max:
                    px = open_[i + 1] if i + 1 < n else close[i]
                    pos = weights[0] * SHORT_SIZE * sz_mult; side = -1; avg = px; nfilled = 1; entry_i = i
                    pb = 0; trailSL = px + dist_max * A; poc_t = P
                    scen0 = scen_label(adx[i], dev, adx_hi); entry_uptrend = cur_uptrend
        i += 1

    return trades


def agg(trades, label, years=None):
    if years is not None:
        trades = [t for t in trades if t['year'] in years]
    if not trades:
        return {'cell': label, 'trades': 0, 'win_pct': 0, 'cumR_pct': 0, 'PF': 0, 'MDD_pct': 0}
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
    print("[stg10] gate-relax(adxhi×gate) + uptrend-shrink(trend_sz) ML grid")
    open(os.path.join(HERE, ".run_start"), 'w').close()
    data = find_data(); print(f"[data] {data}")
    fpath = find_funding()
    funding_map = load_funding(fpath)
    print(f"[funding] {'REAL '+str(fpath)+' ('+str(len(funding_map))+'건)' if funding_map else 'FALLBACK 고정 0.01%/8h'}")
    df1m = load_1m(data)
    print(f"[load] {len(df1m):,}rows | vol={df1m.attrs['has_vol']} | "
          f"{df1m.index.min().date()}~{df1m.index.max().date()}")

    tf_df = {}; tf_sig = {}
    for tf in GRID_TF:
        d = resample_tf(df1m, tf); tf_df[tf] = d; tf_sig[tf] = precompute(d, tf)
        upcnt = int(tf_sig[tf]['uptrend'].sum())
        print(f"[tf {tf//60}h] {len(d)}봉 precomputed | 상승장 봉수={upcnt} ({upcnt/len(d)*100:.1f}%)")

    summary = []; best_pf = None; best_pf_capped = None
    combos = list(itertools.product(GRID_distmax, GRID_adxhi, GRID_a, GRID_d, GRID_short, GRID_nDCA,
                                     GRID_gate, GRID_trend_sz))
    total = len(GRID_TF) * len(combos)
    print(f"[grid] TF{len(GRID_TF)} × params{len(combos)} = {total} runs")

    cnt = 0
    for tf in GRID_TF:
        df = tf_df[tf]; sig = tf_sig[tf]
        for (dm, axh, a, d, sh, nd, gt, ts) in combos:
            par = {'dist_max': dm, 'adx_hi': axh, 'a': a, 'd': d, 'short_on': sh,
                   'nDCA': nd, 'gate': gt, 'trend_sz': ts}
            trades = run_bot(df, sig, par, funding_map)
            lab = f"TF{tf//60}h_adx{axh}_gate{gt}_ts{ts}"
            mTr = agg(trades, lab + "_train", TRAIN_YEARS)
            mTe = agg(trades, lab + "_test", TEST_YEARS)
            mAll = agg(trades, lab + "_all")
            summary.append({'cell': lab, 'TF_h': tf // 60, 'adx_hi': axh,
                            'gate': gt, 'trend_sz': ts,
                            'all_trades': mAll['trades'], 'all_PF': mAll['PF'],
                            'all_cumR': mAll['cumR_pct'], 'all_MDD': mAll['MDD_pct'],
                            'tr_trades': mTr['trades'], 'tr_PF': mTr['PF'], 'tr_cumR': mTr['cumR_pct'],
                            'te_trades': mTe['trades'], 'te_PF': mTe['PF'], 'te_cumR': mTe['cumR_pct'],
                            'wfe': round(mTe['PF']/mTr['PF']*100, 1) if mTr['PF']>0 else 0})
            # best 선정
            if mTr['trades'] >= 15:
                if best_pf is None or mTr['PF'] > best_pf[0]:
                    best_pf = (mTr['PF'], par, tf, trades)
                if mAll['MDD_pct'] >= MDD_CAP_PCT and (best_pf_capped is None or mTr['PF'] > best_pf_capped[0]):
                    best_pf_capped = (mTr['PF'], par, tf, trades, mAll['MDD_pct'])
            cnt += 1
            if cnt % 32 == 0:
                print(f"  [progress] {cnt}/{total}")

    # ──VERDICT 구성──
    v_lines = []
    if best_pf is not None:
        _, p, tf, tr = best_pf
        bm_tr = agg(tr, "bp_train", TRAIN_YEARS); bm_te = agg(tr, "bp_test", TEST_YEARS)
        bm_all = agg(tr, "bp_all")
        wfe = round((bm_te['PF']/bm_tr['PF'])*100, 1) if bm_tr['PF']>0 else 0
        v_lines.append(f"BEST_PF(제약없음) TF{tf//60}h adxhi{p['adx_hi']} gate={p['gate']} ts={p['trend_sz']}"
                       f" | train PF={bm_tr['PF']} cumR={bm_tr['cumR_pct']}% MDD={bm_tr['MDD_pct']}%"
                       f" | test PF={bm_te['PF']} cumR={bm_te['cumR_pct']}% MDD={bm_te['MDD_pct']}%"
                       f" | all MDD={bm_all['MDD_pct']}% WFE={wfe}%")
    if best_pf_capped is not None:
        _, p, tf, tr, _ = best_pf_capped
        bm_tr = agg(tr, "bc_train", TRAIN_YEARS); bm_te = agg(tr, "bc_test", TEST_YEARS)
        bm_all = agg(tr, "bc_all")
        wfe = round((bm_te['PF']/bm_tr['PF'])*100, 1) if bm_tr['PF']>0 else 0
        v_lines.append(f"BEST_PF_MDD_CAPPED(-15%안) TF{tf//60}h adxhi{p['adx_hi']} gate={p['gate']} ts={p['trend_sz']}"
                       f" | train PF={bm_tr['PF']} cumR={bm_tr['cumR_pct']}% MDD={bm_tr['MDD_pct']}%"
                       f" | test PF={bm_te['PF']} cumR={bm_te['cumR_pct']}% MDD={bm_te['MDD_pct']}%"
                       f" | all MDD={bm_all['MDD_pct']}% WFE={wfe}%")
    else:
        v_lines.append("BEST_PF_MDD_CAPPED=없음 (MDD -15% 안에 train 15+거래 없음)")

    # 게이트 모드별 평균 효과
    sdf = pd.DataFrame(summary)
    if len(sdf) > 0:
        g_agg = sdf.groupby('gate').agg(avg_PF=('all_PF','mean'), avg_MDD=('all_MDD','mean'),
                                          avg_cumR=('all_cumR','mean'), avg_n=('all_trades','mean')).round(2)
        v_lines.append(f"GATE효과: {dict(g_agg.to_dict('index'))}")
        t_agg = sdf.groupby('trend_sz').agg(avg_PF=('all_PF','mean'), avg_MDD=('all_MDD','mean'),
                                              avg_cumR=('all_cumR','mean')).round(2)
        v_lines.append(f"TREND_SZ효과: {dict(t_agg.to_dict('index'))}")

    verdict = "VERDICT stg10 | " + " || ".join(v_lines)
    print("\n[verdict]", verdict)

    # 결과 저장
    summary.insert(0, {'cell': verdict})
    pd.DataFrame(summary).to_csv(os.path.join(HERE, "sdca_summary.csv"), index=False, encoding='utf-8-sig')

    # best_pf_capped 우선, 없으면 best_pf trades 저장
    pick = best_pf_capped if best_pf_capped is not None else best_pf
    if pick is not None:
        if len(pick) == 5:
            _, bpar, btf, btr, _ = pick
        else:
            _, bpar, btf, btr = pick
        td = [{'entry_t': t['entry_t'].strftime('%Y-%m-%d %H:%M'),
               'exit_t': t['exit_t'].strftime('%Y-%m-%d %H:%M'),
               'side': t['side'], 'year': t['year'], 'entry': round(t['entry'], 2),
               'exit': round(t['exit'], 2), 'R_pct': round(t['R'] * 100, 4),
               'reason': t['reason'], 'bars': t['bars'], 'scen': t['scen'],
               'nfilled': t['nfilled'], 'uptrend': t['uptrend']} for t in btr]
        pd.DataFrame(td).to_csv(os.path.join(HERE, "sdca_trades.csv"), index=False, encoding='utf-8-sig')
        sb_tr = scen_breakdown(btr, TRAIN_YEARS); sb_te = scen_breakdown(btr, TEST_YEARS)
        scen_rows = [{'cell': f'SCEN_{s}', 'train_n': sb_tr[s][0], 'train_cumR': sb_tr[s][1],
                       'test_n': sb_te[s][0], 'test_cumR': sb_te[s][1]} for s in SCEN]
        pd.DataFrame(scen_rows).to_csv(os.path.join(HERE, "sdca_scenarios.csv"), index=False, encoding='utf-8-sig')
    else:
        pd.DataFrame(columns=['entry_t','exit_t','side','year','entry','exit','R_pct',
                              'reason','bars','scen','nfilled','uptrend']).to_csv(
            os.path.join(HERE, "sdca_trades.csv"), index=False, encoding='utf-8-sig')
        pd.DataFrame([{'cell':f'SCEN_{s}','train_n':0,'train_cumR':0,'test_n':0,'test_cumR':0}
                      for s in SCEN]).to_csv(os.path.join(HERE, "sdca_scenarios.csv"),
                                              index=False, encoding='utf-8-sig')
    print("[save] sdca_summary.csv + sdca_trades.csv + sdca_scenarios.csv")


if __name__ == "__main__":
    main()
