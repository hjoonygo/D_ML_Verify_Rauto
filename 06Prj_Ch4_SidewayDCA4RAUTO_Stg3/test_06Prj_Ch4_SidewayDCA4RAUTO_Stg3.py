# -*- coding: utf-8 -*-
# [파일명] test_06Prj_Ch4_SidewayDCA4RAUTO_Stg3.py
# 코드길이: 약 520줄 | 내부버전: ChampBot_SidewayDCA4RAUTO_06_Ch4_Stg3 | 로직 축약/생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명]
#   추세선수(SpTrd_Fib_V0_stg8) 봇을 그대로 계승하고, 진입 게이트에 'OI 무덤필터'를 추가한다.
#   무덤필터 = Stg2에서 입증된 'oi_zscore_24h 가 0이상 1미만이면 그 진입은 깨진다(승률9% 누적-52%, 순열검정 p=0.0001)'.
#   → 진입 직전에 OI z가 무덤구간[0,1)이면 진입을 보류(롱·숏 모두). 봇의 진입/청산/피보트레일/숏필터는 한 줄도 안 바꿈.
#   필터 OFF(원본) vs ON(무덤차단)을 나란히 돌려 '실제 자본곡선·PF·MDD'를 8시나리오로 비교한다.
#   ★이건 모의(빼기)가 아니라 실제 봇 재백테스트 — 시간순으로 자본을 굴리며 무덤진입을 건너뛴다(TIL 1-2 완성).
#
# [★사용명칭 정의]  ※추정 방지
#   무덤필터(DZ filter) = 진입봉의 oi_zscore_24h 가 DZ_LO(0)<=z<DZ_HI(1) 이면 진입 보류.
#   OI z = oi_zscore_24h. 진입봉(7h봉) 닫힘 시점의 과거24h 기준값. 진입 결정시점에 이미 아는 값(미래참조 없음).
#   필터OFF = 원본 SpTrd 봇 그대로. 필터ON = 무덤구간 진입만 추가 차단.
#
# [미래참조 차단 — Basic 3.4]
#   - OI는 7h봉으로 묶을 때 last(봉 닫힘 시점값)만 사용. 진입 결정은 닫힌 봉, 체결은 원본과 동일(종가체결).
#   - asof backward 매칭(진입시각 이하 최근 OI). 미래봉·청산후값 안 봄. label_smc 사용 안 함.
#   - ★안전장치: OI 데이터(Merged_Data.csv) 없으면 무덤필터 자동 OFF + 경고(추정으로 안 돔).
#
# [PATH] 실행: D:\ML\verify\06Prj_Ch4_SidewayDCA4RAUTO_Stg3\ . 데이터: 상위 D:\ML\verify\ .
# [DATA] (상위) Merged_Data_with_Regime_Features.csv (OHLC, 원본 봇 입력)
#        (상위) Merged_Data.csv / merged_data.csv (oi_zscore_24h, 무덤필터용 — 없으면 필터OFF)
# [OUTPUT] (실행폴더) sfrs_summary.csv + sfrs_trades.csv + sfrs_equity.csv -> check.py 정리.
#          (실행폴더) .sfrs_metric (check.py 증빙)
#
# [FUNCTIONS] 원본(compute_signals/run_strategy/agg/equity_s4) 계승
#   + 신규: find_oi/load_oi_8h(OI 로드·7h매칭) / run_strategy에 dz_z 인자(무덤차단) / main에 OFF·ON 비교·자본곡선
# ==============================================================================

import os, sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)

LEFT = 4; RIGHT = 1
COST = 0.0004; FUND_8H = 0.0001
FIB = (0.3, 0.5, 0.6); SL_PCT = 1.0
ATR_FACTOR = 3.0; ATR_PERIOD = 10
LEVERAGE = 1.0
NOMINAL = 50000.0; START_CAP = 10000.0; MIN_CAP = 100.0
TRAIN_YEARS = [2023, 2024]; TEST_YEARS = [2025, 2026]
TF_MIN = 7 * 60

