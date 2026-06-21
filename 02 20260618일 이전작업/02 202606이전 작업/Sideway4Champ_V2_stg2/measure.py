# -*- coding: utf-8 -*-
# [FILE] measure.py  (Sideway4Champ_V2_stg2 - mean-reversion diagnostics: Hurst/half-life/POC-revert)
# CODE LENGTH: approx 330 lines | INTERNAL VER: Sideway4Champ_V2_stg2 | full output, no omission
#
# [PURPOSE] "POC로 되돌아온다"가 사실인지 데이터로 판정(코딩 전 전략 사활 검증).
#   측정 3종을 TF별(4/6/8/12h), train/test 분리해서 산출:
#   (1) Hurst 지수  H<0.5=평균회귀 / 0.5=랜덤 / >0.5=추세지속
#   (2) 반감기(half-life)  평균에서 절반 돌아오는 데 걸리는 봉수 (-log2/λ, AR(1) 회귀)
#   (3) POC 이탈거리별 회귀확률  POC에서 ATR의 몇 배 벗어났을 때, 향후 N봉 내 POC 터치 비율.
#       ★위(price>POC=숏후보) / 아래(price<POC=롱후보) 분리 측정 -> 양방향 비대칭 확인.
#
# [중요] 이 스크립트는 '측정'이라 미래봉을 본다(회귀했는지 확인하려면 당연). 진입신호 아님.
#   봇(test.py)의 미래참조 차단과는 별개. 여기 결과는 전략 타당성 판정용 통계.
#
# [판정 기준]
#   - H<0.45 이고 half-life가 짧으면(예 <30봉) = 평균회귀 살아있음 -> DCA 정당.
#   - H>0.55 = 추세지속 -> "POC 회귀" 전제 위험 -> DCA 전략 재고.
#   - 회귀확률: 아래(롱)와 위(숏) 비대칭이면 -> 한쪽만/양쪽 차등 적용 근거.
#   - train/test에서 부호·방향 일관해야 신뢰(과최적화/우연 배제).
#
# [SPEED] TF별 신호 1회 계산. Hurst/half-life는 회귀 1패스. 회귀확률은 봉 루프 1패스(벡터화).
# [PATH] 실행: D:\ML\verify\Sideway4Champ_V2_stg2\ . 데이터: 상위 D:\ML\verify\ .
# [DATA] 상위 Merged_Data_with_Regime_Features.csv (없으면 merged_data.csv). volume 자동감지.
# [OUTPUT] (실행폴더) mrv_hurst.csv + mrv_revert.csv  -> check.py가 00WorkHstr로 정리.
#
# [FUNCTIONS]
#   find_data()/load_1m()/resample_tf()  : stg1 재사용(데이터 로드·리샘플)
#   compute_atr(h,l,c,P)                 : ATR (거리 정규화용)
#   compute_poc(df,N,B)                  : 롤링 POC (volume profile, 없으면 TPO)
#   hurst(ts)                            In: 종가배열  Out: H (변동성 스케일링 로그회귀 기울기)
#   half_life(ts)                        In: 종가배열  Out: 반감기(봉), λ
#   var_ratio(ts,q)                      In: 종가,lag  Out: VR (1=랜덤, <1 평균회귀, >1 추세)
#   poc_revert(df,poc,atr,bins,horizon)  In: TFdf,poc,atr,거리bin,관찰봉수
#                                        Out: bin별 (아래회귀율, 위회귀율, 표본수)
#   measure_tf(df, years)                : 한 TF·기간의 3종 측정 묶음
#   main()
# ==============================================================================

import os, sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)

GRID_TF      = [4*60, 6*60, 8*60, 12*60]   # 측정할 TF(분)
ATR_PERIOD   = 14
POC_LOOKBACK = 60
POC_BINS     = 50
DIST_BINS    = [0.5, 1.0, 1.5, 2.0, 3.0]   # POC 이탈거리(ATR 배수) 구간 경계
HORIZONS     = [10, 20, 40]                # 회귀 관찰 봉수(여러개)
TRAIN_YEARS  = [2023, 2024]
TEST_YEARS   = [2025, 2026]


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


