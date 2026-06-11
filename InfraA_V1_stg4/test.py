# -*- coding: utf-8 -*-
# [FILE] test.py  (InfraA_V1_stg4 - accident(34) cause ML: feature logging + 8-hypothesis tradeoff)
# CODE LENGTH: approx 430 lines | INTERNAL VER: stg4_accidentML_v1 | full output, no omission
#
# [PURPOSE / 목적] 사고 34건(강제청산9+구멍25, 합 -171%R)이 피보알파(+124%R)를 다 먹는다.
#   진입 직전 정보만으로 '이 거래 사고날지' 미리 거를 수 있나? ML로 규명.
#   ★핵심=맞교환: 규칙으로 거를 때 '사고 N건 제거 vs 피보승자 M건 동반사망 vs 제거후 평균R'.
#   승자 죽이면 알파 아님. 외부 의존 0 (sklearn 없이 numpy로 결정나무/중요도/군집 직접 구현).
#
# [STEP] 1) 36개월 거래 재생성하며 '진입 직전' 피처를 한 줄씩 기록(자기완결, 미래참조 가드).
#        2) 타깃 y=사고(강제청산 or 구멍하드플로어)=1, 정상=0.
#        3) 깊이3 결정나무(읽는규칙) + permutation 중요도 + 사고만 KMeans군집(유형).
#        4) 8가설 단일필터 맞교환표 + 나무규칙 맞교환표.
#
# [8 HYPOTHESES / Data명세 매핑]
#   H1 추세약함: adx, feat_struct_8(downtrend 여부는 이미 필터됨->adx로) 
#   H2 변동성죽음: norm_atr, atr_ratio
#   H3 스퀴즈(폭발직전): bb_width, atr_ratio
#   H4 얇은RR/OB가까움: sl_dist, tp_dist, rr
#   H5 눌림 깊게진입: 진입가의 최근60봉 스윙내 위치(0=저점,1=고점)
#   H6 EMA역행숏: close vs ema_50/ema_100, ema20_slope
#   H7 역행유입(롱몰림): oi_change_5m/15m/1h, oi_zscore_24h   [파일A]
#   H8 공격매수/역배팅: taker_imbalance_5m_avg, taker_flip_15m, top_retail_divergence [파일A]
#
# [DATA] B=../Merged_Data_with_Regime_Features.csv (필수), A=../merged_data.csv (OI/flow, 있으면 결합)
#   결합: timestamp inner join, 매칭률 로그. A 없으면 H7/H8 피처는 NaN(나무가 알아서 제외).
#
# [SPEED] pivot 전구간 1회 벡터화, 확정시각 searchsorted, 하락장만+청산까지만 4틱+점프,
#   피처는 진입시점 1회 조회(벡터 인덱싱). 나무/군집은 248행이라 즉시.
#
# [PATH] D:\ML\verify\InfraA_V1_stg4\ 실행, 데이터 상위, 결과 CSV -> 이 하위폴더.
# [OUTPUT] acc_trades_feat.csv(거래+피처+사고라벨) + acc_tradeoff.csv(8가설+나무규칙 맞교환)
#          + acc_importance.csv(피처중요도) + acc_clusters.csv(사고유형 군집)
#
# [FUNCTIONS] (ob_mtf inline) + exec_check_exit + simulate_one + build_trades_feat
#   + dtree_fit/predict (numpy CART depth3) + perm_importance + kmeans + tradeoff_eval
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
RNG = np.random.default_rng(20260523)

# 진입시점에 읽을 파일B 피처(있으면 사용). 없으면 자동 제외.
FEAT_B = ['adx', 'adx_chg', 'norm_atr', 'atr_ratio', 'bb_width', 'ema20_slope',
          'ema_50', 'ema_100', 'feat_struct_8']
FEAT_A = ['oi_change_5m_pct', 'oi_change_15m_pct', 'oi_change_1h_pct', 'oi_zscore_24h',
          'taker_imbalance_5m_avg', 'taker_flip_15m', 'top_retail_divergence']


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
    base = ['timestamp', 'open', 'high', 'low', 'close']
    use = base + [cc for cc in FEAT_B if cc in head.columns and cc not in base]
    df = pd.read_csv(path, usecols=use, index_col='timestamp', parse_dates=True)
    if getattr(df.index, 'tz', None) is not None:
        df.index = df.index.tz_localize(None)
    df = df.sort_index()
    return df


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
    before = len(df)
    df = df.join(fa, how='left')          # B 기준 left join(거래시점 보존), 매칭률은 비결측으로
    for cc in FEAT_A:
        if cc not in df.columns:
            df[cc] = np.nan
    matched = df[[c for c in FEAT_A if c in df.columns]].notna().any(axis=1).mean() if before else 0
    info = {'flow': os.path.basename(flow_path), 'match_pct': round(float(matched) * 100, 1)}
    return df, info


