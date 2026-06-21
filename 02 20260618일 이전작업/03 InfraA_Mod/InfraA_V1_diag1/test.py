# -*- coding: utf-8 -*-
# [FILE] test.py  (InfraA_V1_diag1 - regime-exit diagnosis: 사고가 '하락장 이탈 후 미청산'과 관련있나)
# CODE LENGTH: approx 320 lines | INTERNAL VER: diag1_regimeexit_v1 | full output, no omission
#
# [PURPOSE / 목적] 의문: 진입은 하락장만 하지만 청산은 레짐 재확인이 없어, '하락장 끝났는데 숏 유지'가
#   사고(강제청산·구멍)의 원인일 수 있다. 이 가설을 36개월 데이터로 직접 확인(★진단, 새 전략 아님).
#   각 거래에 기록: 진입레짐(항상 downtrend), 청산시점레짐, 보유중 하락장비율, 보유봉수, 청산사유, 사고여부.
#   -> 사고 거래가 '청산시점에 하락장 벗어남' 비율이 정상거래보다 높은가? 가설 검증.
#
# [출력 핵심표]
#   1) 사고 vs 정상: 청산시점 하락장이탈 비율 / 보유중 하락장비율 평균 / 보유봉수 평균
#   2) "레짐이탈시 즉시청산"을 가정한 반사실(counterfactual) R: 보유중 첫 비하락장 봉에서 닫았다면 R이 어땠나
#      -> 사고가 줄고 알파(피보)가 살면 = 다음 단계 '레짐청산' 유망 신호.
#
# [SPEED] pivot/OB 1회 사전계산, 진입스캔 1회, 청산까지만 4틱+점프. 레짐배열 1회 벡터화.
# [LOOKAHEAD] 청산시점 레짐은 '그 시각의 라벨'만 봄(미래참조 아님). 반사실도 보유중 시각만 사용.
#
# [PATH] D:\ML\verify\InfraA_V1_diag1\ 실행, 데이터 상위, 결과 CSV -> 이 하위폴더.
# [DATA] ../Merged_Data_with_Regime_Features.csv (timestamp,open,high,low,close,feat_struct_8)
# [OUTPUT] diag_trades.csv(거래별 레짐추적) + diag_summary.csv(사고vs정상 + 반사실)
#
# [FUNCTIONS] (ob_mtf inline) + exec_check_exit(FLOOR15) + simulate_one_diag(레짐추적+반사실)
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


def find_data():
    for d in [PARENT, HERE, r"D:\ML\verify", r"D:\ML\Verify"]:
        p = os.path.join(d, "Merged_Data_with_Regime_Features.csv")
        if os.path.exists(p):
            return p
    raise FileNotFoundError("상위 D:\\ML\\verify 에 Merged_Data_with_Regime_Features.csv 필요")


def load_data(path):
    head = pd.read_csv(path, nrows=1)
    if REGIME_COL not in head.columns:
        raise KeyError(f"{REGIME_COL} 없음")
    cols = ['timestamp', 'open', 'high', 'low', 'close', REGIME_COL]
    df = pd.read_csv(path, usecols=cols, index_col='timestamp', parse_dates=True)
    if getattr(df.index, 'tz', None) is not None:
        df.index = df.index.tz_localize(None)
    return df.sort_index()


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


def simulate_one_diag(o, h, l, c, idx, is_down, e_idx, tp_targets):
    """실제 청산까지 진행하며 레짐추적 + 반사실(첫 비하락장 봉 종가청산) R 동시 계산."""
    entry = c[e_idx]; liq = entry * (1 + LIQ_MOVE)
    bs = {'position': 'SHORT', 'entry_price': entry, 'remaining_pct': 1.0, 'target_idx': 0,
          'fib_wave_start': entry, 'fib_extreme': entry, 'pulled_back': False, 'fib_stop': None,
          'bullish_obs': tp_targets}
    params = {'leverage': LEVERAGE, 'fib_trigger_roe': FIB_TRIGGER, 'fib_ext_pct': FIB_EXT,
              'hard_floor_roe': HARD_FLOOR_ROE}
    frac = 1.0; reduced = False; R = 0.0
    n = len(c); end_idx = min(n, e_idx + 1 + MAX_HOLD_BARS); xi = end_idx - 1
    # 반사실: 보유중 '첫 비하락장 봉'의 종가에서 닫았다면 R_cf
    cf_done = False; R_cf = None; first_nondown_i = None
    hold_bars = 0; down_bars = 0
    for i in range(e_idx + 1, end_idx):
        hold_bars += 1
        if is_down[i]:
            down_bars += 1
        elif first_nondown_i is None:
            first_nondown_i = i
        # 반사실 R: 첫 비하락장 봉 종가에서 청산했다고 가정(1회만 기록, 실제는 계속 진행)
        if (first_nondown_i is not None) and (not cf_done):
            pcf = c[first_nondown_i]
            R_cf = frac * ((entry - pcf) / entry) - frac * COST * 2
            cf_done = True
        o_, h_, l_, c_ = o[i], h[i], l[i], c[i]
        ticks = (o_, h_, l_, c_) if c_ < o_ else (o_, l_, h_, c_)
        for price in ticks:
            if price >= liq:
                R += frac * ((entry - liq) / entry) - frac * COST * 2
                return _pack(R, 'liq', idx[i], is_down[i], hold_bars, down_bars, R_cf, first_nondown_i is not None)
            sig = exec_check_exit(price, bs, params); act = sig['action']
            if act == 'REDUCE_SHORT' and not reduced:
                R += 0.5 * ((entry - price) / entry) - 0.5 * COST * 2; frac = 0.5; reduced = True; continue
            if act == 'CLOSE_SHORT':
                dur = (idx[i] - idx[e_idx]).total_seconds() / 86400
                R += frac * ((entry - price) / entry) - frac * COST * 2 - frac * FUNDING_DAILY * dur
                return _pack(R, sig['reason'], idx[i], is_down[i], hold_bars, down_bars, R_cf, first_nondown_i is not None)
    R += frac * ((entry - c[xi]) / entry) - frac * COST * 2
    return _pack(R, 'max_hold', idx[xi], is_down[xi], hold_bars, down_bars, R_cf, first_nondown_i is not None)