def hurst(ts):
    """변동성 스케일링(로그-로그 회귀) Hurst. H<0.5=평균회귀,0.5=랜덤,>0.5=추세."""
    ts = np.asarray(ts, dtype=float)
    n = len(ts)
    if n < 120:
        return np.nan
    lags = range(2, min(100, n // 2))
    tau = []
    use = []
    for lag in lags:
        d = ts[lag:] - ts[:-lag]
        s = np.std(d)
        if s > 0:
            tau.append(s); use.append(lag)
    if len(use) < 10:
        return np.nan
    poly = np.polyfit(np.log(use), np.log(tau), 1)
    return float(poly[0])


def half_life(ts):
    """AR(1) 회귀로 반감기. Δy = λ·y(t-1)+c ; half-life = -log(2)/λ (λ<0일때)."""
    ts = np.asarray(ts, dtype=float)
    if len(ts) < 30:
        return np.nan, np.nan
    ylag = ts[:-1]; dy = ts[1:] - ts[:-1]
    A = np.vstack([ylag, np.ones(len(ylag))]).T
    lam, c = np.linalg.lstsq(A, dy, rcond=None)[0]
    if lam >= 0:
        return np.nan, float(lam)   # 평균회귀 아님(발산/추세)
    hl = -np.log(2) / lam
    return float(hl), float(lam)


def var_ratio(ts, q):
    """분산비. VR<1=평균회귀, 1=랜덤워크, >1=추세지속."""
    ts = np.asarray(ts, dtype=float)
    r = np.diff(ts)
    n = len(r)
    if n < q * 2:
        return np.nan
    var1 = np.var(r, ddof=1)
    rq = np.add.reduceat(r, np.arange(0, len(r), q))  # q-기간 합
    # 끝자락 길이 불일치 방지: 완전한 블록만
    full = (len(r) // q) * q
    rq = r[:full].reshape(-1, q).sum(axis=1)
    varq = np.var(rq, ddof=1)
    if var1 <= 0:
        return np.nan
    return float(varq / (q * var1))


def poc_revert(df, poc, atr, dist_edges, horizons):
    """POC 이탈거리(ATR배수)별 회귀확률. 위(price>POC)/아래(price<POC) 분리.
       회귀 = 향후 horizon봉 내 가격이 POC를 터치(아래면 위로 도달, 위면 아래로 도달).
       ★측정이므로 미래봉 사용(진입신호 아님)."""
    close = df['close'].values; high = df['high'].values; low = df['low'].values
    n = len(close)
    nb = len(dist_edges)
    # 결과: [horizon][bin] = [down_rev, down_n, up_rev, up_n]
    out = {h: np.zeros((nb, 4)) for h in horizons}
    for i in range(POC_LOOKBACK, n - max(horizons) - 1):
        P = poc[i]; A = atr[i]
        if np.isnan(P) or np.isnan(A) or A <= 0:
            continue
        dev = (close[i] - P) / A   # +면 위, -면 아래 (ATR 단위)
        ad = abs(dev)
        b = int(np.digitize(ad, dist_edges))   # 0..nb (마지막은 초과)
        if b >= nb:
            b = nb - 1
        for h in horizons:
            fh = high[i + 1:i + 1 + h]; fl = low[i + 1:i + 1 + h]
            if dev < 0:   # 아래 -> 위로 올라와 POC 터치하면 롱 회귀
                rev = 1 if (fh >= P).any() else 0
                out[h][b, 0] += rev; out[h][b, 1] += 1
            elif dev > 0: # 위 -> 아래로 내려와 POC 터치하면 숏 회귀
                rev = 1 if (fl <= P).any() else 0
                out[h][b, 2] += rev; out[h][b, 3] += 1
    return out


def measure_tf(df, years):
    """한 TF·기간 측정. years=None이면 전체."""
    if years is not None:
        df = df[df.index.year.isin(years)]
    if len(df) < 150:
        return None
    close = df['close'].values
    high = df['high'].values; low = df['low'].values
    atr = compute_atr(high, low, close, ATR_PERIOD)
    poc = compute_poc(df, POC_LOOKBACK, POC_BINS)
    H = hurst(close)
    hl, lam = half_life(close)
    vr5 = var_ratio(close, 5)
    vr10 = var_ratio(close, 10)
    rev = poc_revert(df, poc, atr, DIST_BINS, HORIZONS)
    return {'bars': len(df), 'H': H, 'half_life': hl, 'lam': lam,
            'VR5': vr5, 'VR10': vr10, 'rev': rev}


def main():
    print("[Sideway4Champ_V2_stg2] mean-reversion diagnostics (Hurst / half-life / POC-revert)")
    open(os.path.join(HERE, ".run_start"), 'w').close()
    data = find_data(); print(f"[data] {data}")
    df1m = load_1m(data)
    print(f"[load] {len(df1m):,}rows | vol={df1m.attrs['has_vol']} | "
          f"{df1m.index.min().date()}~{df1m.index.max().date()}")

    hurst_rows = []
    revert_rows = []
    verdict_bits = []

    for tf in GRID_TF:
        d = resample_tf(df1m, tf)
        for tag, yrs in [('all', None), ('train', TRAIN_YEARS), ('test', TEST_YEARS)]:
            m = measure_tf(d, yrs)
            if m is None:
                continue
            tfh = tf // 60
            hurst_rows.append({'TF_h': tfh, 'period': tag, 'bars': m['bars'],
                               'Hurst': round(m['H'], 3) if m['H'] == m['H'] else None,
                               'half_life_bars': round(m['half_life'], 1) if m['half_life'] == m['half_life'] else None,
                               'lambda': round(m['lam'], 5) if m['lam'] == m['lam'] else None,
                               'VR5': round(m['VR5'], 3) if m['VR5'] == m['VR5'] else None,
                               'VR10': round(m['VR10'], 3) if m['VR10'] == m['VR10'] else None})
            # 회귀확률 표 펼치기
            for h in HORIZONS:
                mat = m['rev'][h]
                for bi in range(len(DIST_BINS)):
                    dn_rev, dn_n, up_rev, up_n = mat[bi]
                    revert_rows.append({
                        'TF_h': tfh, 'period': tag, 'horizon': h,
                        'dist_atr_max': DIST_BINS[bi],
                        'below_revert_pct': round(dn_rev / dn_n * 100, 1) if dn_n > 0 else None,
                        'below_n': int(dn_n),
                        'above_revert_pct': round(up_rev / up_n * 100, 1) if up_n > 0 else None,
                        'above_n': int(up_n)})
            # all 기준으로 판정 비트 모으기
            if tag == 'all':
                hh = m['H']
                if hh == hh:
                    tag2 = "MR" if hh < 0.45 else ("TREND" if hh > 0.55 else "RANDOM")
                    verdict_bits.append(f"TF{tfh}h H={round(hh,3)}({tag2}) HL={round(m['half_life'],1) if m['half_life']==m['half_life'] else 'na'}")
        print(f"[tf {tf//60}h] measured")

    pd.DataFrame(hurst_rows).to_csv(os.path.join(HERE, "mrv_hurst.csv"),
                                    index=False, encoding='utf-8-sig')
    pd.DataFrame(revert_rows).to_csv(os.path.join(HERE, "mrv_revert.csv"),
                                     index=False, encoding='utf-8-sig')

    verdict = "VERDICT: " + " | ".join(verdict_bits) if verdict_bits else "VERDICT: 측정 표본 부족"
    # 맨 앞에 판정 한 줄 끼우기(summary 성격)
    hd = pd.DataFrame(hurst_rows)
    with open(os.path.join(HERE, "mrv_hurst.csv"), "w", encoding="utf-8-sig") as f:
        f.write(verdict + "\n")
        hd.to_csv(f, index=False)
    print("[" + verdict + "]")
    print("[save] mrv_hurst.csv + mrv_revert.csv")


if __name__ == "__main__":
    main()
