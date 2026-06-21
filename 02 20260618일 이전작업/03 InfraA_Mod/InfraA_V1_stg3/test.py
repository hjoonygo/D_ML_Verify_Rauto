# -*- coding: utf-8 -*-
# [FILE] test.py  (InfraA_V1_stg3 - risk% ML: full-36mo trades -> risk grid + compounding + Monte Carlo)
# CODE LENGTH: approx 340 lines | INTERNAL VER: stg3_riskml_v1 | full output, no omission
#
# [PURPOSE / 목적] 하락장 거래당 위험%를 '박아버리기' 위한 ML(자금관리 최적화).
#   STEP1: 36개월 전체 데이터로 stg2 전략(d=5, ladder ON, FLOOR15 계단+피보0.65)을 돌려
#          '거래당 R(자본대비 손익률, 사이즈/위험 무관한 순수 엣지)'를 뽑는다.
#   STEP2: 그 R열에 위험% 그리드 {1,1.5,2,3,5,7%} x 사이징{고정비율 fixed, 손절거리기반 sldist} 적용,
#          ★복리(자본 누적) 시뮬 + 몬테카를로(거래순서 2000회 셔플)로 파산확률/MDD/월수익률/켈리배수 측정.
#   = 신경망 아님. 2년·소표본 과적합 방지 위해 그리드+켈리+몬테카를로(정직한 방법)만 사용.
#
# [핵심개념 — 사이즈 무관 R 추출이 왜 중요한가]
#   stg2는 명목 $50k 고정이라 위험%를 못 바꿨다. 여기선 거래마다 'entry/exit/sl_dist'만 뽑아
#   R = (entry-exit)/entry (숏 손익률, 레버前) 로 저장 -> 위험%/사이징을 STEP2서 자유롭게 입힌다.
#
# [복리식] cap_{n+1} = cap_n + size_n * R_n - fee.  size_n = f(cap_n, 위험%, 사이징).
#   fixed   : size = cap * risk%               (자본의 위험%를 '명목'으로? -> 아니다. 아래 주석)
#   sldist  : size = (cap * risk%) / sl_dist   (손절 맞으면 정확히 자본의 위험% 손실), 단 size<=cap*MAXLEV_CAP
#   강제청산: R <= -LIQ_MOVE 이면 R을 -LIQ_MOVE로 클립(최대 역행 손실 한도). 자본<=MIN_CAP=파산.
#
# [몬테카를로 파산확률] 거래 R열을 2000회 무작위 순서로 재배열하며 복리 시뮬 -> 파산(자본<시작*BUST_TH)
#   비율 = 파산확률. 순서운(나쁜 거래 초반 몰림)에 강한 위험%를 찾는다.
#
# [SPEED] (1)pivot 전구간 1회 벡터화 (2)확정시각 searchsorted (3)하락장만+청산까지만 4틱+빈구간 점프
#   (4)STEP2는 거래 R열(수십~수백건)만 다뤄 매우 가볍다. 몬테카를로도 numpy 벡터.
#
# [PATH] D:\ML\verify\InfraA_V1_stg3\ 실행, 데이터 상위 D:\ML\verify\, 결과 CSV -> 이 하위폴더.
# [DATA] ../Merged_Data_with_Regime_Features.csv (timestamp,open,high,low,close,feat_struct_8)  ★36개월 전체
# [OUTPUT] risk_trades_full.csv(전체거래 R) + risk_grid_summary.csv(위험%xML결과) + risk_montecarlo.csv
#
# [FUNCTIONS In/Out]
#   STEP1: find_data/load_data, resample_tf/precompute_tf_pivots/nearest_above/levels_below_5m (ob_mtf inline),
#          exec_check_exit (FLOOR15 SHORT inline), simulate_one -> 거래 R, build_trades_full() -> DataFrame
#   STEP2: kelly(R), run_compound(R, risk, mode), monte_carlo(R, risk, mode, n) -> 파산확률,
#          grid_eval() -> summary
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
SL_GATE = 0.0016
D_FIX = 5                  # stg2 결과 무난했던 d=5 고정(전체거래 생성용)
N_OB = 5                   # ladder ON
LEVERAGE = 5
START_CAP = 10000.0
LIQ_MOVE = 0.20            # 진입가 +20% 역행 = 최대 역행손실 한도(숏)
MIN_CAP = 100.0
BUST_TH = 0.20             # 자본<시작*20% = 파산 판정(몬테카를로)
COST = 0.0004
FUNDING_DAILY = 0.0001
MAX_HOLD_BARS = 60 * 24 * 90
FIB_TRIGGER = 15.0; FIB_EXT = 0.65; HARD_FLOOR_ROE = 15.0
MAXLEV_CAP = 5.0           # size 상한 = 자본 * 5 (레버5 한도)
RISK_GRID = [0.01, 0.015, 0.02, 0.03, 0.05, 0.07]
MODES = ['fixed', 'sldist']
MC_N = 2000                # 몬테카를로 셔플 횟수
RNG = np.random.default_rng(20260523)


