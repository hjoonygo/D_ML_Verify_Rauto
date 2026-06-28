# -*- coding: utf-8 -*-
# [FILE] test.py  (InfraA_V1_stg2 - TP=5min OB bottom + whipsaw margin d, multi-OB ladder ON/OFF)
# CODE LENGTH: approx 300 lines | INTERNAL VER: stg2_tpd_ladder_v1 | full output, no omission
#
# [PURPOSE / 목적]
#   A(실측)에서 확정: SL=1H OB mean(~52bp), TP=5분 OB '윗선'은 0.6bp라 즉사 -> 5분 OB '바닥(bottom)'을
#   기준으로 위로 d bp 당겨 TP(휩소방지). d in {3,5,8,10}. 추가로 B작업: 다중 OB 계단(ladder) ON/OFF 비교.
#   = 검증된 흑자엔진(FLOOR15 Exec_Dynamic_TS_GridD_v2)의 다중OB계단+피보0.65를 1분봉 청산으로 그대로 사용.
#   grid = d{3,5,8,10} x ladder{ON,OFF} = 8 scenario.  ★거래/손익 시뮬(측정 아님).
#
# [DESIGN / 설계 - all from verified code, no guess]
#   - SL price = 1H resistance OB mean  (nearest_above_mtf top/bottom -> mean=(top+bottom)/2)
#   - TP targets = 5min support OB list, each target price = ob.bottom*(1 + d/1e4)   (휩소방지 d)
#       ladder ON : feed multiple 5min support OBs -> engine walks them (Phase1 다중OB), stop ratchets down
#       ladder OFF: feed only the nearest 1 OB     -> first reduce then Phase2 fibo (no ladder)
#   - gate: RR REMOVED (A로 확정). only SL>=SL_GATE(16bp). TP는 d로 정해지므로 하한 없음.
#   - exit on 1min bars, 4-tick intrabar (FLOOR15 verbatim), entry on bar close.
#   - money: fixed nominal $50,000 (FLOOR15 흑자 방식; risk%/clamp는 흑자판에 없던 것이라 배제) + compounding OFF.
#       단, 파산/강제청산 안전판: 진입가 +20% 역행시 강제청산(LIQ_MOVE), 자본<=MIN_CAP 정지.
#
# [SPEED / 속도가속] (1)5분/60분 pivot 전구간 1회 사전계산(벡터화) (2)pivot 확정시각 정렬+searchsorted 활성슬라이스
#   (3)하락장 진입후보만, 청산까지만 4틱 진행하고 빈구간 점프 (4)OB스캔 윈도우 1회 생성.
#
# [LOOKAHEAD GUARD] ob_mtf 원본 인라인: pivot 확정시각=(center+w)봉 마감. 그 시각<=진입시각 OB만.
#
# [PATH] runs in D:\ML\verify\InfraA_V1_stg2\ ; data one level up D:\ML\verify\ ; result CSV -> this subfolder.
# [DATA] ../Merged_Data_with_Regime_Features.csv  (timestamp,open,high,low,close,feat_struct_8)
# [OUTPUT] obtest_trades_<tag>.csv (per scenario) + obtest_summary.csv + obtest_yearly.csv  (all files; no paste)
#
# [FUNCTIONS In/Out]
#   find_data()/load_data(path)                 -> df
#   resample_tf/precompute_tf_pivots/nearest_above/levels_below_5m  [ob_mtf inline]
#   exec_check_exit(price, bs, params)          -> action dict  (FLOOR15 engine inline, SHORT used)
#   simulate_one(...)                           -> (rows, pnl, why)
#   run_scenario(d, ladder)                     -> (trades, cap_curve, bankrupt, diag)
# ==============================================================================

import os, sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
REGIME_COL = 'feat_struct_8'
W_TF = 3
SL_TF = 60                 # SL: 1H resistance OB mean
TP_TF = 5                  # TP: 5min support OB bottom + d
SL_GATE = 0.0016           # 16bp (A 확정). RR gate removed.
D_LIST = [3, 5, 8, 10]     # whipsaw margin bp
LADDER_LIST = [True, False]
N_OB = 5                   # ladder ON: feed up to 5 support OBs
LEVERAGE = 5
NOMINAL = 50000.0          # FLOOR15 fixed nominal
START_CAP = 10000.0
LIQ_MOVE = 0.20
MIN_CAP = 100.0
COST = 0.0004
FUNDING_DAILY = 0.0001
MAX_HOLD_BARS = 60 * 24 * 90
FIB_TRIGGER = 15.0
FIB_EXT = 0.65             # FLOOR15 흑자 비율
HARD_FLOOR_ROE = 15.0      # 구멍(보호스탑 없을 때)만 작동하는 파국손절(FLOOR15 best)


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