# ----- ob_mtf inline (verified, lookahead-guarded) ------------------------------
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
    entry = bs['entry_price']; lev = params['leverage']
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


def swing_pos(h, l, e_idx, win=60):
    """진입가가 최근 win봉 [저점,고점] 안 어디(0=저점,1=고점). H5용."""
    lo = max(0, e_idx - win + 1)
    hh = h[lo:e_idx + 1].max(); ll = l[lo:e_idx + 1].min()
    if hh <= ll:
        return 0.5
    return float((l[e_idx] - ll) / (hh - ll))


def build_trades_feat(df):
    o = df['open'].values; h = df['high'].values; l = df['low'].values; c = df['close'].values
    idx = df.index
    cols = {cc: (df[cc].values if cc in df.columns else np.full(len(df), np.nan)) for cc in (FEAT_B + FEAT_A)}
    down_idx = np.where(df[REGIME_COL].astype(str).values == 'downtrend')[0]
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
        sl_dist = tp_dist = rr = np.nan
        if ok:
            sl_mean = (ab[0] + ab[1]) / 2.0; sl_dist = (sl_mean - price) / price
            tp0 = bl[0][1] * (1 + D_FIX / 1e4); tp_dist = (price - tp0) / price
            rr = tp_dist / sl_dist if sl_dist > 0 else np.nan
            if sl_dist < SL_GATE:
                ok = False
        if ok:
            tps = [{'top': t, 'bottom': b, 'mean': b * (1 + D_FIX / 1e4)} for (t, b) in bl if b * (1 + D_FIX / 1e4) < price]
            if not tps:
                cur = t0 + 1; dptr = np.searchsorted(down_idx, cur, side='left'); continue
            R, reason, xt = simulate_one(o, h, l, c, idx, t0, tps)
            acc = 1 if reason in ('liq', 'hole_hardfloor') else 0
            row = dict(진입시간=ts.strftime('%Y-%m-%d %H:%M:%S'), 연도=ts.year, R=round(R, 6),
                       청산사유=reason, 사고=acc,
                       sl_dist_bp=round(sl_dist * 1e4, 1), tp_dist_bp=round(tp_dist * 1e4, 1),
                       rr=round(rr, 3) if rr == rr else np.nan,
                       swing_pos=round(swing_pos(h, l, t0), 3))
            # 파일 피처(진입시점 값) + 파생
            for cc in FEAT_B:
                if cc == 'feat_struct_8':
                    continue
                v = cols[cc][t0]
                if cc == 'ema_50':
                    row['close_vs_ema50'] = round((price - v) / price * 1e4, 1) if v == v and v else np.nan
                elif cc == 'ema_100':
                    row['close_vs_ema100'] = round((price - v) / price * 1e4, 1) if v == v and v else np.nan
                else:
                    row[cc] = round(float(v), 5) if v == v else np.nan
            for cc in FEAT_A:
                v = cols[cc][t0]
                row[cc] = round(float(v), 5) if v == v else np.nan
            rows.append(row)
            x_idx = idx.searchsorted(pd.to_datetime(xt.strftime('%Y-%m-%d %H:%M:%S')))
            cur = max(int(x_idx) + 1, t0 + 1)
        else:
            cur = t0 + 1
        dptr = np.searchsorted(down_idx, cur, side='left')
    return pd.DataFrame(rows)


# ----- numpy CART depth-3 (사람이 읽는 규칙) ------------------------------------
def _gini(y):
    if len(y) == 0:
        return 0.0
    p = y.mean()
    return 1 - p * p - (1 - p) * (1 - p)


def _best_split(X, y):
    best = None; best_g = _gini(y); n = len(y)
    for j in range(X.shape[1]):
        col = X[:, j]; vals = col[~np.isnan(col)]
        if len(vals) < 4:
            continue
        for thr in np.unique(np.percentile(vals, [20, 40, 50, 60, 80])):
            left = col <= thr
            if left.sum() < 3 or (~left).sum() < 3:
                continue
            g = (left.sum() * _gini(y[left]) + (~left).sum() * _gini(y[~left])) / n
            if g < best_g - 1e-9:
                best_g = g; best = (j, thr)
    return best


