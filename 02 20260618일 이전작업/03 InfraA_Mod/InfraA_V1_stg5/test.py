# -*- coding: utf-8 -*-
# [FILE] test.py  (InfraA_V1_stg5 - stop-tighten in real exit engine: 6 stop% x 2 modes = 12 cells)
# CODE LENGTH: approx 400 lines | INTERNAL VER: stg5_stoptighten_v1 | full output, no omission
#
# [PURPOSE / 목적] stg4 ML이 가리킨 '손절당김(-2~3%)'을 실제 청산엔진에 박아 36개월 재백테스트.
#   지난건 사고손실 숫자만 자른 근사치 -> 이번은 진짜 손절선이라, 손절선이 빡빡하면 정상거래·피보도 잘림.
#   = +59%가 진짜인지(피보 희생까지 포함) 가른다.
#   grid: stop_pct {0.5,1,1.5,2,2.5,3%} x mode {A:익절전까지만, B:전구간(피보까지)} = 12칸.
#
# [MODE 정의 — 코드사실 기반]
#   사고(구멍·강제청산)는 전부 '1차 익절 전'(보호스탑 없을 때) 발생, 알파(피보)는 '익절 후' 발생.
#   A: 손절당김을 reduced(1차익절)=False 일 때만 적용 -> 사고만 차단, 피보 보호.
#   B: 손절당김을 전 구간 적용 -> 사고차단 동일 + 피보도 -X% 닿으면 컷(알파 희생 측정).
#   손절당김 = 진입가 대비 ROE <= -stop_pct 이면 즉시 CLOSE (1분봉 4틱마다 검사).
#   기존 FLOOR15 로직(다중OB계단/피보0.65/구멍하드플로어15%)은 그대로, 그 '위에' 손절당김을 우선검사.
#
# [측정] 각 칸: PF, 승률, 누적R, 사고건수, 피보승자 생존수(피보로 청산된 +R 거래수), 강제청산/구멍 잔존수.
#   + 학습(2023~24)/검증(2025~26) 분리 PF·누적R (과적합 점검).
#   ★거래시뮬(측정 아님). 합격선 PF>1·파산NO·자본>=시작50%.
#
# [SPEED] pivot/OB 전구간 1회 사전계산, 진입스캔 1회 -> 12칸은 손절선만 바꿔 재평가(진입동일).
#   하락장만+청산까지만 4틱+빈구간 점프. 12칸 동일 진입목록 재사용으로 스캔 6배 절약.
#
# [PATH] D:\ML\verify\InfraA_V1_stg5\ 실행, 데이터 상위, 결과 CSV -> 이 하위폴더.
# [DATA] ../Merged_Data_with_Regime_Features.csv (timestamp,open,high,low,close,feat_struct_8) 36개월
# [OUTPUT] stop_summary.csv(12칸 성과) + stop_split.csv(학습/검증) + stop_trades_best.csv(최선칸 거래)
#
# [FUNCTIONS In/Out]
#   (ob_mtf inline) nearest_above/levels_below_5m
#   collect_entries(df) -> 진입목록[(e_idx, tp_targets)]  (12칸 공용, 1회만)
#   exec_check_exit(price, bs, params) -> action  (FLOOR15 + 손절당김 우선검사)
#   simulate_one(...stop_pct, mode) -> (R, reason, et, xt, reduced_done)
#   run_cell(entries, stop_pct, mode) -> trades_df
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
STOP_GRID = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]      # 손절당김 % (ROE 기준, 레버 포함 실손익률로 환산)
MODES = ['A_preTP', 'B_full']
START_CAP = 10000.0
TRAIN_YEARS = [2023, 2024]; TEST_YEARS = [2025, 2026]


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
    """FLOOR15 SHORT + 손절당김 우선검사. 손절당김: ROE<=-stop_pct면 컷.
       mode A: reduced=False(1차익절 전)일 때만. mode B: 항상."""
    entry = bs['entry_price']; lev = params['leverage']
    stop_pct = params['stop_pct']; mode = params['mode']
    # --- 손절당김 우선검사 ---
    apply_stop = (mode == 'B_full') or (not bs['reduced'])
    if apply_stop and stop_pct is not None:
        roe = ((entry - price) / entry) * lev * 100      # SHORT ROE%
        if roe <= -stop_pct:
            return {"action": "CLOSE_SHORT", "reason": f"stoptighten(-{stop_pct}%)"}
    # --- 이하 FLOOR15 원본 ---
    target_idx = bs['target_idx']
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


