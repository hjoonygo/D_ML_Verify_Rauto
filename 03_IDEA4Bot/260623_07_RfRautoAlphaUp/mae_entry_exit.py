# -*- coding: utf-8 -*-
# [mae_entry_exit.py] MAE 기반 진입·청산 재설계 (챗GPT 금광).
#   MAE측정: 승자 0.46σ < 1σ < 패자 1.31σ → ① 손절 변동성비례(~1σ atr) = 승자보존+패자컷
#            ② 승자 되돌림여지 p50 0.62% → 되돌림 지정가 진입.
#   ★1m 실체결·갭반영(낙관금지)·비용8bp. vol_sizing_compare.build 재사용(atr_pct·oi_int·side).
import os, sys, itertools
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import vol_sizing_compare as V

COST = 0.0008; TRAIL = 0.03; MAXHOLD = 60; PB_WAIT = 360


def mdd(r): eq = np.cumprod(1 + r); return ((eq - np.maximum.accumulate(eq)) / np.maximum.accumulate(eq)).min() * 100
def tot(r): return (np.cumprod(1 + r)[-1] - 1) * 100
def cpcv(r, g=6):
    gs = np.array_split(np.arange(len(r)), g); ps = []
    for c in itertools.combinations(range(g), 2):
        rr = r[np.concatenate([gs[k] for k in c])]
        ps.append(rr.mean() / rr.std() * np.sqrt(len(rr) / 3) if rr.std() > 0 else 0)
    return np.percentile(ps, 25)
def sqn(R): return R.mean() / R.std() * np.sqrt(len(R)) if R.std() > 0 else 0


def sim(d, S, oi, PBm, SLmode, SLm):
    es = S.side.to_dict(); atr_of = S.atr_pct.to_dict(); bar8 = set(S.index)
    ti = d["t"]; O = d["open"].values; H = d["high"].values; L = d["low"].values
    tr = []; pos = 0; entry = TS = risk = init_sl = None; hwm = lwm = None; bars = 0; pend = None; atr_e = oi_e = None
    for i in range(len(d)):
        t = ti.iloc[i]
        if pos == 0:
            if pend is None:
                sd = es.get(t, 0)
                if t in bar8 and sd != 0:
                    ae = atr_of.get(t, np.nan)
                    if not np.isnan(ae):
                        tg = O[i] * (1 - ae * PBm) if sd == 1 else O[i] * (1 + ae * PBm)
                        pend = (int(sd), tg, i + PB_WAIT, ae, oi[i])
            else:
                sd, tg, exp, ae, oe = pend
                hit = (L[i] <= tg) if sd == 1 else (H[i] >= tg)
                if hit:
                    pos = sd; entry = tg; atr_e = ae; oi_e = oe
                    risk = 0.02 if SLmode == "fix" else float(np.clip(ae * SLm, 0.008, 0.05))
                    init_sl = entry * (1 - risk) if pos == 1 else entry * (1 + risk); TS = init_sl
                    hwm = H[i]; lwm = L[i]; bars = 0; pend = None
                elif i >= exp:
                    pend = None
        else:
            if H[i] > hwm: hwm = H[i]
            if L[i] < lwm: lwm = L[i]
            ex = None
            if pos == 1 and L[i] <= TS: ex = min(O[i], TS)
            elif pos == -1 and H[i] >= TS: ex = max(O[i], TS)
            if ex is None and t in bar8:
                bars += 1
                if bars >= MAXHOLD: ex = O[i]
            if ex is not None:
                moved = (TS > init_sl + 1e-9) if pos == 1 else (TS < init_sl - 1e-9)
                tr.append(dict(ret=pos * (ex - entry) / entry - COST, risk=risk, atr_e=atr_e, oi_e=oi_e,
                               tag="trailing" if moved else "initial_SL")); pos = 0
            else:
                TS = max(TS, hwm * (1 - TRAIL)) if pos == 1 else min(TS, lwm * (1 + TRAIL))
    return pd.DataFrame(tr)


def report(nm, T, size=None):
    if len(T) < 20: print(f"{nm:<22} 표본 {len(T)}"); return
    r = T.ret.values if size is None else T.ret.values * size
    R = T.ret.values / T.risk.values
    isl = 100 * (T.tag == "initial_SL").mean()
    print(f"{nm:<22}{len(T):>5}{tot(r):>+8.0f}{mdd(r):>+8.1f}{sqn(R):>7.2f}{cpcv(r):>+8.2f}{isl:>6.0f}%")


def main():
    d, S, oi = V.build(V.find_data())
    print(f"{'변형':<22}{'거래':>5}{'복리%':>8}{'MDD%':>8}{'SQN':>7}{'CPCV':>8}{'초기SL':>6}")
    print("-" * 64)
    VAR = [("①베이스(즉시·SL2%)", 0, "fix", 0),
           ("②변동성SL(1.5×atr)", 0, "vol", 1.5),
           ("③되돌림(0.5×atr)", 0.5, "fix", 0),
           ("④되돌림+변동성SL", 0.5, "vol", 1.5)]
    Ts = {}
    for nm, pb, slm, slmul in VAR:
        T = sim(d, S, oi, pb, slm, slmul); Ts[nm] = T; report(nm, T)
    print("--- +ATR×OI 사이징 ---")
    med = None
    for nm in ["②변동성SL(1.5×atr)", "④되돌림+변동성SL"]:
        T = Ts[nm]
        if len(T) < 20: continue
        if med is None: med = np.median(T.atr_e.values)
        soi = np.clip(1 - 0.3 * np.maximum(0, T.oi_e.values - 1.5), 0.25, 1)
        sat = np.clip(med / T.atr_e.values, 0.25, 1)
        report(nm + "+사이징", T, sat * soi)
    # 최고 변형 ledger 저장(검증엔진 복기용)
    best = Ts["④되돌림+변동성SL"]
    if len(best) >= 20:
        b = best.copy(); b["mfe"] = np.nan
        b.to_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "mae_entry_exit_ledger.csv"), index=False, encoding="utf-8-sig")
        print("\n[저장] mae_entry_exit_ledger.csv (검증엔진 복기용)")
    print("[판정] 변동성SL/되돌림이 초기SL%↓·SQN↑·MDD↓면 MAE개선. +사이징서 MDD<-20%·CPCV>0이 목표.")


if __name__ == "__main__":
    main()