def dtree_fit(X, y, names, depth=3, node='root', lines=None):
    if lines is None:
        lines = []
    p = y.mean() if len(y) else 0
    if depth == 0 or len(y) < 6 or p in (0, 1):
        lines.append((node, f"잎: 사고율 {p*100:.0f}% (n={len(y)})"))
        return lines
    sp = _best_split(X, y)
    if sp is None:
        lines.append((node, f"잎: 사고율 {p*100:.0f}% (n={len(y)})"))
        return lines
    j, thr = sp; col = X[:, j]; left = col <= thr
    lines.append((node, f"{names[j]} <= {thr:.4g} ?  (n={len(y)}, 사고율 {p*100:.0f}%)"))
    dtree_fit(X[left], y[left], names, depth - 1, node + " └Y", lines)
    dtree_fit(X[~left], y[~left], names, depth - 1, node + " └N", lines)
    return lines


def perm_importance(X, y, names):
    """단일변수 분리 지니감소로 중요도 근사(트리없이 빠르게)."""
    base = _gini(y); imp = []
    for j in range(X.shape[1]):
        col = X[:, j]; vals = col[~np.isnan(col)]
        if len(vals) < 4:
            imp.append((names[j], 0.0)); continue
        bestred = 0.0
        for thr in np.unique(np.percentile(vals, [25, 50, 75])):
            left = col <= thr
            if left.sum() < 3 or (~left).sum() < 3:
                continue
            g = (left.sum() * _gini(y[left]) + (~left).sum() * _gini(y[~left])) / len(y)
            bestred = max(bestred, base - g)
        imp.append((names[j], round(bestred, 5)))
    return sorted(imp, key=lambda x: -x[1])


def kmeans(X, k=3, iters=50):
    X = np.nan_to_num(X, nan=0.0)
    Xs = (X - X.mean(0)) / (X.std(0) + 1e-9)
    c = Xs[RNG.choice(len(Xs), k, replace=False)]
    lab = np.zeros(len(Xs), int)
    for _ in range(iters):
        d = ((Xs[:, None, :] - c[None, :, :]) ** 2).sum(2)
        nl = d.argmin(1)
        if (nl == lab).all():
            break
        lab = nl
        for i in range(k):
            if (lab == i).any():
                c[i] = Xs[lab == i].mean(0)
    return lab


def tradeoff_eval(td, feat_names):
    """8가설 단일필터 + 나무규칙: 거를때 사고제거/승자사망/제거후평균R."""
    R = td['R'].values; acc = td['사고'].values
    win = (R > 0) & (acc == 0)               # 정상 승자
    base_meanR = R.mean()
    out = []

    def evalrule(name, drop_mask):
        kept = ~drop_mask
        rem_acc = int((drop_mask & (acc == 1)).sum())
        rem_win = int((drop_mask & win).sum())
        keptR = R[kept].mean() if kept.any() else 0
        out.append(dict(규칙=name, 거른건수=int(drop_mask.sum()),
                        제거사고=rem_acc, 동반사망승자=rem_win,
                        제거후평균R_pct=round(keptR * 100, 4),
                        제거후거래=int(kept.sum()),
                        엣지양전='YES' if keptR > 0 else 'NO'))

    # 8가설 단일필터(있는 피처만; 임계는 사고측 중앙값)
    hyp = {
        'H1_adx낮음': ('adx', 'low'), 'H2_norm_atr낮음': ('norm_atr', 'low'),
        'H3_bb_width낮음': ('bb_width', 'low'), 'H4_rr낮음': ('rr', 'low'),
        'H5_swing깊음': ('swing_pos', 'low'), 'H6_ema100역행': ('close_vs_ema100', 'low'),
        'H7_oi_1h급증': ('oi_change_1h_pct', 'high'), 'H8_taker불균형': ('taker_imbalance_5m_avg', 'high'),
    }
    for name, (col, side) in hyp.items():
        if col not in td.columns:
            continue
        v = pd.to_numeric(td[col], errors='coerce').values
        accv = v[(acc == 1) & ~np.isnan(v)]
        if len(accv) < 3:
            continue
        thr = np.median(accv)
        drop = (v <= thr) if side == 'low' else (v >= thr)
        drop = drop & ~np.isnan(v)
        evalrule(f"{name}({col}{'<=' if side=='low' else '>='}{thr:.4g})", drop)
    out.append(dict(규칙='[기준]필터없음', 거른건수=0, 제거사고=0, 동반사망승자=0,
                    제거후평균R_pct=round(base_meanR * 100, 4), 제거후거래=len(R), 엣지양전='YES' if base_meanR > 0 else 'NO'))
    return pd.DataFrame(out)


