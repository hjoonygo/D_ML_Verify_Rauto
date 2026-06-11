# -*- coding: utf-8 -*-
# [FILE] test.py  (InfraA_V2_stg1 - post-reduce SL design compare: C0..C4, real engine, 36mo, train/test split)
# CODE LENGTH: approx 360 lines | INTERNAL VER: slpost_v1 | full output, no omission
#
# [PURPOSE / 목적]
#   진단(diag1)으로 확정: 강제청산(liq) 9건은 '1차 50%익절(REDUCE) 뒤 남은 절반'이 Phase2에서
#   보호스탑이 사라진 채(현 엔진 결함) 장기 표류하다 +20% 강제청산된 것. 총 -89%R = 최대 단일 손실원.
#   -> 1차익절 후 '남은 절반'의 손절선(SL design)을 여러 구조형으로 바꿔, 실제 청산엔진에 박아 비교.
#   ★고정%SL은 stg5에서 5배레버와 상극으로 기각됨. 여기 후보는 전부 '구조형/변동성형'(가격%아님).
#   ★사후보정 아님(stg4/5 교훈): 실엔진에 실제로 박아 실시간 청산.
#
# [SL DESIGNS — Phase2(=익절후 남은절반)에만 적용. 정상거래/진입로직은 안건드림]
#   C0_none      : (기준) 현행 엔진 그대로. Phase2는 +15%ROE(fib_trigger) 못찍으면 스탑없음 -> 표류.
#   C1_obtop     : Phase2에서도 기존 fib_stop(=직전OB윗선)을 상시 체크. 결함의 직접수정(유력가설).
#   C2_breakeven : 익절했으면 남은절반은 최소 본전사수. price>=entry 면 청산.
#   C3_fibearly  : 피보 트레일을 Phase2 진입즉시 발동(fib_trigger_roe=0). FIB_EXT 0.65 그대로.
#   C4_resob     : 진입시 위쪽 저항OB(SL기준)의 윗선을 스탑으로. 가장 느슨한 구조선.
#
# [MEASURE] 설계별: 거래수/강제청산수/구멍수/피보승자수/누적R/평균R/PF/파산/최저자본
#   + 학습(2023~24)/검증(2025~26) 분리. ★합격선 PF>1·파산NO·자본>=시작50%·검증 양전유지.
#   ★핵심비교: 강제청산 줄이면서 '피보승자(추세이익)·검증기간 흑자'를 안 죽이는 설계가 있나.
#
# [SPEED / 속도가속] (1)5/60분 pivot 전구간 1회 사전계산(벡터화 sliding_window)
#   (2)진입후보+필요레벨 1회 수집(collect_entries) -> 5설계는 그 위에서 청산만 재시뮬
#   (3)하락장 진입후보만, 청산까지만 4틱 진행 후 빈구간 점프 (4)OB스캔 윈도우 1회 생성.
#
# [LOOKAHEAD GUARD] OB는 pivot 확정시각(center+swing) 이후만 사용. feat_struct_8은 생성단계서
#   shift(swing_len)로 인과성 확보(별도 실측 완료: 누수 0%). 청산은 진입이후 봉만 사용.
#
# [PATH] D:\ML\verify\InfraA_V2_stg1\ 에서 실행, 데이터는 상위 D:\ML\verify\ , 결과 CSV -> 이 하위폴더.
# [DATA] ../Merged_Data_with_Regime_Features.csv (timestamp,open,high,low,close,feat_struct_8)
# [OUTPUT] sl_summary.csv(5설계 전체) + sl_split.csv(학습/검증) + sl_trades_best.csv(최선설계 거래) (전량파일)
#
# [FUNCTIONS In/Out]
#   find_data()->path ; load_data(path)->df
#   resample_tf/precompute_tf_pivots/nearest_above/levels_below_5m  [ob_mtf inline, verified]
#   exec_check_exit(price,bs,params)->action dict  (FLOOR15 + Phase2 SL design switch)
#   simulate_one(arrays,e_idx,tps,res_ob_top,design)->(R,reason,exit_idx)
#   collect_entries(df)->[(e_idx,tps,res_ob_top,ts)]  (진입후보 1회수집)
#   run_design(entries,arrays,design)->(trades_list)   (한 설계 전구간)
#   metrics(trades)->dict  (PF/파산/최저자본/사고수 등)
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
NOMINAL = 50000.0; START_CAP = 10000.0; MIN_CAP = 100.0   # FLOOR15 money model (파산/최저자본 판정용)
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
    """FLOOR15 엔진 + Phase2(익절후) SL design 스위치. C0는 원본과 100% 동일."""
    entry = bs['entry_price']; lev = params['leverage']; target_idx = bs['target_idx']
    design = params['sl_design']
    # 구멍 하드플로어: OB 한번도 못찍어 보호스탑 없을 때만(=pre-reduce). 설계 무관.
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
        # ===== Phase2 (모든 OB 소진 = 익절 이미 완료된 상태). 여기서만 SL design 작동 =====
        roe = ((entry - price) / entry) * lev * 100
        max_roe = ((entry - bs['fib_extreme']) / entry) * lev * 100
        if price < bs['fib_extreme']:
            if bs['pulled_back']:
                bs['fib_wave_start'] = bs['fib_extreme']; bs['pulled_back'] = False
            bs['fib_extreme'] = price
        elif price > bs['fib_extreme']:
            bs['pulled_back'] = True
        # --- SL design 스탑 (구조형, 가격%아님) : fib_trigger 로직보다 먼저 검사 ---
        stop_price = None
        if design == 'C1_obtop':
            stop_price = bs['fib_stop']                     # 직전 OB윗선(현 엔진이 무시하던 그 스탑)
        elif design == 'C2_breakeven':
            stop_price = entry                              # 본전 사수
        elif design == 'C4_resob':
            stop_price = bs['res_ob_top']                   # 진입시 위쪽 저항OB 윗선
        if design != 'C0_none' and stop_price is not None and price >= stop_price:
            return {"action": "CLOSE_SHORT", "reason": "sl_design"}
        # --- 피보 트레일 : C3는 진입즉시 발동(trigger=0), 그 외는 기존 +15% ---
        trig = 0.0 if design == 'C3_fibearly' else params['fib_trigger_roe']
        if roe >= trig or max_roe >= trig:
            downswing = bs['fib_wave_start'] - bs['fib_extreme']
            fib_lock = bs['fib_wave_start'] - downswing * params['fib_ext_pct']
            prev = bs.get('fib_stop', None)
            bs['fib_stop'] = min(prev if prev is not None else float('inf'), fib_lock)
            if price >= bs['fib_stop']:
                return {"action": "CLOSE_SHORT", "reason": "Fibonacci"}
    return {"action": "HOLD", "reason": "hold"}


