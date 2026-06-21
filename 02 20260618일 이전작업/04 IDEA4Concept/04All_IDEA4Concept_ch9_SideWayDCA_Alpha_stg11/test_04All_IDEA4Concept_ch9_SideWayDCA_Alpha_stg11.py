# -*- coding: utf-8 -*-
# [FILE] test_04All_IDEA4Concept_ch9_SideWayDCA_Alpha_stg11.py
# CODE LENGTH: approx 600 lines | INTERNAL VER: stg11 champion-mix regime-switching | full output
#
# [PURPOSE] 사장님 통찰: "장세별 유리한 세팅값으로 투입"
#   사후 시뮬 결과: 챔피언믹스 +70.7%/MDD-9.7%/PF 2.04 (stg9 단독 +44/MDD-16.6 보다 압도)
#   stg11 = 실시간 장세 판정 + 장세별 다른 세팅 → 사후 우월성을 실시간으로 재현 가능한지 검증
#
# [장세별 세팅 (champion_mix 모드 - 사후 best 합산 결과 기반)]
#   상승장 (uptrend)   → gate=short_only, ts=0.5  (stg10 채택안: 상승장 +32%)
#   하락장 (downtrend) → gate=strict,     ts=1.0  (stg9 방식: 하락장 +16%)
#   횡보장 (range)     → gate=strict,     ts=1.0  (stg9 방식: 횡보장 +4%)
#
# [실시간 장세 판정 4모드 ML 그리드]
#   pct30_5  : 30일 가격변화율 ±5%  (빠른 반응)
#   pct60_7  : 60일 변화율 ±7%      (사후 분기라벨과 일치, 균형)
#   pct90_10 : 90일 변화율 ±10%     (보수적, 늦은 반응)
#   ema_adx  : EMA200 기준 ±2% + ADX≥25 (지표 기반)
#
# [비교 기준 - bot_mode 그리드]
#   stg9_only    : 모든 장세에서 strict+ts1.0 (단일세팅 베이스라인)
#   champion_mix : 장세별 다른 세팅 (★검증 대상)
#
# [그리드 압축] TF(4) × regime(4) × bot_mode(2) = 32셀
#   기존 best 고정: adxhi=22, dist_max=1.5, a=0.3, d=0.1, short=1, nDCA=1
#
# [best 선정 - 2종]
#   best_PF        = train PF 최고 (제약 없음)
#   best_PF_capped = train PF 최고 + MDD≥-15% + 거래≥15
#
# [중요 규칙]
#   - 진입 시점의 장세 판정으로 세팅 확정 → 청산까지 그 세팅 유지 (도중 장세 바뀌어도)
#   - 미래참조 차단: 판정도 진입 직전 봉까지의 close만 사용
#   - 실펀딩 csv 자동탐색, 인트라바 모호 계측, 1m경로 추적
# ==============================================================================

import os, sys, itertools
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)

# ── CFG ──
COST_SIDE   = 0.0005 + 0.0002
FUND_8H_FALLBACK = 0.0001
RISK_BUDGET = 0.015
NOTIONAL_CAP= 2.5
START_CAP   = 10000.0
LEFT, RIGHT = 4, 1
ATR_PERIOD  = 14
ADX_N       = 14
POC_LOOKBACK= 60
POC_BINS    = 50
TIME_STOP   = 40
TRAIN_YEARS = [2023, 2024]
TEST_YEARS  = [2025, 2026]
MDD_CAP_PCT = -15.0
EMA_LEN     = 200
SHORT_SIZE  = 0.5

# ── 그리드 ──
GRID_TF       = [4*60, 6*60, 8*60, 12*60]
GRID_regime   = ['pct30_5', 'pct60_7', 'pct90_10', 'ema_adx']
GRID_bot_mode = ['stg9_only', 'champion_mix']
# 기존 best 고정
F_distmax = 1.5; F_a = 0.3; F_d = 0.1; F_short = 1; F_nDCA = 1; F_adxhi = 22