# 지표 기간
ADX_N = 14; CHOP_N = 14; ATR_SMA_N = 50; VGUARD_K = 6

# 후보 필터 (이름, 임계 후보들, 방향) - 임계는 사전선언(곡선맞춤 방지)
#   판정: 숏 진입을 '보류'하는 조건
#   adx<th / chop>th / atrcmp(=atr<sma*0.8 bool) / bandw<th / drop>=th
# (필터, adx임계, 조합모드, atr배수)  mode: solo_adx/solo_atr/OR/AND/none
GRID = [
    ('C0_none',      0,  'none', 0.8),
    ('C1_adx20',     20, 'solo_adx', 0.8),
    ('C2_atrcmp',    20, 'solo_atr', 0.8),
    ('C3_OR',        20, 'OR', 0.8),
    ('C4_AND',       20, 'AND', 0.8),
    ('C5_OR_adx18',  18, 'OR', 0.8),
    ('C6_OR_adx22',  22, 'OR', 0.8),
    ('C7_atr07',     20, 'OR', 0.7),
]
S4_PCT = 0.30   # 참고 자본곡선용 (자본30%)


def find_data():
    for d in [PARENT, HERE, r"D:\ML\verify", r"D:\ML\Verify"]:
        p = os.path.join(d, "Merged_Data_with_Regime_Features.csv")
        if os.path.exists(p):
            return p
    raise FileNotFoundError("상위 D:\\ML\\verify 에 Merged_Data_with_Regime_Features.csv 필요")


def load_data(path):
    cols = ['timestamp', 'open', 'high', 'low', 'close']
    df = pd.read_csv(path, usecols=cols, index_col='timestamp', parse_dates=True)
    if getattr(df.index, 'tz', None) is not None:
        df.index = df.index.tz_localize(None)
    return df.sort_index()


# ── 무덤필터(DZ) 설정: Stg2에서 입증된 OI z[0,1) 진입금지 구간 ──
DZ_LO, DZ_HI = 0.0, 1.0
OI_CANDS = ["Merged_Data.csv", "merged_data.csv", "merged_data_sample.csv"]


def find_oi():
    for d in [PARENT, HERE, r"D:\ML\verify", r"D:\ML\Verify"]:
        for c in OI_CANDS:
            p = os.path.join(d, c)
            if os.path.exists(p):
                try:
                    if 'oi_zscore_24h' in pd.read_csv(p, nrows=1).columns:
                        return p
                except Exception:
                    pass
    return None


def load_oi_8h(path, tf_index):
    # OI(oi_zscore_24h) 1분봉을 읽어, 7h봉 시각 각각에 'last(봉 닫힘 시점값)'으로 매칭.
    #   tf_index = 7h봉의 DatetimeIndex. 각 봉 [start, start+7h) 구간의 마지막 oi값을 그 봉 값으로.
    #   ★미래참조 없음: 봉 닫힘 시점의 과거24h 기준 oi라 진입 결정시점에 이미 아는 값.
    df = pd.read_csv(path, usecols=['timestamp', 'oi_zscore_24h'], index_col='timestamp', parse_dates=True)
    if getattr(df.index, 'tz', None) is not None:
        df.index = df.index.tz_localize(None)
    df = df.sort_index()
    # 7h봉으로 resample해서 last
    oi_7h = df['oi_zscore_24h'].resample(f"{TF_MIN}min", label='left', closed='left').last()
    # tf_index에 맞춰 정렬(없는 봉은 NaN → 필터 통과)
    return oi_7h.reindex(tf_index).values.astype('float64')


def resample_tf(df1m, tf_min):
    rule = f"{tf_min}min"
    agg = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}
    return df1m[['open', 'high', 'low', 'close']].resample(rule, label='left', closed='left').agg(agg).dropna()


