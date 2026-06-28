# -*- coding: utf-8 -*-
# [260627_02_OBOICharacter_Stg4_REVoiOBOverlay.py]
# OB Character 4단계 — ★검증된 REVoi 봇 + OB 오버레이 (캡틴 지시 2026-06-27).
#   캡틴 프레임: REVoi 진입신호 시점에 '진행방향 전방의 OB'를 분석 → 돌파/저지 판단 →
#               사이징(분할진입의 1차=진입품질 필터) 조절. "불리진입 감량·유리진입 증량"의 OB 버전.
#   ★무손상: REVoiBot 무수정 호출(§8·§15.1) + BASE(균등사이징)=앵커 +1851.6% 재현 확인.
#   ★룩어헤드0: OB는 conf_time<et 인 것만(진입 전 확정), 전방=진행방향(롱=위 저항/숏=아래).
#   변형: BASE / AVOID_near / BOOST_near / AVOID_strong / BOOST_clear → REVoi 개선여부.
#   산출(§19): 변형별 36mo수익 + 분기 롱숏 + MDD + CPCV. 난수0.
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
OUTDIR = os.path.join(ROOT, "00_WorkHstr", "BackTest_Output", "260627_02_OBOICharacter_Stg4_REVoiOBOverlay")

# 앵커 사이징(run_gates와 동일)
SIZE_PCT, LEV = 75.0, 3.0
EXPOSURE = SIZE_PCT / 100.0 * LEV          # = 2.25
REF_ANCHOR = 1851.6

OB_TF = 240        # REVoi rev_tf=240(4h)와 동일
N_SWING = 5
ATR_PD = 14
MAX_OB_LOOKBACK = 10
NEAR_ATR = 1.5     # 전방 OB '가까움' 기준(ATR)
FAR_ATR = 3.0      # 전방 OB '멀음/공간넓음' 기준
MAX_AGE_DAYS = 30  # 전방 OB 최근성(생성 후 N일내)
MULT_DN, MULT_UP = 0.5, 1.5
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
                obs.append(dict(conf_time=idx[i], side=1, ob_lo=float(L[j]), ob_hi=float(H[j]), atr=float(atr[i])))
            last_ph = np.nan
        if not np.isnan(last_pl) and C[i] < last_pl:
            j = i
            while j >= max(0, i - MAX_OB_LOOKBACK) and not (C[j] > O[j]):
                j -= 1
            if j >= max(0, i - MAX_OB_LOOKBACK) and C[j] > O[j]:
                obs.append(dict(conf_time=idx[i], side=-1, ob_lo=float(L[j]), ob_hi=float(H[j]), atr=float(atr[i])))
            last_pl = np.nan
    return obs


def attach_liquidity(obs):
    """OB 생성시 OI/거래량 유동성(게이트용). Merged 별도 로드(volume·oi_change)."""
    d = pd.read_csv(DATA, usecols=["timestamp", "volume", "oi_change_1h_pct"])
    d["timestamp"] = pd.to_datetime(d["timestamp"], utc=True)
    d = d.set_index("timestamp").sort_index()
    r = d.resample(f"{OB_TF}min", label="left", closed="left")
    f = pd.DataFrame({"oi_chg1h": r["oi_change_1h_pct"].last(), "vol": r["volume"].sum()}).dropna()
    f["vol_ratio"] = f["vol"] / f["vol"].rolling(20).mean()
    for ob in obs:
        ct = ob["conf_time"]
        if ct in f.index:
            row = f.loc[ct]
            ob["liq"] = float(np.nan_to_num(abs(row["oi_chg1h"]), nan=0.0)) + float(np.nan_to_num(row["vol_ratio"], nan=0.0))
        else:
            ob["liq"] = np.nan
    vals = np.array([o["liq"] for o in obs if o["liq"] == o["liq"]])
    med = np.median(vals) if len(vals) else 0.0
    for ob in obs:
        ob["liq_hi"] = (ob["liq"] == ob["liq"]) and (ob["liq"] >= med)
    return obs