# 장세별 세팅
REGIME_SETTINGS = {
    'uptrend':   {'gate': 'short_only', 'ts': 0.5},
    'downtrend': {'gate': 'strict',     'ts': 1.0},
    'range':     {'gate': 'strict',     'ts': 1.0},
}

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
    cands = ["sample_BTCUSDT_funding_history_8h.csv", "BTCUSDT_funding.csv", "funding.csv"]
    for d in [PARENT, HERE, r"D:\ML\verify", r"D:\ML\Verify"]:
        for c in cands:
            p = os.path.join(d, c)
            if os.path.exists(p):
                return p
    return None


def load_funding(path):
    if path is None: return {}
    try:
        df = pd.read_csv(path)
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
    if has_vol: cols.append('volume')
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
    if N <= n + 1: return adx
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


def compute_ema(close, length):
    n = len(close); ema = np.full(n, np.nan)
    alpha = 2.0/(length+1)
    if n >= length:
        ema[length-1] = close[:length].mean()
        for i in range(length, n):
            ema[i] = alpha*close[i] + (1-alpha)*ema[i-1]
    return ema


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
    """TF별 지표 + 4가지 regime 라벨 사전계산 (모두 진입봉 시점까지의 정보만)."""
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
    ema = compute_ema(close, EMA_LEN)
    years = df.index.year.values
    eh = ((df.index - pd.Timestamp('1970-01-01')) / pd.Timedelta(hours=1)).values.astype('float64')

    # 4가지 regime 라벨 사전계산
    look30 = int((30*24*60)/tf_min); look60 = int((60*24*60)/tf_min); look90 = int((90*24*60)/tf_min)
    regimes = {}
    for mode in GRID_regime:
        r = np.full(n, 'range', dtype=object)
        if mode == 'pct30_5':
            look, thr = look30, 0.05
        elif mode == 'pct60_7':
            look, thr = look60, 0.07
        elif mode == 'pct90_10':
            look, thr = look90, 0.10
        if mode in ('pct30_5','pct60_7','pct90_10'):
            for i in range(look, n):
                if close[i-look] > 0:
                    pct = close[i]/close[i-look] - 1
                    if pct >= thr:    r[i] = 'uptrend'
                    elif pct <= -thr: r[i] = 'downtrend'
        else:   # ema_adx
            for i in range(EMA_LEN, n):
                if not np.isnan(ema[i]) and ema[i]>0 and adx[i]>=25:
                    if close[i] > ema[i]*1.02:    r[i] = 'uptrend'
                    elif close[i] < ema[i]*0.98:  r[i] = 'downtrend'
        regimes[mode] = r
    return {'high': high, 'low': low, 'close': close, 'open': df['open'].values, 'n': n,
            'ph_conf': ph_conf, 'pl_conf': pl_conf, 'atr': atr, 'adx': adx, 'ema': ema,
            'poc': poc, 'years': years, 'eh': eh, 'regimes': regimes, 'index': df.index}


def scen_label(adx_i, dev, adx_hi):
    strong = adx_i >= adx_hi
    if strong and dev < 0:  return 'break_down'
    if strong and dev > 0:  return 'break_up'
    if strong:              return 'strong_trend'
    if abs(dev) < 0.5:      return 'clean_range'
    return 'regime_shift'


