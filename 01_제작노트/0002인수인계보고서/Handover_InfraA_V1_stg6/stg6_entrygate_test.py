# -*- coding: utf-8 -*-
# [FILE] test.py  (InfraA_V1_stg6 - entry-gate filter: none / tree-3leaf / simple-2cond, real gate, 36mo)
# CODE LENGTH: approx 420 lines | INTERNAL VER: stg6_entrygate_v1 | full output, no omission
#
# [PURPOSE / 목적] stg5에서 '손절당김' 막힘(고정%손절이 5배레버와 상극, 정상거래 학살). 방향전환:
#   손실%를 자르지 말고 '나쁜 진입자리를 피한다'(진입게이트). stg4 결정나무 고사고잎을 실제 게이트에 박음.
#   ★stg5 교훈 준수: 사후보정 아님. 진입 결정 시점에 규칙검사 -> 위험조합이면 진입 SKIP(정상거래 안건드림).
#   grid: gate {none(기준), tree3(나무3잎), simple2(tp+oiZ 단순)} -> 3칸 x 학습/검증분리.
#
# [GATE 규칙 — stg4 acc_tree.csv 고사고잎(사고율31/35/100%) 그대로]
#   진입 직전 피처 계산 후, 아래 중 하나라도 참이면 SKIP(진입안함):
#   tree3:
#     L100: tp_dist_bp>20.45 AND oi_zscore_24h<=-1.306 AND swing_pos>0.6604
#     L35 : tp_dist_bp>20.45 AND oi_zscore_24h> -1.306 AND tp_dist_bp>76.64
#     L31 : tp_dist_bp<=20.45 AND oi_change_1h_pct<=-0.1602 AND sl_dist_bp>82.74
#   simple2 (과적합 줄인 단순판): tp_dist_bp>76.64 OR oi_zscore_24h<=-1.306  -> SKIP
#     (나무 1·2순위 분기 핵심만. 둘 중 하나라도 참이면 위험자리로 보고 스킵)
#
# [엔진] FLOOR15(다중OB계단/피보0.65/구멍하드플로어15%) 그대로. 손절당김 없음(stg5서 기각).
# [측정] 각 게이트: PF/승률/누적R/사고/피보승자/진입수 + 학습(2023~24)/검증(2025~26) 분리.
#   ★핵심비교: 기준 대비 '사고 줄고 + 누적R 양전 + 검증도 양전' 인 게이트가 있나.
#   합격선 PF>1·파산NO·자본>=시작50%.
#
# [SPEED] pivot/OB 전구간 1회, 진입스캔 1회로 진입후보+피처 수집 -> 3게이트는 그 위에서 SKIP만 분기.
#   merged_data(OI)는 timestamp left join 1회. 하락장만+청산까지만 4틱+빈구간 점프.
#
# [PATH] D:\ML\verify\InfraA_V1_stg6\ 실행, 데이터 상위, 결과 CSV -> 이 하위폴더.
# [DATA] B=../Merged_Data_with_Regime_Features.csv, A=../merged_data.csv(OI/flow, 나무규칙 필수)
# [OUTPUT] gate_summary.csv(3칸) + gate_split.csv(학습/검증) + gate_trades_best.csv(최선칸 거래)
#
# [FUNCTIONS] (ob_mtf inline) + merge_flow + collect_entries(피처포함) + gate_skip(row,gate)
#   + exec_check_exit(FLOOR15) + simulate_one + run_gate
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
START_CAP = 10000.0
TRAIN_YEARS = [2023, 2024]; TEST_YEARS = [2025, 2026]
GATES = ['none', 'tree3', 'simple2']
FEAT_A = ['oi_change_1h_pct', 'oi_zscore_24h']   # 나무규칙에 쓰는 OI 피처만


def find_data():
    for d in [PARENT, HERE, r"D:\ML\verify", r"D:\ML\Verify"]:
        p = os.path.join(d, "Merged_Data_with_Regime_Features.csv")
        if os.path.exists(p):
            return p
    raise FileNotFoundError("상위 D:\\ML\\verify 에 Merged_Data_with_Regime_Features.csv 필요")


def find_flow():
    for d in [PARENT, HERE, r"D:\ML\verify", r"D:\ML\Verify"]:
        for n in ["merged_data.csv", "merged_data_sample.csv"]:
            p = os.path.join(d, n)
            if os.path.exists(p):
                return p
    return None


