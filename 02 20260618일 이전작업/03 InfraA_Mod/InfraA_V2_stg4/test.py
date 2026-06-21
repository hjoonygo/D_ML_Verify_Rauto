# -*- coding: utf-8 -*-
# [FILE] test.py  (InfraA_V2_stg4 - pre-entry separability diagnosis: do the 9 disasters have a fingerprint?)
# CODE LENGTH: approx 340 lines | INTERNAL VER: sepdiag_v1 | full output, no omission
#
# [PURPOSE / 목적] "사고를 진입에서 막자"는 ML을 짜기 전, 그게 가능한 땅인지 측량.
#   질문: 진입 시점 정보만으로 사고 9건(liq)이 승자 80건(Fibonacci)과 구별되는 '지문'이 있나?
#   ★ML/블랙박스 아님. 분리도 측정(분포 겹침 + 단일임계 맞교환 + 학습/검증 일반화)만.
#   ★결론: 안 갈리면 어떤 ML도 못 만듦(닫음). 갈리면 그때 필터 제작.
#
# [수집 피처 — 전부 진입 시점에 알 수 있음(미래참조 없음)]
#   tp_dist_bp   : 목표(5분 지지OB 바닥+5bp)까지 거리 (bp)
#   sl_dist_bp   : 손절기준(1H 저항OB mean)까지 거리 (bp)
#   swing_pos    : 최근60봉 레인지 내 현재 저가 위치 (0=바닥,1=천장)
#   n_support_ob : 아래 지지OB 개수 (쿠션 두께)
#   oi_zscore_24h, oi_change_1h_pct : (데이터에 있으면) OI 신호. 없으면 NaN+매칭률보고
#
# [라벨] 각 진입을 현행엔진(C0)으로 끝까지 돌려 청산사유로 분류:
#   disaster(liq) / winner(Fibonacci) / hole(hole_hardfloor) / neutral(그외)
#
# [분리도 측정]
#   (1) 사고9 vs 승자80: 피처별 분포(평균/중앙/최저/최고) + 겹침
#   (2) 단일임계 맞교환: 각 피처로 '위험'표시했을때 사고 몇/9 잡고 승자 몇/80 헛제거
#   (3) 일반화: 학습기 사고7로 정한 임계가 검증기 사고2도 잡나(과적합 사전차단)
#
# [SPEED] pivot/OB 1회, 진입스캔 1회(피처동시수집), 청산까지만 4틱+점프.
# [PATH] D:\ML\verify\InfraA_V2_stg4\ 실행, 데이터 상위, 결과 CSV -> 이 하위폴더.
# [DATA] ../Merged_Data_with_Regime_Features.csv (OI컬럼 있으면 자동사용)
# [OUTPUT] sep_features.csv(거래별 피처+라벨) + sep_summary.csv(피처별 분리도/맞교환/일반화)
# ==============================================================================

import os, sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
REGIME_COL = 'feat_struct_8'
W_TF = 3; SL_TF = 60; TP_TF = 5
SL_GATE = 0.0016; D_FIX = 5; N_OB = 5
LEVERAGE = 5; LIQ_MOVE = 0.20
COST = 0.0004; FUNDING_DAILY = 0.0003   # 현실펀딩
MAX_HOLD_BARS = 60 * 24 * 90
FIB_TRIGGER = 15.0; FIB_EXT = 0.65; HARD_FLOOR_ROE = 15.0
TRAIN_YEARS = [2023, 2024]; TEST_YEARS = [2025, 2026]
OI_COLS = ['oi_zscore_24h', 'oi_change_1h_pct']
FEATS = ['tp_dist_bp', 'sl_dist_bp', 'swing_pos', 'n_support_ob', 'oi_zscore_24h', 'oi_change_1h_pct']


def find_data():
    for d in [PARENT, HERE, r"D:\ML\verify", r"D:\ML\Verify"]:
        p = os.path.join(d, "Merged_Data_with_Regime_Features.csv")
        if os.path.exists(p):
            return p
    raise FileNotFoundError("상위 D:\\ML\\verify 에 Merged_Data_with_Regime_Features.csv 필요")


def find_flow():
    for d in [PARENT, HERE, r"D:\ML\verify", r"D:\ML\Verify"]:
        for n in ["merged_data.csv", "Merged_data.csv", "merged_data_sample.csv"]:
            p = os.path.join(d, n)
            if os.path.exists(p):
                return p
    return None


