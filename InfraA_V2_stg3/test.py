# -*- coding: utf-8 -*-
# [FILE] test.py  (InfraA_V2_stg3 - hard max-hold time cut x realistic funding, fixed+free entry)
# CODE LENGTH: approx 360 lines | INTERNAL VER: timecut_v1 | full output, no omission
#
# [PURPOSE / 목적] 강제청산 9건은 전부 6.8일+ 장기보유(중앙17.5일). 17일 보유는 펀딩비로도 비현실.
#   가설: '진입후 최대 N일 넘기면 강제청산(시간컷)'으로 사고는 잡되, 승자는 3일은 태운 뒤 자르므로
#   SL(초반 출렁임에서 절단)보다 승자를 더 보존한다. ★실엔진 실시간 청산(사후보정 아님).
#   ★stg2 교훈: 거래폭증이 비교를 오염시키므로 '고정진입(C0 248집합)'을 1차 비교로, 자유진입은 참고.
#   ★사장님 지적: 현 펀딩비 0.01%/일은 과소. 실제 ~0.03%/일 반영해 둘 다 비교.
#
# [GRID] cut_days {none(=현행 90일상한), 5, 3, 2} x funding {0.0001(구), 0.0003(현실)} = 8칸
#   각 칸: 거래수/강제청산/구멍/피보승자/시간컷수/누적R/PF/파산/최저자본 + 학습/검증분리.
#   ★합격선: 강제청산 줄고 + 누적R C0보다 개선 + 검증(2025~26) 양전유지(+4.3% 안깸) + 파산NO.
#
# [SPEED] pivot/OB 1회, 진입후보 1회수집. C0(none,구펀딩) 진입집합 확보후 고정모드 공유.
#   각 칸은 청산만 재시뮬(시간컷은 봉인덱스 비교 1회라 추가비용 거의 0).
# [PATH] D:\ML\verify\InfraA_V2_stg3\ 실행, 데이터 상위, 결과 CSV -> 이 하위폴더.
# [DATA] ../Merged_Data_with_Regime_Features.csv
# [OUTPUT] timecut_summary.csv(8칸×모드) + timecut_split.csv(학습/검증) + timecut_trades.csv(C0집합 거래별)
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
COST = 0.0004
FIB_TRIGGER = 15.0; FIB_EXT = 0.65; HARD_FLOOR_ROE = 15.0
NOMINAL = 50000.0; START_CAP = 10000.0; MIN_CAP = 100.0
HARD_CAP_BARS = 60 * 24 * 90        # 현행(none): 90일 상한
TRAIN_YEARS = [2023, 2024]; TEST_YEARS = [2025, 2026]
CUT_DAYS = [None, 5, 3, 2]                       # None=현행
FUNDINGS = [('fund_old', 0.0001), ('fund_real', 0.0003)]   # /일
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
    """FLOOR15 엔진 원본 그대로(시간컷은 simulate_one에서 처리, 엔진 미수정)."""
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


def simulate_one(arrays, e_idx, tp_targets, cut_bars, funding):
    """청산엔진 원본 + 시간컷(cut_bars 도달시 그 봉 종가청산 'time_cut')."""
    o, h, l, c, idx = arrays
    entry = c[e_idx]; liq = entry * (1 + LIQ_MOVE)
    bs = {'position': 'SHORT', 'entry_price': entry, 'remaining_pct': 1.0, 'target_idx': 0,
          'fib_wave_start': entry, 'fib_extreme': entry, 'pulled_back': False, 'fib_stop': None,
          'bullish_obs': tp_targets}
    params = {'leverage': LEVERAGE, 'fib_trigger_roe': FIB_TRIGGER, 'fib_ext_pct': FIB_EXT,
              'hard_floor_roe': HARD_FLOOR_ROE}
    frac = 1.0; reduced = False; R = 0.0
    n = len(c)
    cap_bars = min(cut_bars if cut_bars is not None else HARD_CAP_BARS, HARD_CAP_BARS)
    end_idx = min(n, e_idx + 1 + cap_bars); xi = end_idx - 1
    for i in range(e_idx + 1, end_idx):
        o_, h_, l_, c_ = o[i], h[i], l[i], c[i]
        ticks = (o_, h_, l_, c_) if c_ < o_ else (o_, l_, h_, c_)
        for price in ticks:
            if price >= liq:
                R += frac * ((entry - liq) / entry) - frac * COST * 2
                return R, 'liq', i
            sig = exec_check_exit(price, bs, params); act = sig['action']
            if act == 'REDUCE_SHORT' and not reduced:
                R += 0.5 * ((entry - price) / entry) - 0.5 * COST * 2; frac = 0.5; reduced = True; continue
            if act == 'CLOSE_SHORT':
                dur = (idx[i] - idx[e_idx]).total_seconds() / 86400
                R += frac * ((entry - price) / entry) - frac * COST * 2 - frac * funding * dur
                return R, sig['reason'], i
    # 시간컷(또는 90일상한) 도달 -> 그 봉 종가 청산
    dur = (idx[xi] - idx[e_idx]).total_seconds() / 86400
    R += frac * ((entry - c[xi]) / entry) - frac * COST * 2 - frac * funding * dur
    reason = 'time_cut' if (cut_bars is not None) else 'max_hold'
    return R, reason, xi


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
                entries.append((t0, tps, ts))
        cur = t0 + 1
        dptr = np.searchsorted(down_idx, cur, side='left')
    return entries, (o, h, l, c, idx)


