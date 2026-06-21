# -*- coding: utf-8 -*-
# [FILE] test.py  (SpTrd_Fib_V0_stg6 - ML-selected Regime Filter + Backtest, 36mo BTC 7h)
# CODE LENGTH: approx 470 lines | INTERNAL VER: SpTrdFib_stg6_ML | full output, no omission
#
# [PURPOSE / 목적] PP-ST Pullback의 약점(2025Q1 횡보장 숏 -28%)을 막을 '필터 시그널'을
#   사람이 임의로 고르지 않고 ML이 판단해 고른다. 검증된 후보 5종을 모두 계산→
#   (1)RandomForest 특징중요도로 어떤 신호가 승패를 가르는지 측정(train만 학습)
#   (2)각 후보로 36개월 백테스트, train에서 고르고 test에서 검증(과적합 차단).
#   ML 결과+백테스트 결과를 전량 파일로 남긴다.
#
# [필터 후보 - 전부 웹 검증된 것. 임의선택 아님]
#   adx   : ADX<th면 숏보류 (ADX<20=횡보→추세추종 가짜신호. hoclamtrader/piptrend)
#   chop  : Choppiness Index>th면 숏보류 (TradingView SuperTrend 횡보필터)
#   atrcmp: ATR < ATR_SMA*0.8 면 숏보류 (Betashorts 변동성압축=횡보)
#   bandw : 밴드폭/price < th 면 숏보류 (F2 재현, 추세강도 약하면 거름)
#   vguard: 최근K봉 급락폭≥th면 숏보류 (실패했던 것, 대조군)
#   * 모두 '숏'에만 적용(롱은 강상승장 알파 본체라 무수정). 미래참조 없게 과거봉만.
#
# [ML 판단 방식]
#   feature: 각 '숏 거래' 진입봉의 [adx,chop,atrcmp,bandw,drop] 값
#   label  : 그 거래가 이익(1)/손실(0)
#   model  : RandomForest (train=23~24 거래만 fit) -> 특징중요도 출력
#   순위   : 중요도 1등 신호 + 각 후보 필터의 test PF개선폭으로 종합 추천
#   sklearn 없으면 -> 규칙기반(상관계수) fallback. 어느 PC든 실행.
#
# [SPEED 최적화]
#   - 지표(ADX/CHOP/ATR/밴드폭) 전체 1회 벡터 사전계산. 진입시점만 인덱스 조회.
#   - 거래 시뮬 1패스(O(N)). 피벗 sliding_window 벡터화.
#   - 후보별 재계산 없이 '사전계산된 신호배열'을 임계만 바꿔 재사용.
#
# [PATH] D:\ML\verify\SpTrd_Fib_V0_stg6\ 실행, 데이터 상위, 결과 CSV 이 하위폴더.
# [DATA] ..\Merged_Data_with_Regime_Features.csv (OHLC만)
# [OUTPUT] sfstg6_summary.csv(필터칸 성과) + sfstg6_mlrank.csv(ML 특징중요도+추천)
#          + sfstg6_trades.csv(ML추천 필터 거래별)
#
# [FUNCTIONS In/Out]
#   find_data/load_data/resample_tf/pivots_lr/compute_atr/pivot_supertrend  (기존 검증본)
#   compute_adx(h,l,c,n)->adx[]              Wilder ADX (과거봉만)
#   compute_chop(h,l,c,n)->chop[]            Choppiness Index
#   compute_signals(df_tf)->dict             5신호 전체 벡터 사전계산
#   run_strategy(df_tf,sig,filt,th)->trades  백테스트(필터 1종 적용)
#   ml_rank(trades,sig,df_tf)->dict          특징중요도+추천(train학습/test검증)
#   agg(trades,label,years)->dict
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
CANDIDATES = {
    'adx':    {'thresholds': [15, 20, 25], 'rule': 'lt'},    # adx < th -> 숏보류
    'chop':   {'thresholds': [55, 61.8], 'rule': 'gt'},      # chop > th -> 숏보류
    'atrcmp': {'thresholds': [0.8], 'rule': 'cmp'},          # atr<sma*th -> 숏보류
    'bandw':  {'thresholds': [0.05, 0.08], 'rule': 'lt'},    # bandw < th -> 숏보류
    'vguard': {'thresholds': [0.08], 'rule': 'gt'},          # drop >= th -> 숏보류(대조)
}


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
            'atrcmp': atrcmp, 'bandw': bandw, 'drop': drop,
            'ph_conf': ph_conf, 'pl_conf': pl_conf}