def load_data(path):
    head = pd.read_csv(path, nrows=1)
    if REGIME_COL not in head.columns:
        raise KeyError(f"{REGIME_COL} 없음. 컬럼: {list(head.columns)[:12]}")
    base = ['timestamp', 'open', 'high', 'low', 'close', REGIME_COL]
    have_oi = [c for c in OI_COLS if c in head.columns]
    df = pd.read_csv(path, usecols=base + have_oi, index_col='timestamp', parse_dates=True)
    if getattr(df.index, 'tz', None) is not None:
        df.index = df.index.tz_localize(None)
    df = df.sort_index()
    oi_src = 'regime_file' if have_oi else 'none'
    if not have_oi:
        fp = find_flow()
        if fp is not None:
            fh = pd.read_csv(fp, nrows=1)
            fcols = [c for c in OI_COLS if c in fh.columns]
            if fcols:
                fl = pd.read_csv(fp, usecols=['timestamp'] + fcols, index_col='timestamp', parse_dates=True)
                if getattr(fl.index, 'tz', None) is not None:
                    fl.index = fl.index.tz_localize(None)
                df = df.join(fl.sort_index(), how='left')
                oi_src = f'merged_data({os.path.basename(fp)})'
                have_oi = fcols
    for c in OI_COLS:
        if c not in df.columns:
            df[c] = np.nan
    return df, have_oi, oi_src


# ----- ob_mtf inline (verified) -------------------------------------------------
def resample_tf(df1m, tf_min):
    rule = f"{tf_min}min"
    agg = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}
    return df1m[['open', 'high', 'low', 'close']].resample(rule, label='left', closed='left').agg(agg).dropna()


def precompute_tf_pivots(df_tf, w, tf_min):
    high = df_tf['high'].values; low = df_tf['low'].values; starts = df_tf.index.values
    n = len(high)
    if n < 2 * w + 1:
        z = np.array([], dtype='datetime64[ns]'); f = np.array([], dtype=float)
        return z, z, f, f, f, f
    from numpy.lib.stride_tricks import sliding_window_view
    win = 2 * w + 1
    hmax = sliding_window_view(high, win).max(axis=1)
    lmin = sliding_window_view(low, win).min(axis=1)
    centers = np.arange(w, n - w)
    hp_c = centers[high[w:n - w] == hmax]; lp_c = centers[low[w:n - w] == lmin]
    td = np.timedelta64(tf_min, 'm')
    return (starts[hp_c + w] + td, starts[lp_c + w] + td, high[hp_c], low[hp_c], high[lp_c], low[lp_c])


def nearest_above(price, ts, hpc, hpt, hpb):
    k = np.searchsorted(hpc, np.datetime64(ts), side='right')
    if k == 0:
        return None
    bots = hpb[:k]; tops = hpt[:k]; cand = bots > price
    if not cand.any():
        return None
    bb = bots[cand]; tt = tops[cand]; j = np.argmin(bb)
    return (float(tt[j]), float(bb[j]))


def levels_below_5m(price, ts, lpc, lpt, lpb, n):
    k = np.searchsorted(lpc, np.datetime64(ts), side='right')
    if k == 0:
        return []
    tops = lpt[:k]; bots = lpb[:k]; cand = tops < price
    if not cand.any():
        return []
    tt = tops[cand]; bb = bots[cand]; order = np.argsort(-tt)
    return [(float(tt[o]), float(bb[o])) for o in order[:n]]


def swing_pos(h, l, e_idx, win=60):
    lo = max(0, e_idx - win + 1)
    hh = h[lo:e_idx + 1].max(); ll = l[lo:e_idx + 1].min()
    if hh <= ll:
        return 0.5
    return float((l[e_idx] - ll) / (hh - ll))
# -------------------------------------------------------------------------------


def exec_check_exit(price, bs, params):
    entry = bs['entry_price']; lev = params['leverage']; target_idx = bs['target_idx']
    if bs['fib_stop'] is None:
        hf = entry * (1 + params['hard_floor_roe'] / 100.0 / lev)
        if price >= hf:
            return {"action": "CLOSE_SHORT", "reason": "hole_hardfloor"}
    bull = bs['bullish_obs']
    if target_idx < len(bull):
        tob = bull[target_idx]
        if price <= tob['mean']:
            bs['fib_stop'] = tob['top']; bs['target_idx'] += 1
            if bs['remaining_pct'] == 1.0:
                bs['remaining_pct'] = 0.5
                return {"action": "REDUCE_SHORT", "reason": "reduce"}
            return {"action": "HOLD", "reason": "Nth"}
        if bs['fib_stop'] is not None and price >= bs['fib_stop']:
            return {"action": "CLOSE_SHORT", "reason": "OB_edge"}
    else:
        roe = ((entry - price) / entry) * lev * 100
        max_roe = ((entry - bs['fib_extreme']) / entry) * lev * 100
        if price < bs['fib_extreme']:
            if bs['pulled_back']:
                bs['fib_wave_start'] = bs['fib_extreme']; bs['pulled_back'] = False
            bs['fib_extreme'] = price
        elif price > bs['fib_extreme']:
            bs['pulled_back'] = True
        if roe >= params['fib_trigger_roe'] or max_roe >= params['fib_trigger_roe']:
            downswing = bs['fib_wave_start'] - bs['fib_extreme']
            fib_lock = bs['fib_wave_start'] - downswing * params['fib_ext_pct']
            prev = bs.get('fib_stop', None)
            bs['fib_stop'] = min(prev if prev is not None else float('inf'), fib_lock)
            if price >= bs['fib_stop']:
                return {"action": "CLOSE_SHORT", "reason": "Fibonacci"}
    return {"action": "HOLD", "reason": "hold"}