def simulate_one(o, h, l, c, idx, e_idx, tp_targets, stop_pct, mode):
    entry = c[e_idx]; liq = entry * (1 + LIQ_MOVE)
    bs = {'position': 'SHORT', 'entry_price': entry, 'remaining_pct': 1.0, 'target_idx': 0,
          'fib_wave_start': entry, 'fib_extreme': entry, 'pulled_back': False, 'fib_stop': None,
          'bullish_obs': tp_targets, 'reduced': False}
    params = {'leverage': LEVERAGE, 'fib_trigger_roe': FIB_TRIGGER, 'fib_ext_pct': FIB_EXT,
              'hard_floor_roe': HARD_FLOOR_ROE, 'stop_pct': stop_pct, 'mode': mode}
    frac = 1.0; R = 0.0
    n = len(c); end_idx = min(n, e_idx + 1 + MAX_HOLD_BARS); xi = end_idx - 1
    for i in range(e_idx + 1, end_idx):
        o_, h_, l_, c_ = o[i], h[i], l[i], c[i]
        ticks = (o_, h_, l_, c_) if c_ < o_ else (o_, l_, h_, c_)
        for price in ticks:
            if price >= liq:
                R += frac * ((entry - liq) / entry) - frac * COST * 2
                return R, 'liq', idx[i]
            sig = exec_check_exit(price, bs, params); act = sig['action']
            if act == 'REDUCE_SHORT' and not bs['reduced']:
                R += 0.5 * ((entry - price) / entry) - 0.5 * COST * 2
                frac = 0.5; bs['reduced'] = True; continue
            if act == 'CLOSE_SHORT':
                dur = (idx[i] - idx[e_idx]).total_seconds() / 86400
                R += frac * ((entry - price) / entry) - frac * COST * 2 - frac * FUNDING_DAILY * dur
                return R, sig['reason'], idx[i]
    R += frac * ((entry - c[xi]) / entry) - frac * COST * 2
    return R, 'max_hold', idx[xi]


def collect_entries(df):
    """12칸 공용 진입목록 1회 생성: [(e_idx, tp_targets, ts)]. 청산은 칸마다 달라 진입만 고정."""
    o = df['open'].values; h = df['high'].values; l = df['low'].values; c = df['close'].values
    idx = df.index
    down_idx = np.where(df[REGIME_COL].astype(str).values == 'downtrend')[0]
    hpc, _, hpt, hpb, _, _ = precompute_tf_pivots(resample_tf(df, SL_TF), W_TF, SL_TF)
    _, lpc, _, _, lpt, lpb = precompute_tf_pivots(resample_tf(df, TP_TF), W_TF, TP_TF)
    entries = []; n = len(c); cur = 0
    dptr = np.searchsorted(down_idx, cur, side='left')
    # 진입목록은 '청산 무관'이라 겹침 방지를 위해 최소간격(이전진입+1봉) 아닌, 실제론 청산후 재진입.
    # 칸마다 청산시점이 달라지므로, 진입겹침 방지는 run_cell에서 청산시각 기준으로 처리.
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
                entries.append((t0, tps, ts))
        cur = t0 + 1
        dptr = np.searchsorted(down_idx, cur, side='left')
    return entries, (o, h, l, c, idx)