def pivots_lr(high, low, left, right):
    n = len(high); ph_conf = {}; pl_conf = {}
    if n < left + right + 1:
        return ph_conf, pl_conf
    from numpy.lib.stride_tricks import sliding_window_view
    win = left + right + 1
    hwin = sliding_window_view(high, win); lwin = sliding_window_view(low, win)
    centers = np.arange(left, n - right)
    hmax = hwin.max(axis=1); lmin = lwin.min(axis=1)
    hc = high[left:n - right]; lc = low[left:n - right]
    is_ph = (hc == hmax) & ((hwin == hmax[:, None]).sum(axis=1) == 1)
    is_pl = (lc == lmin) & ((lwin == lmin[:, None]).sum(axis=1) == 1)
    for k in np.where(is_ph)[0]:
        c = centers[k]; ph_conf[c + right] = (c, float(high[c]))
    for k in np.where(is_pl)[0]:
        c = centers[k]; pl_conf[c + right] = (c, float(low[c]))
    return ph_conf, pl_conf


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
    """Wilder ADX. 전부 과거봉 기반(미래참조 없음). 벡터+1패스."""
    N = len(close)
    tr = np.zeros(N); pdm = np.zeros(N); ndm = np.zeros(N)
    up = high[1:] - high[:-1]
    dn = low[:-1] - low[1:]
    pdm[1:] = np.where((up > dn) & (up > 0), up, 0.0)
    ndm[1:] = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr[1:] = np.maximum.reduce([high[1:] - low[1:],
                                np.abs(high[1:] - close[:-1]),
                                np.abs(low[1:] - close[:-1])])
    atrw = np.zeros(N); pdmw = np.zeros(N); ndmw = np.zeros(N)
    adx = np.zeros(N)
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
    # ADX = DX의 Wilder 평활
    start = 2 * n
    if N > start:
        adx[start] = dx[n + 1:start + 1].mean()
        for i in range(start + 1, N):
            adx[i] = (adx[i - 1] * (n - 1) + dx[i]) / n
    return adx


def compute_chop(high, low, close, n):
    """Choppiness Index. 100*log10(sum(TR,n)/(maxHigh-minLow))/log10(n). 과거봉만."""
    N = len(close); chop = np.zeros(N)
    tr = np.zeros(N)
    tr[1:] = np.maximum.reduce([high[1:] - low[1:],
                                np.abs(high[1:] - close[:-1]),
                                np.abs(low[1:] - close[:-1])])
    if N <= n:
        return chop
    from numpy.lib.stride_tricks import sliding_window_view
    trsum = np.convolve(tr, np.ones(n), 'valid')          # len N-n+1, idx i->[i..i+n-1]
    hh = sliding_window_view(high, n).max(axis=1)
    ll = sliding_window_view(low, n).min(axis=1)
    rng = hh - ll
    val = np.zeros(len(trsum))
    ok = rng > 0
    val[ok] = 100 * np.log10(trsum[ok] / rng[ok]) / np.log10(n)
    # 정렬: 윈도 [i..i+n-1]의 chop을 끝봉 i+n-1에 기록(과거만 사용)
    chop[n - 1:n - 1 + len(val)] = val
    return chop


def pivot_supertrend(df_tf):
    high = df_tf['high'].values; low = df_tf['low'].values; close = df_tf['close'].values
    n = len(close); atr = compute_atr(high, low, close, ATR_PERIOD)
    ph_conf, pl_conf = pivots_lr(high, low, LEFT, LEFT)
    center = np.full(n, np.nan); cur = np.nan
    for i in range(n):
        lastpp = np.nan
        if i in ph_conf: lastpp = ph_conf[i][1]
        elif i in pl_conf: lastpp = pl_conf[i][1]
        if not np.isnan(lastpp):
            cur = lastpp if np.isnan(cur) else (cur * 2 + lastpp) / 3
        center[i] = cur
    Up = center - ATR_FACTOR * atr; Dn = center + ATR_FACTOR * atr
    TUp = np.full(n, np.nan); TDown = np.full(n, np.nan); Trend = np.zeros(n, dtype=int)
    for i in range(n):
        if i == 0 or np.isnan(Up[i]) or np.isnan(Dn[i]):
            TUp[i] = Up[i] if not np.isnan(Up[i]) else -1e18
            TDown[i] = Dn[i] if not np.isnan(Dn[i]) else 1e18
            Trend[i] = 1; continue
        TUp[i] = max(Up[i], TUp[i - 1]) if close[i - 1] > TUp[i - 1] else Up[i]
        TDown[i] = min(Dn[i], TDown[i - 1]) if close[i - 1] < TDown[i - 1] else Dn[i]
        if close[i] > TDown[i - 1]: Trend[i] = 1
        elif close[i] < TUp[i - 1]: Trend[i] = -1
        else: Trend[i] = Trend[i - 1] if Trend[i - 1] != 0 else 1
    return Trend, center, atr, Up, Dn