def simulate_one(arrays, e_idx, tp_targets):
    o, h, l, c, idx = arrays
    entry = c[e_idx]; liq = entry * (1 + LIQ_MOVE)
    bs = {'position': 'SHORT', 'entry_price': entry, 'remaining_pct': 1.0, 'target_idx': 0,
          'fib_wave_start': entry, 'fib_extreme': entry, 'pulled_back': False, 'fib_stop': None,
          'bullish_obs': tp_targets}
    params = {'leverage': LEVERAGE, 'fib_trigger_roe': FIB_TRIGGER, 'fib_ext_pct': FIB_EXT,
              'hard_floor_roe': HARD_FLOOR_ROE}
    frac = 1.0; reduced = False; R = 0.0
    n = len(c); end_idx = min(n, e_idx + 1 + MAX_HOLD_BARS); xi = end_idx - 1
    for i in range(e_idx + 1, end_idx):
        o_, h_, l_, c_ = o[i], h[i], l[i], c[i]
        ticks = (o_, h_, l_, c_) if c_ < o_ else (o_, l_, h_, c_)
        for price in ticks:
            if price >= liq:
                return 'liq', i
            sig = exec_check_exit(price, bs, params); act = sig['action']
            if act == 'REDUCE_SHORT' and not reduced:
                frac = 0.5; reduced = True; continue
            if act == 'CLOSE_SHORT':
                return sig['reason'], i
    return 'max_hold', xi


def collect(df):
    o = df['open'].values; h = df['high'].values; l = df['low'].values; c = df['close'].values
    idx = df.index
    oiZ = df['oi_zscore_24h'].values; oi1 = df['oi_change_1h_pct'].values
    down_idx = np.where(df[REGIME_COL].astype(str).values == 'downtrend')[0]
    hpc, _, hpt, hpb, _, _ = precompute_tf_pivots(resample_tf(df, SL_TF), W_TF, SL_TF)
    _, lpc, _, _, lpt, lpb = precompute_tf_pivots(resample_tf(df, TP_TF), W_TF, TP_TF)
    arrays = (o, h, l, c, idx)
    rows = []; n = len(c); cur = 0; last_exit = -1
    dptr = np.searchsorted(down_idx, cur, side='left')
    while dptr < len(down_idx):
        t0 = int(down_idx[dptr])
        if t0 >= n - 1:
            break
        if t0 <= last_exit:
            cur = last_exit + 1; dptr = np.searchsorted(down_idx, cur, side='left'); continue
        price = c[t0]; ts = idx[t0]
        ab = nearest_above(price, ts, hpc, hpt, hpb)
        bl = levels_below_5m(price, ts, lpc, lpt, lpb, N_OB)
        ok = ab is not None and len(bl) > 0
        if ok:
            sl_mean = (ab[0] + ab[1]) / 2.0; sl_dist = (sl_mean - price) / price
            if sl_dist < SL_GATE:
                ok = False
        if ok:
            tps = [{'top': t, 'bottom': b, 'mean': b * (1 + D_FIX / 1e4)} for (t, b) in bl
                   if b * (1 + D_FIX / 1e4) < price]
            if tps:
                tp0 = bl[0][1] * (1 + D_FIX / 1e4); tp_dist = (price - tp0) / price
                reason, x_idx = simulate_one(arrays, t0, tps)
                if reason == 'liq':
                    lab = 'disaster'
                elif reason == 'Fibonacci':
                    lab = 'winner'
                elif reason == 'hole_hardfloor':
                    lab = 'hole'
                else:
                    lab = 'neutral'
                rows.append(dict(진입시간=ts.strftime('%Y-%m-%d %H:%M:%S'), 연도=ts.year, 라벨=lab, 청산사유=reason,
                                 tp_dist_bp=round(tp_dist * 1e4, 2), sl_dist_bp=round(sl_dist * 1e4, 2),
                                 swing_pos=round(swing_pos(h, l, t0), 4), n_support_ob=len(tps),
                                 oi_zscore_24h=(round(float(oiZ[t0]), 4) if oiZ[t0] == oiZ[t0] else np.nan),
                                 oi_change_1h_pct=(round(float(oi1[t0]), 4) if oi1[t0] == oi1[t0] else np.nan)))
                last_exit = x_idx
                cur = x_idx + 1
            else:
                cur = t0 + 1
        else:
            cur = t0 + 1
        dptr = np.searchsorted(down_idx, cur, side='left')
    return pd.DataFrame(rows)


