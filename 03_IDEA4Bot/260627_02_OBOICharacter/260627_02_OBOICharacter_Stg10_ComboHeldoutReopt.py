# -*- coding: utf-8 -*-
# [260627_02_OBOICharacter_Stg10_ComboHeldoutReopt.py]
# COMBO ★진짜 held-out 재최적 (캡틴 지시 2026-06-27 "진짜 held-out 재최적화").
#   기존 0.75%는 36개월 전체 최적(Stg6). 진짜 OOS = train(≤2024-12)서 early_tp% 재탐색 → test(2025~26) blind.
#   과적합이면 train최적이 test서 무너짐. 강건이면 train최적 ≈ test최상권.
#   tp_frac=0.7 고정(기존 검증값), early_frac=1.0. 후처리(청산만 조기, 진입시퀀스 고정·OOS 분리는 정확).
#   ★무손상: early%=0 → tp0.7 거래원장 그대로. 룩어헤드0: et~xt 1m 도달, train/test 시점분리.
import os, sys, json
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
sys.path.insert(0, os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp"))
from path_finder import ensure_paths
ensure_paths()
from fib_replay_1m import load_1m, load_funding
from REVoi_bot import REVoiBot

PJSON = os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp", "back2tv_rev_winners.json")
EXPO = 0.75 * 3.0
COST = 0.0008
TRAIN_END = np.datetime64("2024-12-31")
EARLY_GRID = [0.0, 0.005, 0.0075, 0.01, 0.0125, 0.015, 0.02]


def equity_mdd(rows):
    if not rows:
        return 0.0, 0.0
    cap = 10000.0; peak = cap; mdd = 0.0
    for _, re in sorted(rows, key=lambda x: x[0]):
        cap *= (1.0 + re); peak = max(peak, cap); mdd = min(mdd, cap / peak - 1.0)
    return 100.0 * (cap / 10000.0 - 1.0), 100.0 * mdd


def main():
    p = json.load(open(PJSON))["REV_MDD25_36mo"]["p"]
    d1m = load_1m(); fund = load_funding()
    T = REVoiBot({**p, "tp_frac": 0.7}).make_trades(d1m, fund)   # tp_frac0.7 거래원장(1회)
    m_t = d1m.index.values; mH = d1m["high"].values; mL = d1m["low"].values
    # 거래별 et,xt,side,entry,R7 + 각 early% 도달여부
    rec = []
    for _, tr in T.iterrows():
        et64 = np.datetime64(tr["et"]); xt64 = np.datetime64(tr["xt"])
        side = int(tr["side"]); entry = float(tr["entry"]); r7 = float(tr["R"])
        a = int(np.searchsorted(m_t, et64, "left")); b = int(np.searchsorted(m_t, xt64, "right"))
        sh = mH[a:b]; sl = mL[a:b]
        hit = {}
        for e in EARLY_GRID:
            if e == 0:
                hit[e] = False; continue
            up = entry * (1 + e); dn = entry * (1 - e)
            hit[e] = bool((sh >= up).any()) if side == 1 else bool((sl <= dn).any())
        rec.append(dict(et64=et64, r7=r7, hit=hit, is_train=(et64 <= TRAIN_END)))

    def rows_for(early, subset):
        out = []
        for r in rec:
            if subset == "train" and not r["is_train"]: continue
            if subset == "test" and r["is_train"]: continue
            re = (early - COST) if (early > 0 and r["hit"][early]) else r["r7"]
            out.append((r["et64"], re * EXPO))
        return out

    print(f"[REVoi tp0.7] {len(T)}건 | train≤2024-12 {sum(r['is_train'] for r in rec)} / test {sum(not r['is_train'] for r in rec)}", flush=True)
    print("\n[① train 재탐색 — early% 별 train 복리(lev3)]", flush=True)
    best_e, best_tr = 0.0, -1e18
    for e in EARLY_GRID:
        tr_ret, _ = equity_mdd(rows_for(e, "train"))
        mark = ""
        if tr_ret > best_tr: best_tr, best_e = tr_ret, e
        print(f"  early {e*100:5.2f}% : train {tr_ret:+.0f}%", flush=True)
    print(f"  ▶ train 최적 early% = {best_e*100:.2f}%", flush=True)

    print("\n[② test blind — early% 별 test 복리/MDD (★train최적이 test 최상권이면 강건)]", flush=True)
    test_best_e, test_best = 0.0, -1e18
    for e in EARLY_GRID:
        te_ret, te_mdd = equity_mdd(rows_for(e, "test"))
        if te_ret > test_best: test_best, test_best_e = te_ret, e
        mark = " ←train최적" if e == best_e else ""
        print(f"  early {e*100:5.2f}% : test {te_ret:+.0f}% / MDD {te_mdd:.1f}%{mark}", flush=True)
    print(f"  ▶ test 최적 early% = {test_best_e*100:.2f}%", flush=True)

    # 판정
    te_at_best, te_mdd_at_best = equity_mdd(rows_for(best_e, "test"))
    te_off, _ = equity_mdd(rows_for(0.0, "test"))
    print("\n[판정]", flush=True)
    print(f"  train최적 {best_e*100:.2f}% → test {te_at_best:+.0f}%/MDD{te_mdd_at_best:.1f}% vs early off test {te_off:+.0f}%", flush=True)
    gap = abs(best_e - test_best_e) * 100
    verdict = "강건(과적합 아님)" if (gap <= 0.5 and te_at_best > te_off) else ("부분강건" if te_at_best > te_off else "과적합 의심")
    print(f"  train최적 vs test최적 거리 {gap:.2f}%p · train최적이 test서 early-off 대비 {'우위' if te_at_best>te_off else '열위'} → ★{verdict}", flush=True)


if __name__ == "__main__":
    main()