def main():
    print("[InfraA_V1_stg4] 사고 34건 원인 ML — 거래+피처 재생성 -> 8가설 맞교환 + 결정나무/중요도/군집")
    open(os.path.join(HERE, ".run_start"), 'w').close()
    data = find_data(); print(f"[data B] {data}")
    df = load_data(data)
    flow = find_flow(); df, finfo = merge_flow(df, flow)
    print(f"[data A] {finfo['flow']} (매칭률 {finfo['match_pct']}%)")
    print(f"[load] {len(df):,}rows | {df.index.min().date()}~{df.index.max().date()}")
    print("[STEP1] 거래+피처 재생성...")
    td = build_trades_feat(df)
    td.to_csv(os.path.join(HERE, "acc_trades_feat.csv"), index=False, encoding='utf-8-sig')
    if len(td) == 0:
        print("[중단] 거래 0건")
        for nm in ["acc_tradeoff.csv", "acc_importance.csv", "acc_clusters.csv"]:
            pd.DataFrame().to_csv(os.path.join(HERE, nm), index=False)
        return
    nacc = int(td['사고'].sum())
    print(f"  거래 {len(td)} | 사고 {nacc} | 정상 {len(td)-nacc} | 사고율 {nacc/len(td)*100:.1f}%")

    # 피처행렬
    feat_names = [c for c in td.columns if c not in ('진입시간', '연도', 'R', '청산사유', '사고')]
    X = td[feat_names].apply(pd.to_numeric, errors='coerce').values
    y = td['사고'].values.astype(int)

    # 중요도
    imp = perm_importance(X, y, feat_names)
    pd.DataFrame(imp, columns=['피처', '지니감소']).to_csv(os.path.join(HERE, "acc_importance.csv"), index=False, encoding='utf-8-sig')
    print("[STEP3] 중요도 top5:", ", ".join(f"{n}({v})" for n, v in imp[:5]))

    # 결정나무(읽는 규칙) -> txt는 check가, 여기선 tradeoff에 반영
    tree_lines = dtree_fit(X, y, feat_names, depth=3)
    pd.DataFrame(tree_lines, columns=['노드', '규칙']).to_csv(os.path.join(HERE, "acc_tree.csv"), index=False, encoding='utf-8-sig')

    # 사고 군집
    acc_mask = y == 1
    if acc_mask.sum() >= 6:
        Xa = X[acc_mask]
        # 결측많은 열 제외
        valid = [i for i in range(Xa.shape[1]) if np.isfinite(Xa[:, i]).mean() > 0.5]
        lab = kmeans(Xa[:, valid], k=3)
        cl = td[acc_mask].copy(); cl['군집'] = lab
        prof = cl.groupby('군집').agg(건수=('R', 'size'), 평균R_pct=('R', lambda s: round(s.mean()*100, 2)),
                                     평균손절bp=('sl_dist_bp', 'mean'), 평균swing=('swing_pos', 'mean')).reset_index()
        prof.to_csv(os.path.join(HERE, "acc_clusters.csv"), index=False, encoding='utf-8-sig')
    else:
        pd.DataFrame().to_csv(os.path.join(HERE, "acc_clusters.csv"), index=False, encoding='utf-8-sig')

    # ★맞교환표
    to = tradeoff_eval(td, feat_names)
    to.to_csv(os.path.join(HERE, "acc_tradeoff.csv"), index=False, encoding='utf-8-sig')
    print("[STEP4] 맞교환표 — 엣지 양전되는 규칙:")
    pos = to[(to['엣지양전'] == 'YES') & (to['규칙'] != '[기준]필터없음')]
    if len(pos):
        for _, r in pos.iterrows():
            print(f"  {r['규칙']}: 사고제거 {r['제거사고']} / 승자사망 {r['동반사망승자']} -> 제거후평균R {r['제거후평균R_pct']}%")
    else:
        print("  ★엣지 양전 규칙 없음 — 단일가설로는 사고만 깔끔히 못 거름(나무/조합 필요 신호)")
    print("\n[save] acc_trades_feat.csv + acc_tradeoff.csv + acc_importance.csv + acc_clusters.csv + acc_tree.csv")


if __name__ == "__main__":
    main()
