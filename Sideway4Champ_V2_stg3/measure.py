# -*- coding: utf-8 -*-
# [FILE] measure.py  (Sideway4Champ_V2_stg3 - POC reversion BY stg8 regime classification)
# CODE LENGTH: approx 320 lines | INTERNAL VER: Sideway4Champ_V2_stg3 | full output, no omission
#
# [PURPOSE] 핵심질문: "stg8 장세분류로 횡보장을 가려내면, 손실 컸던 깊은이탈을 피할 수 있나?"
#   stg2 측정에서 확인: 얕은이탈(<=1ATR)=83~96% 회귀(수익), 깊은이탈(>=2ATR)=22% 회귀(손실).
#   가설: 깊은이탈은 '추세 시작(ADX↑·ATR확장)' 구간에 몰려있다. stg8 분류로 그 구간을 끄면 개선.
#   -> 각 봉을 stg8 방식(ADX × ATR압축)으로 4장세 분류 후, 장세별 거리별 POC회귀율 측정.
#
# [stg8 분류 재현 - test.py 확인본] ADX_N=14, ATR_SMA_N=50, atrcmp = atr < atr_sma*0.8 (1=압축).
#   장세 4분류:
#     Q_RANGE(조용한횡보) : ADX<adxLo  AND atr압축        <- DCA가 살 것으로 기대되는 구간
#     L_RANGE(느슨한횡보) : ADX<adxLo  AND atr확장
#     W_TREND(약한추세)   : adxLo<=ADX<adxHi
#     S_TREND(강한추세)   : ADX>=adxHi                    <- 깊은이탈·손실 몰릴 것으로 의심되는 구간
#
# [판정] Q_RANGE의 얕은이탈(<=1ATR) 회귀율이 S_TREND보다 뚜렷이 높으면
#        -> stg8 게이트(Q_RANGE에서만 DCA)가 알파 상승. 차이 없으면 게이트 무익.
#   * train/test 일관 필수(우연 배제).
#
# [중요] 측정이라 미래봉 사용(회귀확인용). 진입신호 아님. 봇 미래참조 차단과 별개.
# [SPEED] TF별 신호 1회 계산. 장세 라벨은 봉 루프에서 부여. 1패스.
# [PATH] 실행: D:\ML\verify\Sideway4Champ_V2_stg3\ . 데이터: 상위 D:\ML\verify\ .
# [DATA] 상위 Merged_Data_with_Regime_Features.csv (없으면 merged_data.csv). volume 자동감지.
# [OUTPUT] (실행폴더) mrv_regime.csv  -> check.py가 00WorkHstr로 정리.
#
# [FUNCTIONS]
#   find_data/load_1m/resample_tf : 데이터 로드(재사용)
#   compute_atr(h,l,c,P)          : ATR
#   compute_adx(h,l,c,n)          : Wilder ADX (stg8 재사용)
#   compute_poc(df,N,B)           : 롤링 POC
#   classify(adx,atrcmp,lo,hi)    In: ADX값,압축bool,임계 Out: 장세라벨 4종
#   revert_by_regime(...)         In: TFdf,poc,atr,adx,atrcmp,거리bin,horizon
#                                 Out: (장세,거리)별 [below_rev,below_n,above_rev,above_n]
#   measure_tf(df,years)          : 한 TF·기간 측정
#   main()
# ==============================================================================

import os, sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)

GRID_TF      = [4*60, 6*60, 8*60, 12*60]
ATR_PERIOD   = 14
ADX_N        = 14
ATR_SMA_N    = 50           # stg8 동일
ATR_COMP_K   = 0.8          # stg8 동일: atr < sma*0.8 = 압축
ADX_LO       = 20           # 횡보/추세 경계
ADX_HI       = 25           # 강추세 경계
POC_LOOKBACK = 60
POC_BINS     = 50
DIST_BINS    = [0.5, 1.0, 1.5, 2.0, 3.0]
HORIZON      = 20           # stg2 측정서 적당했던 값으로 고정(표 축소)
TRAIN_YEARS  = [2023, 2024]
TEST_YEARS   = [2025, 2026]
REGIMES      = ['Q_RANGE', 'L_RANGE', 'W_TREND', 'S_TREND']


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
    """Wilder ADX (stg8 재사용). 과거봉만."""
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
    poc = np.full(n, np.nan)
    midall = (high + low) / 2.0
    for i in range(lookback, n):
        s = i - lookback
        lo = low[s:i].min(); hi = high[s:i].max()
        if hi <= lo:
            poc[i] = close[i - 1]; continue
        edges = np.linspace(lo, hi, bins + 1)
        idxb = np.clip(np.digitize(midall[s:i], edges) - 1, 0, bins - 1)
        hist = np.zeros(bins)
        np.add.at(hist, idxb, vol[s:i])
        kmax = int(hist.argmax())
        poc[i] = (edges[kmax] + edges[kmax + 1]) / 2.0
    return poc


def classify(adx_i, atrcmp_i, lo, hi):
    """stg8 방식 장세 4분류."""
    if adx_i < lo:
        return 'Q_RANGE' if atrcmp_i else 'L_RANGE'
    if adx_i < hi:
        return 'W_TREND'
    return 'S_TREND'