def simulate_one(arrays, e_idx, tp_targets, res_ob_top, design):
    o, h, l, c, idx = arrays
    entry = c[e_idx]; liq = entry * (1 + LIQ_MOVE)
    bs = {'position': 'SHORT', 'entry_price': entry, 'remaining_pct': 1.0, 'target_idx': 0,
          'fib_wave_start': entry, 'fib_extreme': entry, 'pulled_back': False, 'fib_stop': None,
          'bullish_obs': tp_targets, 'res_ob_top': res_ob_top}
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
                return R, 'liq', i
            sig = exec_check_exit(price, bs, params); act = sig['action']
            if act == 'REDUCE_SHORT' and not reduced:
                R += 0.5 * ((entry - price) / entry) - 0.5 * COST * 2; frac = 0.5; reduced = True; continue
            if act == 'CLOSE_SHORT':
                dur = (idx[i] - idx[e_idx]).total_seconds() / 86400
                R += frac * ((entry - price) / entry) - frac * COST * 2 - frac * FUNDING_DAILY * dur
                return R, sig['reason'], i
    R += frac * ((entry - c[xi]) / entry) - frac * COST * 2
    return R, 'max_hold', xi


def collect_entries(df):
    """진입후보 + 청산설계에 필요한 레벨(지지OB들, 저항OB윗선) 1회 수집."""
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
                entries.append((t0, tps, float(ab[0]), ts))    # ab[0]=저항OB top -> C4
        cur = t0 + 1
        dptr = np.searchsorted(down_idx, cur, side='left')
    return entries, (o, h, l, c, idx)


def run_design(entries, arrays, design):
    """한 설계로 전구간 청산 재시뮬. 진입겹침은 그 설계의 청산시점 기준으로 순차 처리."""
    idx = arrays[4]; rows = []; last_exit = -1
    for (e_idx, tps, res_ob_top, ts) in entries:
        if e_idx <= last_exit:
            continue
        R, reason, x_idx = simulate_one(arrays, e_idx, tps, res_ob_top, design)
        rows.append({'진입시간': ts.strftime('%Y-%m-%d %H:%M:%S'), '연도': ts.year,
                     'R': round(R, 6), '청산사유': reason,
                     '사고': int(reason in ACC_REASONS), '청산봉i': int(x_idx)})
        last_exit = x_idx
    return rows


