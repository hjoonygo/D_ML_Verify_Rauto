# -*- coding: utf-8 -*-
# [FILE] test.py  (SpTrd_Fib_V0_stg7 - Sizing study + ADX plateau check, 36mo BTC 7h)
# CODE LENGTH: approx 430 lines | INTERNAL VER: SpTrdFib_stg7_sizing | full output, no omission
#
# [PURPOSE / 목적] stg6에서 ML이 고른 ADX 필터가 검증기 PF를 1.14->1.40 올렸으나,
#   '파산 YES'가 떴다. 이는 진짜 파산이 아니라 사이징 착시(명목5만 고정/자본1만)다.
#   stg7은 (A) 전략·거래는 그대로 두고 '사이징 방식'만 8종으로 바꿔 진짜 성과를 본다.
#   (B) 동시에 ADX 18/20/22를 비교해 '20만 튀는가 아니면 18~22가 다 좋은가(고원)'를 확인한다.
#   ★전략 로직(진입·청산·ADX필터)은 stg6와 한 줄도 안 바뀜. 사이징 계산만 분기.
#
# [사이징 8종 - 사용자 승인]
#   S0_fixed      : 고정명목 5만 (현재 방식, 파산착시 재현 기준선)
#   S1_pct05      : 자본의 5% 명목 (보수 복리)
#   S2_pct10      : 자본의 10%
#   S3_pct20      : 자본의 20%
#   S4_pct30      : 자본의 30% (공격)
#   S5_kelly      : 1/4 분수켈리 (승률·손익비 기반, 직전까지 데이터로 추정=미래참조 없음)
#   S6_fixed_r    : 고정리스크 - 매 거래 자본의 1%만 위험(손절폭으로 명목 역산)
#   S7_pct10_lev3 : 자본10% x 레버3배 (선물 레버 효과, MDD 같이 봄)
#   + S8_pct10_lev5: 자본10% x 레버5배 (참고용, 위험)
#
# [ADX 고원확인 - 사용자 승인] ADX {18,20,22} 각각 필터 적용 (고정명목 기준) 비교.
#
# [핵심지표] 최종자본 / CAGR(연복리) / 월환산 / MDD(최대낙폭) / 진짜파산 / 최저자본
#   ★사이징은 R 기댓값(알파)을 안 바꾼다. '같은 알파를 얼마나 키우/지키느냐'만 본다.
#
# [SPEED] 거래는 ADX필터별 1회만 생성(사전계산), 사이징은 그 거래 R배열에 후처리(초고속).
# [PATH] D:\ML\verify\SpTrd_Fib_V0_stg7\ , 데이터 상위, 결과 CSV 이 하위폴더.
# [DATA] ..\Merged_Data_with_Regime_Features.csv (OHLC만)
# [OUTPUT] sfstg7_sizing.csv(사이징8칸) + sfstg7_adx.csv(ADX고원3칸) + sfstg7_trades.csv
#
# [FUNCTIONS In/Out]
#   find_data/load_data/resample_tf/pivots_lr/compute_atr/compute_adx/pivot_supertrend/compute_signals
#                                              (stg6 검증본 그대로)
#   run_strategy(df_tf,sig,adx_th)->trades     ADX필터 백테스트(거래 생성)
#   equity_by_sizing(trades,mode,param,lev)->dict   거래R배열에 사이징 적용->자본곡선지표
#   max_drawdown(caps)->float
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
TF_MIN = 7 * 60
ADX_N = 14
START_CAP = 10000.0; MIN_CAP_FRAC = 0.01   # 시작자본의 1% 밑이면 진짜 파산
ADX_MAIN = 20
ADX_PLATEAU = [18, 20, 22]

# 사이징 칸 (라벨, 모드, 파라미터, 레버)
SIZINGS = [
    ('S0_fixed',      'fixed',   50000, 1.0),
    ('S1_pct05',      'pct',     0.05,  1.0),
    ('S2_pct10',      'pct',     0.10,  1.0),
    ('S3_pct20',      'pct',     0.20,  1.0),
    ('S4_pct30',      'pct',     0.30,  1.0),
    ('S5_kelly',      'kelly',   0.25,  1.0),
    ('S6_fixed_r',    'fixedr',  0.01,  1.0),
    ('S7_pct10_lev3', 'pct',     0.10,  3.0),
    ('S8_pct10_lev5', 'pct',     0.10,  5.0),
]


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
    N = len(close)
    tr = np.zeros(N); pdm = np.zeros(N); ndm = np.zeros(N)
    up = high[1:] - high[:-1]; dn = low[:-1] - low[1:]
    pdm[1:] = np.where((up > dn) & (up > 0), up, 0.0)
    ndm[1:] = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr[1:] = np.maximum.reduce([high[1:] - low[1:],
                                np.abs(high[1:] - close[:-1]),
                                np.abs(low[1:] - close[:-1])])
    atrw = np.zeros(N); pdmw = np.zeros(N); ndmw = np.zeros(N); adx = np.zeros(N); dx = np.zeros(N)
    if N <= n + 1:
        return adx
    atrw[n] = tr[1:n + 1].sum(); pdmw[n] = pdm[1:n + 1].sum(); ndmw[n] = ndm[1:n + 1].sum()
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
    high = df_tf['high'].values; low = df_tf['low'].values; close = df_tf['close'].values
    Trend, center, atr, Up, Dn = pivot_supertrend(df_tf)
    adx = compute_adx(high, low, close, ADX_N)
    ph_conf, pl_conf = pivots_lr(high, low, LEFT, RIGHT)
    return {'Trend': Trend, 'adx': adx, 'ph_conf': ph_conf, 'pl_conf': pl_conf}