def compute_signals(df_tf):
    """5신호 전체 1회 사전계산 (속도 최적화 핵심). 전부 과거봉만(미래참조 없음)."""
    high = df_tf['high'].values; low = df_tf['low'].values; close = df_tf['close'].values
    n = len(close)
    Trend, center, atr, Up, Dn = pivot_supertrend(df_tf)
    adx = compute_adx(high, low, close, ADX_N)
    chop = compute_chop(high, low, close, CHOP_N)
    atr_sma = pd.Series(atr).rolling(ATR_SMA_N, min_periods=1).mean().values
    atrcmp = (atr < atr_sma * 0.8).astype(float)   # 1=압축(횡보)
    bandw = np.where(close > 0, (Dn - Up) / close, 0.0)
    # 급락폭(vguard): 최근 K봉 최고대비 낙폭
    drop = np.zeros(n)
    for i in range(n):
        lo = max(0, i - VGUARD_K); w = close[lo:i + 1]
        peak = w.max() if len(w) else close[i]
        drop[i] = (peak - close[i]) / peak if peak > 0 else 0.0
    ph_conf, pl_conf = pivots_lr(high, low, LEFT, RIGHT)
    return {'Trend': Trend, 'Up': Up, 'Dn': Dn, 'adx': adx, 'chop': chop,
            'atrcmp': atrcmp, 'atr': atr, 'atr_sma': atr_sma, 'bandw': bandw, 'drop': drop,
            'ph_conf': ph_conf, 'pl_conf': pl_conf}


def short_blocked_combo(sig, i, adx_th, mode, atr_mult):
    """숏 보류 판정 (과거/현재 봉만). mode별 조합."""
    if mode == 'none':
        return False
    adx_low = sig['adx'][i] < adx_th
    # atr 압축: 현재 atr < sma * atr_mult
    atr_comp = sig['atr'][i] < sig['atr_sma'][i] * atr_mult
    if mode == 'solo_adx':
        return adx_low
    if mode == 'solo_atr':
        return atr_comp
    if mode == 'OR':
        return adx_low or atr_comp
    if mode == 'AND':
        return adx_low and atr_comp
    return False