# ----- ob_mtf inline (verified) -------------------------------------------------
def resample_tf(df1m, tf_min):
    rule = f"{tf_min}min"
    agg = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}
    return df1m[['open', 'high', 'low', 'close']].resample(rule, label='left', closed='left').agg(agg).dropna()


def precompute_tf_pivots(df_tf, w, tf_min):
    high = df_tf['high'].values; low = df_tf['low'].values
    starts = df_tf.index.values
    n = len(high)
    if n < 2 * w + 1:
        z = np.array([], dtype='datetime64[ns]'); f = np.array([], dtype=float)
        return z, z, f, f, f, f
    from numpy.lib.stride_tricks import sliding_window_view
    win = 2 * w + 1
    hmax = sliding_window_view(high, win).max(axis=1)
    lmin = sliding_window_view(low, win).min(axis=1)
    centers = np.arange(w, n - w)
    hp_c = centers[high[w:n - w] == hmax]
    lp_c = centers[low[w:n - w] == lmin]
    td = np.timedelta64(tf_min, 'm')
    return (starts[hp_c + w] + td, starts[lp_c + w] + td, high[hp_c], low[hp_c], high[lp_c], low[lp_c])


def nearest_above(price, ts, hpc, hpt, hpb):
    """1H resistance OB nearest above -> (top,bottom). SL=mean=(top+bottom)/2."""
    k = np.searchsorted(hpc, np.datetime64(ts), side='right')
    if k == 0:
        return None
    bots = hpb[:k]; tops = hpt[:k]
    cand = bots > price
    if not cand.any():
        return None
    bb = bots[cand]; tt = tops[cand]
    j = np.argmin(bb)
    return (float(tt[j]), float(bb[j]))


def levels_below_5m(price, ts, lpc, lpt, lpb, n):
    """5min support OBs below price, nearest first (top desc). up to n. -> list[(top,bottom)]."""
    k = np.searchsorted(lpc, np.datetime64(ts), side='right')
    if k == 0:
        return []
    tops = lpt[:k]; bots = lpb[:k]
    cand = tops < price
    if not cand.any():
        return []
    tt = tops[cand]; bb = bots[cand]
    order = np.argsort(-tt)        # top 내림차순 = 가까운 것 먼저
    return [(float(tt[o]), float(bb[o])) for o in order[:n]]
# -------------------------------------------------------------------------------


def exec_check_exit(price, bs, params):
    """FLOOR15 Exec_Dynamic_TS_GridD_v2 SHORT branch inline (다중OB계단+피보0.65+구멍하드플로어)."""
    pos = bs['position']
    entry = bs['entry_price']
    lev = params['leverage']
    fib_trigger = params['fib_trigger_roe']
    fib_ext = params['fib_ext_pct']
    innovation1 = params.get('innovation1', True)
    target_idx = bs['target_idx']

    # 구멍(보호스탑 없음)일 때만 파국 하드플로어
    if bs['fib_stop'] is None:
        hf_pct = params.get('hard_floor_roe', 15.0) / 100.0
        hf = entry * (1 + hf_pct / lev)        # SHORT
        if price >= hf:
            return {"action": "CLOSE_SHORT", "reason": f"hole_hardfloor(-{hf_pct*100:.1f}%ROE)"}

    bull = bs['bullish_obs']       # 지지 OB 타겟 리스트(가까운 순), 각 dict{top,bottom,mean(=TP price)}
    # [Phase1] 다중 OB 타겟팅
    if target_idx < len(bull):
        tob = bull[target_idx]
        if price <= tob['mean']:               # mean에 'TP price'(=bottom+d)를 담아둠
            new_sl = tob['top']                # 스탑 하향(아래쪽 진행이라 top쪽으로)
            bs['fib_stop'] = new_sl
            bs['target_idx'] += 1
            if bs['remaining_pct'] == 1.0:
                bs['remaining_pct'] = 0.5
                return {"action": "REDUCE_SHORT", "reason": "SMC 1st target reduce"}
            else:
                return {"action": "HOLD", "reason": "SMC Nth target stop-down"}
        if bs['fib_stop'] is not None and price >= bs['fib_stop']:
            return {"action": "CLOSE_SHORT", "reason": f"OB edge stop({bs['fib_stop']:.2f})"}
    # [Phase2] 계단식 피보
    else:
        max_roe = ((entry - bs['fib_extreme']) / entry) * lev * 100
        roe = ((entry - price) / entry) * lev * 100
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
            fib_lock = bs['fib_wave_start'] - (downswing * fib_ext)
            prev = bs.get('fib_stop', None)
            bs['fib_stop'] = min(prev if prev is not None else float('inf'), fib_lock)
            if price >= bs['fib_stop']:
                return {"action": "CLOSE_SHORT", "reason": f"Fibonacci lock({fib_ext:.2f}:{bs['fib_stop']:.2f})"}
    return {"action": "HOLD", "reason": "hold"}