def front_ob(et, side, entry, ob_t, ob_lo, ob_hi, ob_atr, ob_strong):
    """진행방향 전방 가장 가까운 OB(룩어헤드0: conf_time<et, 최근 MAX_AGE_DAYS). 반환 (dist_atr, strong)."""
    et64 = np.datetime64(et)
    age_lim = et64 - np.timedelta64(MAX_AGE_DAYS, "D")
    m = (ob_t < et64) & (ob_t >= age_lim)
    if side == 1:
        m &= ob_lo > entry
        if not m.any():
            return None, False
        d = (ob_lo[m] - entry) / np.maximum(1e-9, ob_atr[m])
    else:
        m &= ob_hi < entry
        if not m.any():
            return None, False
        d = (entry - ob_hi[m]) / np.maximum(1e-9, ob_atr[m])
    k = int(np.argmin(d))
    return float(d[k]), bool(ob_strong[m][k])


def size_mult(variant, dist, strong):
    near = (dist is not None) and (dist < NEAR_ATR)
    clear = (dist is None) or (dist > FAR_ATR)
    if variant == "BASE": return 1.0
    if variant == "AVOID_near": return MULT_DN if near else 1.0
    if variant == "BOOST_near": return MULT_UP if near else 1.0
    if variant == "AVOID_strong": return MULT_DN if (near and strong) else 1.0
    if variant == "BOOST_clear": return MULT_UP if clear else 1.0
    return 1.0


def equity_mdd(rows):
    """rows=[(t, R_eff)]. 복리(capital*= 1+R_eff). 반환 (수익%, MDD%)."""
    if not rows:
        return 0.0, 0.0
    cap = 10000.0; peak = cap; mdd = 0.0
    for _, re in sorted(rows, key=lambda x: x[0]):
        cap *= (1.0 + re)
        peak = max(peak, cap)
        mdd = min(mdd, cap / peak - 1.0)
    return 100.0 * (cap / 10000.0 - 1.0), 100.0 * mdd


def cpcv(rows):
    if len(rows) < 60:
        return None
    R = np.array([r for _, r in sorted(rows, key=lambda x: x[0])])
    groups = np.array_split(np.arange(len(R)), N_GROUPS)
    rets = []
    for tg in combinations(range(N_GROUPS), K_TEST):
        idx = np.concatenate([groups[g] for g in tg])
        seg = R[idx]
        rets.append(np.prod(1 + seg) - 1)
    return np.array(rets)


