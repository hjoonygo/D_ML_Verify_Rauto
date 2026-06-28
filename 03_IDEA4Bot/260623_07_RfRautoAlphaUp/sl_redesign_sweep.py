# -*- coding: utf-8 -*-
# [sl_redesign_sweep.py] 향상안 1차 탐색 — 초기 손절 재설계 (trade_diagnostics가 지목한 MDD 주범 대응).
#   발견: initial_SL(고정2%) 174건 승률0%/-362%p = MDD 범인. Edge Ratio 1.57=진입엣지 있음 → 손절이 잘라먹음.
#   가설: 초기 손절을 완화(고정3~5%) 또는 변동성비례(ATR배수)로 바꾸면 휩쏘 절단이 줄어 MDD 개선?
#   ★1m 실체결·갭반영(낙관금지)·레버1·비용8bp 유지. 트레일 3% 고정(통제). 미최적화 탐색(과적합 경계).
import os, itertools
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ANCHOR = pd.Timestamp("2023-05-01", tz="UTC")
COST = 0.0008; TRAIL = 0.03; ENTRY_Q = 0.33; MAX_HOLD = 60; ATR_N = 14


def _p(*a): print(*a, flush=True)
def zr(s): return s.rank(pct=True) - 0.5


def find_data():
    for c in [r"D:\ML\RfRauto\08_BTC_Data\derived\Merged_Data.csv", r"D:\ML\Verify\Merged_Data.csv"]:
        if os.path.exists(c): return c
    raise FileNotFoundError("Merged_Data.csv")


def build_signal(DATA):
    d = pd.read_csv(DATA, usecols=["timestamp", "open", "high", "low", "oi_zscore_24h"])
    d["t"] = pd.to_datetime(d["timestamp"], utc=True, format="ISO8601")
    d = d.dropna(subset=["open", "high", "low"]).sort_values("t").reset_index(drop=True)
    g = d.set_index("t").resample("480min", origin=ANCHOR)
    o8 = g["open"].first(); h8 = g["high"].max(); l8 = g["low"].min()
    oi8 = g["oi_zscore_24h"].last().shift(1)
    S = pd.DataFrame({"open8": o8, "high8": h8, "low8": l8}).dropna(subset=["open8"]).join(oi8.rename("oi_z"))
    S["mom_24h"] = S["open8"].pct_change(3)
    # ATR%(8h): true range 간이=고저폭, rolling N, 진입가 대비 % (과거롤링·룩어헤드0)
    tr = (S["high8"] - S["low8"])
    S["atr_pct"] = (tr.rolling(ATR_N).mean() / S["open8"]).shift(1)  # 직전까지
    S = S.dropna(subset=["mom_24h", "oi_z", "atr_pct"])
    S["combo"] = (-zr(S["mom_24h"])) * 0.048 + (-zr(S["oi_z"])) * 0.037
    hi = S["combo"].quantile(1 - ENTRY_Q); lo = S["combo"].quantile(ENTRY_Q)
    S["side"] = np.where(S["combo"] >= hi, 1, np.where(S["combo"] <= lo, -1, 0))
    return d, S