def metrics(rows, label):
    if not rows:
        return {'설계': label, '거래수': 0}
    t = pd.DataFrame(rows)
    R = t['R'].values
    gp = R[R > 0].sum(); gl = -R[R < 0].sum()
    pf = (gp / gl) if gl > 0 else float('inf')
    # 명목 고정 자본곡선(FLOOR15) -> 파산/최저자본
    cap = START_CAP; mincap = START_CAP; bankrupt = False
    for r in R:
        cap += r * NOMINAL
        mincap = min(mincap, cap)
        if cap <= MIN_CAP:
            bankrupt = True; cap = MIN_CAP; break
    return {'설계': label, '거래수': len(t),
            '강제청산': int((t['청산사유'] == 'liq').sum()),
            '구멍': int((t['청산사유'] == 'hole_hardfloor').sum()),
            '피보승자': int((t['청산사유'] == 'Fibonacci').sum()),
            '누적R_pct': round(R.sum() * 100, 2),
            '평균R_pct': round(R.mean() * 100, 4),
            'PF': round(pf, 3) if pf != float('inf') else 999.0,
            '파산': 'YES' if bankrupt else 'NO',
            '최저자본': round(mincap, 0),
            '자본보존pct': round(mincap / START_CAP * 100, 1)}


def main():
    print("[InfraA_V2_stg1] 1차익절후 SL설계 비교: C0(기준)/C1(OB윗선)/C2(본전)/C3(피보조기)/C4(저항OB)")
    open(os.path.join(HERE, ".run_start"), 'w').close()
    data = find_data(); print(f"[data] {data}")
    df = load_data(data)
    print(f"[load] {len(df):,}rows | {df.index.min().date()}~{df.index.max().date()}")
    entries, arrays = collect_entries(df)
    print(f"[entries] 진입후보 {len(entries)}건 (설계 무관, 1회수집)")

    summary = []; split = []; best_rows = None; best_key = None; best_score = -1e9
    for d in DESIGNS:
        rows = run_design(entries, arrays, d)
        m_all = metrics(rows, d)
        summary.append(m_all)
        # 학습/검증 분리
        tr = [r for r in rows if r['연도'] in TRAIN_YEARS]
        te = [r for r in rows if r['연도'] in TEST_YEARS]
        m_tr = metrics(tr, d + '|train'); m_te = metrics(te, d + '|test')
        split.append(m_tr); split.append(m_te)
        # 최선설계 선택점수: 누적R 높고 + 검증 양전 + 파산아님(과적합/파산 배제)
        te_pos = (m_te.get('누적R_pct', -1) or -1) > 0
        score = (m_all['누적R_pct'] if m_all['파산'] == 'NO' else -1e6) + (50 if te_pos else -50)
        print(f"  [{d:13s}] 거래{m_all['거래수']:3d} 강제청산{m_all['강제청산']:2d} 구멍{m_all['구멍']:2d} "
              f"피보승자{m_all['피보승자']:3d} 누적R{m_all['누적R_pct']:8.2f}% PF{m_all['PF']:.2f} "
              f"파산{m_all['파산']} 검증R{m_te.get('누적R_pct','?')}%")
        if score > best_score:
            best_score = score; best_key = d; best_rows = rows

    pd.DataFrame(summary).to_csv(os.path.join(HERE, "sl_summary.csv"), index=False, encoding='utf-8-sig')
    pd.DataFrame(split).to_csv(os.path.join(HERE, "sl_split.csv"), index=False, encoding='utf-8-sig')
    if best_rows:
        bt = pd.DataFrame(best_rows); bt.insert(0, '최선설계', best_key)
        bt.to_csv(os.path.join(HERE, "sl_trades_best.csv"), index=False, encoding='utf-8-sig')
    else:
        pd.DataFrame([{'최선설계': 'none'}]).to_csv(os.path.join(HERE, "sl_trades_best.csv"),
                                                  index=False, encoding='utf-8-sig')
    print(f"\n[best] 선택설계: {best_key}")
    print("[save] sl_summary.csv + sl_split.csv + sl_trades_best.csv (this subfolder) - all files")


if __name__ == "__main__":
    main()