def run_strategy(df_tf, sig, adx_th, mode, atr_mult, dz_oi=None, dz_lo=DZ_LO, dz_hi=DZ_HI):
    # dz_oi: 7h봉별 oi_zscore 배열(길이=봉수) 또는 None. None이면 무덤필터 OFF(원본 동작).
    # dz_lo,dz_hi: 무덤구간 경계(기본 0~1). 시나리오6에서 폭 바꿔 호출.
    """백테스트 1패스. 숏에만 조합필터(adx_th,mode,atr_mult). 롱 무수정."""
    high = df_tf['high'].values; low = df_tf['low'].values
    close = df_tf['close'].values; open_ = df_tf['open'].values
    idx = df_tf.index; n = len(close)
    Trend = sig['Trend']; ph_conf = sig['ph_conf']; pl_conf = sig['pl_conf']
    eh = ((idx - pd.Timestamp('1970-01-01')) / pd.Timedelta(hours=1)).values.astype('float64')

    def n_fund(a, b):
        return int(np.floor(eh[b] / 8.0) - np.floor(eh[a] / 8.0))

    lastPH = np.nan; lastPL = np.nan
    pos = 0; entry_price = np.nan; entry_i = -1; sl = np.nan; pb = 0
    trades = []
    for i in range(n):
        new_ph = i in ph_conf; new_pl = i in pl_conf
        if new_ph: lastPH = ph_conf[i][1]
        if new_pl: lastPL = pl_conf[i][1]

        if pos != 0:
            if (pos == 1 and Trend[i] == -1) or (pos == -1 and Trend[i] == 1):
                px = close[i]; R = pos * (px - entry_price) / entry_price * LEVERAGE
                fp = FUND_8H * n_fund(entry_i, i); R = R - COST - fp
                tr = {'entry_t': idx[entry_i], 'exit_t': idx[i], 'side': pos,
                      'entry': entry_price, 'exit': px, 'R': R, 'reason': 'trend_flip',
                      'bars': i - entry_i, 'fund': fp, 'year': idx[i].year}
                trades.append(tr); pos = 0; sl = np.nan; pb = 0; continue
            if i > entry_i and not np.isnan(sl):
                o_, h_, l_, c_ = open_[i], high[i], low[i], close[i]
                ticks = (o_, h_, l_, c_) if c_ < o_ else (o_, l_, h_, c_)
                hit = False
                for px in ticks:
                    if pos == 1 and px <= sl: hit = True; break
                    if pos == -1 and px >= sl: hit = True; break
                if hit:
                    R = pos * (sl - entry_price) / entry_price * LEVERAGE
                    fp = FUND_8H * n_fund(entry_i, i); R = R - COST - fp
                    tr = {'entry_t': idx[entry_i], 'exit_t': idx[i], 'side': pos,
                          'entry': entry_price, 'exit': sl, 'R': R, 'reason': 'sl',
                          'bars': i - entry_i, 'fund': fp, 'year': idx[i].year}
                    trades.append(tr); pos = 0; sl = np.nan; pb = 0; continue

        if pos == 1 and new_pl:
            pb += 1; ratio = FIB[0] if pb == 1 else FIB[1] if pb == 2 else FIB[2]
            if not np.isnan(lastPH):
                cand = lastPH - ratio * (lastPH - pl_conf[i][1])
                sl = cand if np.isnan(sl) else max(sl, cand)
        if pos == -1 and new_ph:
            pb += 1; ratio = FIB[0] if pb == 1 else FIB[1] if pb == 2 else FIB[2]
            if not np.isnan(lastPL):
                cand = lastPL + ratio * (ph_conf[i][1] - lastPL)
                sl = cand if np.isnan(sl) else min(sl, cand)

        if pos == 0:
            le = Trend[i] == 1 and new_pl and not np.isnan(lastPH)
            se = Trend[i] == -1 and new_ph and not np.isnan(lastPL)
            if se and short_blocked_combo(sig, i, adx_th, mode, atr_mult):
                se = False
            # ── 무덤필터(DZ): 진입봉 OI z가 [DZ_LO, DZ_HI)이면 롱·숏 모두 진입 보류 ──
            #   Stg2 입증: 이 구간 진입은 승률9%·누적-52%(순열검정 p=0.0001). 미래참조 없음(봉 닫힘값).
            if dz_oi is not None:
                z = dz_oi[i]
                if not np.isnan(z) and (dz_lo <= z < dz_hi):
                    le = False; se = False
            if le:
                pos = 1; entry_price = close[i]; entry_i = i; pb = 0
                sl = entry_price * (1 - SL_PCT / 100)
            elif se:
                pos = -1; entry_price = close[i]; entry_i = i; pb = 0
                sl = entry_price * (1 + SL_PCT / 100)
    return trades


def agg(trades, label, years=None):
    if years is not None:
        trades = [t for t in trades if t['year'] in years]
    if not trades:
        return {'칸': label, '거래수': 0}
    R = np.array([t['R'] for t in trades])
    wins = R[R > 0]; losses = R[R < 0]
    gp = wins.sum(); gl = -losses.sum(); pf = (gp / gl) if gl > 0 else 999.0
    cap = START_CAP; mincap = START_CAP; bankrupt = False
    for r in R:
        cap += r * NOMINAL; mincap = min(mincap, cap)
        if cap <= MIN_CAP: bankrupt = True; break
    reasons = {}
    for t in trades:
        reasons[t['reason']] = reasons.get(t['reason'], 0) + 1
    return {'칸': label, '거래수': len(trades),
            '승률_pct': round(len(wins) / len(trades) * 100, 1),
            '누적R_pct': round(R.sum() * 100, 2), 'PF': round(pf, 3),
            '파산_참고': 'YES' if bankrupt else 'NO', '최저자본': round(mincap, 0),
            'trend_flip': reasons.get('trend_flip', 0), 'sl': reasons.get('sl', 0)}