def run_cell(entries, arrays, stop_pct, mode):
    """한 칸(손절폭,모드): 진입목록 순회하되 청산시각 이후로만 재진입(겹침방지)."""
    o, h, l, c, idx = arrays
    rows = []; last_exit_idx = -1
    for (e_idx, tps, ts) in entries:
        if e_idx <= last_exit_idx:
            continue
        R, reason, xt = simulate_one(o, h, l, c, idx, e_idx, tps, stop_pct, mode)
        x_idx = int(idx.searchsorted(pd.to_datetime(xt.strftime('%Y-%m-%d %H:%M:%S'))))
        last_exit_idx = max(x_idx, e_idx)
        acc = 1 if reason in ('liq', 'hole_hardfloor') else 0
        rows.append(dict(진입시간=ts.strftime('%Y-%m-%d %H:%M:%S'), 연도=ts.year,
                         R=round(R, 6), 청산사유=reason, 사고=acc))
    return pd.DataFrame(rows)


def metrics(td):
    if len(td) == 0:
        return dict(진입=0, PF=0, 승률=0, 누적R=0, 사고=0, 피보승자=0, 강제청산=0, 구멍=0)
    R = td['R'].values
    pf = R[R > 0].sum() / abs(R[R < 0].sum()) if (R < 0).any() else 9.99
    fibwin = int(((td['청산사유'] == 'Fibonacci') & (R > 0)).sum())
    return dict(진입=len(td), PF=round(pf, 3), 승률=round((R > 0).mean() * 100, 1),
                누적R=round(R.sum() * 100, 1), 사고=int(td['사고'].sum()),
                피보승자=fibwin, 강제청산=int((td['청산사유'] == 'liq').sum()),
                구멍=int((td['청산사유'] == 'hole_hardfloor').sum()))


def main():
    print("[InfraA_V1_stg5] 손절당김 6칸 x 모드(A익절전/B전구간) 2 = 12칸, 36mo + 학습/검증분리")
    open(os.path.join(HERE, ".run_start"), 'w').close()
    data = find_data(); print(f"[data] {data}")
    df = load_data(data)
    print(f"[load] {len(df):,}rows | {df.index.min().date()}~{df.index.max().date()}")
    print("[진입목록 1회 생성...]")
    entries, arrays = collect_entries(df)
    print(f"  진입후보 {len(entries)}건 (12칸 공용)\n")

    summary = []; split = []; best = None; best_key = (-9, None)
    for mode in MODES:
        for sp in STOP_GRID:
            td = run_cell(entries, arrays, sp, mode)
            m = metrics(td)
            cap_mult = 1 + m['누적R'] / 100.0
            row = dict(모드=mode, 손절폭pct=sp, **m,
                       최종자본배수=round(cap_mult, 3),
                       파산='YES' if cap_mult <= 0.5 else 'NO')
            summary.append(row)
            # 학습/검증
            for split_name, yrs in [('학습2023_24', TRAIN_YEARS), ('검증2025_26', TEST_YEARS)]:
                sub = td[td['연도'].isin(yrs)]
                ms = metrics(sub)
                split.append(dict(모드=mode, 손절폭pct=sp, 구간=split_name,
                                  진입=ms['진입'], PF=ms['PF'], 누적R=ms['누적R'], 사고=ms['사고']))
            print(f"  [{mode} {sp}%] 진입{m['진입']} PF{m['PF']} 누적R{m['누적R']}% 사고{m['사고']} 피보승자{m['피보승자']} 파산{row['파산']}")
            # best = 누적R 최대 & 파산NO
            if row['파산'] == 'NO' and m['누적R'] > best_key[0]:
                best_key = (m['누적R'], (mode, sp)); best = td.copy()

    pd.DataFrame(summary).to_csv(os.path.join(HERE, "stop_summary.csv"), index=False, encoding='utf-8-sig')
    pd.DataFrame(split).to_csv(os.path.join(HERE, "stop_split.csv"), index=False, encoding='utf-8-sig')
    if best is not None:
        best.to_csv(os.path.join(HERE, "stop_trades_best.csv"), index=False, encoding='utf-8-sig')
        print(f"\n[best] {best_key[1]} 누적R {best_key[0]}%")
    else:
        pd.DataFrame().to_csv(os.path.join(HERE, "stop_trades_best.csv"), index=False, encoding='utf-8-sig')
    print("\n[save] stop_summary.csv + stop_split.csv + stop_trades_best.csv (this subfolder) - all files")


if __name__ == "__main__":
    main()