def run_strategy(df_tf, sig, adx_th):
    """ADX 필터 백테스트. 숏은 adx>=adx_th일 때만(ADX<th=횡보 보류). 롱 무수정.
    각 거래에 R과 손절폭(sl_dist=초기손절까지 거리%)을 기록(고정리스크 사이징용)."""
    high = df_tf['high'].values; low = df_tf['low'].values
    close = df_tf['close'].values; open_ = df_tf['open'].values
    idx = df_tf.index; n = len(close)
    Trend = sig['Trend']; adx = sig['adx']; ph_conf = sig['ph_conf']; pl_conf = sig['pl_conf']
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
                px = close[i]; R = pos * (px - entry_price) / entry_price
                fp = FUND_8H * n_fund(entry_i, i); Rn = R - COST - fp
                trades.append({'entry_t': idx[entry_i], 'exit_t': idx[i], 'side': pos,
                               'entry': entry_price, 'exit': px, 'R': Rn, 'reason': 'trend_flip',
                               'bars': i - entry_i, 'year': idx[i].year, 'sl_dist': SL_PCT / 100})
                pos = 0; sl = np.nan; pb = 0; continue
            if i > entry_i and not np.isnan(sl):
                o_, h_, l_, c_ = open_[i], high[i], low[i], close[i]
                ticks = (o_, h_, l_, c_) if c_ < o_ else (o_, l_, h_, c_)
                hit = False
                for px in ticks:
                    if pos == 1 and px <= sl: hit = True; break
                    if pos == -1 and px >= sl: hit = True; break
                if hit:
                    R = pos * (sl - entry_price) / entry_price
                    fp = FUND_8H * n_fund(entry_i, i); Rn = R - COST - fp
                    trades.append({'entry_t': idx[entry_i], 'exit_t': idx[i], 'side': pos,
                                   'entry': entry_price, 'exit': sl, 'R': Rn, 'reason': 'sl',
                                   'bars': i - entry_i, 'year': idx[i].year, 'sl_dist': SL_PCT / 100})
                    pos = 0; sl = np.nan; pb = 0; continue
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
            if se and adx[i] < adx_th:   # ADX<th=횡보 -> 숏 보류
                se = False
            if le:
                pos = 1; entry_price = close[i]; entry_i = i; pb = 0
                sl = entry_price * (1 - SL_PCT / 100)
            elif se:
                pos = -1; entry_price = close[i]; entry_i = i; pb = 0
                sl = entry_price * (1 + SL_PCT / 100)
    return trades


def max_drawdown(caps):
    peak = -1e18; mdd = 0.0
    for c in caps:
        peak = max(peak, c)
        if peak > 0:
            dd = (c - peak) / peak
            mdd = min(mdd, dd)
    return mdd


def equity_by_sizing(trades, mode, param, lev):
    """거래 R배열에 사이징 적용 -> 자본곡선 지표. 사이징은 알파(R) 불변, 자본관리만.
    kelly/fixedr은 직전까지 정보로만 추정(미래참조 없음)."""
    cap = START_CAP; caps = [cap]; bankrupt = False
    floor = START_CAP * MIN_CAP_FRAC
    Rs = [t['R'] for t in trades]
    win_hist = []  # 켈리용 누적 승/패
    for t in trades:
        R = t['R']
        if mode == 'fixed':
            notional = param
        elif mode == 'pct':
            notional = cap * param
        elif mode == 'fixedr':
            # 자본의 param(1%)만 위험. 손절폭 sl_dist로 명목 역산: notional = riskcash/sl_dist
            riskcash = cap * param
            notional = riskcash / max(t['sl_dist'], 1e-4)
            notional = min(notional, cap * 1.0)  # 명목이 자본 넘지 않게 cap
        elif mode == 'kelly':
            # 직전까지 승률·손익비로 분수켈리(param=1/4). 표본 부족시 보수적 5%.
            if len(win_hist) >= 20:
                w = np.array(win_hist)
                p = (w > 0).mean(); avgW = w[w > 0].mean() if (w > 0).any() else 0
                avgL = -w[w < 0].mean() if (w < 0).any() else 1e-4
                b = avgW / max(avgL, 1e-4)
                kelly = max(0.0, p - (1 - p) / max(b, 1e-4))
                frac = min(kelly * param, 0.5)   # 분수켈리, 상한 50%
                notional = cap * max(frac, 0.01)
            else:
                notional = cap * 0.05
        else:
            notional = param
        cap += R * notional * lev
        caps.append(cap)
        win_hist.append(R)
        if cap <= floor:
            bankrupt = True
            break
    caps = np.array(caps)
    years = 36 / 12.0
    final = caps[-1]
    if bankrupt or final <= 0:
        cagr = -1.0
    else:
        cagr = (final / START_CAP) ** (1 / years) - 1
    mdd = max_drawdown(caps)
    return {'최종자본': round(float(final), 0), 'CAGR_pct': round(cagr * 100, 1),
            '월환산_pct': round(((1 + cagr) ** (1 / 12) - 1) * 100, 2) if cagr > -1 else -100,
            'MDD_pct': round(mdd * 100, 1), '진짜파산': 'YES' if bankrupt else 'NO',
            '최저자본': round(float(caps.min()), 0), '거래수': len(trades)}