def equity_s4(trades, pct=0.30):
    """참고용 자본곡선(자본 pct% 베팅). MDD 동반표기용. 진짜파산 체크."""
    cap = START_CAP; caps = [cap]; floor = START_CAP * 0.01; bust = False
    for t in trades:
        cap += t['R'] * cap * pct
        caps.append(cap)
        if cap <= floor:
            bust = True; break
    caps = np.array(caps)
    peak = -1e18; mdd = 0.0
    for c in caps:
        peak = max(peak, c)
        if peak > 0: mdd = min(mdd, (c - peak) / peak)
    return round(float(caps[-1]), 0), round(mdd * 100, 1), ('YES' if bust else 'NO')


def pf_of(R):
    R = np.asarray(R, float)
    if len(R) == 0:
        return 0.0
    gp = R[R > 0].sum(); gl = -R[R < 0].sum()
    return round(float(gp / gl), 3) if gl > 0 else 999.0


def stats_of(trades, years=None):
    # 거래 리스트 -> 거래수/승률/누적R%/PF/손익비/수익금($, S4자본곡선) 한 묶음.
    if years is not None:
        trades = [t for t in trades if t['year'] in years]
    if not trades:
        return dict(n=0, win=0.0, cumR=0.0, PF=0.0, payoff=0.0, fin=START_CAP, mdd=0.0, flips=0)
    R = np.array([t['R'] for t in trades])
    wins = R[R > 0]; losses = R[R < 0]
    payoff = round((wins.mean() / -losses.mean()), 2) if len(wins) and len(losses) else 0.0
    fin, mdd, _ = equity_s4(trades, S4_PCT)
    flips = sum(1 for t in trades if t['reason'] == 'trend_flip')
    return dict(n=len(trades), win=round(100 * len(wins) / len(trades), 1),
                cumR=round(R.sum() * 100, 2), PF=pf_of(R), payoff=payoff,
                fin=fin, mdd=mdd, flips=flips)