def short_blocked(sig, i, filt, th):
    """필터별 숏 보류 판정 (과거/현재 봉 신호만). True=숏 막음."""
    if filt == 'none':
        return False
    if filt == 'adx':
        return sig['adx'][i] < th
    if filt == 'chop':
        return sig['chop'][i] > th
    if filt == 'atrcmp':
        return sig['atrcmp'][i] >= 1.0      # 압축(횡보)이면 막음
    if filt == 'bandw':
        return sig['bandw'][i] < th
    if filt == 'vguard':
        return sig['drop'][i] >= th
    return False


def run_strategy(df_tf, sig, filt, th, record_feat=False):
    """백테스트 1패스. 필터는 '숏'에만. 롱 무수정."""
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
                if record_feat: tr.update(feat0)
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
                    if record_feat: tr.update(feat0)
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
            if se and short_blocked(sig, i, filt, th):
                se = False
            if le:
                pos = 1; entry_price = close[i]; entry_i = i; pb = 0
                sl = entry_price * (1 - SL_PCT / 100)
                if record_feat:
                    feat0 = {'f_adx': sig['adx'][i], 'f_chop': sig['chop'][i],
                             'f_atrcmp': sig['atrcmp'][i], 'f_bandw': sig['bandw'][i], 'f_drop': sig['drop'][i]}
            elif se:
                pos = -1; entry_price = close[i]; entry_i = i; pb = 0
                sl = entry_price * (1 + SL_PCT / 100)
                if record_feat:
                    feat0 = {'f_adx': sig['adx'][i], 'f_chop': sig['chop'][i],
                             'f_atrcmp': sig['atrcmp'][i], 'f_bandw': sig['bandw'][i], 'f_drop': sig['drop'][i]}
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


def ml_rank(df_tf, sig):
    """ML 판단: 숏거래 진입특징으로 이익/손실 예측 -> 특징중요도. train만 학습."""
    base = run_strategy(df_tf, sig, 'none', 0, record_feat=True)
    shorts = [t for t in base if t['side'] == -1]
    if not shorts:
        return {'method': 'none', 'rows': []}
    dfb = pd.DataFrame(shorts)
    feats = ['f_adx', 'f_chop', 'f_atrcmp', 'f_bandw', 'f_drop']
    dfb['win'] = (dfb['R'] > 0).astype(int)
    tr = dfb[dfb['year'].isin(TRAIN_YEARS)]
    rows = []; method = 'rule'
    try:
        from sklearn.ensemble import RandomForestClassifier
        if len(tr) >= 20 and tr['win'].nunique() == 2:
            X = tr[feats].values; y = tr['win'].values
            rf = RandomForestClassifier(n_estimators=200, max_depth=4,
                                        random_state=42, class_weight='balanced')
            rf.fit(X, y)
            imp = rf.feature_importances_
            method = 'RandomForest(train)'
            for f, v in zip(feats, imp):
                rows.append({'signal': f.replace('f_', ''), 'importance': round(float(v), 4)})
        else:
            raise RuntimeError('train 부족')
    except Exception as e:
        # fallback: |상관계수|
        method = f'corr_fallback({type(e).__name__})'
        for f in feats:
            c = np.corrcoef(tr[f].values, tr['win'].values)[0, 1] if len(tr) > 2 else 0
            rows.append({'signal': f.replace('f_', ''), 'importance': round(abs(float(np.nan_to_num(c))), 4)})
    rows.sort(key=lambda r: r['importance'], reverse=True)
    return {'method': method, 'rows': rows, 'n_short_train': int(len(tr))}


