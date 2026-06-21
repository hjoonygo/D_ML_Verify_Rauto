# -*- coding: utf-8 -*-
# [FILE] test.py  (InfraA_V2_stg2 - SL distance diagnosis + fixed-entry-set clean compare)
# CODE LENGTH: approx 380 lines | INTERNAL VER: sldist_v1 | full output, no omission
#
# [PURPOSE / 목적] stg1에서 "SL설계가 거래폭증으로 더 나빠짐"이 SL을 너무 타이트하게 잡은 탓인지 확인.
#   질문2개에 숫자로 답한다:
#   (Q1) 1차익절 후 잡힌 SL이 실제로 작동하나? 각 설계의 SL거리(진입가 대비 %) 평균/최저/최고 + 발동률.
#   (Q2) 거래폭증을 배제하면(=C0가 실제 잡은 동일 진입집합에 SL만 적용, 새 거래 안늘림) SL순효과는?
#   ★사후보정 아님: 실엔진으로 같은 진입에서 청산만 설계별로 재시뮬.
#
# [측정 SL거리 정의] '1차익절 후 잡힌 SL' = Phase2 진입 첫 순간의 설계 스탑가격.
#   sl_dist_pct = (stop_price - entry)/entry*100  (+면 진입가 위, -면 아래). 숏이라 스탑은 보통 위(양수)거나 직전저점근처.
#
# [모드]
#   A. 자유진입(stg1과 동일): 설계가 일찍닫으면 새 진입 허용 -> 거래수 변동(폭증 확인용).
#   B. 고정진입(C0집합): C0가 실제 잡은 진입 e_idx 그대로, 설계별 청산만. 거래수 동일 -> 순수 SL효과.
#
# [DESIGNS] C0_none / C1_obtop / C2_breakeven / C3_fibearly / C4_resob  (전부 구조형, 고정%아님)
#
# [SPEED] pivot/OB 1회, 진입후보 1회수집. C0 1회돌려 진입집합 확보후 B모드 공유.
# [PATH] D:\ML\verify\InfraA_V2_stg2\ 실행, 데이터 상위, 결과 CSV -> 이 하위폴더.
# [DATA] ../Merged_Data_with_Regime_Features.csv
# [OUTPUT] sldist_summary.csv(설계×모드 거리/발동/누적R) + sldist_trades.csv(B모드 거래별 SL거리/사유)
#
# [FUNCTIONS] ob_mtf inline + exec_check_exit(SL design + sl거리기록) + simulate_one
#   + collect_entries + run_free(자유) + run_fixed(고정진입집합) + dist_stats
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
COST = 0.0004; FUNDING_DAILY = 0.0001
MAX_HOLD_BARS = 60 * 24 * 90
FIB_TRIGGER = 15.0; FIB_EXT = 0.65; HARD_FLOOR_ROE = 15.0
NOMINAL = 50000.0; START_CAP = 10000.0; MIN_CAP = 100.0
TRAIN_YEARS = [2023, 2024]; TEST_YEARS = [2025, 2026]
DESIGNS = ['C0_none', 'C1_obtop', 'C2_breakeven', 'C3_fibearly', 'C4_resob']
ACC_REASONS = ('liq', 'hole_hardfloor')


def find_data():
    for d in [PARENT, HERE, r"D:\ML\verify", r"D:\ML\Verify"]:
        p = os.path.join(d, "Merged_Data_with_Regime_Features.csv")
        if os.path.exists(p):
            return p
    raise FileNotFoundError("상위 D:\\ML\\verify 에 Merged_Data_with_Regime_Features.csv 필요")


def load_data(path):
    head = pd.read_csv(path, nrows=1)
    if REGIME_COL not in head.columns:
        raise KeyError(f"{REGIME_COL} 없음. 컬럼: {list(head.columns)[:12]}")
    cols = ['timestamp', 'open', 'high', 'low', 'close', REGIME_COL]
    df = pd.read_csv(path, usecols=cols, index_col='timestamp', parse_dates=True)
    if getattr(df.index, 'tz', None) is not None:
        df.index = df.index.tz_localize(None)
    return df.sort_index()


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
# -------------------------------------------------------------------------------