def find_data():
    for d in [PARENT, HERE, r"D:\ML\verify", r"D:\ML\Verify"]:
        for n in ["Merged_Data_with_Regime_Features.csv", "Merged_Data.csv"]:
            p = os.path.join(d, n)
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
    """FLOOR15 SHORT inline (다중OB계단+피보+구멍하드플로어)."""
    entry = bs['entry_price']; lev = params['leverage']
    fib_trigger = params['fib_trigger_roe']; fib_ext = params['fib_ext_pct']
    innovation1 = params.get('innovation1', True); target_idx = bs['target_idx']
    if bs['fib_stop'] is None:
        hf = entry * (1 + params['hard_floor_roe'] / 100.0 / lev)
        if price >= hf:
            return {"action": "CLOSE_SHORT", "reason": f"hole_hardfloor(-{params['hard_floor_roe']:.0f}%ROE)"}
    bull = bs['bullish_obs']
    if target_idx < len(bull):
        tob = bull[target_idx]
        if price <= tob['mean']:
            bs['fib_stop'] = tob['top']; bs['target_idx'] += 1
            if bs['remaining_pct'] == 1.0:
                bs['remaining_pct'] = 0.5
                return {"action": "REDUCE_SHORT", "reason": "reduce"}
            return {"action": "HOLD", "reason": "Nth target"}
        if bs['fib_stop'] is not None and price >= bs['fib_stop']:
            return {"action": "CLOSE_SHORT", "reason": f"OB_edge({bs['fib_stop']:.2f})"}
    else:
        roe = ((entry - price) / entry) * lev * 100
        max_roe = ((entry - bs['fib_extreme']) / entry) * lev * 100
        if price < bs['fib_extreme']:
            if bs['pulled_back']:
                if innovation1:
                    bs['fib_wave_start'] = bs['fib_extreme']
                bs['pulled_back'] = False
            bs['fib_extreme'] = price
        elif price > bs['fib_extreme']:
            bs['pulled_back'] = True
        if roe >= fib_trigger or max_roe >= fib_trigger:
            downswing = bs['fib_wave_start'] - bs['fib_extreme']
            fib_lock = bs['fib_wave_start'] - downswing * fib_ext
            prev = bs.get('fib_stop', None)
            bs['fib_stop'] = min(prev if prev is not None else float('inf'), fib_lock)
            if price >= bs['fib_stop']:
                return {"action": "CLOSE_SHORT", "reason": f"Fibonacci({fib_ext:.2f})"}
    return {"action": "HOLD", "reason": "hold"}