def _row(entry, price, size, et, xt, reason, net):
    return dict(진입시간=et.strftime('%Y-%m-%d %H:%M:%S'), 청산시간=xt.strftime('%Y-%m-%d %H:%M:%S'),
                연도=et.year, 진입가=round(entry, 2), 청산가=round(price, 2), 명목=round(size, 2),
                청산사유=reason, 순수익=round(net, 2),
                구분='REDUCE' if 'reduce' in reason.lower() else 'CLOSE')


def simulate_one(df, o, h, l, c, idx, e_idx, sl_mean, tp_targets):
    entry = c[e_idx]
    size = NOMINAL
    liq = entry * (1 + LIQ_MOVE)
    bs = {'position': 'SHORT', 'entry_price': entry, 'remaining_pct': 1.0, 'target_idx': 0,
          'fib_wave_start': entry, 'fib_extreme': entry, 'pulled_back': False, 'fib_stop': None,
          'bullish_obs': tp_targets}
    params = {'leverage': LEVERAGE, 'fib_trigger_roe': FIB_TRIGGER, 'fib_ext_pct': FIB_EXT,
              'innovation1': True, 'hard_floor_roe': HARD_FLOOR_ROE}
    reduced = False; pnl_total = 0.0; rows = []
    n = len(c); end_idx = min(n, e_idx + 1 + MAX_HOLD_BARS)
    for i in range(e_idx + 1, end_idx):
        o_, h_, l_, c_ = o[i], h[i], l[i], c[i]
        ticks = (o_, h_, l_, c_) if c_ < o_ else (o_, l_, h_, c_)
        for price in ticks:
            if price >= liq:
                loss = size * ((entry - liq) / entry); fee = size * COST * 2
                pnl_total += loss - fee
                rows.append(_row(entry, liq, size, idx[e_idx], idx[i], 'liq(-20%)', loss - fee))
                return rows, pnl_total, 'liq'
            sig = exec_check_exit(price, bs, params); act = sig['action']
            if act == 'REDUCE_SHORT' and not reduced:
                amt = size * 0.5; pnl = amt * ((entry - price) / entry); fee = amt * COST * 2
                pnl_total += pnl - fee
                rows.append(_row(entry, price, amt, idx[e_idx], idx[i], 'reduce', pnl - fee))
                size *= 0.5; reduced = True; continue
            if act == 'CLOSE_SHORT':
                pnl = size * ((entry - price) / entry); fee = size * COST * 2
                dur = (idx[i] - idx[e_idx]).total_seconds() / 86400; fund = size * FUNDING_DAILY * dur
                pnl_total += pnl - fee - fund
                rows.append(_row(entry, price, size, idx[e_idx], idx[i], sig['reason'][:28], pnl - fee - fund))
                return rows, pnl_total, 'close'
    price = c[end_idx - 1]; pnl = size * ((entry - price) / entry)
    pnl_total += pnl - size * COST * 2
    rows.append(_row(entry, price, size, idx[e_idx], idx[end_idx - 1], 'max_hold', pnl))
    return rows, pnl_total, 'max_hold'


def run_scenario(df, o, h, l, c, idx, down_idx, hpc, hpt, hpb, lpc, lpt, lpb, d, ladder):
    cap = START_CAP; trades = []; bankrupt = False
    diag = {'pass': 0, 'no_sl': 0, 'no_tp': 0, 'sl_gate': 0}
    n = len(c); cur = 0
    dptr = np.searchsorted(down_idx, cur, side='left')
    while dptr < len(down_idx):
        t0 = int(down_idx[dptr])
        if t0 >= n - 1:
            break
        if cap <= MIN_CAP:
            bankrupt = True; break
        price = c[t0]; ts = idx[t0]
        ab = nearest_above(price, ts, hpc, hpt, hpb)         # 1H resistance -> SL mean
        bl = levels_below_5m(price, ts, lpc, lpt, lpb, N_OB if ladder else 1)   # 5min support OBs
        ok = True
        if ab is None:
            diag['no_sl'] += 1; ok = False
        if not bl:
            diag['no_tp'] += 1; ok = False
        if ok:
            sl_mean = (ab[0] + ab[1]) / 2.0
            sl_dist = (sl_mean - price) / price
            if sl_dist < SL_GATE:
                diag['sl_gate'] += 1; ok = False
        if ok:
            # TP targets: 각 5분 지지OB bottom + d bp. mean칸에 'TP price' 담아 엔진에 전달.
            tp_targets = []
            for (top, bot) in bl:
                tp_price = bot * (1 + d / 1e4)
                if tp_price < price:                     # 진입가 아래여야 SHORT TP로 유효
                    tp_targets.append({'top': top, 'bottom': bot, 'mean': tp_price})
            if not tp_targets:
                diag['no_tp'] += 1
                cur = t0 + 1; dptr = np.searchsorted(down_idx, cur, side='left'); continue
            diag['pass'] += 1
            rows, pnl, why = simulate_one(df, o, h, l, c, idx, t0, sl_mean, tp_targets)
            cap += pnl
            for r in rows:
                r['거래후자본'] = round(cap, 2)
            trades.extend(rows)
            last_x = pd.to_datetime(rows[-1]['청산시간']); x_idx = idx.searchsorted(last_x)
            cur = max(int(x_idx) + 1, t0 + 1)
        else:
            cur = t0 + 1
        dptr = np.searchsorted(down_idx, cur, side='left')
    return trades, cap, bankrupt, diag