def simulate(d, S, *, sl_mode="fix", sl_pct=0.02, atr_mult=2.0):
    es = S["side"].to_dict(); atr_of = S["atr_pct"].to_dict(); bar8 = set(S.index)
    ti = d["t"]; O = d["open"].values; H = d["high"].values; L = d["low"].values
    trades = []; pos = 0; entry = TS = init_sl = None; et = None; hi_px = lo_px = None; bars = 0; cur_atr = np.nan
    for i in range(len(d)):
        t = ti.iloc[i]
        if t in bar8:
            a = atr_of.get(t, np.nan)
            if not (isinstance(a, float) and np.isnan(a)): cur_atr = a
        if pos == 0:
            sd = es.get(t, 0)
            if t in bar8 and sd != 0:
                pos = int(sd); entry = O[i]; et = t; bars = 0; hi_px = H[i]; lo_px = L[i]
                dist = sl_pct if sl_mode == "fix" else max(cur_atr * atr_mult, 0.005)  # ATR기반(하한0.5%)
                init_sl = entry * (1 - dist) if pos == 1 else entry * (1 + dist); TS = init_sl
        else:
            if H[i] > hi_px: hi_px = H[i]
            if L[i] < lo_px: lo_px = L[i]
            ex = None; tag = None
            if pos == 1 and L[i] <= TS:
                ex = min(O[i], TS)
            elif pos == -1 and H[i] >= TS:
                ex = max(O[i], TS)
            if ex is None and t in bar8:
                bars += 1
                if bars >= MAX_HOLD: ex = O[i]; tag = "maxhold"
            if ex is not None:
                ret = pos * (ex - entry) / entry - COST
                moved = (TS > init_sl + 1e-9) if pos == 1 else (TS < init_sl - 1e-9)
                tag = tag or ("trailing" if moved else "initial_SL")
                trades.append(dict(ret=ret, tag=tag, year=pd.Timestamp(et).year)); pos = 0
            else:
                TS = max(TS, hi_px * (1 - TRAIL)) if pos == 1 else min(TS, lo_px * (1 + TRAIL))
    return pd.DataFrame(trades)


def metrics(T):
    eq = (1 + T.ret).cumprod(); tot = (eq.iloc[-1] - 1) * 100
    mdd = ((eq - eq.cummax()) / eq.cummax()).min() * 100
    g6 = np.array_split(np.arange(len(T)), 6); ps = []
    for c in itertools.combinations(range(6), 2):
        r = T.ret.values[np.concatenate([g6[k] for k in c])]
        ps.append(r.mean() / r.std() * np.sqrt(len(r) / 3) if r.std() > 0 else 0)
    isl = T[T.tag == "initial_SL"]
    return dict(n=len(T), tot=tot, mdd=mdd, p25=np.percentile(ps, 25),
                isl_n=len(isl), isl_win=100*(isl.ret > 0).mean() if len(isl) else 0,
                isl_share=100*len(isl)/len(T))


def main():
    DATA = find_data(); _p(f"[데이터] {DATA}")
    d, S = build_signal(DATA)
    VARI = [("고정 2%(베이스)", dict(sl_mode="fix", sl_pct=0.02)),
            ("고정 3%", dict(sl_mode="fix", sl_pct=0.03)),
            ("고정 4%", dict(sl_mode="fix", sl_pct=0.04)),
            ("고정 5%", dict(sl_mode="fix", sl_pct=0.05)),
            ("ATR×1.5", dict(sl_mode="atr", atr_mult=1.5)),
            ("ATR×2.0", dict(sl_mode="atr", atr_mult=2.0)),
            ("ATR×2.5", dict(sl_mode="atr", atr_mult=2.5)),
            ("ATR×3.0", dict(sl_mode="atr", atr_mult=3.0))]
    _p(f"\n{'손절방식':<16}{'거래':>5}{'복리%':>9}{'MDD%':>8}{'CPCVp25':>9}{'초기SL건':>8}{'초기SL승률':>9}{'초기SL비중':>9}{'-20내':>6}")
    _p("-" * 84)
    for nm, kw in VARI:
        T = simulate(d, S, **kw)
        if len(T) < 10: _p(f"{nm}: 표본부족"); continue
        m = metrics(T)
        ok = "O" if (m["tot"] > 0 and m["p25"] > 0 and m["mdd"] > -20) else "X"
        _p(f"{nm:<16}{m['n']:>5}{m['tot']:>+9.1f}{m['mdd']:>+8.1f}{m['p25']:>+9.2f}"
           f"{m['isl_n']:>8}{m['isl_win']:>8.0f}%{m['isl_share']:>8.0f}%{ok:>6}")
    _p("\n[판정] 초기손절 완화/ATR화로 MDD가 -20% 안에 들고 복리·CPCV 양수면 향상후보. 초기SL비중↓·승률↑이 메커니즘.")
    _p("[정직] 탐색적 미최적화(트레일3%·진입분위 고정). 과적합 경계 — 후보는 WF/CPCV 표준6 재검증 필요.")


if __name__ == "__main__":
    main()
