# [파일명] trendstack_signal_engine.py
# 코드길이: 약 320줄 / 내부버전: trendstack_signal_engine_v1 (SpTrd_Fib_V1_Champion 추출)
# ─────────────────────────────────────────────────────────────────────────
# [목적] TrendStack 진입/청산 '신호 코어'. SpTrd_Fib_V1_Champion.py(06_Ch4 통합, 업로드 원본)에서
#        신호 생성 로직을 '한 글자도 바꾸지 않고' 추출(전사 오류 방지: sed로 원본 라인 그대로 복사).
#        원본 라인: 상수 100-126·146-153 / 함수 196-508
#          resample_tf · pivots_lr · compute_atr · compute_adx · compute_chop ·
#          pivot_supertrend · compute_signals · short_blocked_combo · compute_split_entry · run_strategy
# [확정설정(FINAL)] gate_mode='er', gate_er=0.45, dz=[0,1), split_mode='A', split_n=3, fib=(0.3,0.5,0.6), 숏차단 none
# [미래참조] 원본과 동일 — ER/ADX/피벗/OI 진입봉까지 과거값, 종가체결. (단 compute_split_entry는
#            진입 후 i+1..i+20 봉으로 '체결가'를 모사 = 백테스트 체결 모사이지 진입결정의 미래참조 아님.)
# [In] df_tf(7h OHLC, DatetimeIndex) + sig(compute_signals 결과) [Out] trades 리스트
# ─────────────────────────────────────────────────────────────────────────
import os, sys
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

DZ_LO, DZ_HI = 0.0, 1.0
OI_CANDS = ["Merged_Data.csv", "merged_data.csv", "merged_data_sample.csv"]

# ── 장세판단(추세장 게이트) 설정 ──
ER_N = 20                 # ER 계산 봉수
ER_TREND = 0.40           # ER 이상이면 추세장(검색 출처 문턱)
ADX_TREND = 25.0          # ADX 이상이면 추세장
BB_EXPAND_PCT = 0.5       # bb_width_pct 이상이면 변동성 확장(2축 정의용)


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
    # ── ER(Efficiency Ratio): |끝-시작| / Σ|봉별변화| (ER_N봉). 1=추세, 0=횡보. 과거봉만(미래참조X) ──
    er = np.zeros(n)
    for i in range(n):
        lo = max(0, i - ER_N + 1)
        seg = close[lo:i + 1]
        if len(seg) >= 2:
            net = abs(seg[-1] - seg[0])
            tot = np.abs(np.diff(seg)).sum()
            er[i] = (net / tot) if tot > 0 else 0.0
    return {'Trend': Trend, 'Up': Up, 'Dn': Dn, 'adx': adx, 'chop': chop,
            'atrcmp': atrcmp, 'atr': atr, 'atr_sma': atr_sma, 'bandw': bandw, 'drop': drop,
            'er': er, 'ph_conf': ph_conf, 'pl_conf': pl_conf}


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


def compute_split_entry(d, i, close, high, low, open_, n, pl_conf, ph_conf, lastPH, lastPL,
                        split_mode, split_n):
    # 분할진입 평단가 반환. 미래참조 없음: 진입봉 i의 종가는 확정, 이후 분할은 i+1.. 봉 가격 사용
    #   (이후 봉 가격을 '그때 가서' 체결하는 것이라 진입결정 시점 미래참조 아님 — 실제 체결을 모사).
    #   split_mode 'none' → 전량 close[i].
    #   'A' 피보되돌림: 신호가 대비 0.382/0.5/0.618 되돌림 가격에 분할 지정가. 도달한 것만 체결,
    #                   미도달분은 마지막 가능가로 마감(보수적). 평단 = 체결가 평균.
    #   'B' 시간균등: i, i+1, ... i+split_n-1 봉 종가에 1/split_n씩. 평단 = 종가 평균.
    base = close[i]
    if split_mode == 'none' or split_n <= 1:
        return base
    fills = [base]   # 1차는 신호봉 종가(항상 체결)
    if split_mode == 'B':
        for k in range(1, split_n):
            j = i + k
            fills.append(close[j] if j < n else close[min(i + k, n - 1)])
    elif split_mode == 'A':
        # 되돌림 레벨(진입방향 반대로 되돌림). 최근 스윙폭 기준 근사.
        levels = [0.382, 0.5, 0.618][:split_n - 1]
        if d == 1 and not np.isnan(lastPH) and not np.isnan(lastPL):
            swing = lastPH - lastPL
            for lv in levels:
                target = base - lv * swing * 0.1   # 되돌림 목표(보수적 축소)
                # 이후 20봉 내 target 이하 도달하면 체결, 아니면 미체결→평단에서 제외
                got = None
                for j in range(i + 1, min(i + 21, n)):
                    if low[j] <= target:
                        got = target; break
                fills.append(got if got is not None else base)
        elif d == -1 and not np.isnan(lastPH) and not np.isnan(lastPL):
            swing = lastPH - lastPL
            for lv in levels:
                target = base + lv * swing * 0.1
                got = None
                for j in range(i + 1, min(i + 21, n)):
                    if high[j] >= target:
                        got = target; break
                fills.append(got if got is not None else base)
        else:
            return base
    return float(np.mean(fills))


