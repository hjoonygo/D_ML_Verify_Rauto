# -*- coding: utf-8 -*-
# [FILE] test.py  (04FromAll_IDEA4Concept_Ch3_PullbackEntryDist_stg1)
# CODE LENGTH: approx 290 lines | INTERNAL VER: pullback_entrydist_v1 | full output, no omission
#
# [PURPOSE / 목적]
#   검증된 두 자산을 결합한다:
#     (1) 진입 = SpTrd_Fib식 '눌림목'(추세 중 되돌림에서 진입). 양방향(롱·숏).
#     (2) 청산 = InfraA_V3_stg2 엔진(OB계단 + 1차익절REDUCE + 피보락인 + 눌림목재설정 + gap_guard).
#   진입 '시점'만 4칸으로 비교한다 (청산엔진은 고정 = 한 번에 한 로직):
#     E0 즉시 / E1 거리확보(가) / E2 대기(나) / E3 결합
#   거리 임계는 ATR배수와 % 둘 다 스윕. 롱/숏 분리 집계.
#
# [방향 일반화] DIR: 롱=+1, 숏=-1. 모든 가격비교를 DIR로 일반화.
#   숏 원본엔진(InfraA_V3_stg2)을 부호대칭으로 양방향화. 숏칸은 원본과 수치 일치해야 함(자기검증).
#
# [거리확보(가) E1] 진입 직전, 진입가와 1차 SL(위 OB; 롱은 아래 OB)의 거리 >= 임계일 때만 진입.
# [대기(나) E2] 눌림 신호 후, 가격이 신호가에서 DIR 반대로 임계만큼 더 가면 그때 진입(눌림 심화 대기).
#              waitMax 봉 안에 조건 미충족 시 신호 취소(만료).
# [E3] (가) AND (나) 동시.
#
# [LOOKAHEAD GUARD] 피벗·OB는 확정시각 이후만 사용(searchsorted right). 진입은 신호확정 '다음 봉'부터.
#   청산은 진입 후 봉만. 미래봉 직접참조 없음.
# [SPEED] 피벗/OB/ATR/eh 1회 사전계산. 진입후보 1회 수집 후 칸×임계만 재평가(저비용).
#
# [PATH] D:\ML\verify\04FromAll_IDEA4Concept_Ch3_PullbackEntryDist_stg1\ 실행, 데이터 상위.
# [DATA] ../Merged_Data_with_Regime_Features.csv  (필요컬럼: timestamp,open,high,low,close,feat_struct_8)
# [OUTPUT] entrydist_summary.csv (칸×임계×방향) + entrydist_trades.csv (거래별)
#
# [FUNCTIONS In/Out]
#   find_data()->path ; load_data(path)->df
#   resample_tf / precompute_tf_pivots / nearest_above / levels_below_5m / build_tps  [InfraA 원본 검증]
#   compute_atr(df, n)->atr(1m 배열)                                  (거리확보 ATR 기준)
#   collect_pullbacks(df)->[(e_idx, DIR, bl_raw, sig_price, atr)]     (양방향 눌림목 신호 수집)
#   exec_check_exit(price, bs, params)->action                        (InfraA 엔진 DIR 일반화)
#   simulate_one(arrays, eh, e_idx, DIR, bl_raw, guard_mode)->(R,reason,xidx,funding)
#   apply_entry_gate(cand, mode, thr_kind, thr_val, arrays, atr)->e_idx or None  (4칸 진입게이트)
# ==============================================================================

import os, sys, time
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)

# ---- 설정 (InfraA_V3_stg2 계승) ----
REGIME_COL = 'feat_struct_8'
W_TF = 3; SL_TF = 60; TP_TF = 5
SL_GATE = 0.0016; D_FIX = 5; N_OB = 5
LEVERAGE = 5; LIQ_MOVE = 0.20
COST = 0.0004
FIB_TRIGGER = 15.0; FIB_EXT = 0.65; HARD_FLOOR_ROE = 15.0
GUARD_MULT = 1.0 + HARD_FLOOR_ROE / 100.0 / LEVERAGE
START_CAP = 10000.0
HARD_CAP_BARS = 60 * 24 * 7    # 보유 상한 7일(=10,080봉). 원본90일→7일로 축소(성능). 그 이상은 펀딩으로 죽음
TRAIN_YEARS = [2023, 2024]; TEST_YEARS = [2025, 2026]
FUND_8H = 0.0001
ATR_LEN = 60                      # 1분봉 ATR 길이(거리확보 기준)
WAIT_MAX = 60 * 8                 # 대기(나) 만료: 8시간(분봉) 안에 미충족이면 취소
GUARD_MODE = 'tight'              # 청산엔진 고정(검증된 보호선)