def funding_cost(funding_map, t_enter, t_exit):
    if not funding_map:
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
    atr = sig['atr']; adx = sig['adx']; poc = sig['poc']; idx = sig['index']
    years = sig['years']
    regime_arr = sig['regimes'][par['regime_mode']]
    bot_mode = par['bot_mode']

    dist_max = F_distmax; adx_hi = F_adxhi; a = F_a; d = F_d
    short_on = F_short; nDCA = F_nDCA
    raw = np.arange(1, nDCA + 1, dtype=float); weights = raw / raw.sum()

    lastPH = np.nan; lastPL = np.nan
    pos = 0.0; side = 0; avg = np.nan; entry_i = -1; nfilled = 0
    pb = 0; trailSL = np.nan; poc_t = np.nan; scen0 = None
    entry_regime = 'range'; entry_gate = 'strict'; entry_ts = 1.0
    trades = []
    i = 0
    while i < n:
        new_ph = i in ph_conf; new_pl = i in pl_conf
        if new_ph: lastPH = ph_conf[i]
        if new_pl: lastPL = pl_conf[i]
        A = atr[i]; P = poc[i]
        dev = (close[i] - P) / A if (not np.isnan(P) and not np.isnan(A) and A > 0) else np.nan

        if pos != 0:
            # 청산 분기 (진입시점 세팅 유지)
            strong = adx[i] >= adx_hi
            gate = entry_gate
            if gate == 'strict':
                block_long = strong; block_short = strong
            elif gate == 'long_only':
                block_long = False; block_short = strong
            elif gate == 'short_only':
                block_long = strong; block_short = False
            else:
                block_long = False; block_short = False
            if side == 1 and new_ph and not np.isnan(lastPL):
                pb += 1; ratio = min(a + d * (pb - 1), 0.95)
                cand = lastPH - ratio * (lastPH - lastPL)
                trailSL = cand if np.isnan(trailSL) else max(trailSL, cand)
            elif side == -1 and new_pl and not np.isnan(lastPH):
                pb += 1; ratio = min(a + d * (pb - 1), 0.95)
                cand = lastPL + ratio * (lastPH - lastPL)
                trailSL = cand if np.isnan(trailSL) else min(trailSL, cand)
            if nfilled < nDCA and not np.isnan(dev):
                addable = False
                if side == 1 and dev < 0 and abs(dev) <= dist_max and new_pl and not block_long:
                    addable = True
                elif side == -1 and dev > 0 and abs(dev) <= dist_max and new_ph and not block_short:
                    addable = True
                if addable:
                    px = open_[i + 1] if i + 1 < n else close[i]
                    w = weights[nfilled] * (SHORT_SIZE if side == -1 else 1.0) * entry_ts
                    if w > 0:
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
                R -= COST_SIDE * pos + funding_cost(funding_map, idx[entry_i], idx[i]) * pos
                trades.append({'entry_t': idx[entry_i], 'exit_t': idx[i], 'side': side,
                               'entry': avg, 'exit': exit_px, 'R': R, 'reason': reason,
                               'bars': i - entry_i, 'scen': scen0, 'year': years[i], 'nfilled': nfilled,
                               'regime': entry_regime})
                pos = 0.0; side = 0; avg = np.nan; nfilled = 0; pb = 0
                trailSL = np.nan; poc_t = np.nan
            i += 1; continue

        # 미보유: 1차 진입
        if not np.isnan(dev) and not np.isnan(A):
            cur_regime = regime_arr[i]
            # bot_mode에 따라 세팅 결정
            if bot_mode == 'champion_mix':
                cur_gate = REGIME_SETTINGS[cur_regime]['gate']
                cur_ts = REGIME_SETTINGS[cur_regime]['ts']
            else:   # stg9_only
                cur_gate = 'strict'; cur_ts = 1.0
            strong = adx[i] >= adx_hi
            if cur_gate == 'strict':
                block_long = strong; block_short = strong
            elif cur_gate == 'long_only':
                block_long = False; block_short = strong
            elif cur_gate == 'short_only':
                block_long = strong; block_short = False
            else:
                block_long = False; block_short = False
            if cur_ts > 0:
                if not block_long and new_pl and dev < 0 and abs(dev) <= dist_max:
                    px = open_[i + 1] if i + 1 < n else close[i]
                    pos = weights[0] * cur_ts; side = 1; avg = px; nfilled = 1; entry_i = i
                    pb = 0; trailSL = px - dist_max * A; poc_t = P
                    scen0 = scen_label(adx[i], dev, adx_hi)
                    entry_regime = cur_regime; entry_gate = cur_gate; entry_ts = cur_ts
                elif short_on and not block_short and new_ph and dev > 0 and abs(dev) <= dist_max:
                    px = open_[i + 1] if i + 1 < n else close[i]
                    pos = weights[0] * SHORT_SIZE * cur_ts; side = -1; avg = px; nfilled = 1; entry_i = i
                    pb = 0; trailSL = px + dist_max * A; poc_t = P
                    scen0 = scen_label(adx[i], dev, adx_hi)
                    entry_regime = cur_regime; entry_gate = cur_gate; entry_ts = cur_ts
        i += 1

    return trades


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
    print("[stg11] champion-mix regime-switching ML grid")
    open(os.path.join(HERE, ".run_start"), 'w').close()
    data = find_data(); print(f"[data] {data}")
    fpath = find_funding()
    funding_map = load_funding(fpath)
    print(f"[funding] {'REAL '+str(fpath)+' ('+str(len(funding_map))+'건)' if funding_map else 'FALLBACK 0.01%/8h'}")
    df1m = load_1m(data)
    print(f"[load] {len(df1m):,}rows | vol={df1m.attrs['has_vol']} | {df1m.index.min().date()}~{df1m.index.max().date()}")

    tf_df = {}; tf_sig = {}
    for tf in GRID_TF:
        d = resample_tf(df1m, tf); tf_df[tf] = d; tf_sig[tf] = precompute(d, tf)
        # 라벨 분포 출력
        for mode in GRID_regime:
            rg = tf_sig[tf]['regimes'][mode]
            up = (rg=='uptrend').sum(); dn = (rg=='downtrend').sum(); rn = (rg=='range').sum()
            print(f"[tf {tf//60}h {mode}] up={up}({up/len(rg)*100:.0f}%) dn={dn}({dn/len(rg)*100:.0f}%) range={rn}({rn/len(rg)*100:.0f}%)")

    summary = []; best_pf = None; best_pf_capped = None
    combos = list(itertools.product(GRID_regime, GRID_bot_mode))
    total = len(GRID_TF) * len(combos)
    print(f"[grid] TF{len(GRID_TF)} × regime{len(GRID_regime)} × bot_mode{len(GRID_bot_mode)} = {total} runs")

    cnt = 0
    for tf in GRID_TF:
        df = tf_df[tf]; sig = tf_sig[tf]
        for (rm, bm) in combos:
            par = {'regime_mode': rm, 'bot_mode': bm}
            trades = run_bot(df, sig, par, funding_map)
            lab = f"TF{tf//60}h_{rm}_{bm}"
            mTr = agg(trades, lab + "_train", TRAIN_YEARS)
            mTe = agg(trades, lab + "_test", TEST_YEARS)
            mAll = agg(trades, lab + "_all")
            # 장세별 분해
            up_t = [t for t in trades if t['regime']=='uptrend']
            dn_t = [t for t in trades if t['regime']=='downtrend']
            rg_t = [t for t in trades if t['regime']=='range']
            summary.append({'cell': lab, 'TF_h': tf // 60, 'regime_mode': rm, 'bot_mode': bm,
                            'all_trades': mAll['trades'], 'all_PF': mAll['PF'],
                            'all_cumR': mAll['cumR_pct'], 'all_MDD': mAll['MDD_pct'],
                            'final_cap': mAll['final_cap'],
                            'tr_PF': mTr['PF'], 'tr_cumR': mTr['cumR_pct'], 'tr_n': mTr['trades'],
                            'te_PF': mTe['PF'], 'te_cumR': mTe['cumR_pct'], 'te_n': mTe['trades'],
                            'wfe': round(mTe['PF']/mTr['PF']*100, 1) if mTr['PF']>0 else 0,
                            'up_n': len(up_t), 'up_R': round(sum(t['R'] for t in up_t)*100,2),
                            'dn_n': len(dn_t), 'dn_R': round(sum(t['R'] for t in dn_t)*100,2),
                            'rg_n': len(rg_t), 'rg_R': round(sum(t['R'] for t in rg_t)*100,2)})
            if mTr['trades'] >= 15:
                if best_pf is None or mTr['PF'] > best_pf[0]:
                    best_pf = (mTr['PF'], par, tf, trades)
                if mAll['MDD_pct'] >= MDD_CAP_PCT and (best_pf_capped is None or mTr['PF'] > best_pf_capped[0]):
                    best_pf_capped = (mTr['PF'], par, tf, trades, mAll['MDD_pct'])
            cnt += 1
            if cnt % 8 == 0:
                print(f"  [progress] {cnt}/{total}")

    # VERDICT
    v_lines = []
    if best_pf is not None:
        _, p, tf, tr = best_pf
        bm_tr = agg(tr, "bp_train", TRAIN_YEARS); bm_te = agg(tr, "bp_test", TEST_YEARS)
        bm_all = agg(tr, "bp_all")
        wfe = round((bm_te['PF']/bm_tr['PF'])*100, 1) if bm_tr['PF']>0 else 0
        v_lines.append(f"BEST_PF(제약없음) TF{tf//60}h regime={p['regime_mode']} mode={p['bot_mode']}"
                       f" | train PF={bm_tr['PF']} cumR={bm_tr['cumR_pct']}% | test PF={bm_te['PF']} cumR={bm_te['cumR_pct']}%"
                       f" | all MDD={bm_all['MDD_pct']}% final=${bm_all['final_cap']} WFE={wfe}%")
    if best_pf_capped is not None:
        _, p, tf, tr, _ = best_pf_capped
        bm_tr = agg(tr, "bc_train", TRAIN_YEARS); bm_te = agg(tr, "bc_test", TEST_YEARS)
        bm_all = agg(tr, "bc_all")
        wfe = round((bm_te['PF']/bm_tr['PF'])*100, 1) if bm_tr['PF']>0 else 0
        v_lines.append(f"BEST_PF_MDD_CAPPED(-15%안) TF{tf//60}h regime={p['regime_mode']} mode={p['bot_mode']}"
                       f" | train PF={bm_tr['PF']} cumR={bm_tr['cumR_pct']}% | test PF={bm_te['PF']} cumR={bm_te['cumR_pct']}%"
                       f" | all MDD={bm_all['MDD_pct']}% final=${bm_all['final_cap']} WFE={wfe}%")
    else:
        v_lines.append("BEST_PF_MDD_CAPPED=없음")

    # 챔피언믹스 vs 단일세팅 평균 효과
    sdf = pd.DataFrame(summary)
    if len(sdf):
        mix = sdf[sdf.bot_mode=='champion_mix']
        single = sdf[sdf.bot_mode=='stg9_only']
        v_lines.append(f"MIX효과: mix_avg_cumR={mix.all_cumR.mean():.1f}% single_avg={single.all_cumR.mean():.1f}%"
                       f" | mix_avg_MDD={mix.all_MDD.mean():.1f}% single={single.all_MDD.mean():.1f}%"
                       f" | mix_avg_PF={mix.all_PF.mean():.2f} single={single.all_PF.mean():.2f}")

    verdict = "VERDICT stg11 | " + " || ".join(v_lines)
    print("\n[verdict]", verdict)

    summary.insert(0, {'cell': verdict})
    pd.DataFrame(summary).to_csv(os.path.join(HERE, "sdca_summary.csv"), index=False, encoding='utf-8-sig')

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
               'nfilled': t['nfilled'], 'regime': t['regime']} for t in btr]
        pd.DataFrame(td).to_csv(os.path.join(HERE, "sdca_trades.csv"), index=False, encoding='utf-8-sig')
        sb_tr = scen_breakdown(btr, TRAIN_YEARS); sb_te = scen_breakdown(btr, TEST_YEARS)
        scen_rows = [{'cell': f'SCEN_{s}', 'train_n': sb_tr[s][0], 'train_cumR': sb_tr[s][1],
                       'test_n': sb_te[s][0], 'test_cumR': sb_te[s][1]} for s in SCEN]
        pd.DataFrame(scen_rows).to_csv(os.path.join(HERE, "sdca_scenarios.csv"), index=False, encoding='utf-8-sig')
    else:
        pd.DataFrame(columns=['entry_t','exit_t','side','year','entry','exit','R_pct',
                              'reason','bars','scen','nfilled','regime']).to_csv(
            os.path.join(HERE, "sdca_trades.csv"), index=False, encoding='utf-8-sig')
        pd.DataFrame([{'cell':f'SCEN_{s}','train_n':0,'train_cumR':0,'test_n':0,'test_cumR':0}
                      for s in SCEN]).to_csv(os.path.join(HERE, "sdca_scenarios.csv"),
                                              index=False, encoding='utf-8-sig')
    print("[save] sdca_summary.csv + sdca_trades.csv + sdca_scenarios.csv")


if __name__ == "__main__":
    main()
