# -*- coding: utf-8 -*-
# [FILE] test.py  (SpTrd_Fib_V0_stg8 - ADX x ATRcmp combo filter, 36mo BTC 7h)
# CODE LENGTH: approx 420 lines | INTERNAL VER: SpTrdFib_stg8_combo | full output, no omission
#
# [PURPOSE] stg6에서 ADX20(+0.26)과 atrcmp(+0.17)가 각각 검증기 PF를 올렸다.
#   stg8은 둘을 조합(OR/AND)해 시너지가 나는지(test PF가 단독보다 오르는지) 본다.
#   엔진(진입/청산/피보트레일)은 stg6/7과 동일. 숏 필터 자리에 조합 로직만 추가.
#
# [조합 로직 - 사용자 승인]
#   OR  : ADX<th 또는 atr압축 중 하나라도면 숏 보류(깐깐). 휩소 강하게 거름.
#   AND : ADX<th 그리고 atr압축 둘다일때만 숏 보류(느슨). 확실한 횡보만.
#   * 필터는 숏에만. 롱 무수정. 미래참조 없게 과거봉만(stg6 검증본 재사용).
#
# [GRID 8칸] none/adx20단독/atrcmp단독/OR/AND/OR_adx18/OR_adx22/atr0.7배
#   각칸: 거래/승률/누적R/train PF/test PF/MDD. 합격선=조합 test PF>단독 test PF.
#
# [측정 - 사용자 승인] 판정=누적R·PF. 참고로 S4(자본30%) 자본곡선 MDD 동반표기.
#   (stg7서 고정명목은 파산착시 확인 -> 자본비율로 곡선 봄)
#
# [SPEED] 신호 1회 사전계산, 조합은 임계만 바꿔 재사용. 거래루프 1패스.
# [PATH] D:\ML\verify\SpTrd_Fib_V0_stg8\ , 데이터 상위, 결과 이 하위폴더.
# [DATA] ..\Merged_Data_with_Regime_Features.csv (OHLC만)
# [OUTPUT] sfstg8_summary.csv(8칸 train/test) + sfstg8_trades.csv(최적칸 거래)
#
# [FUNCTIONS] compute_signals/run_strategy(combo)/agg/equity_s4  + stg6 검증본 재사용
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


def run_strategy(df_tf, sig, adx_th, mode, atr_mult):
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


def main():
    print("[SpTrd_Fib_V0_stg8] ADX x ATRcmp combo filter - 36mo BTC 7h")
    open(os.path.join(HERE, ".run_start"), 'w').close()
    data = find_data(); print(f"[data] {data}")
    df1m = load_data(data)
    print(f"[load] {len(df1m):,}rows | {df1m.index.min().date()}~{df1m.index.max().date()}")
    df_tf = resample_tf(df1m, TF_MIN)
    print(f"[7h] {len(df_tf)}bars (지표 사전계산)")
    sig = compute_signals(df_tf)

    summary = []
    cell_trades = {}
    for lab, adx_th, mode, atr_mult in GRID:
        trades = run_strategy(df_tf, sig, adx_th, mode, atr_mult)
        cell_trades[lab] = trades
        mAll = agg(trades, lab + "_all")
        mTr = agg(trades, lab + "_train", TRAIN_YEARS)
        mTe = agg(trades, lab + "_test", TEST_YEARS)
        # 참고 S4 자본곡선
        fin, mdd, bust = equity_s4(trades, S4_PCT)
        mAll['S4_최종'] = fin; mAll['S4_MDD_pct'] = mdd; mAll['S4_파산'] = bust
        summary.append(mAll); summary.append(mTr); summary.append(mTe)
        print(f"  [{lab:12s}] 거래{mAll.get('거래수')} 누적R{mAll.get('누적R_pct')}% "
              f"PF_all{mAll.get('PF')} train{mTr.get('PF')} test{mTe.get('PF')} "
              f"| S4최종{fin:,.0f} MDD{mdd}%")

    # 조합 시너지 판정: C3_OR/C4_AND test PF vs C1/C2 단독
    def te_pf(lab):
        r = [m for m in summary if m.get('칸') == lab + '_test']
        return r[0].get('PF', 0) if r else 0
    solo_best = max(te_pf('C1_adx20'), te_pf('C2_atrcmp'))
    or_pf = te_pf('C3_OR'); and_pf = te_pf('C4_AND')
    verdict = (f"단독최고 test PF={solo_best} | OR={or_pf} AND={and_pf} -> "
               + ("조합 시너지 있음" if max(or_pf, and_pf) > solo_best else "조합 무익(단독이 낫거나 같음)"))
    summary.insert(0, {'칸': 'VERDICT: ' + verdict})
    print(f"[판정] {verdict}")

    pd.DataFrame(summary).to_csv(os.path.join(HERE, "sfstg8_summary.csv"), index=False, encoding='utf-8-sig')
    # 최적칸(조합 중 test PF 최고, 없으면 C1) 거래 저장
    best_lab = 'C3_OR' if or_pf >= and_pf else 'C4_AND'
    if max(or_pf, and_pf) <= solo_best:
        best_lab = 'C1_adx20'
    bt = cell_trades.get(best_lab, [])
    td = [{'side': t['side'], 'entry_t': t['entry_t'].strftime('%Y-%m-%d %H:%M'),
           'exit_t': t['exit_t'].strftime('%Y-%m-%d %H:%M'), 'year': t['year'],
           'entry': round(t['entry'], 2), 'exit': round(t['exit'], 2),
           'R_pct': round(t['R'] * 100, 4), 'reason': t['reason'], 'bars': t['bars']}
          for t in bt]
    pd.DataFrame(td).to_csv(os.path.join(HERE, "sfstg8_trades.csv"), index=False, encoding='utf-8-sig')
    print(f"[save] sfstg8_summary.csv + sfstg8_trades.csv (best={best_lab}) - all files")


if __name__ == "__main__":
    main()