def main():
    print("[SpTrd_Fib_V0_stg7] Sizing study + ADX plateau - 36mo BTC 7h")
    open(os.path.join(HERE, ".run_start"), 'w').close()
    data = find_data(); print(f"[data] {data}")
    df1m = load_data(data)
    print(f"[load] {len(df1m):,}rows | {df1m.index.min().date()}~{df1m.index.max().date()}")
    df_tf = resample_tf(df1m, TF_MIN)
    print(f"[7h] {len(df_tf)}bars")
    sig = compute_signals(df_tf)

    # === ADX 고원확인: 18/20/22 (고정명목 기준) ===
    print("\n--- ADX 고원확인 (18/20/22) ---")
    adx_rows = []
    trades_main = None
    for th in ADX_PLATEAU:
        tr = run_strategy(df_tf, sig, th)
        R = np.array([t['R'] for t in tr])
        wins = R[R > 0]; losses = R[R < 0]
        pf = wins.sum() / (-losses.sum()) if losses.sum() < 0 else 999
        # train/test
        Rtr = np.array([t['R'] for t in tr if t['year'] in [2023, 2024]])
        Rte = np.array([t['R'] for t in tr if t['year'] in [2025, 2026]])
        pftr = Rtr[Rtr > 0].sum() / max(-Rtr[Rtr < 0].sum(), 1e-9)
        pfte = Rte[Rte > 0].sum() / max(-Rte[Rte < 0].sum(), 1e-9)
        adx_rows.append({'ADX임계': th, '거래수': len(tr), '누적R_pct': round(R.sum() * 100, 2),
                         'PF_all': round(pf, 3), 'PF_train': round(pftr, 3), 'PF_test': round(pfte, 3),
                         '승률_pct': round((R > 0).mean() * 100, 1)})
        print(f"  ADX{th}: 거래{len(tr)} 누적R{R.sum()*100:.1f}% PF_all{pf:.3f} "
              f"train{pftr:.3f} test{pfte:.3f}")
        if th == ADX_MAIN:
            trades_main = tr
    pd.DataFrame(adx_rows).to_csv(os.path.join(HERE, "sfstg7_adx.csv"), index=False, encoding='utf-8-sig')
    plat = all(r['PF_test'] > 1.0 for r in adx_rows)
    print(f"  => {'고원(18~22 모두 test PF>1, 견고)' if plat else '봉우리(일부 미달, 우연의심)'}")

    # === 사이징 8칸 (ADX20 거래에 적용) ===
    print("\n--- 사이징 8칸 (ADX20 거래 기준) ---")
    size_rows = []
    for lab, mode, param, lev in SIZINGS:
        m = equity_by_sizing(trades_main, mode, param, lev)
        m = {'사이징': lab, **m}
        size_rows.append(m)
        print(f"  [{lab:14s}] 최종{m['최종자본']:>12,.0f} CAGR{m['CAGR_pct']:>6.1f}% "
              f"월{m['월환산_pct']:>6.2f}% MDD{m['MDD_pct']:>6.1f}% 파산{m['진짜파산']}")
    pd.DataFrame(size_rows).to_csv(os.path.join(HERE, "sfstg7_sizing.csv"), index=False, encoding='utf-8-sig')

    # 거래 상세(ADX20)
    td = [{'side': t['side'], 'entry_t': t['entry_t'].strftime('%Y-%m-%d %H:%M'),
           'exit_t': t['exit_t'].strftime('%Y-%m-%d %H:%M'), 'year': t['year'],
           'entry': round(t['entry'], 2), 'exit': round(t['exit'], 2),
           'R_pct': round(t['R'] * 100, 4), 'reason': t['reason'], 'bars': t['bars']}
          for t in trades_main]
    pd.DataFrame(td).to_csv(os.path.join(HERE, "sfstg7_trades.csv"), index=False, encoding='utf-8-sig')
    print("[save] sfstg7_sizing.csv + sfstg7_adx.csv + sfstg7_trades.csv - all files")


if __name__ == "__main__":
    main()