def load_data(path):
    head = pd.read_csv(path, nrows=1)
    if REGIME_COL not in head.columns:
        raise KeyError(f"{REGIME_COL} 없음")
    cols = ['timestamp', 'open', 'high', 'low', 'close', REGIME_COL]
    df = pd.read_csv(path, usecols=cols, index_col='timestamp', parse_dates=True)
    if getattr(df.index, 'tz', None) is not None:
        df.index = df.index.tz_localize(None)
    return df.sort_index()


def merge_flow(df, flow_path):
    info = {'flow': 'none', 'match_pct': 0.0}
    if flow_path is None:
        for cc in FEAT_A:
            df[cc] = np.nan
        return df, info
    fh = pd.read_csv(flow_path, nrows=1)
    use = ['timestamp'] + [cc for cc in FEAT_A if cc in fh.columns]
    fa = pd.read_csv(flow_path, usecols=use, index_col='timestamp', parse_dates=True)
    if getattr(fa.index, 'tz', None) is not None:
        fa.index = fa.index.tz_localize(None)
    fa = fa.sort_index()
    df = df.join(fa, how='left')
    for cc in FEAT_A:
        if cc not in df.columns:
            df[cc] = np.nan
    matched = df[[c for c in FEAT_A if c in df.columns]].notna().any(axis=1).mean()
    info = {'flow': os.path.basename(flow_path), 'match_pct': round(float(matched) * 100, 1)}
    return df, info


# ----- ob_mtf inline -----------------------------------------------------------
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


def simulate_one(o, h, l, c, idx, e_idx, tp_targets):
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
                R += frac * ((entry - liq) / entry) - frac * COST * 2
                return R, 'liq', idx[i]
            sig = exec_check_exit(price, bs, params); act = sig['action']
            if act == 'REDUCE_SHORT' and not reduced:
                R += 0.5 * ((entry - price) / entry) - 0.5 * COST * 2; frac = 0.5; reduced = True; continue
            if act == 'CLOSE_SHORT':
                dur = (idx[i] - idx[e_idx]).total_seconds() / 86400
                R += frac * ((entry - price) / entry) - frac * COST * 2 - frac * FUNDING_DAILY * dur
                return R, sig['reason'], idx[i]
    R += frac * ((entry - c[xi]) / entry) - frac * COST * 2
    return R, 'max_hold', idx[xi]


def collect_entries(df):
    """진입후보 + 게이트 판정용 피처 1회 수집. [(e_idx, tps, ts, feat)]"""
    o = df['open'].values; h = df['high'].values; l = df['low'].values; c = df['close'].values
    idx = df.index
    oiZ = df['oi_zscore_24h'].values if 'oi_zscore_24h' in df.columns else np.full(len(df), np.nan)
    oi1h = df['oi_change_1h_pct'].values if 'oi_change_1h_pct' in df.columns else np.full(len(df), np.nan)
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
            tp0 = bl[0][1] * (1 + D_FIX / 1e4); tp_dist = (price - tp0) / price
            tps = [{'top': t, 'bottom': b, 'mean': b * (1 + D_FIX / 1e4)} for (t, b) in bl if b * (1 + D_FIX / 1e4) < price]
            if tps:
                feat = dict(tp_dist_bp=tp_dist * 1e4, sl_dist_bp=sl_dist * 1e4,
                            oi_zscore_24h=oiZ[t0], oi_change_1h_pct=oi1h[t0], swing_pos=swing_pos(h, l, t0))
                entries.append((t0, tps, ts, feat))
        cur = t0 + 1
        dptr = np.searchsorted(down_idx, cur, side='left')
    return entries, (o, h, l, c, idx)


def gate_skip(f, gate):
    """True면 진입 SKIP. NaN(OI없음)인 조건은 '미충족(=안전판정)'으로 처리(보수적: 막지않음)."""
    tp = f['tp_dist_bp']; sl = f['sl_dist_bp']; sw = f['swing_pos']
    oiZ = f['oi_zscore_24h']; oi1 = f['oi_change_1h_pct']
    def le(a, b):  # a<=b, NaN이면 False
        return (a == a) and (a <= b)
    def gt(a, b):
        return (a == a) and (a > b)
    if gate == 'none':
        return False
    if gate == 'tree3':
        L100 = (tp > 20.45) and le(oiZ, -1.306) and (sw > 0.6604)
        L35 = (tp > 20.45) and gt(oiZ, -1.306) and (tp > 76.64)
        L31 = (tp <= 20.45) and le(oi1, -0.1602) and (sl > 82.74)
        return bool(L100 or L35 or L31)
    if gate == 'simple2':
        return bool((tp > 76.64) or le(oiZ, -1.306))
    return False


