# -*- coding: utf-8 -*-
# [FILE] test.py  (Sideway4Champ_V2_stg4 - shallow POC-reversion long/short + regime gate + Fib exit)
# CODE LENGTH: approx 460 lines | INTERNAL VER: Sideway4Champ_V2_stg4 | full output, no omission
#
# [PURPOSE] 측정(stg2/stg3)이 확정한 2규칙을 봇으로 구현하고 실제 성과(레버리지·피보·비용 포함) 첫 백테스트.
#   규칙1(거리): POC ±dist_max(ATR) '얕은 이탈'에서만 진입. 깊어지면(>dist_max) 즉시 손절(추세전환=안돌아옴).
#   규칙2(장세): S_TREND(ADX>=adx_hi)에선 신규진입 OFF (깊은이탈 73%가 S_TREND 집중 -> 지뢰밭 회피).
#   ★사장님 원안 '떨어질수록 크게(깊은 DCA)'는 데이터가 폐기 -> '얕을때만 작게, 깊어지면 판다'로 역전.
#
# [진입] 가격이 POC 아래로 얕게(<=dist_max ATR) 빠지고 새 피벗저점 + 반등 -> 롱(작게).
#        대칭으로 POC 위 얕은 이탈 -> 숏(롱주력이라 size 축소). short_on으로 ON/OFF 비교.
#        얕은영역 내 추가눌림 1회까지 분할(균등; 깊은DCA 아님). 총진입 얕은영역 한정.
# [청산] (1)POC 도달 익절 tp_poc  (2)|dev|>dist_max 깊어짐 손절 sl_deep  (3)피보 트레일 sl_trail
#        (4)시간손절. 피보 스텝업은 stg8 재사용(새 고점마다 SL 위로만).
# [사이징] 1.5% 리스크예산: 손절폭으로 총수량 역산(손절 닿으면 자본 1.5% 손실). 명목 2.5배 캡.
#
# [연동규칙 자유값] TF / dist_max(거리상한) / adx_hi(S_TREND임계) / a,d(피보) / short_on / nDCA
#   * 과최적화 방어: coarse 그리드 + train/test 분리 + 워크포워드(WFE) + 8시나리오 라벨.
# [SPEED] TF별 신호(피벗/ATR/ADX/POC) 1회 사전계산 -> 파라미터 그리드는 거래루프만 재실행.
# [PATH] 실행: D:\ML\verify\Sideway4Champ_V2_stg4\ . 데이터: 상위 D:\ML\verify\ .
# [DATA] 상위 Merged_Data_with_Regime_Features.csv (없으면 merged_data.csv). volume 자동감지.
# [OUTPUT] (실행폴더) sdca_summary.csv + sdca_trades.csv + sdca_scenarios.csv -> check.py 정리.
# [비용] 수수료0.05%+슬리피지0.02%(편도, 왕복0.14%) + 펀딩0.01%/8h. 결정=닫힌봉, 체결=다음봉시가.
# [미래참조 차단] 피벗 r봉뒤 확정. ATR/ADX/POC 과거봉만. 측정용 미래봉 없음(실거래 로직).
#
# [FUNCTIONS]
#   find_data/load_1m/resample_tf : 데이터 로드
#   compute_atr / compute_adx / compute_poc : 지표(재사용)
#   precompute(df)        : TF별 신호 1회 계산 (피벗/atr/adx/atrcmp/poc)
#   run_bot(df,sig,par)   In: TFdf,sig,파라미터  Out: trades 리스트
#   agg(trades,label,yrs) : 성과(PF/누적R/MDD/거래수/승률)
#   scen_label(...)       : 8시나리오 사후 라벨
#   main()                : 그리드 실행 + 최적셀 + WFE + CSV
# [변수] pos(수량비율) avg(평단) entry_i nfilled side(+1롱/-1숏) pb trailSL poc_t dist_max
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