def quarterly(trades):
    d = pd.DataFrame(trades, columns=["t", "side", "R_eff"])
    d["t"] = pd.to_datetime(d["t"], utc=True)
    d["q"] = d["t"].dt.to_period("Q").astype(str)
    out = []
    for q, gq in d.groupby("q"):
        row = {"분기": q, "거래": len(gq)}
        for nm, s in [("롱", 1), ("숏", -1)]:
            sub = gq[gq["side"] == s]
            row[f"{nm}_거래"] = len(sub)
            row[f"{nm}_수익%"] = round(100 * ((1 + sub["R_eff"]).prod() - 1), 1) if len(sub) else 0.0
        out.append(row)
    return pd.DataFrame(out)


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    p = json.load(open(PJSON))["REV_MDD25_36mo"]["p"]
    print(f"[REVoi config] {p}", flush=True)
    d1m = load_1m(); fund = load_funding()
    print(f"[데이터] d1m {len(d1m):,}행 {d1m.index[0]} ~ {d1m.index[-1]}", flush=True)
    bot = REVoiBot(p)
    T = bot.make_trades(d1m, fund)
    print(f"[REVoi 거래] {len(T)}건", flush=True)
    # 앵커 재현(무손상): BASE 복리
    R = T["R"].values
    base_ret = 100.0 * (np.prod(1 + R * EXPOSURE) - 1.0)
    diff = base_ret - REF_ANCHOR
    print(f"[무손상] BASE 복리 = {base_ret:+.1f}% vs 앵커 {REF_ANCHOR:+.1f}% (차 {diff:+.1f}%p) "
          f"{'✅ 재현' if abs(diff) < 50 else '❌ 불일치-중단검토'}", flush=True)
    # OB 추출
    g = TS.resample_tf(d1m, OB_TF)
    atr = TS.compute_atr(g["high"].values, g["low"].values, g["close"].values, ATR_PD)
    obs = extract_obs(g, atr)
    obs = attach_liquidity(obs)
    ob_t = np.array([np.datetime64(o["conf_time"]) for o in obs])
    ob_lo = np.array([o["ob_lo"] for o in obs]); ob_hi = np.array([o["ob_hi"] for o in obs])
    ob_atr = np.array([o["atr"] for o in obs]); ob_strong = np.array([o["liq_hi"] for o in obs])
    order = np.argsort(ob_t)
    ob_t, ob_lo, ob_hi, ob_atr, ob_strong = ob_t[order], ob_lo[order], ob_hi[order], ob_atr[order], ob_strong[order]
    print(f"[OB] {len(obs)}개 (4h)", flush=True)
    # 각 거래 전방 OB
    fronts = []
    near_cnt = 0
    for _, tr in T.iterrows():
        dist, strong = front_ob(tr["et"], int(tr["side"]), float(tr["entry"]),
                                 ob_t, ob_lo, ob_hi, ob_atr, ob_strong)
        fronts.append((dist, strong))
        if dist is not None and dist < NEAR_ATR:
            near_cnt += 1
    print(f"[전방OB] 진입 전방 {NEAR_ATR}ATR내 OB 있는 거래 {near_cnt}/{len(T)} ({100*near_cnt/len(T):.0f}%)", flush=True)
    # 변형별 백테
    VARIANTS = ["BASE", "AVOID_near", "BOOST_near", "AVOID_strong", "BOOST_clear"]
    print("\n" + "=" * 76, flush=True)
    print(f"  {'변형':14s} {'거래':>5s} {'36mo수익':>11s} {'MDD':>8s} {'CPCV중앙':>10s} {'CPCVp25':>10s} {'평균노출':>7s}", flush=True)
    all_q = []
    boost_exp = 1.0
    print("  (★p25/노출 = 노출정규화 risk-adj. 이게 BASE와 비슷하면 '레버효과', 높으면 'OB 선택알파')", flush=True)
    for v in VARIANTS:
        rows = []; trades = []; mults = []
        for (dist, strong), (_, tr) in zip(fronts, T.iterrows()):
            mult = size_mult(v, dist, strong)
            mults.append(mult)
            r_eff = float(tr["R"]) * EXPOSURE * mult
            rows.append((tr["et"], r_eff)); trades.append((tr["et"], int(tr["side"]), r_eff))
        ret, mdd = equity_mdd(rows)
        cp = cpcv(rows)
        avg_m = np.mean(mults)
        if v == "BOOST_near":
            boost_exp = avg_m
        cmed = f"{100*np.median(cp):+.0f}%" if cp is not None else "n/a"
        p25 = 100 * np.percentile(cp, 25) if cp is not None else float("nan")
        radj = p25 / avg_m if avg_m else float("nan")
        print(f"  {v:14s} {len(rows):5d} {ret:+10.1f}% {mdd:7.1f}% {cmed:>10s} {p25:+8.0f}% {avg_m:6.2f}x  risk-adj {radj:+6.0f}", flush=True)
        q = quarterly(trades); q.insert(0, "변형", v); all_q.append(q)
    # ★노출통제: BOOST_near 평균노출로 BASE 균등 → BOOST_near와 같으면 'OB 선택 무가치(레버효과)'
    rows_c = [(tr["et"], float(tr["R"]) * EXPOSURE * boost_exp) for _, tr in T.iterrows()]
    ret_c, mdd_c = equity_mdd(rows_c); cp_c = cpcv(rows_c)
    p25_c = 100 * np.percentile(cp_c, 25)
    print(f"  {'BASE_x'+format(boost_exp,'.2f'):14s} {len(rows_c):5d} {ret_c:+10.1f}% {mdd_c:7.1f}% "
          f"{100*np.median(cp_c):+9.0f}% {p25_c:+8.0f}% {boost_exp:6.2f}x  ← ★노출통제(균등)", flush=True)
    print(f"  ▶ 판정: BOOST_near vs BASE_x{boost_exp:.2f} 비교 → 수익·p25 비슷하면 OB선택 무가치(레버효과), "
          f"BOOST_near 우위면 OB 선택알파", flush=True)
    out = pd.concat(all_q, ignore_index=True)
    csv = os.path.join(OUTDIR, "260627_02_OBOICharacter_Stg4_quarterly.csv")
    out.to_csv(csv, index=False, encoding="utf-8-sig")
    print("\n" + "=" * 76, flush=True)
    print(f"[산출] 분기별 수익표: {csv}", flush=True)
    print("[해석] 변형이 BASE보다 수익↑ 또는 MDD↓(특히 CPCV p25↑)면 = OB 오버레이가 REVoi 개선.", flush=True)
    print("       전부 BASE와 비슷/열위면 = 전방 OB는 REVoi 진입품질에 무용(OI/OB 사이징 기각).", flush=True)


if __name__ == "__main__":
    main()
