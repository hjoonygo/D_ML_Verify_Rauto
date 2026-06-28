# -*- coding: utf-8 -*-
# [dynamic_exit.py] A — 동적 청산 (선행연구: Chandelier ATR트레일·MFE활성 트레일·단계별 타이트).
#   문제: 고정 3% 트레일 = MFE capture 43%(이익 절반 반납). 변동성·수익단계 무시.
#   진입 = 변동성SL(1.5×ATR, 즉시진입=앞 최강). 청산만 모드별 비교. ★1m 실체결·낙관금지·비용8bp.
import os, sys, itertools
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import vol_sizing_compare as V

COST = 0.0008; MAXHOLD = 60; SL_MULT = 1.5


def mdd(r): eq = np.cumprod(1 + r); return ((eq - np.maximum.accumulate(eq)) / np.maximum.accumulate(eq)).min() * 100
def tot(r): return (np.cumprod(1 + r)[-1] - 1) * 100
def cpcv(r, g=6):
    gs = np.array_split(np.arange(len(r)), g); ps = []
    for c in itertools.combinations(range(g), 2):
        rr = r[np.concatenate([gs[k] for k in c])]
        ps.append(rr.mean() / rr.std() * np.sqrt(len(rr) / 3) if rr.std() > 0 else 0)
    return np.percentile(ps, 25)
def sqn(R): return R.mean() / R.std() * np.sqrt(len(R)) if R.std() > 0 else 0


def trail_dist(mode, ae, mfe):
    # 청산 트레일 거리(%) 반환. None = 트레일 비활성(초기SL 유지)
    if mode == "fix3": return 0.03
    if mode == "atr": return 3 * ae
    if mode == "mfe_atr":            # 이익 1.5ATR 전엔 비활성, 후 2ATR
        return 2 * ae if mfe >= 1.5 * ae else None
    if mode == "staged":             # 수익단계별 타이트닝(상황판단)
        if mfe >= 5 * ae: return 1 * ae
        if mfe >= 3 * ae: return 2 * ae
        if mfe >= 1.5 * ae: return 3 * ae
        return None
    return 0.03


def sim(d, S, oi, mode):
    es = S.side.to_dict(); atr_of = S.atr_pct.to_dict(); bar8 = set(S.index)
    ti = d["t"]; O = d["open"].values; H = d["high"].values; L = d["low"].values
    tr = []; pos = 0; entry = TS = init_sl = risk = atr_e = oi_e = None; hwm = lwm = None; bars = 0
    for i in range(len(d)):
        t = ti.iloc[i]
        if pos == 0:
            sd = es.get(t, 0)
            if t in bar8 and sd != 0:
                ae = atr_of.get(t, np.nan)
                if not np.isnan(ae):
                    pos = sd; entry = O[i]; atr_e = ae; oi_e = oi[i]
                    risk = float(np.clip(ae * SL_MULT, 0.008, 0.05))
                    init_sl = entry * (1 - risk) if pos == 1 else entry * (1 + risk); TS = init_sl
                    hwm = H[i]; lwm = L[i]; bars = 0
        else:
            # ★룩어헤드 차단: 청산 체크 먼저(직전봉까지 갱신된 TS) → 그 다음 현재봉 고저로 트레일 갱신(다음봉용)
            ex = None
            if pos == 1 and L[i] <= TS: ex = min(O[i], TS)
            elif pos == -1 and H[i] >= TS: ex = max(O[i], TS)
            if ex is None and t in bar8:
                bars += 1
                if bars >= MAXHOLD: ex = O[i]
            if ex is not None:
                realized = pos * (ex - entry) / entry
                mfe_f = (hwm - entry) / entry if pos == 1 else (entry - lwm) / entry
                tr.append(dict(ret=realized - COST, realized=realized, risk=risk, mfe=mfe_f,
                               atr_e=atr_e, oi_e=oi_e)); pos = 0
            else:
                # 현재봉 고/저로 갱신(다음봉 트레일용) — 룩어헤드 없음
                if H[i] > hwm: hwm = H[i]
                if L[i] < lwm: lwm = L[i]
                mfe = (hwm - entry) / entry if pos == 1 else (entry - lwm) / entry
                td = trail_dist(mode, atr_e, mfe)
                if td is not None:
                    TS = max(TS, hwm * (1 - td)) if pos == 1 else min(TS, lwm * (1 + td))
    return pd.DataFrame(tr)


def report(nm, T, size=None):
    if len(T) < 20: print(f"{nm:<20} 표본 {len(T)}"); return
    r = T.ret.values if size is None else T.ret.values * size
    R = T.ret.values / T.risk.values
    win = T[T.realized > 0]
    cap = (win.realized / win.mfe.replace(0, np.nan)).median() * 100 if len(win) else 0
    print(f"{nm:<20}{len(T):>5}{tot(r):>+8.0f}{mdd(r):>+8.1f}{sqn(R):>7.2f}{cpcv(r):>+8.2f}{cap:>8.0f}%")


def main():
    d, S, oi = V.build(V.find_data())
    print(f"{'청산모드':<20}{'거래':>5}{'복리%':>8}{'MDD%':>8}{'SQN':>7}{'CPCV':>8}{'MFEcap':>8}")
    print("-" * 64)
    Ts = {}
    for nm, mode in [("①고정3%트레일", "fix3"), ("②ATR트레일3×", "atr"),
                     ("③MFE활성(1.5→2ATR)", "mfe_atr"), ("④단계별타이트", "staged")]:
        T = sim(d, S, oi, mode); Ts[nm] = T; report(nm, T)
    print("--- +ATR×OI 사이징 ---")
    med = None
    for nm in Ts:
        T = Ts[nm]
        if len(T) < 20: continue
        if med is None: med = np.median(T.atr_e.values)
        soi = np.clip(1 - 0.3 * np.maximum(0, T.oi_e.values - 1.5), 0.25, 1)
        sat = np.clip(med / T.atr_e.values, 0.25, 1)
        report(nm + "+사이징", T, sat * soi)
    print("\n[판정] 고정3% 대비 MFEcap↑·MDD↓·SQN↑면 동적청산 효과. +사이징서 MDD<-20%·CPCV>0이 목표.")
    print("[정직] 진입=변동성SL즉시. ATR=진입시점 고정(보유중 동적ATR은 후속). 미최적화.")


if __name__ == "__main__":
    main()