def run_gate(entries, arrays, gate):
    o, h, l, c, idx = arrays
    rows = []; last_exit_idx = -1
    for (e_idx, tps, ts, feat) in entries:
        if e_idx <= last_exit_idx:
            continue
        if gate_skip(feat, gate):
            continue                     # 진입 SKIP (정상거래 안건드림, 그냥 안들어감)
        R, reason, xt = simulate_one(o, h, l, c, idx, e_idx, tps)
        x_idx = int(idx.searchsorted(pd.to_datetime(xt.strftime('%Y-%m-%d %H:%M:%S'))))
        last_exit_idx = max(x_idx, e_idx)
        acc = 1 if reason in ('liq', 'hole_hardfloor') else 0
        rows.append(dict(진입시간=ts.strftime('%Y-%m-%d %H:%M:%S'), 연도=ts.year,
                         R=round(R, 6), 청산사유=reason, 사고=acc))
    return pd.DataFrame(rows)


def metrics(td):
    if len(td) == 0:
        return dict(진입=0, PF=0, 승률=0, 누적R=0, 사고=0, 피보승자=0)
    R = td['R'].values
    pf = R[R > 0].sum() / abs(R[R < 0].sum()) if (R < 0).any() else 9.99
    fibwin = int(((td['청산사유'] == 'Fibonacci') & (R > 0)).sum())
    return dict(진입=len(td), PF=round(pf, 3), 승률=round((R > 0).mean() * 100, 1),
                누적R=round(R.sum() * 100, 1), 사고=int(td['사고'].sum()), 피보승자=fibwin)


def main():
    print("[InfraA_V1_stg6] 진입게이트 비교: none / tree3(나무3잎) / simple2(tp+oiZ) — 실제게이트 + 학습/검증")
    open(os.path.join(HERE, ".run_start"), 'w').close()
    data = find_data(); print(f"[data B] {data}")
    df = load_data(data)
    flow = find_flow(); df, finfo = merge_flow(df, flow)
    print(f"[data A] {finfo['flow']} (OI매칭률 {finfo['match_pct']}%)")
    if finfo['match_pct'] < 50:
        print("  ★경고: OI매칭률 낮음 -> 나무규칙 핵심조건(oi_zscore) 작동 제한적")
    print(f"[load] {len(df):,}rows | {df.index.min().date()}~{df.index.max().date()}")
    print("[진입목록+피처 1회 수집...]")
    entries, arrays = collect_entries(df)
    print(f"  진입후보 {len(entries)}건 (3게이트 공용)\n")

    summary = []; split = []; best = None; best_key = (-9e9, None)
    for gate in GATES:
        td = run_gate(entries, arrays, gate)
        m = metrics(td)
        cap_mult = 1 + m['누적R'] / 100.0
        row = dict(게이트=gate, **m, 최종자본배수=round(cap_mult, 3), 파산='YES' if cap_mult <= 0.5 else 'NO')
        summary.append(row)
        for sname, yrs in [('학습2023_24', TRAIN_YEARS), ('검증2025_26', TEST_YEARS)]:
            ms = metrics(td[td['연도'].isin(yrs)])
            split.append(dict(게이트=gate, 구간=sname, 진입=ms['진입'], PF=ms['PF'], 누적R=ms['누적R'], 사고=ms['사고']))
        print(f"  [{gate:8s}] 진입{m['진입']} PF{m['PF']} 승률{m['승률']}% 누적R{m['누적R']}% 사고{m['사고']} 피보승자{m['피보승자']} 파산{row['파산']}")
        if row['파산'] == 'NO' and m['누적R'] > best_key[0]:
            best_key = (m['누적R'], gate); best = td.copy()

    pd.DataFrame(summary).to_csv(os.path.join(HERE, "gate_summary.csv"), index=False, encoding='utf-8-sig')
    pd.DataFrame(split).to_csv(os.path.join(HERE, "gate_split.csv"), index=False, encoding='utf-8-sig')
    if best is not None and len(best):
        best.to_csv(os.path.join(HERE, "gate_trades_best.csv"), index=False, encoding='utf-8-sig')
        print(f"\n[best] {best_key[1]} 누적R {best_key[0]}%")
    else:
        pd.DataFrame(columns=['진입시간', '연도', 'R', '청산사유', '사고']).to_csv(
            os.path.join(HERE, "gate_trades_best.csv"), index=False, encoding='utf-8-sig')
        print("\n[best] 양전 게이트 없음(전부 적자/파산)")
    print("\n[save] gate_summary.csv + gate_split.csv + gate_trades_best.csv (this subfolder) - all files")


if __name__ == "__main__":
    main()