def exec_check_exit(price, bs, params):
    """FLOOR15 + Phase2 SL design. ★Phase2 첫 진입시 설계 스탑가격 기록(sl_set_price)."""
    entry = bs['entry_price']; lev = params['leverage']; target_idx = bs['target_idx']
    design = params['sl_design']
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
        stop_price = None
        if design == 'C1_obtop':
            stop_price = bs['fib_stop']
        elif design == 'C2_breakeven':
            stop_price = entry
        elif design == 'C4_resob':
            stop_price = bs['res_ob_top']
        # ★Phase2 첫 진입시 '잡힌 SL거리' 1회 기록
        if not bs['phase2_logged']:
            bs['phase2_logged'] = True
            sp = stop_price if (design != 'C0_none' and stop_price is not None) else (
                bs['fib_stop'] if bs['fib_stop'] is not None else entry)
            bs['sl_set_dist'] = (sp - entry) / entry * 100.0   # +위 / -아래(진입가 대비 %)
        if design != 'C0_none' and stop_price is not None and price >= stop_price:
            return {"action": "CLOSE_SHORT", "reason": "sl_design"}
        trig = 0.0 if design == 'C3_fibearly' else params['fib_trigger_roe']
        if roe >= trig or max_roe >= trig:
            downswing = bs['fib_wave_start'] - bs['fib_extreme']
            fib_lock = bs['fib_wave_start'] - downswing * params['fib_ext_pct']
            prev = bs.get('fib_stop', None)
            bs['fib_stop'] = min(prev if prev is not None else float('inf'), fib_lock)
            if design == 'C3_fibearly' and not bs['c3_logged']:
                bs['c3_logged'] = True; bs['sl_set_dist'] = (bs['fib_stop'] - entry) / entry * 100.0
            if price >= bs['fib_stop']:
                return {"action": "CLOSE_SHORT", "reason": "Fibonacci"}
    return {"action": "HOLD", "reason": "hold"}


def simulate_one(arrays, e_idx, tp_targets, res_ob_top, design):
    o, h, l, c, idx = arrays
    entry = c[e_idx]; liq = entry * (1 + LIQ_MOVE)
    bs = {'position': 'SHORT', 'entry_price': entry, 'remaining_pct': 1.0, 'target_idx': 0,
          'fib_wave_start': entry, 'fib_extreme': entry, 'pulled_back': False, 'fib_stop': None,
          'bullish_obs': tp_targets, 'res_ob_top': res_ob_top,
          'phase2_logged': False, 'c3_logged': False, 'sl_set_dist': None}
    params = {'leverage': LEVERAGE, 'fib_trigger_roe': FIB_TRIGGER, 'fib_ext_pct': FIB_EXT,
              'hard_floor_roe': HARD_FLOOR_ROE, 'sl_design': design}
    frac = 1.0; reduced = False; R = 0.0
    n = len(c); end_idx = min(n, e_idx + 1 + MAX_HOLD_BARS); xi = end_idx - 1
    for i in range(e_idx + 1, end_idx):
        o_, h_, l_, c_ = o[i], h[i], l[i], c[i]
        ticks = (o_, h_, l_, c_) if c_ < o_ else (o_, l_, h_, c_)
        for price in ticks:
            if price >= liq:
                R += frac * ((entry - liq) / entry) - frac * COST * 2
                return R, 'liq', i, bs['sl_set_dist']
            sig = exec_check_exit(price, bs, params); act = sig['action']
            if act == 'REDUCE_SHORT' and not reduced:
                R += 0.5 * ((entry - price) / entry) - 0.5 * COST * 2; frac = 0.5; reduced = True; continue
            if act == 'CLOSE_SHORT':
                dur = (idx[i] - idx[e_idx]).total_seconds() / 86400
                R += frac * ((entry - price) / entry) - frac * COST * 2 - frac * FUNDING_DAILY * dur
                return R, sig['reason'], i, bs['sl_set_dist']
    R += frac * ((entry - c[xi]) / entry) - frac * COST * 2
    return R, 'max_hold', xi, bs['sl_set_dist']


def collect_entries(df):
    o = df['open'].values; h = df['high'].values; l = df['low'].values; c = df['close'].values
    idx = df.index
    down_idx = np.where(df[REGIME_COL].astype(str).values == 'downtrend')[0]
    hpc, _, hpt, hpb, _, _ = precompute_tf_pivots(resample_tf(df, SL_TF), W_TF, SL_TF)
    _, lpc, _, _, lpt, lpb = precompute_tf_pivots(resample_tf(df, TP_TF), W_TF, TP_TF)
    entries = []; n = len(c); cur = 0
    dptr = np.searchsorted(down_idx, cur, side='left')
    while dptr < len(down_idx):
        t0 = int(down_idx[dptr])
        if t0 >= n - 1:
            break
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
                entries.append((t0, tps, float(ab[0]), ts))
        cur = t0 + 1
        dptr = np.searchsorted(down_idx, cur, side='left')
    return entries, (o, h, l, c, idx)


def run_free(entries, arrays, design):
    """자유진입(stg1동일): 청산 후 타임라인 풀림 -> 거래수 변동."""
    idx = arrays[4]; rows = []; last_exit = -1
    for (e_idx, tps, res_ob_top, ts) in entries:
        if e_idx <= last_exit:
            continue
        R, reason, x_idx, sld = simulate_one(arrays, e_idx, tps, res_ob_top, design)
        rows.append({'진입시간': ts.strftime('%Y-%m-%d %H:%M:%S'), '연도': ts.year, 'R': R,
                     '청산사유': reason, 'sl거리pct': sld, 'e_idx': e_idx})
        last_exit = x_idx
    return rows