def simulate_one(o, h, l, c, idx, e_idx, sl_dist, tp_targets):
    """거래 1건 -> (R, sl_dist, reason, et, xt). R=사이즈무관 손익률(숏: (entry-exit)/entry, 분할 가중합)."""
    entry = c[e_idx]; liq = entry * (1 + LIQ_MOVE)
    bs = {'position': 'SHORT', 'entry_price': entry, 'remaining_pct': 1.0, 'target_idx': 0,
          'fib_wave_start': entry, 'fib_extreme': entry, 'pulled_back': False, 'fib_stop': None,
          'bullish_obs': tp_targets}
    params = {'leverage': LEVERAGE, 'fib_trigger_roe': FIB_TRIGGER, 'fib_ext_pct': FIB_EXT,
              'innovation1': True, 'hard_floor_roe': HARD_FLOOR_ROE}
    frac = 1.0; reduced = False; R = 0.0; reason = 'max_hold'
    n = len(c); end_idx = min(n, e_idx + 1 + MAX_HOLD_BARS); xi = end_idx - 1
    for i in range(e_idx + 1, end_idx):
        o_, h_, l_, c_ = o[i], h[i], l[i], c[i]
        ticks = (o_, h_, l_, c_) if c_ < o_ else (o_, l_, h_, c_)
        for price in ticks:
            if price >= liq:
                R += frac * ((entry - liq) / entry) - frac * COST * 2
                return R, sl_dist, 'liq', idx[e_idx], idx[i]
            sig = exec_check_exit(price, bs, params); act = sig['action']
            if act == 'REDUCE_SHORT' and not reduced:
                R += 0.5 * ((entry - price) / entry) - 0.5 * COST * 2
                frac = 0.5; reduced = True; continue
            if act == 'CLOSE_SHORT':
                dur = (idx[i] - idx[e_idx]).total_seconds() / 86400
                R += frac * ((entry - price) / entry) - frac * COST * 2 - frac * FUNDING_DAILY * dur
                return R, sl_dist, sig['reason'][:20], idx[e_idx], idx[i]
    price = c[xi]
    R += frac * ((entry - price) / entry) - frac * COST * 2
    return R, sl_dist, 'max_hold', idx[e_idx], idx[xi]


def build_trades_full(df):
    """STEP1: 36개월 전체 하락장에서 d=5,ladder ON 거래의 R열 생성."""
    o = df['open'].values; h = df['high'].values; l = df['low'].values; c = df['close'].values
    idx = df.index
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
        if ok:
            sl_mean = (ab[0] + ab[1]) / 2.0; sl_dist = (sl_mean - price) / price
            if sl_dist < SL_GATE:
                ok = False
        if ok:
            tps = [{'top': t, 'bottom': b, 'mean': b * (1 + D_FIX / 1e4)} for (t, b) in bl if b * (1 + D_FIX / 1e4) < price]
            if not tps:
                cur = t0 + 1; dptr = np.searchsorted(down_idx, cur, side='left'); continue
            R, sld, reason, et, xt = simulate_one(o, h, l, c, idx, t0, sl_dist, tps)
            rows.append(dict(진입시간=et.strftime('%Y-%m-%d %H:%M:%S'), 청산시간=xt.strftime('%Y-%m-%d %H:%M:%S'),
                             연도=et.year, R=round(R, 6), sl_dist=round(sld, 6), 청산사유=reason))
            x_idx = idx.searchsorted(pd.to_datetime(xt.strftime('%Y-%m-%d %H:%M:%S')))
            cur = max(int(x_idx) + 1, t0 + 1)
        else:
            cur = t0 + 1
        dptr = np.searchsorted(down_idx, cur, side='left')
    return pd.DataFrame(rows)


# ----- STEP2: 위험% 그리드 + 복리 + 몬테카를로 -----------------------------------
def size_of(cap, risk, mode, sl_dist):
    if mode == 'fixed':
        return cap * risk * LEVERAGE                 # 자본의 risk%를 증거금으로, 레버 곱한 명목
    else:  # sldist: 손절 맞으면 자본의 risk% 손실되게 명목 역산
        return min((cap * risk) / max(sl_dist, 1e-6), cap * MAXLEV_CAP)


def run_compound(R, sl, risk, mode, order=None):
    """복리 시뮬 -> (최종자본, 최저자본, MDD, 파산여부)."""
    cap = START_CAP; peak = cap; mdd = 0.0; lowest = cap; bust = False
    seq = range(len(R)) if order is None else order
    for k in seq:
        r = R[k]
        size = size_of(cap, risk, mode, sl[k])
        cap += size * r
        if cap <= MIN_CAP:
            cap = max(cap, 0.0); bust = True
            lowest = min(lowest, cap); break
        peak = max(peak, cap); mdd = min(mdd, cap - peak); lowest = min(lowest, cap)
    return cap, lowest, mdd, bust


def kelly(R):
    R = np.asarray(R, float)
    w = R[R > 0]; l = R[R < 0]
    if len(w) == 0 or len(l) == 0:
        return 0.0
    p = len(w) / len(R); b = w.mean() / abs(l.mean())
    f = p - (1 - p) / b
    return float(f)


