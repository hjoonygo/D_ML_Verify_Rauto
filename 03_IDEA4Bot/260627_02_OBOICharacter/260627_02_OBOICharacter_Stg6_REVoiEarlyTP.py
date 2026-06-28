# -*- coding: utf-8 -*-
# [260627_02_OBOICharacter_Stg6_REVoiEarlyTP.py]
# 부수발견 검증 — REVoi '일찍 익절'(+9785% FIX_1%)이 과적합인가 (캡틴 지시 2026-06-27).
#   ★OB 무관(Stg5서 OB는 고정%보다 열위로 사망). 순수 '청산 익절거리' 효과 정직검증.
#   점검: ① 익절% 스윕(칼날 vs plateau) ② held-out OOS(train최적→test) ③ 승률·손익분해(이익컷손실런 위험)
#         ④ 대칭손절 대조(손실런 분리).
#   ★무손상: BASE(REVoi 원래청산)=앵커 +1851.6%. ★룩어헤드0: et~xt 1m, 익절/손절 limit·동시 손실우선.
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
from fib_replay_1m import load_1m, load_funding
from REVoi_bot import REVoiBot

PJSON = os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp", "back2tv_rev_winners.json")
OUTDIR = os.path.join(ROOT, "00_WorkHstr", "BackTest_Output", "260627_02_OBOICharacter_Stg6_REVoiEarlyTP")

EXPOSURE = 0.75 * 3.0
REF_ANCHOR = 1851.6
COST = 0.0008
PCTS = [0.005, 0.0075, 0.01, 0.0125, 0.015, 0.02, 0.025, 0.03]
TRAIN_END = np.datetime64("2024-12-31")
N_GROUPS, K_TEST = 6, 2


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