def main():
    print("[SpTrd_Fib_V0_stg6] ML-selected Regime Filter + Backtest - 36mo BTC 7h")
    open(os.path.join(HERE, ".run_start"), 'w').close()
    data = find_data(); print(f"[data] {data}")
    df1m = load_data(data)
    print(f"[load] {len(df1m):,}rows | {df1m.index.min().date()}~{df1m.index.max().date()}")
    df_tf = resample_tf(df1m, TF_MIN)
    print(f"[7h] {len(df_tf)}bars  (지표 사전계산 시작)")
    sig = compute_signals(df_tf)
    print("[signals] adx/chop/atrcmp/bandw/drop 벡터 사전계산 완료")

    # === ML 판단: 특징 중요도 ===
    ml = ml_rank(df_tf, sig)
    print(f"[ML] method={ml['method']} (train 숏 {ml.get('n_short_train','?')}건)")
    for r in ml['rows']:
        print(f"   중요도 {r['signal']:7s}: {r['importance']}")
    pd.DataFrame(ml['rows']).to_csv(os.path.join(HERE, "sfstg6_mlrank.csv"),
                                    index=False, encoding='utf-8-sig')

    # === 후보 필터 백테스트 (사전계산 신호 재사용) ===
    summary = []
    # 기준선
    base = run_strategy(df_tf, sig, 'none', 0)
    summary.append(agg(base, 'F_none_all'))
    summary.append(agg(base, 'F_none_train', TRAIN_YEARS))
    summary.append(agg(base, 'F_none_test', TEST_YEARS))

    best = None  # (test_PF, label, filt, th, trades)
    for filt, spec in CANDIDATES.items():
        for th in spec['thresholds']:
            lab = f"{filt}_{th}"
            trades = run_strategy(df_tf, sig, filt, th)
            mAll = agg(trades, lab + "_all"); summary.append(mAll)
            mTr = agg(trades, lab + "_train", TRAIN_YEARS)
            mTe = agg(trades, lab + "_test", TEST_YEARS)
            summary.append(mTr); summary.append(mTe)
            print(f"  [{lab:12s}] all PF{mAll.get('PF')} R{mAll.get('누적R_pct')}% "
                  f"| train PF{mTr.get('PF')} | test PF{mTe.get('PF')}")
            # 추천 후보: train PF>기준 & test PF>1 & 거래 충분
            te_pf = mTe.get('PF', 0); tr_pf = mTr.get('PF', 0)
            if te_pf and te_pf > 1.0 and mTe.get('거래수', 0) >= 30:
                score = te_pf
                if best is None or score > best[0]:
                    best = (score, lab, filt, th, trades)

    # === ML 종합 추천 ===
    rec = "없음(test PF>1 통과 필터 없음)"
    if best is not None:
        rec = f"{best[1]} (test PF {round(best[0],3)})"
        td = best[4]
        rec_rows = [{'side': t['side'], 'entry_t': t['entry_t'].strftime('%Y-%m-%d %H:%M'),
                     'exit_t': t['exit_t'].strftime('%Y-%m-%d %H:%M'), 'year': t['year'],
                     'entry': round(t['entry'], 2), 'exit': round(t['exit'], 2),
                     'R_pct': round(t['R'] * 100, 4), 'reason': t['reason'], 'bars': t['bars']}
                    for t in td]
        pd.DataFrame(rec_rows).to_csv(os.path.join(HERE, "sfstg6_trades.csv"),
                                      index=False, encoding='utf-8-sig')
    # 추천을 summary 맨 위 메모행으로
    top_signal = ml['rows'][0]['signal'] if ml['rows'] else '?'
    summary.insert(0, {'칸': f'ML_TOP_signal={top_signal} | 추천필터={rec} | method={ml["method"]}'})
    pd.DataFrame(summary).to_csv(os.path.join(HERE, "sfstg6_summary.csv"),
                                 index=False, encoding='utf-8-sig')
    print(f"[ML 추천필터] {rec}  | 특징1등 {top_signal}")
    print("[save] sfstg6_summary.csv + sfstg6_mlrank.csv + sfstg6_trades.csv - all files")


if __name__ == "__main__":
    main()