# 진입 4칸 × 임계 스윕(ATR배수 + % 둘 다)
ENTRY_CELLS = ['E0_now', 'E1_dist', 'E2_wait', 'E3_both']
THRESHOLDS = [('atr', 0.5), ('atr', 1.0), ('atr', 1.5), ('pct', 0.3), ('pct', 0.5), ('pct', 1.0)]


def find_data():
    for p in [os.path.join(PARENT, "Merged_Data_with_Regime_Features.csv"),
              os.path.join(PARENT, "merged_data.csv"),
              os.path.join(HERE, "Merged_Data_with_Regime_Features.csv")]:
        if os.path.exists(p):
            return p
    raise FileNotFoundError("Merged_Data_with_Regime_Features.csv (상위 D:\\ML\\verify)")


def load_data(path):
    head = pd.read_csv(path, nrows=5)
    if REGIME_COL not in head.columns:
        raise KeyError(f"{REGIME_COL} 없음. 컬럼: {list(head.columns)[:12]}")
    cols = ['timestamp', 'open', 'high', 'low', 'close', REGIME_COL]
    df = pd.read_csv(path, usecols=cols)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    if df['timestamp'].dt.tz is not None:
        df['timestamp'] = df['timestamp'].dt.tz_localize(None)
    df = df.sort_values('timestamp').reset_index(drop=True)
    df = df.set_index('timestamp')
    return df


# ----- OB/피벗 (InfraA_V3_stg2 원본, 검증) -----
def resample_tf(df1m, tf_min):
    r = df1m.resample(f'{tf_min}min').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'})
    return r.dropna()


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


def nearest_below(price, ts, hpc, hpt, hpb):
    """롱용: price 아래 가장 가까운 OB(위 OB의 대칭). top<price 중 최댓값."""
    k = np.searchsorted(hpc, np.datetime64(ts), side='right')
    if k == 0:
        return None
    bots = hpb[:k]; tops = hpt[:k]; cand = tops < price
    if not cand.any():
        return None
    bb = bots[cand]; tt = tops[cand]; j = np.argmax(tt)
    return (float(tt[j]), float(bb[j]))


def levels_dir(price, ts, lpc, lpt, lpb, n, DIR):
    """TP용 OB n개. 숏(DIR=-1): price 아래(top<price), 높은 순. 롱(DIR=+1): price 위(bottom>price), 낮은 순."""
    k = np.searchsorted(lpc, np.datetime64(ts), side='right')
    if k == 0:
        return []
    tops = lpt[:k]; bots = lpb[:k]
    if DIR < 0:
        cand = tops < price
        if not cand.any():
            return []
        tt = tops[cand]; bb = bots[cand]; order = np.argsort(-tt)
    else:
        cand = bots > price
        if not cand.any():
            return []
        tt = tops[cand]; bb = bots[cand]; order = np.argsort(bb)
    return [(float(tt[o]), float(bb[o])) for o in order[:n]]


def build_tps(bl_raw, price, sign, DIR):
    """목표가 재구성. DIR 방향으로 price보다 유리한 쪽만 채택.
    sign: TP트리거 미세조정(+1 바닥+5bp / -1 바닥-5bp), DIR: 방향."""
    out = []
    for (t, b) in bl_raw:
        if DIR < 0:
            mean = b * (1 + sign * D_FIX / 1e4)
            if mean < price:
                out.append({'top': t, 'bottom': b, 'mean': mean})
        else:
            mean = t * (1 - sign * D_FIX / 1e4)
            if mean > price:
                out.append({'top': t, 'bottom': b, 'mean': mean})
    return out


def compute_atr(df, n):
    h = df['high'].values; l = df['low'].values; c = df['close'].values
    pc = np.empty_like(c); pc[0] = c[0]; pc[1:] = c[:-1]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    atr = pd.Series(tr).rolling(n, min_periods=1).mean().values
    return atr