def run_free(entries, arrays, cut_bars, funding):
    idx = arrays[4]; rows = []; last_exit = -1
    for (e_idx, tps, ts) in entries:
        if e_idx <= last_exit:
            continue
        R, reason, x_idx = simulate_one(arrays, e_idx, tps, cut_bars, funding)
        rows.append({'진입시간': ts.strftime('%Y-%m-%d %H:%M:%S'), '연도': ts.year, 'R': R,
                     '청산사유': reason, 'e_idx': e_idx})
        last_exit = x_idx
    return rows


def run_fixed(fixed_set, lookup, arrays, cut_bars, funding):
    rows = []
    for e_idx in fixed_set:
        tps, ts = lookup[e_idx]
        R, reason, x_idx = simulate_one(arrays, e_idx, tps, cut_bars, funding)
        rows.append({'진입시간': ts.strftime('%Y-%m-%d %H:%M:%S'), '연도': ts.year, 'R': R,
                     '청산사유': reason, 'e_idx': e_idx})
    return rows


def agg(rows, label, mode):
    if not rows:
        return {'설정': label, '모드': mode, '거래수': 0}
    t = pd.DataFrame(rows); R = t['R'].values
    gp = R[R > 0].sum(); gl = -R[R < 0].sum(); pf = (gp / gl) if gl > 0 else 999.0
    cap = START_CAP; mincap = START_CAP; bankrupt = False
    for r in R:
        cap += r * NOMINAL; mincap = min(mincap, cap)
        if cap <= MIN_CAP:
            bankrupt = True; break
    return {'설정': label, '모드': mode, '거래수': len(t),
            '강제청산': int((t['청산사유'] == 'liq').sum()),
            '구멍': int((t['청산사유'] == 'hole_hardfloor').sum()),
            '피보승자': int((t['청산사유'] == 'Fibonacci').sum()),
            '시간컷': int((t['청산사유'] == 'time_cut').sum()),
            '누적R_pct': round(R.sum() * 100, 2), '평균R_pct': round(R.mean() * 100, 4),
            'PF': round(pf, 3), '파산': 'YES' if bankrupt else 'NO', '최저자본': round(mincap, 0)}


def label_of(cut, fund_name):
    cd = 'none' if cut is None else f'{cut}d'
    return f'cut{cd}_{fund_name}'


def main():
    print("[InfraA_V2_stg3] 시간제한(none/5/3/2일) x 펀딩(0.01%/0.03%) — 고정진입+자유진입")
    open(os.path.join(HERE, ".run_start"), 'w').close()
    data = find_data(); print(f"[data] {data}")
    df = load_data(data)
    print(f"[load] {len(df):,}rows | {df.index.min().date()}~{df.index.max().date()}")
    entries, arrays = collect_entries(df)
    lookup = {e[0]: (e[1], e[2]) for e in entries}
    print(f"[entries] 후보 {len(entries)}건")

    # C0(none, 구펀딩) 진입집합 -> 고정모드 공유
    c0_free = run_free(entries, arrays, None, 0.0001)
    fixed_set = [r['e_idx'] for r in c0_free]
    print(f"[C0 진입집합] {len(fixed_set)}건 (고정모드 공유)")

    summary = []; trades_dump = []
    for fname, fval in FUNDINGS:
        for cut in CUT_DAYS:
            cut_bars = None if cut is None else cut * 1440
            lab = label_of(cut, fname)
            free_rows = (c0_free if (cut is None and fname == 'fund_old') else run_free(entries, arrays, cut_bars, fval))
            fixed_rows = run_fixed(fixed_set, lookup, arrays, cut_bars, fval)
            mA = agg(free_rows, lab, 'A_자유'); mB = agg(fixed_rows, lab, 'B_고정')
            summary.append(mA); summary.append(mB)
            for yrs, nm in [(TRAIN_YEARS, 'B_train'), (TEST_YEARS, 'B_test')]:
                summary.append(agg([r for r in fixed_rows if r['연도'] in yrs], lab, nm))
            print(f"  [{lab:16s}] 고정: 거래{mB.get('거래수')} 강제청산{mB.get('강제청산')} 시간컷{mB.get('시간컷')} "
                  f"피보승자{mB.get('피보승자')} 누적R{mB.get('누적R_pct')}% PF{mB.get('PF')} 파산{mB.get('파산')} "
                  f"| 자유거래{mA.get('거래수')}")
            if fname == 'fund_real':   # 거래별 덤프는 현실펀딩 고정모드만
                for r in fixed_rows:
                    trades_dump.append({'설정': lab, '진입시간': r['진입시간'], '연도': r['연도'],
                                        'R_pct': round(r['R'] * 100, 4), '청산사유': r['청산사유']})

    pd.DataFrame(summary).to_csv(os.path.join(HERE, "timecut_summary.csv"), index=False, encoding='utf-8-sig')
    split = [r for r in summary if r['모드'] in ('B_train', 'B_test')]
    pd.DataFrame(split).to_csv(os.path.join(HERE, "timecut_split.csv"), index=False, encoding='utf-8-sig')
    pd.DataFrame(trades_dump).to_csv(os.path.join(HERE, "timecut_trades.csv"), index=False, encoding='utf-8-sig')
    print("[save] timecut_summary.csv + timecut_split.csv + timecut_trades.csv (this subfolder) - all files")


if __name__ == "__main__":
    main()