def main():
    print("[InfraA_V1_stg2] TP=5min OB bottom + d{3,5,8,10}bp x ladder{ON,OFF}  (SL=1H mean, RR removed)")
    open(os.path.join(HERE, ".run_start"), 'w').close()
    data = find_data(); print(f"[data] {data}")
    df = load_data(data)
    o = df['open'].values; h = df['high'].values; l = df['low'].values; c = df['close'].values
    idx = df.index
    down_idx = np.where(df[REGIME_COL].astype(str).values == 'downtrend')[0]
    # pivots once
    hpc, _, hpt, hpb, _, _ = precompute_tf_pivots(resample_tf(df, SL_TF), W_TF, SL_TF)
    _, lpc, _, _, lpt, lpb = precompute_tf_pivots(resample_tf(df, TP_TF), W_TF, TP_TF)
    print(f"[load] {len(df):,}rows, downtrend {len(down_idx):,}bars. grid d{D_LIST} x ladder{LADDER_LIST}\n")

    summary = []; yearly = []
    for ladder in LADDER_LIST:
        for d in D_LIST:
            tag = f"d{d}_{'ladder' if ladder else 'single'}"
            trades, cap, bankrupt, diag = run_scenario(df, o, h, l, c, idx, down_idx,
                                                        hpc, hpt, hpb, lpc, lpt, lpb, d, ladder)
            pd.DataFrame(trades).to_csv(os.path.join(HERE, f"obtest_trades_{tag}.csv"), index=False, encoding='utf-8-sig')
            if trades:
                td = pd.DataFrame(trades)
                g = td.groupby('진입시간')['순수익'].sum()
                pf = g[g > 0].sum() / abs(g[g < 0].sum()) if (g < 0).any() else 9.99
                row = dict(시나리오=tag, d=d, ladder='ON' if ladder else 'OFF', 진입수=len(g),
                           PF=round(pf, 3), 승률=round((g > 0).mean() * 100, 1),
                           최종자본=round(cap), 수익률=f"{(cap / START_CAP - 1) * 100:.0f}%",
                           파산='YES' if bankrupt else 'NO',
                           진입실패_SL없음=diag['no_sl'], TP없음=diag['no_tp'], SL게이트탈락=diag['sl_gate'])
                # 연도별
                td['연도'] = pd.to_datetime(td['진입시간']).dt.year
                gy = td.groupby(['연도', '진입시간'])['순수익'].sum().reset_index()
                for yr in sorted(gy['연도'].unique()):
                    s = gy[gy['연도'] == yr]['순수익']
                    pfy = s[s > 0].sum() / abs(s[s < 0].sum()) if (s < 0).any() else 9.99
                    yearly.append(dict(시나리오=tag, 연도=int(yr), 진입수=len(s), PF=round(pfy, 3), 순익=round(s.sum())))
            else:
                row = dict(시나리오=tag, d=d, ladder='ON' if ladder else 'OFF', 진입수=0, PF=0, 승률=0,
                           최종자본=int(cap), 수익률='0%', 파산='NO',
                           진입실패_SL없음=diag['no_sl'], TP없음=diag['no_tp'], SL게이트탈락=diag['sl_gate'])
            summary.append(row)
            print(f"  [{tag}] 진입{row['진입수']} PF={row['PF']} 자본{row['수익률']} 파산{row['파산']}")

    pd.DataFrame(summary).to_csv(os.path.join(HERE, "obtest_summary.csv"), index=False, encoding='utf-8-sig')
    pd.DataFrame(yearly).to_csv(os.path.join(HERE, "obtest_yearly.csv"), index=False, encoding='utf-8-sig')
    print("\n[save] obtest_trades_*.csv + obtest_summary.csv + obtest_yearly.csv (this subfolder) - all files")


if __name__ == "__main__":
    main()
