# -*- coding: utf-8 -*-
# [260627_02_OBOICharacter_Stg9_ComboBack2TV.py]
# COMBO(tp_frac+early_tp) ★Back2TV 생성 (캡틴 지시 2026-06-27).
#   COMBO = REVoi + 구조 부분익절(tp_frac0.7) + 고정% 조기익절(early_tp 0.75%). 엔진내장(Stg8 무손상·§26 통과).
#   ★Back2TV(§20): make_back2tv(검증엔진)로 통합표(§19) + Pine v6 + 사례6선 산출. §26 4단(M20/M25/M30) 지표 병기.
#   ★환각0: early_tp=entry±pct limit 1m 도달체결 + tp_frac/fibstop 검증청산 = 전부 1m 가격도달 기반(룩어헤드0).
#   검증엔진 무수정 호출(early_tp opt-in 확장). 36개월(앵커 데이터). 38개월은 데이터확장 별도.
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
import back2tv_REVoi as B2

PJSON = os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp", "back2tv_rev_winners.json")


def main():
    p_base = json.load(open(PJSON))["REV_MDD25_36mo"]["p"]
    combo_p = {**p_base, "tp_frac": 0.7, "early_tp_pct": 0.01, "early_frac": 1.0}   # ★진짜 held-out 최적 1.0%(Stg10)
    print(f"[COMBO config] tp_frac=0.7 · early_tp_pct=1.0%(held-out최적) · early_frac=1.0 (+ REV {p_base['rev_tf']}분)", flush=True)
    d1m = load_1m(); fund = load_funding()
    T = B2.rev_trades(d1m, fund, combo_p)
    R = T["R"].values; MAE = T["mae"].values; FUND = T["fund"].values
    MKEY = pd.to_datetime(T["et"]).dt.strftime("%Y-%m").values
    # 무손상 참고: tp0/early0 복리(lev3) ≈ 앵커
    Tb = B2.rev_trades(d1m, fund, p_base)
    anchor = 100.0 * (np.prod(1 + Tb["R"].values * 0.75 * 3.0) - 1.0)
    print(f"[무손상] BASE(tp0,early0) lev3 = {anchor:+.1f}% (앵커 1851.6%)", flush=True)
    # §26 4단 격리마진 정확(liq_eval) — size75 고정 lev 스윕
    print("\n[§26 4단 — COMBO 격리마진 정확(liq_eval, size75)]", flush=True)
    gate = {}
    best = {"M0": (-1e18,), "M30": (-1e18,), "M25": (-1e18,), "M20": (-1e18,)}
    for lev in range(2, 21):
        tot, mdd, bm, nl = B2.liq_eval(R, MAE, FUND, MKEY, 75.0, float(lev))
        if tot > best["M0"][0]: best["M0"] = (tot, lev, mdd, bm, nl)
        for tag, lim in [("M30", -30), ("M25", -25), ("M20", -20)]:
            if mdd >= lim and tot > best[tag][0]: best[tag] = (tot, lev, mdd, bm, nl)
    for tag in ["M0", "M30", "M25", "M20"]:
        tot, lev, mdd, bm, nl = best[tag]
        rs = f"{tot:+.0f}" if abs(tot) < 1e6 else f"{tot:+.2e}"
        print(f"  {tag:4s}: {rs}% @ lev{lev}/size75 · MDD{mdd:.1f}% · 단일최고월+{bm:.0f}% · 강제청산{nl}회", flush=True)
        gate[tag] = best[tag]
    # ★Back2TV 생성 = M20 챔피언(인증 후보)으로 Pine·통합표·사례6선
    tot, lev, mdd, bm, nl = gate["M20"]
    w = {"p": combo_p, "sz": 75.0, "lev": float(lev), "bm": bm,
         "tot": tot, "mdd": mdd, "nl": nl, "ntr": len(T)}
    print(f"\n[Back2TV 생성] M20 챔피언 = lev{lev}/size75 · {tot:+.0f}%/MDD{mdd:.0f}%/청산{nl}", flush=True)
    base = B2.make_back2tv(d1m, fund, w, f"COMBO_M20_tp07e100_L{int(lev)}")
    print(f"\n[완료] Back2TV base = {base}", flush=True)
    print("[환각0] early_tp=진입가±0.75% limit 1m도달체결 · tp_frac/fibstop=검증청산 → 전부 1m 가격도달(룩어헤드0).", flush=True)


if __name__ == "__main__":
    main()
