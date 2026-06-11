# -*- coding: utf-8 -*-
# [FILE] test.py  (InfraA_V3_stg2 - gap_guard (empty-zone protective line) + TP bottom -5bp)
# CODE LENGTH: approx 330 lines | INTERNAL VER: gapguard_v1 | full output, no omission
#
# [PURPOSE / 목적] stg1 분해로 확정: 손실은 liq 9건(-92%)·hole 25건(-82%)에 뭉쳐있고, 엔진(승자80=+120%)은 자산.
#   이번엔 합의대로 'liq'만 노린다. liq의 정체(코드확인): 1차 OB 닿아 REDUCE→하드플로어 꺼짐→OB 다 소진(Phase2)
#   인데 +15%(피보발동) 못 찍어 'price>=stop' 검사가 빠진 사각지대에서 +20%까지 표류→강제청산.
#   ★해결(빈구간 보호선 gap_guard): REDUCE 후 ~ 피보락인 전 구간에, 보호선=min(진입가*1.03, 직전OB top)을
#     상시 유지. 가격이 그 선 이상이면 청산('gap_guard'). 숏이라 보호선은 위쪽 → 하락(승자방향)은 안 막음.
#   ★승자 보존이 핵심 잣대(stg2 SL은 승자를 죽여 실패했음). hole 25건은 이번 대상 아님(stg3 엔트리품질).
#
# [GRID 3칸 — 같은 C0 진입집합 고정, 펀딩 8h이산 고정]
#   B0_base  : TP 바닥+5bp, guard OFF  (=stg1 R2 재현 기준선)
#   B1_guard : TP 바닥+5bp, guard ON   (빈구간 보호선 순효과만)
#   B2_full  : TP 바닥-5bp, guard ON   (㉠+보호선 최종)
#   각칸: 거래/강제청산/구멍/피보승자/gap_guard수/누적R/PF/파산/최저자본 + train(23~24)/test(25~26).
#   ★판정: liq↓ & 피보승자 80 보존(=) & 검증기 개선 & 파산 해소.
#
# [SPEED] pivot/OB 1회 사전계산, C0 진입집합 1회 확보 후 칸별 청산만 재시뮬. eh(epoch-hours) 1회.
#   TP부호는 진입집합 고정 후 raw OB로 tps만 재구성(저비용).
# [LOOKAHEAD GUARD] OB는 pivot 확정시각 이후만. feat_struct_8 인과확보(별도실측). 청산은 진입후 봉만.
# [PATH] D:\ML\verify\InfraA_V3_stg2\ 실행, 데이터 상위, 결과 CSV -> 이 하위폴더.
# [DATA] ../Merged_Data_with_Regime_Features.csv
# [OUTPUT] guard_summary.csv(3칸×모드) + guard_trades.csv(B2 거래별)
#
# [FUNCTIONS In/Out]
#   find_data/load_data ; resample_tf/precompute_tf_pivots/nearest_above/levels_below_5m [verified]
#   build_tps(bl_raw,price,sign)->tps              (TP부호별 목표 재구성)
#   exec_check_exit(price,bs,params)->action       (stg1엔진 + gap_guard 추가)
#   n_funding_8h(eh_in,eh_out)->int
#   simulate_one(arrays,eh,e_idx,bl_raw,sign,guard)->(R,reason,exit_idx,funding)
#   collect_entries(df)->[(e_idx,bl_raw,ts)]       (B0기준 진입집합, raw OB저장)
#   run_fixed(fixed,lookup,arrays,eh,sign,guard)->rows ; agg(rows,label,mode)->dict
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
GUARD_MULT = 1.0 + HARD_FLOOR_ROE / 100.0 / LEVERAGE   # 진입가*1.03 (=+3% 가격, ROE15%)
NOMINAL = 50000.0; START_CAP = 10000.0; MIN_CAP = 100.0
HARD_CAP_BARS = 60 * 24 * 90
TRAIN_YEARS = [2023, 2024]; TEST_YEARS = [2025, 2026]
FUND_8H = 0.0001   # 0.03%/일을 8h당 0.01% (현실 이산, stg1 확정)
# (라벨, TP부호(+1=바닥+5bp/-1=바닥-5bp), guard_mode)
#   off  : 보호선 없음(=stg1 R2 재현)
#   tight: min(진입가*1.03, 직전OB top) — 사장님 확정안(먹은 이익 적극 보호)
#   loose: 진입가*1.03 만 — 큰 역행(liq)만 막고 눌림목은 허용(승자 보존 우선)
CELLS = [('B0_base', +1, 'off'), ('B1_tight', +1, 'tight'),
         ('B2_full', -1, 'tight'), ('B3_loose', -1, 'loose')]


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