# ── 탐색 그리드 (coarse) ──
GRID_TF      = [4*60, 6*60, 8*60, 12*60]
GRID_distmax = [1.0, 1.5]        # 진입 허용 최대 이탈(ATR). 핵심 규칙1
GRID_adxhi   = [22, 25, 28]      # S_TREND OFF 임계. 규칙2
GRID_a       = [0.3, 0.5]        # 피보 시작
GRID_d       = [0.1, 0.2]        # 피보 간격
GRID_short   = [0, 1]            # 숏 ON/OFF 비교
GRID_nDCA    = [1, 2]            # 얕은영역 내 분할(1=단일, 2=1회추가)
SHORT_SIZE   = 0.5               # 숏 비중(롱 대비) - 데이터 비대칭 반영

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
    short_on = par['short_on']; nDCA = par['nDCA']

    raw = np.arange(1, nDCA + 1, dtype=float); weights = raw / raw.sum()  # 균등化(얕은DCA)

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
            # 피보 스텝업 SL (롱: 새고점 / 숏: 새저점)
            if side == 1 and new_ph and not np.isnan(lastPL):
                pb += 1; ratio = min(a + d * (pb - 1), 0.95)
                cand = lastPH - ratio * (lastPH - lastPL)
                trailSL = cand if np.isnan(trailSL) else max(trailSL, cand)
            elif side == -1 and new_pl and not np.isnan(lastPH):
                pb += 1; ratio = min(a + d * (pb - 1), 0.95)
                cand = lastPL + ratio * (lastPH - lastPL)
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
            # 청산 판정
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

        # 미보유: 1차 진입 (얕은 이탈 + S_TREND 아님)
        if not np.isnan(dev) and not np.isnan(A) and not strong:
            # 롱: POC 아래 얕은 + 새 저점
            if new_pl and dev < 0 and abs(dev) <= dist_max:
                px = open_[i + 1] if i + 1 < n else close[i]
                pos = weights[0]; side = 1; avg = px; nfilled = 1; entry_i = i
                pb = 0; trailSL = px - dist_max * A; poc_t = P
                scen0 = scen_label(adx[i], dev, bool(atrcmp[i]), adx_hi)
            # 숏: POC 위 얕은 + 새 고점 (short_on)
            elif short_on and new_ph and dev > 0 and abs(dev) <= dist_max:
                px = open_[i + 1] if i + 1 < n else close[i]
                pos = weights[0] * SHORT_SIZE; side = -1; avg = px; nfilled = 1; entry_i = i
                pb = 0; trailSL = px + dist_max * A; poc_t = P
                scen0 = scen_label(adx[i], dev, bool(atrcmp[i]), adx_hi)
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
    print("[Sideway4Champ_V2_stg4] shallow POC-reversion + regime gate + Fib exit")
    open(os.path.join(HERE, ".run_start"), 'w').close()
    data = find_data(); print(f"[data] {data}")
    df1m = load_1m(data)
    print(f"[load] {len(df1m):,}rows | vol={df1m.attrs['has_vol']} | "
          f"{df1m.index.min().date()}~{df1m.index.max().date()}")

    tf_df = {}; tf_sig = {}
    for tf in GRID_TF:
        d = resample_tf(df1m, tf); tf_df[tf] = d; tf_sig[tf] = precompute(d)
        print(f"[tf {tf//60}h] {len(d)} bars precomputed")

    summary = []; best = None
    combos = list(itertools.product(GRID_distmax, GRID_adxhi, GRID_a, GRID_d, GRID_short, GRID_nDCA))
    print(f"[grid] TF{len(GRID_TF)} x params{len(combos)} = {len(GRID_TF)*len(combos)} runs")

    for tf in GRID_TF:
        df = tf_df[tf]; sig = tf_sig[tf]
        for (dm, axh, a, d, sh, nd) in combos:
            par = {'dist_max': dm, 'adx_hi': axh, 'a': a, 'd': d, 'short_on': sh, 'nDCA': nd}
            trades = run_bot(df, sig, par)
            lab = f"TF{tf//60}h_dm{dm}_adx{axh}_a{a}_d{d}_sh{sh}_n{nd}"
            mTr = agg(trades, lab + "_train", TRAIN_YEARS)
            mTe = agg(trades, lab + "_test", TEST_YEARS)
            summary.append({'cell': lab, 'TF_h': tf // 60, 'dist_max': dm, 'adx_hi': axh,
                            'a': a, 'd': d, 'short_on': sh, 'nDCA': nd,
                            'tr_trades': mTr['trades'], 'tr_PF': mTr['PF'], 'tr_cumR': mTr['cumR_pct'], 'tr_MDD': mTr['MDD_pct'],
                            'te_trades': mTe['trades'], 'te_PF': mTe['PF'], 'te_cumR': mTe['cumR_pct'], 'te_MDD': mTe['MDD_pct']})
            if mTr['trades'] >= 15 and (best is None or mTr['PF'] > best[0]):
                best = (mTr['PF'], par, tf, trades)

    wfe_rows = []
    if best is not None:
        _, bpar, btf, btr = best
        bm_tr = agg(btr, "best_train", TRAIN_YEARS); bm_te = agg(btr, "best_test", TEST_YEARS)
        wfe = round((bm_te['PF'] / bm_tr['PF']) * 100, 1) if bm_tr['PF'] > 0 else 0
        verdict = (f"BEST TF{btf//60}h {bpar} | train PF={bm_tr['PF']} cumR={bm_tr['cumR_pct']}% MDD={bm_tr['MDD_pct']}% "
                   f"| test PF={bm_te['PF']} cumR={bm_te['cumR_pct']}% MDD={bm_te['MDD_pct']}% | WFE={wfe}%(>50=robust)")
        print("[verdict] " + verdict)
        summary.insert(0, {'cell': 'VERDICT: ' + verdict})
        sb_tr = scen_breakdown(btr, TRAIN_YEARS); sb_te = scen_breakdown(btr, TEST_YEARS)
        for s in SCEN:
            wfe_rows.append({'cell': f'SCEN_{s}', 'train_n': sb_tr[s][0], 'train_cumR': sb_tr[s][1],
                             'test_n': sb_te[s][0], 'test_cumR': sb_te[s][1]})
    else:
        # 표본 부족: 어느 조건에서 거래가 막혔는지 진단을 summary에 남김
        diag = []
        for row in summary[1:]:
            if isinstance(row.get('tr_trades'), (int, float)) and row['tr_trades'] > 0:
                diag.append((row['cell'], row['tr_trades']))
        topdiag = sorted(diag, key=lambda x: -x[1])[:3]
        summary.insert(0, {'cell': 'VERDICT: 거래 표본부족(train<15) - 진단: 거래발생 top ' + str(topdiag)})

    pd.DataFrame(summary).to_csv(os.path.join(HERE, "sdca_summary.csv"), index=False, encoding='utf-8-sig')
    if best is not None:
        _, bpar, btf, btr = best
        td = [{'entry_t': t['entry_t'].strftime('%Y-%m-%d %H:%M'), 'exit_t': t['exit_t'].strftime('%Y-%m-%d %H:%M'),
               'side': t['side'], 'year': t['year'], 'entry': round(t['entry'], 2), 'exit': round(t['exit'], 2),
               'R_pct': round(t['R'] * 100, 4), 'reason': t['reason'], 'bars': t['bars'],
               'scen': t['scen'], 'nfilled': t['nfilled']} for t in btr]
        pd.DataFrame(td).to_csv(os.path.join(HERE, "sdca_trades.csv"), index=False, encoding='utf-8-sig')
        pd.DataFrame(wfe_rows).to_csv(os.path.join(HERE, "sdca_scenarios.csv"), index=False, encoding='utf-8-sig')
    else:
        # 빈 결과라도 헤더 있는 파일은 항상 생성(파이프라인 일관성)
        pd.DataFrame(columns=['entry_t', 'exit_t', 'side', 'year', 'entry', 'exit',
                              'R_pct', 'reason', 'bars', 'scen', 'nfilled']).to_csv(
            os.path.join(HERE, "sdca_trades.csv"), index=False, encoding='utf-8-sig')
        pd.DataFrame([{'cell': f'SCEN_{s}', 'train_n': 0, 'train_cumR': 0,
                       'test_n': 0, 'test_cumR': 0} for s in SCEN]).to_csv(
            os.path.join(HERE, "sdca_scenarios.csv"), index=False, encoding='utf-8-sig')
    print("[save] sdca_summary.csv + sdca_trades.csv + sdca_scenarios.csv")


if __name__ == "__main__":
    main()
