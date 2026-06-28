# -*- coding: utf-8 -*-
# [260627_02_OBOICharacter_Stg5_REVoiOBExit.py]
# OB Character 5단계 — ★REVoi + OB '청산' 오버레이 (캡틴 지시 2026-06-27 "둘 다").
#   캡틴 프레임: REVoi 보유 중 진행방향 전방 OB를 목표/익절로 사용(분할청산). 선행연구 "target=이전 swing 저저항".
#   진입 오버레이(Stg4)=무용(레버효과) 확정. 진입≠청산이라 청산은 마지막 확인.
#   ★무손상: BASE(REVoi 원래 fibstop 청산)=앵커 +1851.6% 재현. REVoiBot 무수정 호출(§8).
#   ★룩어헤드0: OB는 conf_time<et(진입전 확정), 청산경로는 et~xt 1m, target 도달시 그 가격 익절.
#   변형: BASE / OB_TP_full(전방OB 도달시 전량익절) / OB_TP_half(절반 OB익절+절반 REVoi청산).
import os, sys, json
from itertools import combinations
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))


def find_root():
    d = HERE
    for _ in range(7):
        if os.path.isdir(os.path.join(d, "08_BTC_Data")) and os.path.isdir(os.path.join(d, "04_공용엔진코드")):
            return d
        nd = os.path.dirname(d)
        if nd == d:
            break
        d = nd
    return r"D:\ML\RfRauto"


ROOT = find_root()
sys.path.insert(0, os.path.join(ROOT, "04_공용엔진코드", "engines"))
from path_finder import ensure_paths
ensure_paths()
import trendstack_signal_engine as TS
from fib_replay_1m import load_1m, load_funding
from REVoi_bot import REVoiBot

DATA = os.path.join(ROOT, "08_BTC_Data", "derived", "Merged_Data.csv")
PJSON = os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp", "back2tv_rev_winners.json")
OUTDIR = os.path.join(ROOT, "00_WorkHstr", "BackTest_Output", "260627_02_OBOICharacter_Stg5_REVoiOBExit")

SIZE_PCT, LEV = 75.0, 3.0
EXPOSURE = SIZE_PCT / 100.0 * LEV
REF_ANCHOR = 1851.6
OB_TF = 240
N_SWING = 5
ATR_PD = 14
MAX_OB_LOOKBACK = 10
MAX_AGE_DAYS = 30
COST = 0.0008
N_GROUPS, K_TEST = 6, 2


def extract_obs(g, atr):
    H = g["high"].values; L = g["low"].values; C = g["close"].values; O = g["open"].values
    idx = g.index; n = len(C)
    ph, pl = TS.pivots_lr(H, L, N_SWING, 1)
    ph_at = {k: v[1] for k, v in ph.items()}; pl_at = {k: v[1] for k, v in pl.items()}
    obs = []; last_ph = last_pl = np.nan
    for i in range(n):
        if i in ph_at: last_ph = ph_at[i]
        if i in pl_at: last_pl = pl_at[i]
        if not np.isnan(last_ph) and C[i] > last_ph:
            j = i
            while j >= max(0, i - MAX_OB_LOOKBACK) and not (C[j] < O[j]):
                j -= 1
            if j >= max(0, i - MAX_OB_LOOKBACK) and C[j] < O[j]:
                obs.append(dict(conf_time=idx[i], side=1, ob_lo=float(L[j]), ob_hi=float(H[j])))
            last_ph = np.nan
        if not np.isnan(last_pl) and C[i] < last_pl:
            j = i
            while j >= max(0, i - MAX_OB_LOOKBACK) and not (C[j] > O[j]):
                j -= 1
            if j >= max(0, i - MAX_OB_LOOKBACK) and C[j] > O[j]:
                obs.append(dict(conf_time=idx[i], side=-1, ob_lo=float(L[j]), ob_hi=float(H[j])))
            last_pl = np.nan
    return obs


def front_target(et64, side, entry, ob_t, ob_lo, ob_hi):
    """진행방향 전방 가장 가까운 OB 경계가(목표). 롱=위 저항 lo / 숏=아래 지지 hi. 룩어헤드0."""
    age_lim = et64 - np.timedelta64(MAX_AGE_DAYS, "D")
    m = (ob_t < et64) & (ob_t >= age_lim)
    if side == 1:
        m &= ob_lo > entry
        if not m.any():
            return None
        return float(ob_lo[m][np.argmin(ob_lo[m] - entry)])
    else:
        m &= ob_hi < entry
        if not m.any():
            return None
        return float(ob_hi[m][np.argmin(entry - ob_hi[m])])


def equity_mdd(rows):
    if not rows:
        return 0.0, 0.0
    cap = 10000.0; peak = cap; mdd = 0.0
    for _, re in sorted(rows, key=lambda x: x[0]):
        cap *= (1.0 + re); peak = max(peak, cap); mdd = min(mdd, cap / peak - 1.0)
    return 100.0 * (cap / 10000.0 - 1.0), 100.0 * mdd