def total_ret(rows):
    return 100.0 * (np.prod([1 + r for _, r in rows]) - 1.0)


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    p = json.load(open(PJSON))["REV_MDD25_36mo"]["p"]
    d1m = load_1m(); fund = load_funding()
    T = REVoiBot(p).make_trades(d1m, fund)
    rb_all = T["R"].values
    base_ret = 100.0 * (np.prod(1 + rb_all * EXPOSURE) - 1.0)
    print(f"[REVoi] {len(T)}건 | [무손상] BASE {base_ret:+.1f}% vs 앵커 {REF_ANCHOR}% "
          f"({'OK' if abs(base_ret-REF_ANCHOR)<50 else 'X'})", flush=True)
    m_t = d1m.index.values; mH = d1m["high"].values; mL = d1m["low"].values

    # 각 거래 사전계산: et, xt, side, entry, rb, 그리고 각 pct 익절/손절 도달
    rec = []
    for _, tr in T.iterrows():
        et64 = np.datetime64(tr["et"]); xt64 = np.datetime64(tr["xt"])
        side = int(tr["side"]); entry = float(tr["entry"]); rb = float(tr["R"])
        a = int(np.searchsorted(m_t, et64, "left")); b = int(np.searchsorted(m_t, xt64, "right"))
        sh = mH[a:b]; sl = mL[a:b]
        hit_tp = {}; hit_sl = {}
        for pct in PCTS:
            up = entry * (1 + pct); dn = entry * (1 - pct)
            if side == 1:
                hit_tp[pct] = bool((sh >= up).any()); hit_sl[pct] = bool((sl <= dn).any())
            else:
                hit_tp[pct] = bool((sl <= dn).any()); hit_sl[pct] = bool((sh >= up).any())
        rec.append(dict(et=tr["et"], et64=et64, side=side, rb=rb, hit_tp=hit_tp, hit_sl=hit_sl))

    def fix_rows(pct, subset=None):
        """익절 pct 도달→+pct-COST, 미도달→rb (이익컷·손실런). subset=train/test 필터."""
        out = []
        for r in rec:
            if subset == "train" and not (r["et64"] <= TRAIN_END): continue
            if subset == "test" and not (r["et64"] > TRAIN_END): continue
            re = (pct - COST) if r["hit_tp"][pct] else r["rb"]
            out.append((r["et"], re * EXPOSURE))
        return out

    def sym_rows(pct):
        """대칭손절 대조: 익절 pct vs 손절 pct, 동시=손실우선(보수). 둘다 미도달=rb."""
        out = []
        for r in rec:
            if r["hit_sl"][pct]:
                re = -pct - COST                         # 손절(동시 손실우선)
            elif r["hit_tp"][pct]:
                re = pct - COST
            else:
                re = r["rb"]
            out.append((r["et"], re * EXPOSURE))
        return out

    # ① 익절% 스윕 (전체) — 칼날 vs plateau
    print("\n[① 익절% 스윕 — 전체기간 (이익컷·손실런 = 익절pct OR REVoi손절)]", flush=True)
    print(f"  {'익절%':>6s} {'승률(도달)':>9s} {'36mo수익':>11s} {'MDD':>8s} {'CPCV p25':>9s}", flush=True)
    for pct in PCTS:
        rows = fix_rows(pct)
        wr = 100.0 * np.mean([r["hit_tp"][pct] for r in rec])
        ret, mdd = equity_mdd(rows); cp = cpcv(rows)
        print(f"  {pct*100:5.2f}% {wr:8.1f}% {ret:+10.1f}% {mdd:7.1f}% {100*np.percentile(cp,25):+8.0f}%", flush=True)

    # ② held-out: train 최적 pct → test 적용
    print("\n[② held-out OOS (train<=2024-12-31 최적 → test 적용)]", flush=True)
    best_pct, best_tr = None, -1e18
    for pct in PCTS:
        tr_ret = total_ret(fix_rows(pct, "train"))
        if tr_ret > best_tr:
            best_tr, best_pct = tr_ret, pct
    print(f"  train 최적 익절% = {best_pct*100:.2f}% (train수익 {best_tr:+.0f}%)", flush=True)
    print(f"  {'익절%':>6s} {'test수익':>11s} {'test MDD':>9s}  (★train최적이 test서도 최상이면 강건)", flush=True)
    for pct in PCTS:
        rows = fix_rows(pct, "test")
        ret, mdd = equity_mdd(rows)
        mark = " ←train최적" if pct == best_pct else ""
        print(f"  {pct*100:5.2f}% {ret:+10.1f}% {mdd:8.1f}%{mark}", flush=True)

    # ③ 손익분해 (1% 기준)
    print("\n[③ 손익분해 — 이익컷·손실런 위험]", flush=True)
    for pct in [0.01, 0.015]:
        wins = [r for r in rec if r["hit_tp"][pct]]
        miss = [r for r in rec if not r["hit_tp"][pct]]
        miss_R = np.array([r["rb"] for r in miss]) if miss else np.array([0.0])
        print(f"  익절 {pct*100:.1f}%: 도달 {len(wins)}건(+{pct*100:.1f}%) / 미도달 {len(miss)}건 "
              f"평균 {100*miss_R.mean():+.2f}% 최악 {100*miss_R.min():+.2f}% (미도달=REVoi손절런)", flush=True)

    # ④ 대칭손절 대조
    print("\n[④ 대칭손절 대조 (익절pct + 손절pct, 손실런 제거)]", flush=True)
    print(f"  {'pct':>6s} {'36mo수익':>11s} {'MDD':>8s} {'CPCV p25':>9s}", flush=True)
    for pct in [0.01, 0.015, 0.02]:
        rows = sym_rows(pct)
        ret, mdd = equity_mdd(rows); cp = cpcv(rows)
        print(f"  {pct*100:5.2f}% {ret:+10.1f}% {mdd:7.1f}% {100*np.percentile(cp,25):+8.0f}%", flush=True)
    print("\n[해석] 스윕이 plateau(이웃 pct도 양호)+held-out에서 train최적이 test도 우위 = 강건(진짜).", flush=True)
    print("       1%만 튀고 이웃 나쁨 or test서 무너짐 or 대칭손절서 폭락 = 과적합/이익컷손실런 아티팩트.", flush=True)


if __name__ == "__main__":
    main()