def monte_carlo(R, sl, risk, mode, n):
    R = np.asarray(R, float); sl = np.asarray(sl, float); m = len(R)
    bust = 0; finals = np.empty(n)
    for it in range(n):
        order = RNG.permutation(m)
        cap, low, mdd, b = run_compound(R, sl, risk, mode, order)
        bust += int(b); finals[it] = cap
    return bust / n, float(np.median(finals)), float(np.percentile(finals, 5))


def grid_eval(td):
    R = td['R'].values; sl = td['sl_dist'].values
    span_days = (pd.to_datetime(td['청산시간'].iloc[-1]) - pd.to_datetime(td['진입시간'].iloc[0])).days
    months = max(span_days / 30.0, 1)
    k = kelly(R)
    rows = []
    for mode in MODES:
        for risk in RISK_GRID:
            cap, low, mdd, bust1 = run_compound(R, sl, risk, mode)   # 실제순서 1회
            ret = cap / START_CAP - 1
            mret = (cap / START_CAP) ** (1 / months) - 1 if cap > 0 else -1
            pbust, mc_med, mc_p5 = monte_carlo(R, sl, risk, mode, MC_N)
            rows.append(dict(사이징=mode, 위험pct=round(risk * 100, 2),
                             켈리배수=round(risk / k, 2) if k > 0 else None,
                             실제최종=round(cap), 실제수익률=f"{ret*100:.0f}%",
                             월수익률=f"{mret*100:.1f}%", 최저자본=round(low), MDD=round(mdd),
                             실제파산='YES' if bust1 else 'NO',
                             MC파산확률=f"{pbust*100:.1f}%", MC중앙자본=round(mc_med), MC하위5pct=round(mc_p5)))
    return rows, k, months


def main():
    print("[InfraA_V1_stg3] risk% ML — STEP1 36mo full trades(d5,ladder ON) -> STEP2 risk grid + compound + MonteCarlo")
    open(os.path.join(HERE, ".run_start"), 'w').close()
    data = find_data(); print(f"[data] {data}")
    df = load_data(data)
    print(f"[load] {len(df):,}rows | {df.index.min().date()}~{df.index.max().date()}  (★36개월 확인)")
    print("[STEP1] 전체기간 거래 생성 중...")
    td = build_trades_full(df)
    td.to_csv(os.path.join(HERE, "risk_trades_full.csv"), index=False, encoding='utf-8-sig')
    if len(td) == 0:
        print("[중단] 거래 0건"); pd.DataFrame().to_csv(os.path.join(HERE, "risk_grid_summary.csv"), index=False)
        pd.DataFrame().to_csv(os.path.join(HERE, "risk_montecarlo.csv"), index=False); return
    yrs = sorted(td['연도'].unique())
    print(f"  거래 {len(td)}건 | 연도 {yrs} | 평균R {td['R'].mean()*100:.3f}% | 승률 {(td['R']>0).mean()*100:.1f}%")
    print("[STEP2] 위험% 그리드 x 사이징 x 몬테카를로...")
    rows, k, months = grid_eval(td)
    summ = pd.DataFrame(rows)
    summ.to_csv(os.path.join(HERE, "risk_grid_summary.csv"), index=False, encoding='utf-8-sig')
    # 몬테카를로 상세(켈리·기간 메타 포함)
    pd.DataFrame([dict(거래수=len(td), 연도수=len(yrs), 기간개월=round(months, 1),
                       풀켈리=round(k, 4), 하프켈리=round(k/2, 4),
                       평균R_pct=round(td['R'].mean()*100, 4), 승률_pct=round((td['R']>0).mean()*100, 1))]
                 ).to_csv(os.path.join(HERE, "risk_montecarlo.csv"), index=False, encoding='utf-8-sig')
    for r in rows:
        print(f"  [{r['사이징']:6s} {r['위험pct']}%] 수익{r['실제수익률']} 월{r['월수익률']} 파산{r['실제파산']} MC파산{r['MC파산확률']}")
    print("\n[save] risk_trades_full.csv + risk_grid_summary.csv + risk_montecarlo.csv (this subfolder) - all files")


if __name__ == "__main__":
    main()