# ----- 청산엔진 (InfraA_V3_stg2 exec_check_exit DIR 일반화) -----
def exec_check_exit(price, bs, params):
    """DIR 일반화. 숏(DIR=-1)은 원본과 동일 동작. 롱(DIR=+1)은 부호 대칭.
    내부적으로 '수익방향'을 d = DIR*(entry-price)>0 으로 통일."""
    entry = bs['entry_price']; lev = params['leverage']; DIR = bs['DIR']; ti = bs['target_idx']
    # 진입가 대비 가격이 '불리하게' 갔는가 = adverse>0
    adverse = DIR * (price - entry)          # 숏: price>entry면 +(불리) / 롱: price<entry면 +(불리)
    # (1) 구멍 하드플로어: 보호스탑 없을 때(1차OB 닿기 전)만
    if bs['fib_stop'] is None:
        if adverse >= entry * (params['hard_floor_roe'] / 100.0 / lev):
            return {"action": "CLOSE", "reason": "hole_hardfloor"}
    # (2) 빈구간 보호선: REDUCE 후 & 피보 미발동
    gm = params['guard_mode']
    if gm != 'off' and bs['reduced'] and not bs['fib_active']:
        g_adv = entry * (HARD_FLOOR_ROE / 100.0 / lev)     # +3% 상당
        if gm == 'tight' and bs['last_ob_top'] is not None:
            # 직전 OB 경계까지로 더 타이트하게
            ob_adv = DIR * (bs['last_ob_top'] - entry)
            if ob_adv > 0:
                g_adv = min(g_adv, ob_adv)
        if adverse >= g_adv:
            return {"action": "CLOSE", "reason": "gap_guard"}
    bull = bs['bullish_obs']
    if ti < len(bull):
        tob = bull[ti]
        favor = DIR * (tob['mean'] - price)   # 목표를 유리방향으로 통과?
        if favor >= 0:
            bs['fib_stop'] = tob['top']; bs['last_ob_top'] = tob['top']; bs['target_idx'] += 1
            if bs['remaining_pct'] == 1.0:
                bs['remaining_pct'] = 0.5; bs['reduced'] = True
                return {"action": "REDUCE", "reason": "reduce"}
            return {"action": "HOLD", "reason": "Nth"}
        if bs['fib_stop'] is not None and DIR * (price - bs['fib_stop']) >= 0:
            return {"action": "CLOSE", "reason": "OB_edge"}
    else:
        # 피보 구간: extreme = 가장 유리했던 가격
        roe = adverse_to_roe(DIR, entry, price, lev, favor=True)
        max_roe = adverse_to_roe(DIR, entry, bs['fib_extreme'], lev, favor=True)
        if DIR * (price - bs['fib_extreme']) < 0:   # 더 유리한 극값 갱신
            if bs['pulled_back']:
                bs['fib_wave_start'] = bs['fib_extreme']; bs['pulled_back'] = False
            bs['fib_extreme'] = price
        elif DIR * (price - bs['fib_extreme']) > 0:  # 되돌림
            bs['pulled_back'] = True
        if roe >= params['fib_trigger_roe'] or max_roe >= params['fib_trigger_roe']:
            downswing = DIR * (bs['fib_wave_start'] - bs['fib_extreme'])   # 유리방향 파동크기(+)
            fib_lock = bs['fib_wave_start'] - DIR * downswing * params['fib_ext_pct']
            prev = bs.get('fib_stop', None)
            if prev is None:
                bs['fib_stop'] = fib_lock
            else:
                # 유리방향으로 더 바짝(숏:더 낮게 min / 롱:더 높게 max)
                bs['fib_stop'] = min(prev, fib_lock) if DIR < 0 else max(prev, fib_lock)
            bs['fib_active'] = True
            if DIR * (price - bs['fib_stop']) >= 0:
                return {"action": "CLOSE", "reason": "Fibonacci"}
    return {"action": "HOLD", "reason": "hold"}


def adverse_to_roe(DIR, entry, price, lev, favor=True):
    """유리방향 ROE% (favor 수익률). 숏: (entry-price)/entry, 롱: (price-entry)/entry."""
    return (DIR * (entry - price) / entry) * lev * 100.0