def cpcv(rows):
    if len(rows) < 60:
        return None
    R = np.array([r for _, r in sorted(rows, key=lambda x: x[0])])
    groups = np.array_split(np.arange(len(R)), N_GROUPS)
    return np.array([np.prod(1 + R[np.concatenate([groups[g] for g in tg])]) - 1
                     for tg in combinations(range(N_GROUPS), K_TEST)])


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    p = json.load(open(PJSON))["REV_MDD25_36mo"]["p"]
    d1m = load_1m(); fund = load_funding()
    bot = REVoiBot(p)
    T = bot.make_trades(d1m, fund)
    print(f"[REVoi 거래] {len(T)}건 | config rev_tf={p['rev_tf']}", flush=True)
    R = T["R"].values
    base_ret = 100.0 * (np.prod(1 + R * EXPOSURE) - 1.0)
    print(f"[무손상] BASE 복리 = {base_ret:+.1f}% vs 앵커 {REF_ANCHOR}% "
          f"({'✅ 재현' if abs(base_ret - REF_ANCHOR) < 50 else '❌'})", flush=True)
    g = TS.resample_tf(d1m, OB_TF)
    atr = TS.compute_atr(g["high"].values, g["low"].values, g["close"].values, ATR_PD)
    obs = extract_obs(g, atr)
    ob_t = np.array([np.datetime64(o["conf_time"]) for o in obs])
    ob_lo = np.array([o["ob_lo"] for o in obs]); ob_hi = np.array([o["ob_hi"] for o in obs])
    od = np.argsort(ob_t); ob_t, ob_lo, ob_hi = ob_t[od], ob_lo[od], ob_hi[od]
    m_t = d1m.index.values; mH = d1m["high"].values; mL = d1m["low"].values
    # 각 거래: 전방 OB 목표 + ★고정% 익절 대조 도달 여부(et~xt 1m, 룩어헤드0)
    FIX_PCTS = [0.01, 0.02, 0.03, 0.04]
    hit_cnt = 0; dists = []
    recs = []   # (et, side, rb, r_full, r_half, {pct:r_fix})
    for _, tr in T.iterrows():
        et = tr["et"]; xt = tr["xt"]; side = int(tr["side"]); entry = float(tr["entry"]); rb = float(tr["R"])
        et64 = np.datetime64(et); xt64 = np.datetime64(xt)
        a = int(np.searchsorted(m_t, et64, "left")); b = int(np.searchsorted(m_t, xt64, "right"))
        sh = mH[a:b]; sl = mL[a:b]

        def reach(target):
            return bool((sh >= target).any()) if side == 1 else bool((sl <= target).any())

        tgt = front_target(et64, side, entry, ob_t, ob_lo, ob_hi)
        r_full = rb; r_half = rb
        if tgt is not None:
            dists.append(abs(tgt - entry) / entry)
            if reach(tgt):
                hit_cnt += 1
                r_tp = side * (tgt - entry) / entry - COST
                r_full = r_tp; r_half = 0.5 * r_tp + 0.5 * rb
        rfix = {}
        for pct in FIX_PCTS:
            ftgt = entry * (1 + side * pct)
            rfix[pct] = (pct - COST) if reach(ftgt) else rb     # 고정% 익절(같은 청산틀, OB 대신 거리고정)
        recs.append((et, side, rb, r_full, r_half, rfix))
    print(f"[전방OB 목표도달] {hit_cnt}/{len(T)} ({100*hit_cnt/len(T):.0f}%) | OB target 거리 중앙 {100*np.median(dists):.2f}%", flush=True)
    print("\n" + "=" * 74, flush=True)
    print(f"  {'변형':22s} {'36mo수익':>11s} {'MDD':>8s} {'CPCV중앙':>10s} {'CPCVp25':>10s}", flush=True)

    def show(nm, getter):
        rows = [(r[0], getter(r) * EXPOSURE) for r in recs]
        ret, mdd = equity_mdd(rows); cp = cpcv(rows)
        cmed = f"{100*np.median(cp):+.0f}%" if cp is not None else "n/a"
        cp25 = f"{100*np.percentile(cp,25):+.0f}%" if cp is not None else "n/a"
        print(f"  {nm:22s} {ret:+10.1f}% {mdd:7.1f}% {cmed:>10s} {cp25:>10s}", flush=True)

    show("BASE(REVoi청산)", lambda r: r[2])
    show("OB_TP_full(전량OB익절)", lambda r: r[3])
    show("OB_TP_half(절반분할)", lambda r: r[4])
    print("  --- ★대조: 고정% 익절(OB 대신 거리고정, 같은 청산틀) ---", flush=True)
    for pct in FIX_PCTS:
        show(f"FIX_{int(pct*100)}%익절", (lambda p: (lambda r: r[5][p]))(pct))
    print("\n" + "=" * 74, flush=True)
    print("[해석] ★OB_TP_full이 모든 FIX_x%보다 수익↑·MDD↓·p25↑면 = OB '위치'가 고유알파(진짜).", flush=True)
    print("       어떤 FIX가 OB_TP와 비슷/우위면 = OB 무관, 단지 '빨리 익절'이 REVoi보다 나은 것.", flush=True)


if __name__ == "__main__":
    main()