def revert_by_regime(df, poc, atr, adx, atrcmp, dist_edges, horizon):
    """(장세, 거리)별 POC 회귀율. 위(숏)/아래(롱) 분리. ★측정용 미래봉 사용."""
    close = df['close'].values; high = df['high'].values; low = df['low'].values
    n = len(close); nb = len(dist_edges)
    # key=(regime, bin) -> [below_rev, below_n, above_rev, above_n]
    acc = {(rg, bi): np.zeros(4) for rg in REGIMES for bi in range(nb)}
    for i in range(POC_LOOKBACK, n - horizon - 1):
        P = poc[i]; A = atr[i]
        if np.isnan(P) or np.isnan(A) or A <= 0:
            continue
        rg = classify(adx[i], bool(atrcmp[i]), ADX_LO, ADX_HI)
        dev = (close[i] - P) / A
        ad = abs(dev)
        b = int(np.digitize(ad, dist_edges))
        if b >= nb:
            b = nb - 1
        fh = high[i + 1:i + 1 + horizon]; fl = low[i + 1:i + 1 + horizon]
        cell = acc[(rg, b)]
        if dev < 0:      # 아래 -> 위로 POC 터치 = 롱 회귀
            cell[0] += 1 if (fh >= P).any() else 0; cell[1] += 1
        elif dev > 0:    # 위 -> 아래로 POC 터치 = 숏 회귀
            cell[2] += 1 if (fl <= P).any() else 0; cell[3] += 1
    return acc


def measure_tf(df, years):
    if years is not None:
        df = df[df.index.year.isin(years)]
    if len(df) < 200:
        return None
    high = df['high'].values; low = df['low'].values; close = df['close'].values
    atr = compute_atr(high, low, close, ATR_PERIOD)
    adx = compute_adx(high, low, close, ADX_N)
    atr_sma = pd.Series(atr).rolling(ATR_SMA_N, min_periods=1).mean().values
    atrcmp = (atr < atr_sma * ATR_COMP_K)
    poc = compute_poc(df, POC_LOOKBACK, POC_BINS)
    acc = revert_by_regime(df, poc, atr, adx, atrcmp, DIST_BINS, HORIZON)
    return acc


def main():
    print("[Sideway4Champ_V2_stg3] POC reversion BY stg8 regime (ADX x ATRcmp)")
    open(os.path.join(HERE, ".run_start"), 'w').close()
    data = find_data(); print(f"[data] {data}")
    df1m = load_1m(data)
    print(f"[load] {len(df1m):,}rows | vol={df1m.attrs['has_vol']} | "
          f"{df1m.index.min().date()}~{df1m.index.max().date()}")

    rows = []
    verdict_bits = []
    for tf in GRID_TF:
        d = resample_tf(df1m, tf)
        for tag, yrs in [('all', None), ('train', TRAIN_YEARS), ('test', TEST_YEARS)]:
            acc = measure_tf(d, yrs)
            if acc is None:
                continue
            tfh = tf // 60
            for rg in REGIMES:
                for bi in range(len(DIST_BINS)):
                    bl_r, bl_n, ab_r, ab_n = acc[(rg, bi)]
                    rows.append({'TF_h': tfh, 'period': tag, 'regime': rg,
                                 'dist_atr_max': DIST_BINS[bi],
                                 'below_revert_pct': round(bl_r / bl_n * 100, 1) if bl_n > 0 else None,
                                 'below_n': int(bl_n),
                                 'above_revert_pct': round(ab_r / ab_n * 100, 1) if ab_n > 0 else None,
                                 'above_n': int(ab_n)})
            # 판정용: all 기준 Q_RANGE vs S_TREND 얕은이탈(<=1.0ATR) 롱 회귀율
            if tag == 'all':
                def shallow_long(rg):
                    rr = 0.0; nn = 0
                    for bi in range(len(DIST_BINS)):
                        if DIST_BINS[bi] <= 1.0:
                            c = acc[(rg, bi)]; rr += c[0]; nn += c[1]
                    return (rr / nn * 100) if nn > 0 else None, nn
                q, qn = shallow_long('Q_RANGE')
                s, sn = shallow_long('S_TREND')
                if qn >= 20 and sn >= 20 and q is not None and s is not None:
                    verdict_bits.append(f"TF{tfh}h Q={round(q,1)}%(n{qn}) vs S={round(s,1)}%(n{sn}) diff={round(q-s,1)}%p")
                else:
                    dist = {rg: int(sum(acc[(rg, bi)][1] for bi in range(len(DIST_BINS)) if DIST_BINS[bi] <= 1.0)) for rg in REGIMES}
                    verdict_bits.append(f"TF{tfh}h 표본분포(얕은롱) {dist}")
        print(f"[tf {tf//60}h] measured")

    df_out = pd.DataFrame(rows)
    verdict = ("VERDICT(얕은<=1ATR 롱회귀 Q_RANGE vs S_TREND): " + " | ".join(verdict_bits)
               if verdict_bits else "VERDICT: 표본부족")
    with open(os.path.join(HERE, "mrv_regime.csv"), "w", encoding="utf-8-sig") as f:
        f.write(verdict + "\n")
        df_out.to_csv(f, index=False)
    print("[" + verdict + "]")
    print("[save] mrv_regime.csv")


if __name__ == "__main__":
    main()
