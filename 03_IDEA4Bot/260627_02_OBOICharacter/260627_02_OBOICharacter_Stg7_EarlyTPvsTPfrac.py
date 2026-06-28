# -*- coding: utf-8 -*-
# [260627_02_OBOICharacter_Stg7_EarlyTPvsTPfrac.py]
# 조기익절 정식검증 + 기존 tp_frac 통합 (캡틴 지시 2026-06-27 "제대로 검증·통합·정식화").
#   tp_frac(구조 부분익절, gen_trades 내장) vs EARLY_TP(고정% 익절) vs COMBO. 같은 철학(REVoi 청산 늦음) 다른 방식.
#   ★검증: CPCV 표준6 · held-out(train→test) · §26 4단 게이트(M0/M30/M25/M20 레버스윕+강제청산).
#   ★무손상: BASE(tp_frac=0, 조기익절off)=앵커 +1851.6%. REVoiBot 무수정 호출(§8).
#   ★1차 한계(정직): 조기익절은 거래원장 '후처리'(청산만 조기, 진입시퀀스 고정) 근사.
#     엔진내장(gen_trades early_tp) 정확검증·공용엔진화는 이 방향 확인 후 별도(캡틴 승인).
#   ★룩어헤드0: et~xt 1m 익절도달, 강제청산 mae기반. 난수0.
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
OUTDIR = os.path.join(ROOT, "00_WorkHstr", "BackTest_Output", "260627_02_OBOICharacter_Stg7_EarlyTPvsTPfrac")

SIZE = 0.75            # 증거금 비율(고정), lev는 §26 스윕
BASE_LEV = 3.0
COST = 0.0008
MMR_SLIP = 0.0045      # 강제청산 근사(mmr+slip)
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


def build_recs(T, d1m):
    """거래별 et,xt,side,entry,rb,mae + 익절% 도달여부 사전계산."""
    m_t = d1m.index.values; mH = d1m["high"].values; mL = d1m["low"].values
    PCTS = [0.0075, 0.01]
    rec = []
    for _, tr in T.iterrows():
        et64 = np.datetime64(tr["et"]); xt64 = np.datetime64(tr["xt"])
        side = int(tr["side"]); entry = float(tr["entry"]); rb = float(tr["R"]); mae = float(tr["mae"])
        a = int(np.searchsorted(m_t, et64, "left")); b = int(np.searchsorted(m_t, xt64, "right"))
        sh = mH[a:b]; sl = mL[a:b]
        hit = {}
        for pct in PCTS:
            up = entry * (1 + pct); dn = entry * (1 - pct)
            hit[pct] = bool((sh >= up).any()) if side == 1 else bool((sl <= dn).any())
        rec.append(dict(et=tr["et"], et64=et64, rb=rb, mae=mae, hit=hit))
    return rec


def variant_R(rec, early_pct=None):
    """변형별 거래 (et, R_unsized, mae). early_pct 익절 적용(후처리)."""
    out = []
    for r in rec:
        if early_pct is not None and r["hit"][early_pct]:
            R = early_pct - COST            # 조기익절
        else:
            R = r["rb"]
        out.append((r["et"], r["et64"], R, r["mae"]))
    return out


def sized_rows(vR, lev, subset=None):
    exp = SIZE * lev
    rows = []
    hsd = 1.0 / lev - MMR_SLIP
    liq = 0
    for et, et64, R, mae in vR:
        if subset == "train" and not (et64 <= TRAIN_END): continue
        if subset == "test" and not (et64 > TRAIN_END): continue
        if mae <= -hsd:                      # 격리마진 강제청산(근사)
            re = -exp * (hsd + COST); liq += 1
        else:
            re = R * exp
        rows.append((et, re))
    return rows, liq


def gate4(vR):
    """§26 4단: lev 스윕 → M0(무제한)·M30·M25·M20 최대수익 + 강제청산."""
    res = {"M0": (-1e18, 0, 0), "M30": (-1e18, 0, 0), "M25": (-1e18, 0, 0), "M20": (-1e18, 0, 0)}
    for lev in range(2, 21):
        rows, liq = sized_rows(vR, lev)
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
    print("[REVoi] 거래원장 생성 (tp0 / tp0.7) ...", flush=True)
    T0 = REVoiBot({**p, "tp_frac": 0.0}).make_trades(d1m, fund)
    T7 = REVoiBot({**p, "tp_frac": 0.7}).make_trades(d1m, fund)
    base_ret = 100.0 * (np.prod(1 + T0["R"].values * SIZE * BASE_LEV) - 1.0)
    print(f"[무손상] BASE(tp0) lev{BASE_LEV} = {base_ret:+.1f}% vs 앵커 1851.6% "
          f"({'OK' if abs(base_ret-1851.6)<50 else 'X'}) | T0 {len(T0)}건 T7 {len(T7)}건", flush=True)
    rec0 = build_recs(T0, d1m); rec7 = build_recs(T7, d1m)

    VAR = {
        "BASE(REVoi원청산)": variant_R(rec0, None),
        "TPF(tp_frac0.7)": variant_R(rec7, None),
        "EARLY_0.75%": variant_R(rec0, 0.0075),
        "EARLY_1.0%": variant_R(rec0, 0.01),
        "COMBO(tpf+early0.75)": variant_R(rec7, 0.0075),
    }
    print("\n[정식검증 — 고정 lev3/size75, 후처리 근사]", flush=True)
    print(f"  {'변형':22s} {'36mo수익':>11s} {'MDD':>8s} {'CPCVp25':>9s} {'held-out test':>13s}", flush=True)
    for nm, vR in VAR.items():
        rows, _ = sized_rows(vR, BASE_LEV)
        ret, mdd = equity_mdd(rows); cp = cpcv(rows)
        trows, _ = sized_rows(vR, BASE_LEV, "test"); tret, tmdd = equity_mdd(trows)
        p25 = f"{100*np.percentile(cp,25):+.0f}%" if cp is not None else "n/a"
        print(f"  {nm:22s} {ret:+10.1f}% {mdd:7.1f}% {p25:>9s} {tret:+11.1f}%", flush=True)

    print("\n[§26 4단 게이트 — 변형별 (M0무제한/M30/M25/M20 최대수익·레버·MDD·강제청산)]", flush=True)
    print(f"  {'변형':22s} {'M0':>22s} {'M30':>20s} {'M25':>20s} {'M20':>20s}", flush=True)
    for nm, vR in VAR.items():
        g = gate4(vR)
        def fmt(t):
            r, lev, mdd, liq = t
            return f"{r:+.0f}%@L{lev}({mdd:.0f}%,청{liq})"
        print(f"  {nm:22s} {fmt(g['M0']):>22s} {fmt(g['M30']):>20s} {fmt(g['M25']):>20s} {fmt(g['M20']):>20s}", flush=True)
    print("\n[해석] EARLY/TPF가 BASE보다 수익↑·MDD↓·CPCVp25↑·held-out↑면 채택가치. M20(MDD>=-20) 최대수익이 챔피언인증.", flush=True)
    print("       COMBO가 단독보다 우위면 결합 시너지. 후처리 근사 → 통과시 엔진내장 정확검증·공용엔진화.", flush=True)


if __name__ == "__main__":
    main()
