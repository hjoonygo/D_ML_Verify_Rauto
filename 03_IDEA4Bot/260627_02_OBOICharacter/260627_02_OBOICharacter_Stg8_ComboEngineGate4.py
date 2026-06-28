# -*- coding: utf-8 -*-
# [260627_02_OBOICharacter_Stg8_ComboEngineGate4.py]
# 조기익절 ★엔진내장 정확검증 + COMBO §26 4단 (캡틴 지시 2026-06-27).
#   Stg7(후처리)는 §26 레버스윕 폭주(+10^18%) = 보유기간/mae 부정확. → gen_trades에 early_tp 내장(opt-in).
#   ★무손상 최우선: BASE(tp0,early0) lev3 = 앵커 +1851.6% 재현(엔진수정 무해 증명).
#   ★COMBO = tp_frac(구조) + early_tp(고정%). §26 4단(M0/M30/M25/M20 최대수익 + 격리마진 강제청산) 정확.
#   검증엔진 무수정 호출(early_tp는 opt-in 확장·기존경로 보존). 난수0. CPCV 표준6.
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
OUTDIR = os.path.join(ROOT, "00_WorkHstr", "BackTest_Output", "260627_02_OBOICharacter_Stg8_ComboEngineGate4")

SIZE = 0.75
BASE_LEV = 3.0
COST = 0.0008
MMR_SLIP = 0.0045
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
    g = np.array_split(np.arange(len(R)), N_GROUPS)
    return np.array([np.prod(1 + R[np.concatenate([g[i] for i in tg])]) - 1
                     for tg in combinations(range(N_GROUPS), K_TEST)])


def sized_rows(T, lev, subset=None):
    exp = SIZE * lev; hsd = 1.0 / lev - MMR_SLIP
    rows = []; liq = 0
    for _, tr in T.iterrows():
        t = tr["et"]; t64 = np.datetime64(t)
        if subset == "train" and not (t64 <= TRAIN_END): continue
        if subset == "test" and not (t64 > TRAIN_END): continue
        if float(tr["mae"]) <= -hsd:                 # 격리마진 강제청산(mae=보유중 최대역행)
            re = -exp * (hsd + COST); liq += 1
        else:
            re = float(tr["R"]) * exp
        rows.append((t, re))
    return rows, liq


def gate4(T):
    res = {"M0": (-1e18, 0, 0, 0), "M30": (-1e18, 0, 0, 0), "M25": (-1e18, 0, 0, 0), "M20": (-1e18, 0, 0, 0)}
    for lev in range(2, 21):
        rows, liq = sized_rows(T, lev)
        ret, mdd = equity_mdd(rows)
        if ret > res["M0"][0]: res["M0"] = (ret, lev, mdd, liq)
        for tag, lim in [("M30", -30), ("M25", -25), ("M20", -20)]:
            if mdd >= lim and ret > res[tag][0]:
                res[tag] = (ret, lev, mdd, liq)
    return res


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    p = json.load(open(PJSON))["REV_MDD25_36mo"]["p"]
    d1m = load_1m(); fund = load_funding()
    CFG = {
        "BASE(tp0,early0)": {},
        "TPF(tp0.7)": {"tp_frac": 0.7},
        "EARLY0.75_full": {"early_tp_pct": 0.0075, "early_frac": 1.0},
        "EARLY1.0_full": {"early_tp_pct": 0.01, "early_frac": 1.0},
        "COMBO(tp0.7+e0.75)": {"tp_frac": 0.7, "early_tp_pct": 0.0075, "early_frac": 1.0},
        "COMBO_half(tp0.7+e0.75f0.5)": {"tp_frac": 0.7, "early_tp_pct": 0.0075, "early_frac": 0.5},
    }
    print("[REVoi 엔진내장 거래생성] ...", flush=True)
    Ts = {}
    for nm, cfg in CFG.items():
        Ts[nm] = REVoiBot({**p, **cfg}).make_trades(d1m, fund)
    base_ret = 100.0 * (np.prod(1 + Ts["BASE(tp0,early0)"]["R"].values * SIZE * BASE_LEV) - 1.0)
    ok = abs(base_ret - 1851.6) < 50
    print(f"[★무손상] BASE(tp0,early0) lev3 = {base_ret:+.1f}% vs 앵커 1851.6% "
          f"({'✅ 엔진수정 무해' if ok else '❌ 깨짐-수정버그 점검'})", flush=True)

    print("\n[정식검증 — lev3/size75 고정]", flush=True)
    print(f"  {'변형':28s} {'거래':>5s} {'36mo':>10s} {'MDD':>8s} {'CPCVp25':>9s} {'test':>9s}", flush=True)
    for nm, T in Ts.items():
        rows, _ = sized_rows(T, BASE_LEV); ret, mdd = equity_mdd(rows); cp = cpcv(rows)
        trows, _ = sized_rows(T, BASE_LEV, "test"); tret, _ = equity_mdd(trows)
        p25 = f"{100*np.percentile(cp,25):+.0f}%" if cp is not None else "n/a"
        print(f"  {nm:28s} {len(T):5d} {ret:+9.1f}% {mdd:7.1f}% {p25:>9s} {tret:+8.1f}%", flush=True)

    print("\n[§26 4단 게이트 — 엔진내장 정확(레버스윕·격리마진 강제청산)]", flush=True)
    print(f"  {'변형':28s} {'M0(천장)':>20s} {'M30':>17s} {'M25':>17s} {'M20(챔피언)':>18s}", flush=True)
    rows_out = []
    for nm, T in Ts.items():
        g = gate4(T)
        def fmt(t):
            r, lev, mdd, liq = t
            rs = f"{r:+.0f}" if abs(r) < 1e6 else f"{r:+.2e}"
            return f"{rs}%@L{lev}({mdd:.0f}%,청{liq})"
        print(f"  {nm:28s} {fmt(g['M0']):>20s} {fmt(g['M30']):>17s} {fmt(g['M25']):>17s} {fmt(g['M20']):>18s}", flush=True)
        rows_out.append({"변형": nm, **{k: f"{v[0]:+.1f}%@L{v[1]}/MDD{v[2]:.1f}/청{v[3]}" for k, v in g.items()}})
    pd.DataFrame(rows_out).to_csv(os.path.join(OUTDIR, "260627_02_OBOICharacter_Stg8_gate4.csv"),
                                 index=False, encoding="utf-8-sig")
    print("\n[해석] M20(MDD>=-20) 최대수익 = 챔피언 인증 후보. 폭주 사라지고 현실 레버(L<=~12)면 엔진내장 정확.", flush=True)
    print("       COMBO가 EARLY/TPF 단독보다 M20수익↑·강제청산0이면 결합 채택 → Back2TV 대상.", flush=True)


if __name__ == "__main__":
    main()
