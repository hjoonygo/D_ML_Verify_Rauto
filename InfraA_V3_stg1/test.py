# -*- coding: utf-8 -*-
# [FILE] test.py  (InfraA_V3_stg1 - REALISM: discrete 8h funding vs continuous, engine UNCHANGED)
# CODE LENGTH: approx 300 lines | INTERNAL VER: real8h_v1 | full output, no omission
#
# [PURPOSE / 목적] 사장님 목표 "현실적 거래환경 먼저". 엔진/진입은 한 줄도 안 건드린다(=현실화 순효과만 측정).
#   바꾸는 단 하나: 펀딩비를 '연속근사(funding*보유일수)'에서 '실제처럼 8시간마다(00/08/16 UTC) 이산 부과'로.
#   질문: 지난 보고서의 본전(+0.25%)이, 펀딩을 8시간 이산으로 현실화하면 어떻게 변하나(적자전환?).
#   ★stg2 교훈(거래폭증 오염)대로 '고정진입(C0 집합)'으로만 깨끗 비교. ㉠(바닥-5bp)·빈구간보호선은 stg2.
#
# [GRID 3칸 — 같은 C0 진입집합, 청산만 펀딩설정 달리]
#   R0_old_cont  : 0.0001/일 '연속'      (지난 채팅 pre-realism 재현용 기준선)
#   R1_real_cont : 0.0003/일 '연속'      (stg3/4가 쓴 현실펀딩 연속근사 — 참조)
#   R2_real_8h   : 0.0001/8h '이산'(=0.03%/일) (★이번 현실화. 실제 부과방식)
#   R1 vs R2 = '연속근사 vs 8시간이산' 순수차이 / R0 vs R2 = 현실화 총효과
#   각 칸: 거래수/강제청산/구멍/피보승자/누적R/평균R/PF/파산/최저자본 + 학습(23~24)/검증(25~26) 분리 + 펀딩총액.
#
# [펀딩 회계 규약 — 한 변수만 바꿔 깨끗 비교]
#   세 칸 모두 '청산 시 1회, 생존프랙션(frac)×보유'에 부과(원본 stg 규약 유지).
#   연속: frac*rate_day*보유일수.   8h이산: frac*rate_8h*(진입~청산 사이 8h경계 통과횟수).
#   8h경계 = epoch(1970-01-01 00:00 UTC)부터 8시간 배수 시각(=매일 00/08/16 UTC). 데이터는 tz제거된 UTC로 취급.
#
# [SPEED 속도가속] pivot/OB 1회 사전계산(벡터화) -> C0 진입집합 1회 확보 -> 칸별 청산만 재시뮬.
#   진입후보만, 청산까지만 4틱 진행 후 빈구간 점프. idx의 epoch-hours 1회 사전계산(이산펀딩 가속).
# [LOOKAHEAD GUARD] OB는 pivot 확정시각 이후만. feat_struct_8은 생성단계서 인과확보(별도 실측). 청산은 진입후 봉만.
# [PATH] D:\ML\verify\InfraA_V3_stg1\ 실행, 데이터 상위 D:\ML\verify\ , 결과 CSV -> 이 하위폴더.
# [DATA] ../Merged_Data_with_Regime_Features.csv (timestamp,open,high,low,close,feat_struct_8)
# [OUTPUT] real_summary.csv(3칸×모드) + real_trades.csv(R2 현실 8h 고정집합 거래별)
#
# [FUNCTIONS In/Out]
#   find_data()->path ; load_data(path)->df
#   resample_tf/precompute_tf_pivots/nearest_above/levels_below_5m  [ob_mtf inline, verified]
#   exec_check_exit(price,bs,params)->action dict   (stg3 원본 그대로, 무수정)
#   n_funding_8h(entry_eh,exit_eh)->int             (8h경계 통과횟수)
#   simulate_one(arrays,eh,e_idx,tps,fmode,frate)->(R,reason,exit_idx,funding_paid)
#   collect_entries(df)->[(e_idx,tps,ts)]           (진입후보 1회수집, 엔진과 동일규칙)
#   run_fixed(fixed_set,lookup,arrays,eh,fmode,frate)->rows
#   agg(rows,label,mode)->dict
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
HARD_CAP_BARS = 60 * 24 * 90
TRAIN_YEARS = [2023, 2024]; TEST_YEARS = [2025, 2026]
ACC_REASONS = ('liq', 'hole_hardfloor')
# 펀딩 설정 3칸: (라벨, 모드 'cont'|'disc8h', 비율)  cont=일률(/일), disc8h=8h율
FUND_CELLS = [('R0_old_cont', 'cont', 0.0001),
              ('R1_real_cont', 'cont', 0.0003),
              ('R2_real_8h', 'disc8h', 0.0001)]


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