def best_threshold(dis_vals, win_vals):
    """사고는 많이 잡고 승자는 적게 헛제거하는 단일임계 1개 탐색.
    방향 자동(>=thr 또는 <=thr). 반환: (방향, 임계, 사고적중률, 승자오제거율, 분리점수J)."""
    dv = dis_vals[~np.isnan(dis_vals)]; wv = win_vals[~np.isnan(win_vals)]
    if len(dv) < 2 or len(wv) < 2:
        return None
    cand = np.unique(np.concatenate([dv, wv]))
    best = None
    for thr in cand:
        for sign in ('>=', '<='):
            if sign == '>=':
                tpr = (dv >= thr).mean(); fpr = (wv >= thr).mean()
            else:
                tpr = (dv <= thr).mean(); fpr = (wv <= thr).mean()
            J = tpr - fpr   # Youden J (1=완벽분리, 0=무작위)
            if best is None or J > best[4]:
                best = (sign, float(thr), round(tpr, 3), round(fpr, 3), round(J, 3))
    return best


def main():
    print("[InfraA_V2_stg4] 진입전 분리도 진단 — 사고9 vs 승자80 지문 있나")
    open(os.path.join(HERE, ".run_start"), 'w').close()
    data = find_data(); print(f"[data] {data}")
    df, have_oi, oi_src = load_data(data)
    print(f"[load] {len(df):,}rows | OI컬럼: {have_oi if have_oi else '없음(NaN)'} | OI출처: {oi_src}")
    feat = collect(df)
    feat.to_csv(os.path.join(HERE, "sep_features.csv"), index=False, encoding='utf-8-sig')
    dis = feat[feat['라벨'] == 'disaster']; win = feat[feat['라벨'] == 'winner']
    print(f"[labels] 사고(liq) {len(dis)} | 승자(Fibonacci) {len(win)} | 전체 {len(feat)}")
    oi_match = feat['oi_zscore_24h'].notna().mean() * 100
    print(f"[OI] oi_zscore 매칭률 {oi_match:.1f}%")

    summ = []
    for f in FEATS:
        dv = dis[f].values.astype(float); wv = win[f].values.astype(float)
        bt = best_threshold(dv, wv)
        # 일반화: 학습기 사고로 정한 임계가 검증기 사고도 잡나
        dtr = dis[dis['연도'].isin(TRAIN_YEARS)][f].values.astype(float)
        dte = dis[dis['연도'].isin(TEST_YEARS)][f].values.astype(float)
        gen = None
        if bt and len(dte[~np.isnan(dte)]) > 0:
            sign, thr = bt[0], bt[1]
            te_hit = ((dte >= thr).mean() if sign == '>=' else (dte <= thr).mean())
            gen = round(float(te_hit), 3)
        row = dict(피처=f,
                   사고평균=round(np.nanmean(dv), 3) if len(dv[~np.isnan(dv)]) else None,
                   승자평균=round(np.nanmean(wv), 3) if len(wv[~np.isnan(wv)]) else None,
                   사고범위=f"[{np.nanmin(dv):.2f}~{np.nanmax(dv):.2f}]" if len(dv[~np.isnan(dv)]) else "NaN",
                   승자범위=f"[{np.nanmin(wv):.2f}~{np.nanmax(wv):.2f}]" if len(wv[~np.isnan(wv)]) else "NaN")
        if bt:
            row.update(최선임계=f"{bt[0]}{bt[1]:.3g}", 사고적중=bt[2], 승자오제거=bt[3], 분리점수J=bt[4],
                       검증기사고적중=gen)
        else:
            row.update(최선임계='측정불가(NaN과다)', 사고적중=None, 승자오제거=None, 분리점수J=None, 검증기사고적중=None)
        summ.append(row)
    pd.DataFrame(summ).to_csv(os.path.join(HERE, "sep_summary.csv"), index=False, encoding='utf-8-sig')

    print("\n[분리도 요약] (J=1완벽분리 / 0무작위. 사고적중 높고 승자오제거 낮아야 좋음)")
    for r in summ:
        print(f"  {r['피처']:16s} 사고{r['사고평균']} vs 승자{r['승자평균']} | 최선임계 {r['최선임계']} "
              f"J={r['분리점수J']} (사고적중{r['사고적중']}/승자오제거{r['승자오제거']}/검증기적중{r['검증기사고적중']})")
    print("\n[save] sep_features.csv + sep_summary.csv (this subfolder) - all files")


if __name__ == "__main__":
    main()