# ----- ob_mtf inline (verified, stg1 동일) --------------------------------------
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


def build_tps(bl_raw, price, sign):
    """TP부호별 목표 재구성. sign=+1 바닥+5bp / -1 바닥-5bp. mean<price 만 채택."""
    out = []
    for (t, b) in bl_raw:
        mean = b * (1 + sign * D_FIX / 1e4)
        if mean < price:
            out.append({'top': t, 'bottom': b, 'mean': mean})
    return out


def exec_check_exit(price, bs, params):
    """stg1 엔진 그대로 + gap_guard(빈구간 보호선) 추가.
    gap_guard: REDUCE 후 ~ 피보락인 전, 보호선=min(진입가*1.03, 직전OB top) 이상이면 청산."""
    entry = bs['entry_price']; lev = params['leverage']; target_idx = bs['target_idx']
    # (1) 구멍 하드플로어 — 보호스탑 전혀 없을 때만(=1차OB 닿기 전). 무수정.
    if bs['fib_stop'] is None:
        hf = entry * (1 + params['hard_floor_roe'] / 100.0 / lev)
        if price >= hf:
            return {"action": "CLOSE_SHORT", "reason": "hole_hardfloor"}
    # (2) ★빈구간 보호선 — REDUCE 후 & 피보 미발동 구간. (사각지대 메움)
    gm = params['guard_mode']
    if gm != 'off' and bs['reduced'] and not bs['fib_active']:
        g = entry * GUARD_MULT
        if gm == 'tight' and bs['last_ob_top'] is not None:
            g = min(g, bs['last_ob_top'])
        if price >= g:
            return {"action": "CLOSE_SHORT", "reason": "gap_guard"}
    bull = bs['bullish_obs']
    if target_idx < len(bull):
        tob = bull[target_idx]
        if price <= tob['mean']:
            bs['fib_stop'] = tob['top']; bs['last_ob_top'] = tob['top']; bs['target_idx'] += 1
            if bs['remaining_pct'] == 1.0:
                bs['remaining_pct'] = 0.5; bs['reduced'] = True
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
            bs['fib_active'] = True
            if price >= bs['fib_stop']:
                return {"action": "CLOSE_SHORT", "reason": "Fibonacci"}
    return {"action": "HOLD", "reason": "hold"}


def n_funding_8h(eh_in, eh_out):
    return int(np.floor(eh_out / 8.0) - np.floor(eh_in / 8.0))


def simulate_one(arrays, eh, e_idx, bl_raw, sign, guard_mode):
    o, h, l, c, idx = arrays
    entry = c[e_idx]; liq = entry * (1 + LIQ_MOVE)
    tps = build_tps(bl_raw, entry, sign)
    bs = {'position': 'SHORT', 'entry_price': entry, 'remaining_pct': 1.0, 'target_idx': 0,
          'fib_wave_start': entry, 'fib_extreme': entry, 'pulled_back': False, 'fib_stop': None,
          'bullish_obs': tps, 'reduced': False, 'fib_active': False, 'last_ob_top': None}
    params = {'leverage': LEVERAGE, 'fib_trigger_roe': FIB_TRIGGER, 'fib_ext_pct': FIB_EXT,
              'hard_floor_roe': HARD_FLOOR_ROE, 'guard_mode': guard_mode}
    frac = 1.0; reduced = False; R = 0.0
    n = len(c); end_idx = min(n, e_idx + 1 + HARD_CAP_BARS); xi = end_idx - 1
    for i in range(e_idx + 1, end_idx):
        o_, h_, l_, c_ = o[i], h[i], l[i], c[i]
        ticks = (o_, h_, l_, c_) if c_ < o_ else (o_, l_, h_, c_)
        for price in ticks:
            if price >= liq:
                fp = frac * FUND_8H * n_funding_8h(eh[e_idx], eh[i])
                R += frac * ((entry - liq) / entry) - frac * COST * 2 - fp
                return R, 'liq', i, fp
            sig = exec_check_exit(price, bs, params); act = sig['action']
            if act == 'REDUCE_SHORT' and not reduced:
                R += 0.5 * ((entry - price) / entry) - 0.5 * COST * 2; frac = 0.5; reduced = True; continue
            if act == 'CLOSE_SHORT':
                fp = frac * FUND_8H * n_funding_8h(eh[e_idx], eh[i])
                R += frac * ((entry - price) / entry) - frac * COST * 2 - fp
                return R, sig['reason'], i, fp
    fp = frac * FUND_8H * n_funding_8h(eh[e_idx], eh[xi])
    R += frac * ((entry - c[xi]) / entry) - frac * COST * 2 - fp
    return R, 'max_hold', xi, fp