# ----- ob_mtf inline (verified, stg3 동일) --------------------------------------
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
    """stg3 원본 그대로 — 엔진 무수정(현실화는 펀딩 회계만)."""
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


def n_funding_8h(entry_eh, exit_eh):
    """진입~청산 사이 8시간 펀딩경계(epoch부터 8h배수=매일 00/08/16 UTC) 통과 횟수.
    경계에 '걸쳐 있으면 부과' = floor(exit/8) - floor(entry/8)."""
    return int(np.floor(exit_eh / 8.0) - np.floor(entry_eh / 8.0))


def simulate_one(arrays, eh, e_idx, tp_targets, fmode, frate):
    """청산엔진 원본(무수정) + 펀딩회계만 모드별. 반환에 funding_paid 추가."""
    o, h, l, c, idx = arrays
    entry = c[e_idx]; liq = entry * (1 + LIQ_MOVE)
    bs = {'position': 'SHORT', 'entry_price': entry, 'remaining_pct': 1.0, 'target_idx': 0,
          'fib_wave_start': entry, 'fib_extreme': entry, 'pulled_back': False, 'fib_stop': None,
          'bullish_obs': tp_targets}
    params = {'leverage': LEVERAGE, 'fib_trigger_roe': FIB_TRIGGER, 'fib_ext_pct': FIB_EXT,
              'hard_floor_roe': HARD_FLOOR_ROE}
    frac = 1.0; reduced = False; R = 0.0
    n = len(c); end_idx = min(n, e_idx + 1 + HARD_CAP_BARS); xi = end_idx - 1

    def funding_at(exit_i, frac_now):
        if fmode == 'cont':
            dur = (idx[exit_i] - idx[e_idx]).total_seconds() / 86400.0
            return frac_now * frate * dur
        else:  # disc8h
            nf = n_funding_8h(eh[e_idx], eh[exit_i])
            return frac_now * frate * nf

    for i in range(e_idx + 1, end_idx):
        o_, h_, l_, c_ = o[i], h[i], l[i], c[i]
        ticks = (o_, h_, l_, c_) if c_ < o_ else (o_, l_, h_, c_)
        for price in ticks:
            if price >= liq:
                R += frac * ((entry - liq) / entry) - frac * COST * 2
                fpaid = funding_at(i, frac)
                return R - fpaid, 'liq', i, fpaid
            sig = exec_check_exit(price, bs, params); act = sig['action']
            if act == 'REDUCE_SHORT' and not reduced:
                R += 0.5 * ((entry - price) / entry) - 0.5 * COST * 2; frac = 0.5; reduced = True; continue
            if act == 'CLOSE_SHORT':
                fpaid = funding_at(i, frac)
                R += frac * ((entry - price) / entry) - frac * COST * 2 - fpaid
                return R, sig['reason'], i, fpaid
    # 90일 상한 도달 -> 종가청산
    fpaid = funding_at(xi, frac)
    R += frac * ((entry - c[xi]) / entry) - frac * COST * 2 - fpaid
    return R, 'max_hold', xi, fpaid


def collect_entries(df):
    """진입후보 1회수집 — 엔진과 100% 동일 규칙(stg3). ㉠/보호선 미적용(stg2부터)."""
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


def run_fixed(fixed_set, lookup, arrays, eh, fmode, frate):
    rows = []
    for e_idx in fixed_set:
        tps, ts = lookup[e_idx]
        R, reason, x_idx, fpaid = simulate_one(arrays, eh, e_idx, tps, fmode, frate)
        rows.append({'진입시간': ts.strftime('%Y-%m-%d %H:%M:%S'), '연도': ts.year, 'R': R,
                     '청산사유': reason, '펀딩': fpaid, 'e_idx': e_idx})
    return rows