def run_strategy(df_tf, sig, adx_th, mode, atr_mult, dz_oi=None, dz_lo=DZ_LO, dz_hi=DZ_HI,
                 gate_mode='none', gate_adx=ADX_TREND, gate_er=ER_TREND, gate_bb=None,
                 fib=FIB, lev=LEVERAGE, split_mode='none', split_n=1):
    # [묶음2 신규 인자]
    #   fib: 피보 트레일링 비율 튜플(pb 1·2·3단계). 원본 (0.3,0.5,0.6).
    #   lev: 레버리지 배수(R에 곱). 원본 1.0.
    #   split_mode: 분할진입. 'none'=전량(원본) / 'A'=피보되돌림 분할 / 'B'=시간균등 분할.
    #   split_n: 분할 수(2 또는 3). 진입을 N등분.
    #   ※분할은 진입가를 N개 평균으로 만듦. R 계산은 평단가 기준(미래참조 없음, 진입후 봉만 사용).
    # gate_mode: 무덤필터를 켤 '추세장' 정의.
    #   'none'=항상 켬(Stg3 방식) / 'adx'=adx>=gate_adx일때만 / 'er'=er>=gate_er일때만 /
    #   'adx_bb'=adx>=gate_adx AND bb확장(gate_bb[i]>=BB_EXPAND_PCT)일때만.
    # gate_bb: 7h봉별 bb_width_pct 배열(adx_bb 모드용) 또는 None.
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
                px = close[i]; R = pos * (px - entry_price) / entry_price * lev
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
                    R = pos * (sl - entry_price) / entry_price * lev
                    fp = FUND_8H * n_fund(entry_i, i); R = R - COST - fp
                    tr = {'entry_t': idx[entry_i], 'exit_t': idx[i], 'side': pos,
                          'entry': entry_price, 'exit': sl, 'R': R, 'reason': 'sl',
                          'bars': i - entry_i, 'fund': fp, 'year': idx[i].year}
                    trades.append(tr); pos = 0; sl = np.nan; pb = 0; continue

        if pos == 1 and new_pl:
            pb += 1; ratio = fib[0] if pb == 1 else fib[1] if pb == 2 else fib[2]
            if not np.isnan(lastPH):
                cand = lastPH - ratio * (lastPH - pl_conf[i][1])
                sl = cand if np.isnan(sl) else max(sl, cand)
        if pos == -1 and new_ph:
            pb += 1; ratio = fib[0] if pb == 1 else fib[1] if pb == 2 else fib[2]
            if not np.isnan(lastPL):
                cand = lastPL + ratio * (ph_conf[i][1] - lastPL)
                sl = cand if np.isnan(sl) else min(sl, cand)

        if pos == 0:
            le = Trend[i] == 1 and new_pl and not np.isnan(lastPH)
            se = Trend[i] == -1 and new_ph and not np.isnan(lastPL)
            if se and short_blocked_combo(sig, i, adx_th, mode, atr_mult):
                se = False
            # ── 무덤필터(DZ): 진입봉 OI z가 [DZ_LO, DZ_HI)이면 진입 보류 ──
            #   단, gate_mode가 'none'이 아니면 '추세장일 때만' 무덤필터 적용(조건부).
            #   Stg2 입증: 무덤구간 승률9%·누적-52%(p=0.0001). Stg3: 추세장엔 약, 횡보장엔 독.
            if dz_oi is not None:
                z = dz_oi[i]
                if not np.isnan(z) and (dz_lo <= z < dz_hi):
                    # 추세장 판정(게이트). 미래참조 없음(진입봉까지 신호).
                    if gate_mode == 'none':
                        is_trend = True
                    elif gate_mode == 'adx':
                        is_trend = sig['adx'][i] >= gate_adx
                    elif gate_mode == 'er':
                        is_trend = sig['er'][i] >= gate_er
                    elif gate_mode == 'adx_bb':
                        bb_ok = (gate_bb is not None and not np.isnan(gate_bb[i]) and gate_bb[i] >= BB_EXPAND_PCT)
                        is_trend = (sig['adx'][i] >= gate_adx) and bb_ok
                    else:
                        is_trend = True
                    if is_trend:           # 추세장 + 무덤구간 → 진입보류
                        le = False; se = False
            if le or se:
                d = 1 if le else -1
                # ── 분할진입: 평단가 계산(미래참조 없음, 진입봉 이후 봉만) ──
                ep = compute_split_entry(d, i, close, high, low, open_, n,
                                         pl_conf, ph_conf, lastPH, lastPL,
                                         split_mode, split_n)
                pos = d; entry_price = ep; entry_i = i; pb = 0
                sl = ep * (1 - d * SL_PCT / 100)
    return trades