def collect_entries(df):
    """B0기준 진입집합 1회수집. raw OB(top,bottom) 저장(TP부호 재구성용)."""
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
            # B0기준(+5bp)으로 진입유효성 판정 — 목표 1개라도 있어야 진입
            if build_tps(bl, price, +1):
                entries.append((t0, bl, ts))
        cur = t0 + 1
        dptr = np.searchsorted(down_idx, cur, side='left')
    return entries, (o, h, l, c, idx)


def run_fixed(fixed_set, lookup, arrays, eh, sign, guard_mode):
    rows = []
    for e_idx in fixed_set:
        bl_raw, ts = lookup[e_idx]
        R, reason, x_idx, fp = simulate_one(arrays, eh, e_idx, bl_raw, sign, guard_mode)
        rows.append({'진입시간': ts.strftime('%Y-%m-%d %H:%M:%S'), '연도': ts.year, 'R': R,
                     '청산사유': reason, '펀딩': fp, 'e_idx': e_idx})
    return rows


def run_free(entries, arrays, eh, sign, guard_mode):
    idx = arrays[4]; rows = []; last_exit = -1
    for (e_idx, bl_raw, ts) in entries:
        if e_idx <= last_exit:
            continue
        R, reason, x_idx, fp = simulate_one(arrays, eh, e_idx, bl_raw, sign, guard_mode)
        rows.append({'진입시간': ts.strftime('%Y-%m-%d %H:%M:%S'), '연도': ts.year, 'R': R,
                     '청산사유': reason, '펀딩': fp, 'e_idx': e_idx})
        last_exit = x_idx
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
            'gap_guard': int((t['청산사유'] == 'gap_guard').sum()),
            '피보승자': int((t['청산사유'] == 'Fibonacci').sum()),
            'OB_edge': int((t['청산사유'] == 'OB_edge').sum()),
            '누적R_pct': round(R.sum() * 100, 2), '평균R_pct': round(R.mean() * 100, 4),
            'PF': round(pf, 3), '파산': 'YES' if bankrupt else 'NO', '최저자본': round(mincap, 0),
            '펀딩총액_R_pct': round(float(t['펀딩'].sum()) * 100, 3)}


def main():
    print("[InfraA_V3_stg2] 빈구간 보호선(gap_guard) + TP바닥-5bp (엔진 Phase2 사각지대 메움, 고정진입)")
    open(os.path.join(HERE, ".run_start"), 'w').close()
    data = find_data(); print(f"[data] {data}")
    df = load_data(data)
    print(f"[load] {len(df):,}rows | {df.index.min().date()}~{df.index.max().date()}")
    eh = ((df.index - pd.Timestamp('1970-01-01')) / pd.Timedelta(hours=1)).values.astype('float64')
    entries, arrays = collect_entries(df)
    lookup = {e[0]: (e[1], e[2]) for e in entries}
    print(f"[entries] 진입후보 {len(entries)}건 (B0기준 1회수집)")

    # C0(B0: +5bp, guard off) 자유진입 1회 -> 고정집합
    c0_free = run_free(entries, arrays, eh, +1, 'off')
    fixed_set = [r['e_idx'] for r in c0_free]
    print(f"[C0 진입집합] {len(fixed_set)}건 (고정모드 공유)")

    summary = []; trades_dump = []
    for lab, sign, guard_mode in CELLS:
        rows = run_fixed(fixed_set, lookup, arrays, eh, sign, guard_mode)
        mAll = agg(rows, lab, 'ALL'); summary.append(mAll)
        for yrs, nm in [(TRAIN_YEARS, 'train'), (TEST_YEARS, 'test')]:
            summary.append(agg([r for r in rows if r['연도'] in yrs], lab, nm))
        print(f"  [{lab:9s}] 거래{mAll.get('거래수')} liq{mAll.get('강제청산')} hole{mAll.get('구멍')} "
              f"gap_guard{mAll.get('gap_guard')} 피보승자{mAll.get('피보승자')} "
              f"누적R{mAll.get('누적R_pct')}% PF{mAll.get('PF')} 파산{mAll.get('파산')}")
        if lab == 'B2_full':
            for r in rows:
                trades_dump.append({'설정': lab, '진입시간': r['진입시간'], '연도': r['연도'],
                                    'R_pct': round(r['R'] * 100, 4), '청산사유': r['청산사유'],
                                    '펀딩_pct': round(r['펀딩'] * 100, 4)})

    pd.DataFrame(summary).to_csv(os.path.join(HERE, "guard_summary.csv"), index=False, encoding='utf-8-sig')
    pd.DataFrame(trades_dump).to_csv(os.path.join(HERE, "guard_trades.csv"), index=False, encoding='utf-8-sig')
    print("[save] guard_summary.csv + guard_trades.csv (this subfolder) - all files")


if __name__ == "__main__":
    main()