def run_free(entries, arrays, eh, fmode, frate):
    """C0 진입집합 확보용(자유진입 1회). 이후 고정모드 공유."""
    idx = arrays[4]; rows = []; last_exit = -1
    for (e_idx, tps, ts) in entries:
        if e_idx <= last_exit:
            continue
        R, reason, x_idx, fpaid = simulate_one(arrays, eh, e_idx, tps, fmode, frate)
        rows.append({'진입시간': ts.strftime('%Y-%m-%d %H:%M:%S'), '연도': ts.year, 'R': R,
                     '청산사유': reason, '펀딩': fpaid, 'e_idx': e_idx})
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
            '피보승자': int((t['청산사유'] == 'Fibonacci').sum()),
            '누적R_pct': round(R.sum() * 100, 2), '평균R_pct': round(R.mean() * 100, 4),
            'PF': round(pf, 3), '파산': 'YES' if bankrupt else 'NO', '최저자본': round(mincap, 0),
            '펀딩총액_R_pct': round(float(t['펀딩'].sum()) * 100, 3)}


def main():
    print("[InfraA_V3_stg1] 현실화: 펀딩 8시간 이산 vs 연속 (엔진 무수정, 고정진입 깨끗비교)")
    open(os.path.join(HERE, ".run_start"), 'w').close()
    data = find_data(); print(f"[data] {data}")
    df = load_data(data)
    print(f"[load] {len(df):,}rows | {df.index.min().date()}~{df.index.max().date()}")
    # idx의 epoch-hours 1회 사전계산(이산펀딩 가속)
    eh = ((df.index - pd.Timestamp('1970-01-01')) / pd.Timedelta(hours=1)).values.astype('float64')  # epoch-hours(해상도무관)
    entries, arrays = collect_entries(df)
    print(f"[entries] 진입후보 {len(entries)}건 (엔진과 동일규칙, 1회수집)")

    # C0(R0 기준) 진입집합 -> 고정모드 공유 (거래폭증 배제)
    c0_free = run_free(entries, arrays, eh, 'cont', 0.0001)
    fixed_set = [r['e_idx'] for r in c0_free]
    lookup = {e[0]: (e[1], e[2]) for e in entries}
    print(f"[C0 진입집합] {len(fixed_set)}건 (고정모드 공유)")

    summary = []; trades_dump = []
    for lab, fmode, frate in FUND_CELLS:
        rows = run_fixed(fixed_set, lookup, arrays, eh, fmode, frate)
        mAll = agg(rows, lab, 'ALL')
        summary.append(mAll)
        for yrs, nm in [(TRAIN_YEARS, 'train'), (TEST_YEARS, 'test')]:
            summary.append(agg([r for r in rows if r['연도'] in yrs], lab, nm))
        print(f"  [{lab:13s}] 거래{mAll.get('거래수')} 강제청산{mAll.get('강제청산')} "
              f"피보승자{mAll.get('피보승자')} 누적R{mAll.get('누적R_pct')}% PF{mAll.get('PF')} "
              f"파산{mAll.get('파산')} 펀딩총액{mAll.get('펀딩총액_R_pct')}%")
        if lab == 'R2_real_8h':
            for r in rows:
                trades_dump.append({'설정': lab, '진입시간': r['진입시간'], '연도': r['연도'],
                                    'R_pct': round(r['R'] * 100, 4), '청산사유': r['청산사유'],
                                    '펀딩_pct': round(r['펀딩'] * 100, 4)})

    pd.DataFrame(summary).to_csv(os.path.join(HERE, "real_summary.csv"), index=False, encoding='utf-8-sig')
    pd.DataFrame(trades_dump).to_csv(os.path.join(HERE, "real_trades.csv"), index=False, encoding='utf-8-sig')
    print("[save] real_summary.csv + real_trades.csv (this subfolder) - all files")


if __name__ == "__main__":
    main()