def main():
    print("[ChampBot_SidewayDCA4RAUTO_06_Ch4_Stg3] 추세선수 봇 + OI 무덤필터 실증 재백테스트")
    open(os.path.join(HERE, ".run_start"), 'w').close()
    data = find_data(); print(f"[data] {data}")
    df1m = load_data(data)
    print(f"[load] {len(df1m):,}rows | {df1m.index.min().date()}~{df1m.index.max().date()}")
    df_tf = resample_tf(df1m, TF_MIN)
    print(f"[7h] {len(df_tf)}bars")
    sig = compute_signals(df_tf)

    # ── OI 로드(무덤필터용). 없으면 필터 OFF만 ──
    oipath = find_oi()
    has_oi = oipath is not None
    oi_arr = None
    if has_oi:
        oi_arr = load_oi_8h(oipath, df_tf.index)
        n_dz = int(np.sum((~np.isnan(oi_arr)) & (oi_arr >= DZ_LO) & (oi_arr < DZ_HI)))
        print(f"[oi] {os.path.basename(oipath)} | 7h봉 무덤구간 {n_dz}봉 (전체 {len(oi_arr)}봉)")
    else:
        print("[oi] ★Merged_Data.csv(oi_zscore) 없음 → 무덤필터 OFF만 실행(추정 안 함)")

    # 기본 칸: C0_none(원본 무필터) 기준. 무덤필터만 얹어 비교(한 번에 한 로직).
    adx_th, mode, atr_mult = 0, 'none', 0.8

    # 필터 OFF(원본)
    tr_off = run_strategy(df_tf, sig, adx_th, mode, atr_mult, dz_oi=None)
    # 필터 ON(무덤차단)
    tr_on = run_strategy(df_tf, sig, adx_th, mode, atr_mult, dz_oi=oi_arr) if has_oi else tr_off

    rows = []

    def add(cell, off, on, note=""):
        rows.append({'cell': cell,
                     'OFF_n': off['n'], 'OFF_PF': off['PF'], 'OFF_cumR': off['cumR'],
                     'OFF_win': off['win'], 'OFF_payoff': off['payoff'],
                     'OFF_fin': off['fin'], 'OFF_mdd': off['mdd'],
                     'ON_n': on['n'], 'ON_PF': on['PF'], 'ON_cumR': on['cumR'],
                     'ON_win': on['win'], 'ON_payoff': on['payoff'],
                     'ON_fin': on['fin'], 'ON_mdd': on['mdd'], 'note': note})

    # ── 시나리오1: 전체 OFF vs ON ──
    s_off = stats_of(tr_off); s_on = stats_of(tr_on)
    add("S1_전체_OFFvsON", s_off, s_on,
        f"PF {s_off['PF']}->{s_on['PF']} | MDD {s_off['mdd']}->{s_on['mdd']}% | 수익금 {s_off['fin']:,.0f}->{s_on['fin']:,.0f}")

    # ── 시나리오2: 연도별 ──
    for y in sorted(set(t['year'] for t in tr_off)):
        add(f"S2_연도_{y}", stats_of(tr_off, [y]), stats_of(tr_on, [y]))

    # ── 시나리오3: 롱숏별 ──
    for sd, nm in [(1, "롱"), (-1, "숏")]:
        off_s = stats_of([t for t in tr_off if t['side'] == sd])
        on_s = stats_of([t for t in tr_on if t['side'] == sd])
        add(f"S3_방향_{nm}", off_s, on_s)

    # ── 시나리오4: 청산사유(trend_flip 줄었나) ──
    off_flip = stats_of([t for t in tr_off if t['reason'] == 'trend_flip'])
    on_flip = stats_of([t for t in tr_on if t['reason'] == 'trend_flip'])
    add("S4_청산_trend_flip", off_flip, on_flip,
        f"trend_flip {off_flip['n']}건->{on_flip['n']}건")

    # ── 시나리오5: train(23~25)/test(26) ──
    add("S5_train_2325", stats_of(tr_off, [2023, 2024, 2025]), stats_of(tr_on, [2023, 2024, 2025]))
    add("S5_test_26", stats_of(tr_off, [2026]), stats_of(tr_on, [2026]))

    # ── 시나리오6: 무덤경계 폭 비교 (0~1 vs 0~0.5 vs 0.5~1) ──
    if has_oi:
        for lo, hi, nm in [(0.0, 1.0, "0~1"), (0.0, 0.5, "0~0.5"), (0.5, 1.0, "0.5~1")]:
            tr_v = run_strategy(df_tf, sig, adx_th, mode, atr_mult, dz_oi=oi_arr, dz_lo=lo, dz_hi=hi)
            sv = stats_of(tr_v)
            add(f"S6_경계_{nm}", s_off, sv, f"무덤[{lo}~{hi}) 차단시 PF {sv['PF']} MDD {sv['mdd']}%")

    # ── 시나리오7: 큰 거래 상위3 제거 후 ON (쏠림 착시) ──
    if has_oi and len(tr_on) > 3:
        R_on = sorted([t['R'] for t in tr_on])
        trimmed = [r for r in R_on if r not in R_on[-3:]]  # 상위3 이익 제거
        if trimmed:
            gp = sum(r for r in trimmed if r > 0); gl = -sum(r for r in trimmed if r < 0)
            pf_t = round(gp / gl, 3) if gl > 0 else 999.0
            add("S7_큰이익3제거_ON", s_off, dict(n=len(trimmed), win=0, cumR=round(sum(trimmed)*100,2),
                PF=pf_t, payoff=0, fin=0, mdd=0),
                f"상위3이익 제거후 ON PF {pf_t} (OFF PF {s_off['PF']}보다 높으면 견고)")

    # ── 시나리오8: 위험(MDD·파산·최저자본) ──
    add("S8_위험_OFFvsON", s_off, s_on,
        f"MDD {s_off['mdd']}%->{s_on['mdd']}% | 수익금 {s_off['fin']:,.0f}->{s_on['fin']:,.0f}")

    # ── VERDICT ──
    verdict = (f"VERDICT 무덤필터 실증 | 전체 OFF PF{s_off['PF']} cumR{s_off['cumR']}% MDD{s_off['mdd']}% 수익금{s_off['fin']:,.0f} "
               f"-> ON PF{s_on['PF']} cumR{s_on['cumR']}% MDD{s_on['mdd']}% 수익금{s_on['fin']:,.0f} "
               f"| 거래 {s_off['n']}->{s_on['n']} | trend_flip {off_flip['n']}->{on_flip['n']} | OI {'O' if has_oi else 'X(필터OFF)'}")
    print("[verdict] " + verdict)

    out = [{'cell': verdict}] + rows
    pd.DataFrame(out).to_csv(os.path.join(HERE, "sfrs_summary.csv"), index=False, encoding='utf-8-sig')

    # 거래원장(ON 기준, OI 매칭값 포함)
    td = []
    for t in tr_on:
        bi = df_tf.index.get_loc(t['entry_t']) if t['entry_t'] in df_tf.index else -1
        z = oi_arr[bi] if (has_oi and bi >= 0 and bi < len(oi_arr)) else np.nan
        td.append({'side': t['side'], 'entry_t': t['entry_t'].strftime('%Y-%m-%d %H:%M'),
                   'exit_t': t['exit_t'].strftime('%Y-%m-%d %H:%M'), 'year': t['year'],
                   'entry': round(t['entry'], 2), 'exit': round(t['exit'], 2),
                   'R_pct': round(t['R'] * 100, 4), 'reason': t['reason'], 'bars': t['bars'],
                   'oi_z': round(float(z), 3) if not np.isnan(z) else ''})
    pd.DataFrame(td).to_csv(os.path.join(HERE, "sfrs_trades.csv"), index=False, encoding='utf-8-sig')

    # 자본곡선(OFF vs ON, S4 기준)
    def eqcurve(trades):
        cap = START_CAP; out = [(None, round(cap, 2))]
        for t in trades:
            cap += t['R'] * cap * S4_PCT
            out.append((t['exit_t'].strftime('%Y-%m-%d'), round(cap, 2)))
        return out
    eoff = eqcurve(tr_off); eon = eqcurve(tr_on)
    L = max(len(eoff), len(eon))
    eq_rows = []
    for k in range(L):
        eq_rows.append({'step': k,
                        'OFF_date': eoff[k][0] if k < len(eoff) else '',
                        'OFF_cap': eoff[k][1] if k < len(eoff) else '',
                        'ON_date': eon[k][0] if k < len(eon) else '',
                        'ON_cap': eon[k][1] if k < len(eon) else ''})
    pd.DataFrame(eq_rows).to_csv(os.path.join(HERE, "sfrs_equity.csv"), index=False, encoding='utf-8-sig')

    with open(os.path.join(HERE, ".sfrs_metric"), 'w', encoding='utf-8') as f:
        f.write(f"has_oi={int(has_oi)}\n")
        f.write(f"off_n={s_off['n']}\non_n={s_on['n']}\n")
        f.write(f"off_PF={s_off['PF']}\non_PF={s_on['PF']}\n")
        f.write(f"off_cumR={s_off['cumR']}\non_cumR={s_on['cumR']}\n")
        f.write(f"off_mdd={s_off['mdd']}\non_mdd={s_on['mdd']}\n")
        f.write(f"off_fin={s_off['fin']}\non_fin={s_on['fin']}\n")
        f.write(f"off_flip={off_flip['n']}\non_flip={on_flip['n']}\n")
        f.write(f"bars={len(df_tf)}\n")

    print(f"[save] sfrs_summary.csv + sfrs_trades.csv + sfrs_equity.csv")


if __name__ == "__main__":
    main()