def n_funding_8h(eh_in, eh_out):
    return max(0, int(eh_out // 8) - int(eh_in // 8))


def simulate_one(arrays, eh, e_idx, DIR, bl_raw, guard_mode):
    o, h, l, c, idx = arrays
    entry = c[e_idx]
    tps = build_tps(bl_raw, entry, +1, DIR)
    bs = {'entry_price': entry, 'DIR': DIR, 'remaining_pct': 1.0, 'target_idx': 0,
          'fib_wave_start': entry, 'fib_extreme': entry, 'pulled_back': False, 'fib_stop': None,
          'bullish_obs': tps, 'reduced': False, 'fib_active': False, 'last_ob_top': None}
    params = {'leverage': LEVERAGE, 'fib_trigger_roe': FIB_TRIGGER, 'fib_ext_pct': FIB_EXT,
              'hard_floor_roe': HARD_FLOOR_ROE, 'guard_mode': guard_mode}
    frac = 1.0; reduced = False; R = 0.0
    n = len(c); end_idx = min(n, e_idx + 1 + HARD_CAP_BARS)
    # ★최적화: 불리방향 강제청산 도달 시점을 numpy로 미리 찾아 루프 상한 단축
    seg_h = h[e_idx + 1:end_idx]; seg_l = l[e_idx + 1:end_idx]
    if DIR < 0:   # 숏: price(고가)가 entry*1.20 이상이면 강제청산
        hit = np.where(seg_h >= entry * (1 + LIQ_MOVE))[0]
    else:         # 롱: price(저가)가 entry*0.80 이하이면 강제청산
        hit = np.where(seg_l <= entry * (1 - LIQ_MOVE))[0]
    if len(hit) > 0:
        end_idx = min(end_idx, e_idx + 1 + int(hit[0]) + 1)   # 강제청산 봉까지만
    xi = end_idx - 1
    for i in range(e_idx + 1, end_idx):
        o_, h_, l_, c_ = o[i], h[i], l[i], c[i]
        ticks = (o_, h_, l_, c_) if c_ < o_ else (o_, l_, h_, c_)
        for price in ticks:
            adverse = DIR * (price - entry)              # 불리방향 이동(+면 손실쪽)
            if adverse >= entry * LIQ_MOVE:              # 강제청산: 불리방향 20% 도달
                fp = frac * FUND_8H * n_funding_8h(eh[e_idx], eh[i])
                R += frac * (DIR * (entry - price) / entry) - frac * COST * 2 - fp
                return R, 'liq', i, fp
            sig = exec_check_exit(price, bs, params); act = sig['action']
            if act == 'REDUCE' and not reduced:
                R += 0.5 * (DIR * (entry - price) / entry) - 0.5 * COST * 2; frac = 0.5; reduced = True; continue
            if act == 'CLOSE':
                fp = frac * FUND_8H * n_funding_8h(eh[e_idx], eh[i])
                R += frac * (DIR * (entry - price) / entry) - frac * COST * 2 - fp
                return R, sig['reason'], i, fp
    fp = frac * FUND_8H * n_funding_8h(eh[e_idx], eh[xi])
    R += frac * (DIR * (entry - c[xi]) / entry) - frac * COST * 2 - fp
    return R, 'max_hold', xi, fp


def collect_pullbacks(df):
    """양방향 눌림목 신호 수집.
    uptrend + 새 저점(되돌림 저점) -> 롱 후보 / downtrend + 새 고점(되돌림 고점) -> 숏 후보.
    각 후보에 1차 SL OB(롱:아래 nearest_below, 숏:위 nearest_above)와 TP OB(levels_dir) 부착."""
    o = df['open'].values; h = df['high'].values; l = df['low'].values; c = df['close'].values
    idx = df.index; reg = df[REGIME_COL].astype(str).values
    atr = compute_atr(df, ATR_LEN)
    hpc, lpc_h, hpt, hpb, lpt_h, lpb_h = precompute_tf_pivots(resample_tf(df, SL_TF), W_TF, SL_TF)
    _, lpc, _, _, lpt, lpb = precompute_tf_pivots(resample_tf(df, TP_TF), W_TF, TP_TF)
    # 5m 피벗 확정시각으로 '새 저점/새 고점' 신호 시점 산출
    cands = []
    n = len(c)
    # 새 저점(롱 트리거) 시각 = lpc(5m 저점 확정시각), 새 고점(숏 트리거) = (5m 고점 확정시각)
    hpc5, lpc5, hpt5, hpb5, lpt5, lpb5 = precompute_tf_pivots(resample_tf(df, TP_TF), W_TF, TP_TF)
    # 각 1분봉 인덱스로 매핑
    ts_all = idx.values
    def to_iidx(tarr):
        return np.searchsorted(ts_all, tarr, side='left')
    low_sig = to_iidx(lpc5)   # 새 저점 확정 봉
    high_sig = to_iidx(hpc5)  # 새 고점 확정 봉
    # 롱 후보: uptrend 구간의 새 저점
    for t0 in low_sig:
        if t0 <= 0 or t0 >= n - 1:
            continue
        if reg[t0] != 'uptrend':
            continue
        price = c[t0]; ts = idx[t0]
        sl_ob = nearest_below(price, ts, hpc, hpt, hpb)   # 롱 SL = 아래 OB
        tp_ob = levels_dir(price, ts, lpc, lpt, lpb, N_OB, +1)
        if sl_ob is None or len(tp_ob) == 0:
            continue
        sl_mean = (sl_ob[0] + sl_ob[1]) / 2.0; sl_dist = (price - sl_mean) / price
        if sl_dist < SL_GATE:
            continue
        if build_tps(tp_ob, price, +1, +1):
            cands.append((t0, +1, tp_ob, price, atr[t0], sl_mean))
    # 숏 후보: downtrend 구간의 새 고점
    for t0 in high_sig:
        if t0 <= 0 or t0 >= n - 1:
            continue
        if reg[t0] != 'downtrend':
            continue
        price = c[t0]; ts = idx[t0]
        sl_ob = nearest_above(price, ts, hpc, hpt, hpb)   # 숏 SL = 위 OB
        tp_ob = levels_dir(price, ts, lpc, lpt, lpb, N_OB, -1)
        if sl_ob is None or len(tp_ob) == 0:
            continue
        sl_mean = (sl_ob[0] + sl_ob[1]) / 2.0; sl_dist = (sl_mean - price) / price
        if sl_dist < SL_GATE:
            continue
        if build_tps(tp_ob, price, +1, -1):
            cands.append((t0, -1, tp_ob, price, atr[t0], sl_mean))
    cands.sort(key=lambda x: x[0])
    return cands, (o, h, l, c, idx)


def apply_entry_gate(cand, mode, thr_kind, thr_val, arrays):
    """4칸 진입게이트. 반환: 실제 진입 e_idx 또는 None(무효).
    cand=(t0,DIR,tp_ob,sig_price,atr,sl_mean)."""
    t0, DIR, tp_ob, sig_price, atr0, sl_mean = cand
    o, h, l, c, idx = arrays
    n = len(c)
    # 임계 거리(가격 단위)
    thr_dist = (atr0 * thr_val) if thr_kind == 'atr' else (sig_price * thr_val / 100.0)
    if mode == 'E0_now':
        return t0
    if mode == 'E1_dist':
        # 거리확보(가): 진입가와 SL의 거리 >= 임계일 때만 진입(신호봉에서 즉시)
        sl_gap = abs(sig_price - sl_mean)
        return t0 if sl_gap >= thr_dist else None
    if mode == 'E2_wait':
        # 대기(나): 신호 후 가격이 '불리(눌림 심화)' 방향으로 임계만큼 더 가면 그 봉에서 진입
        #   롱(DIR+1): 가격이 더 내려가 sig-thr 도달 / 숏(DIR-1): 더 올라가 sig+thr 도달
        target = sig_price - DIR * thr_dist
        end = min(n, t0 + 1 + WAIT_MAX)
        for i in range(t0 + 1, end):
            if DIR > 0 and l[i] <= target:
                return i
            if DIR < 0 and h[i] >= target:
                return i
        return None  # 만료
    if mode == 'E3_both':
        sl_gap = abs(sig_price - sl_mean)
        if sl_gap < thr_dist:
            return None
        target = sig_price - DIR * thr_dist
        end = min(n, t0 + 1 + WAIT_MAX)
        for i in range(t0 + 1, end):
            if DIR > 0 and l[i] <= target:
                return i
            if DIR < 0 and h[i] >= target:
                return i
        return None
    return None


def year_of(ts):
    return ts.year


def main():
    t_start = time.time()
    open(os.path.join(HERE, ".run_start"), 'w').close()
    df = load_data(find_data())
    eh = ((df.index.values - df.index.values[0]) / np.timedelta64(1, 'h')).astype(float)
    cands, arrays = collect_pullbacks(df)
    o, h, l, c, idx = arrays
    print(f"[수집] 눌림목 후보 {len(cands)}건 (롱 {sum(1 for x in cands if x[1]>0)} / 숏 {sum(1 for x in cands if x[1]<0)})")

    rows = []; trade_rows = []
    # ★최적화: 같은 e_idx 진입은 결과가 동일 → 캐시(메모이제이션). 중복 시뮬 제거.
    sim_cache = {}   # e_idx -> (R, reason)
    def get_sim(e_idx, DIR, bl_raw):
        hit = sim_cache.get(e_idx)
        if hit is not None:
            return hit
        R, reason, xi, fp = simulate_one(arrays, eh, e_idx, DIR, bl_raw, GUARD_MODE)
        sim_cache[e_idx] = (R, reason)
        return (R, reason)

    for mode in ENTRY_CELLS:
        for thr_kind, thr_val in THRESHOLDS:
            if mode == 'E0_now' and not (thr_kind == 'atr' and thr_val == 0.5):
                continue
            agg = {}
            seen = set()   # (DIR, e_idx) 중복 진입 방지 — 단일포지션 원칙(같은봉 같은방향 1회)
            for cand in cands:
                e_idx = apply_entry_gate(cand, mode, thr_kind, thr_val, arrays)
                if e_idx is None or e_idx >= len(c) - 1:
                    continue
                DIR = cand[1]; bl_raw = cand[2]
                if (DIR, e_idx) in seen:
                    continue
                seen.add((DIR, e_idx))
                R, reason = get_sim(e_idx, DIR, bl_raw)
                ts = idx[e_idx]; yr = ts.year
                span = 'train' if yr in TRAIN_YEARS else ('test' if yr in TEST_YEARS else 'other')
                dlab = 'LONG' if DIR > 0 else 'SHORT'
                for key in [(dlab, 'ALL'), (dlab, span), ('BOTH', 'ALL'), ('BOTH', span)]:
                    agg.setdefault(key, []).append(R)
                if mode == 'E3_both' and thr_kind == 'atr' and thr_val == 1.0:
                    trade_rows.append({'mode': mode, 'thr': f'{thr_kind}{thr_val}', 'dir': dlab,
                                       '진입시간': ts.strftime('%Y-%m-%d %H:%M:%S'),
                                       'R': round(R, 4), '청산사유': reason})
            label = 'E0_now' if mode == 'E0_now' else f'{mode}_{thr_kind}{thr_val}'
            for (dlab, span), Rs in agg.items():
                arr = np.array(Rs)
                wins = arr[arr > 0]; losses = arr[arr < 0]
                pf = (wins.sum() / abs(losses.sum())) if losses.sum() != 0 else (99.0 if wins.sum() > 0 else 0.0)
                cum = arr.sum() * 100.0
                rows.append({'설정': label, '방향': dlab, '구간': span, '거래수': len(arr),
                             '승률_pct': round((arr > 0).mean() * 100, 1) if len(arr) else 0,
                             '누적R_pct': round(cum, 2), 'PF': round(pf, 3),
                             '평균R_pct': round(arr.mean() * 100, 3) if len(arr) else 0,
                             '최악R_pct': round(arr.min() * 100, 2) if len(arr) else 0})

    summ = pd.DataFrame(rows)
    summ.to_csv(os.path.join(HERE, "entrydist_summary.csv"), index=False, encoding='utf-8-sig')
    pd.DataFrame(trade_rows).to_csv(os.path.join(HERE, "entrydist_trades.csv"), index=False, encoding='utf-8-sig')
    print(f"[완료] {time.time()-t_start:.1f}s | summary {len(summ)}행 -> entrydist_summary.csv")
    # 콘솔 미리보기(BOTH/ALL만)
    prev = summ[(summ['방향'] == 'BOTH') & (summ['구간'] == 'ALL')].sort_values('누적R_pct', ascending=False)
    print(prev.head(12).to_string(index=False))


if __name__ == "__main__":
    main()