def run_fixed(fixed_entries, lookup, arrays, design):
    """고정진입(C0집합): 동일 e_idx로 설계별 청산만. 거래수 동일 -> 순수 SL효과."""
    rows = []
    for e_idx in fixed_entries:
        tps, res_ob_top, ts = lookup[e_idx]
        R, reason, x_idx, sld = simulate_one(arrays, e_idx, tps, res_ob_top, design)
        rows.append({'진입시간': ts.strftime('%Y-%m-%d %H:%M:%S'), '연도': ts.year, 'R': R,
                     '청산사유': reason, 'sl거리pct': sld, 'e_idx': e_idx})
    return rows


def dist_stats(rows):
    d = [r['sl거리pct'] for r in rows if r['sl거리pct'] is not None]
    if not d:
        return (None, None, None, 0)
    a = np.array(d)
    return (round(float(a.mean()), 3), round(float(a.min()), 3), round(float(a.max()), 3), len(d))


def agg(rows, design, mode):
    if not rows:
        return {'설계': design, '모드': mode, '거래수': 0}
    t = pd.DataFrame(rows); R = t['R'].values
    gp = R[R > 0].sum(); gl = -R[R < 0].sum(); pf = (gp / gl) if gl > 0 else 999.0
    cap = START_CAP; mincap = START_CAP; bankrupt = False
    for r in R:
        cap += r * NOMINAL; mincap = min(mincap, cap)
        if cap <= MIN_CAP:
            bankrupt = True; break
    m, lo, hi, nfired = dist_stats(rows)
    fired = int((t['청산사유'] == 'sl_design').sum())
    return {'설계': design, '모드': mode, '거래수': len(t),
            '강제청산': int((t['청산사유'] == 'liq').sum()),
            '구멍': int((t['청산사유'] == 'hole_hardfloor').sum()),
            '피보승자': int((t['청산사유'] == 'Fibonacci').sum()),
            'SL발동수': fired,
            'SL거리_평균pct': m, 'SL거리_최저pct': lo, 'SL거리_최고pct': hi,
            '누적R_pct': round(R.sum() * 100, 2), '평균R_pct': round(R.mean() * 100, 4),
            'PF': round(pf, 3), '파산': 'YES' if bankrupt else 'NO',
            '최저자본': round(mincap, 0)}


def main():
    print("[InfraA_V2_stg2] SL거리 진단 + 고정진입 깨끗비교")
    open(os.path.join(HERE, ".run_start"), 'w').close()
    data = find_data(); print(f"[data] {data}")
    df = load_data(data)
    print(f"[load] {len(df):,}rows | {df.index.min().date()}~{df.index.max().date()}")
    entries, arrays = collect_entries(df)
    lookup = {e[0]: (e[1], e[2], e[3]) for e in entries}
    print(f"[entries] 후보 {len(entries)}건")

    # C0 자유진입 1회 -> 진입집합(고정모드 공유)
    c0_free = run_free(entries, arrays, 'C0_none')
    fixed_set = [r['e_idx'] for r in c0_free]
    print(f"[C0 진입집합] {len(fixed_set)}건 (고정모드 공유)")

    summary = []; best_trades = None
    for d in DESIGNS:
        free_rows = c0_free if d == 'C0_none' else run_free(entries, arrays, d)
        fixed_rows = run_fixed(fixed_set, lookup, arrays, d)
        mA = agg(free_rows, d, 'A_자유진입'); mB = agg(fixed_rows, d, 'B_고정진입')
        summary.append(mA); summary.append(mB)
        # 고정모드 train/test
        for yrs, nm in [(TRAIN_YEARS, 'B_train'), (TEST_YEARS, 'B_test')]:
            summary.append(agg([r for r in fixed_rows if r['연도'] in yrs], d, nm))
        print(f"  [{d:13s}] B고정: SL거리 평균{mB.get('SL거리_평균pct')}% "
              f"[{mB.get('SL거리_최저pct')}~{mB.get('SL거리_최고pct')}] 발동{mB.get('SL발동수')} "
              f"강제청산{mB.get('강제청산')} 누적R{mB.get('누적R_pct')}% (자유진입누적R{mA.get('누적R_pct')}%)")
        if d == 'C4_resob':
            best_trades = fixed_rows

    pd.DataFrame(summary).to_csv(os.path.join(HERE, "sldist_summary.csv"), index=False, encoding='utf-8-sig')
    # 거래별 상세: 고정모드 전 설계 (SL거리/사유)
    detail = []
    for d in DESIGNS:
        for r in run_fixed(fixed_set, lookup, arrays, d):
            detail.append({'설계': d, '진입시간': r['진입시간'], '연도': r['연도'],
                           'R_pct': round(r['R'] * 100, 4), '청산사유': r['청산사유'],
                           'sl거리pct': (round(r['sl거리pct'], 3) if r['sl거리pct'] is not None else None)})
    pd.DataFrame(detail).to_csv(os.path.join(HERE, "sldist_trades.csv"), index=False, encoding='utf-8-sig')
    print("[save] sldist_summary.csv + sldist_trades.csv (this subfolder) - all files")


if __name__ == "__main__":
    main()
