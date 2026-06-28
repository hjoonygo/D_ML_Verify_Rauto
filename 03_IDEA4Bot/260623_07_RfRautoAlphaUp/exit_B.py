# -*- coding: utf-8 -*-
# [exit_B.py] B — reversion형 청산. A(ATR트레일=추세추종형)는 우리 reversion 신호에 부적합 판명.
#   reversion 가설: "추세 끝까지 태우기"가 아니라 "반등 목표서 빠지기" → 목표익절·시간·신호소멸 청산.
#   진입=변동성SL(1.5×ATR, 즉시). ★1m 실체결·낙관금지·비용8bp.
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


def sim(d, S, oi, mode, param):
    es = S.side.to_dict(); atr_of = S.atr_pct.to_dict(); bar8 = set(S.index)
    ti = d["t"]; O = d["open"].values; H = d["high"].values; L = d["low"].values
    tr = []; pos = 0; entry = init_sl = risk = atr_e = oi_e = e_side = None; hwm = lwm = None; bars = 0
    for i in range(len(d)):
        t = ti.iloc[i]
        if pos == 0:
            sd = es.get(t, 0)
            if t in bar8 and sd != 0:
                ae = atr_of.get(t, np.nan)
                if not np.isnan(ae):
                    pos = sd; e_side = sd; entry = O[i]; atr_e = ae; oi_e = oi[i]
                    risk = float(np.clip(ae * SL_MULT, 0.008, 0.05))
                    init_sl = entry * (1 - risk) if pos == 1 else entry * (1 + risk)
                    hwm = H[i]; lwm = L[i]; bars = 0
        else:
            if H[i] > hwm: hwm = H[i]
            if L[i] < lwm: lwm = L[i]
            ex = None; tp = None
            # 손절(변동성SL) — 직전봉 init_sl
            if pos == 1 and L[i] <= init_sl: ex = min(O[i], init_sl)
            elif pos == -1 and H[i] >= init_sl: ex = max(O[i], init_sl)
            # 목표익절(R배수) — 1m 터치
            if ex is None and mode == "targetR":
                tp = entry * (1 + param * risk) if pos == 1 else entry * (1 - param * risk)
                if pos == 1 and H[i] >= tp: ex = max(O[i], tp)
                elif pos == -1 and L[i] <= tp: ex = min(O[i], tp)
            # 8h봉 경계 처리: 시간·신호소멸·maxhold
            if ex is None and t in bar8:
                bars += 1
                if mode == "time" and bars >= param: ex = O[i]
                elif mode == "signal" and es.get(t, 0) != e_side: ex = O[i]   # 진입신호 소멸/반전
                elif bars >= MAXHOLD: ex = O[i]
            if ex is not None:
                realized = pos * (ex - entry) / entry
                mfe = (hwm - entry) / entry if pos == 1 else (entry - lwm) / entry
                tr.append(dict(ret=realized - COST, realized=realized, risk=risk, mfe=mfe,
                               atr_e=atr_e, oi_e=oi_e)); pos = 0
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
    print(f"{'청산모드(B)':<20}{'거래':>5}{'복리%':>8}{'MDD%':>8}{'SQN':>7}{'CPCV':>8}{'MFEcap':>8}")
    print("-" * 64)
    Ts = {}
    for nm, mode, p in [("①목표익절2R", "targetR", 2.0), ("②목표익절3R", "targetR", 3.0),
                        ("③시간8봉", "time", 8), ("④시간16봉", "time", 16),
                        ("⑤신호소멸", "signal", 0)]:
        T = sim(d, S, oi, mode, p); Ts[nm] = T; report(nm, T)
    print("--- +ATR×OI 사이징 ---")
    med = None
    for nm in Ts:
        T = Ts[nm]
        if len(T) < 20: continue
        if med is None: med = np.median(T.atr_e.values)
        soi = np.clip(1 - 0.3 * np.maximum(0, T.oi_e.values - 1.5), 0.25, 1)
        sat = np.clip(med / T.atr_e.values, 0.25, 1)
        report(nm + "+사이징", T, sat * soi)
    print("\n[대조] A 최선(고정3%트레일+사이징) = MDD-25.8%·SQN1.60·cap43%.")
    print("[판정] B(reversion형)가 SQN↑·MDD↓·cap↑면 reversion엔 목표/시간/신호 청산이 맞다는 증거.")


if __name__ == "__main__":
    main()