def _pack(R, reason, xt, exit_down, hold_bars, down_bars, R_cf, left_down):
    acc = 1 if reason in ('liq', 'hole_hardfloor') else 0
    return dict(R=round(R, 6), 청산사유=reason, 청산시각=xt.strftime('%Y-%m-%d %H:%M:%S'),
                사고=acc, 청산시점_하락장=int(bool(exit_down)),
                청산시점_하락장이탈=int(not bool(exit_down)),
                보유봉수=hold_bars, 보유중_하락장비율=round(down_bars / max(hold_bars, 1), 3),
                보유중_하락장이탈여부=int(bool(left_down)),
                반사실R_레짐이탈청산=(round(R_cf, 6) if R_cf is not None else None))


def main():
    print("[InfraA_V1_diag1] 진단: 사고가 '하락장 이탈 후 미청산'과 관련있나 + 레짐청산 반사실")
    open(os.path.join(HERE, ".run_start"), 'w').close()
    data = find_data(); print(f"[data] {data}")
    df = load_data(data)
    o = df['open'].values; h = df['high'].values; l = df['low'].values; c = df['close'].values
    idx = df.index
    is_down = (df[REGIME_COL].astype(str).values == 'downtrend')
    down_idx = np.where(is_down)[0]
    print(f"[load] {len(df):,}rows | {df.index.min().date()}~{df.index.max().date()} | 하락장봉 {len(down_idx):,}")
    hpc, _, hpt, hpb, _, _ = precompute_tf_pivots(resample_tf(df, SL_TF), W_TF, SL_TF)
    _, lpc, _, _, lpt, lpb = precompute_tf_pivots(resample_tf(df, TP_TF), W_TF, TP_TF)

    rows = []; n = len(c); cur = 0
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
            tps = [{'top': t, 'bottom': b, 'mean': b * (1 + D_FIX / 1e4)} for (t, b) in bl if b * (1 + D_FIX / 1e4) < price]
            if tps:
                d = simulate_one_diag(o, h, l, c, idx, is_down, t0, tps)
                d['진입시간'] = ts.strftime('%Y-%m-%d %H:%M:%S'); d['연도'] = ts.year
                rows.append(d)
                x_idx = int(idx.searchsorted(pd.to_datetime(d['청산시각'])))
                cur = max(x_idx + 1, t0 + 1)
            else:
                cur = t0 + 1
        else:
            cur = t0 + 1
        dptr = np.searchsorted(down_idx, cur, side='left')

    td = pd.DataFrame(rows)
    td.to_csv(os.path.join(HERE, "diag_trades.csv"), index=False, encoding='utf-8-sig')
    if len(td) == 0:
        print("[중단] 거래 0건"); pd.DataFrame().to_csv(os.path.join(HERE, "diag_summary.csv"), index=False); return

    # 요약: 사고 vs 정상
    summ = []
    for label, sub in [('사고', td[td['사고'] == 1]), ('정상', td[td['사고'] == 0]), ('전체', td)]:
        if len(sub) == 0:
            continue
        summ.append(dict(구분=label, 거래수=len(sub),
                         청산시점_하락장이탈_비율pct=round(sub['청산시점_하락장이탈'].mean() * 100, 1),
                         보유중_하락장이탈_비율pct=round(sub['보유중_하락장이탈여부'].mean() * 100, 1),
                         보유중_하락장비율_평균=round(sub['보유중_하락장비율'].mean(), 3),
                         보유봉수_중앙=int(sub['보유봉수'].median()),
                         평균R_pct=round(sub['R'].mean() * 100, 4)))
    # 반사실: 레짐이탈 즉시청산 가정 시 전체 평균R
    cf = td.copy()
    cf['R_eff'] = np.where(cf['반사실R_레짐이탈청산'].notna(), cf['반사실R_레짐이탈청산'], cf['R'])
    base_meanR = td['R'].mean() * 100
    cf_meanR = cf['R_eff'].mean() * 100
    cf_acc = td['사고'].sum()
    # 반사실에서 '레짐이탈로 먼저 닫힌' 거래 중 원래 사고였던 것
    left = td['보유중_하락장이탈여부'] == 1
    acc_in_left = int(td[left]['사고'].sum())
    summ.append(dict(구분='[반사실]레짐이탈즉시청산', 거래수=len(td),
                     청산시점_하락장이탈_비율pct=None, 보유중_하락장이탈_비율pct=round(left.mean() * 100, 1),
                     보유중_하락장비율_평균=None, 보유봉수_중앙=None,
                     평균R_pct=round(cf_meanR, 4)))
    s = pd.DataFrame(summ)
    s.to_csv(os.path.join(HERE, "diag_summary.csv"), index=False, encoding='utf-8-sig')

    print(f"\n[결과 요약]")
    print(s.to_string(index=False))
    print(f"\n  기준 평균R {base_meanR:.4f}% -> 반사실(레짐이탈청산) 평균R {cf_meanR:.4f}%")
    print(f"  레짐이탈 경험거래 {int(left.sum())}건 중 사고 {acc_in_left}/{int(td['사고'].sum())}")
    print("\n[save] diag_trades.csv + diag_summary.csv (this subfolder) - all files")


if __name__ == "__main__":
    main()
