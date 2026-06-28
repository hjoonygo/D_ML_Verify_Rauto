# -*- coding: utf-8 -*-
# [ts_trail_size.py] TS 진입(무수정) + 긴 ATR 트레일(추세 태움) + ATR×OI 사이징(MDD↓).
#   두 문제: ①트레일3% 짧음(추세 못탐) → ATR배수 트레일 ②MDD-44.6% → 변동성 사이징.
#   선행연구: 추세추종 ATR배수 2.5~3.5·변동성타게팅. ★1m 실체결·낙관금지·비용8bp. 엔진 무수정.
import sys
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\engines")
import trendstack_signal_engine as TS
import numpy as np, pandas as pd, itertools

DATA = r"D:\ML\RfRauto\08_BTC_Data\derived\Merged_Data.csv"
COST = 0.0008; SL_MULT = 1.5; TF = TS.TF_MIN


def mdd(r): eq = np.cumprod(1 + r); return ((eq - np.maximum.accumulate(eq)) / np.maximum.accumulate(eq)).min() * 100
def tot(r): return (np.cumprod(1 + r)[-1] - 1) * 100
def sqn(R): return R.mean() / R.std() * np.sqrt(len(R)) if R.std() > 0 else 0
def cpcv(r, g=6):
    gs = np.array_split(np.arange(len(r)), g); ps = []
    for c in itertools.combinations(range(g), 2):
        rr = r[np.concatenate([gs[k] for k in c])]
        ps.append(rr.mean() / rr.std() * np.sqrt(len(rr) / 3) if rr.std() > 0 else 0)
    return np.percentile(ps, 25)


def get_entries(d, doi):
    df7h = TS.resample_tf(d[["open", "high", "low", "close"]], TF)
    sig = TS.compute_signals(df7h)
    trades = TS.run_strategy(df7h, sig, 0, "none", 0.8, gate_mode="er", gate_er=0.45,
                             split_mode="A", split_n=3, fib=(0.3, 0.5, 0.6))
    atr = sig["atr"]; c7 = df7h["close"].values; idx7 = df7h.index
    oi7 = doi.reindex(idx7, method="ffill").values   # 7h봉 OI z (직전값)
    for tr in trades:
        ei = idx7.get_loc(tr["entry_t"])
        tr["atr_pct"] = float(atr[ei] / c7[ei]) if c7[ei] > 0 else 0.02
        tr["oi_z"] = float(oi7[ei]) if not np.isnan(oi7[ei]) else 0.0
    return trades


def sim(d, trades, trail_mode, tp):
    ti = d.index; O = d["open"].values; H = d["high"].values; L = d["low"].values; C = d["close"].values
    out = []
    for tr in trades:
        side = int(tr["side"]); entry = float(tr["entry"]); ap = tr["atr_pct"]
        risk = float(np.clip(ap * SL_MULT, 0.008, 0.05))
        et = pd.Timestamp(tr["entry_t"]) + pd.Timedelta(minutes=TF)
        si = ti.searchsorted(et)
        if si >= len(ti): continue
        init_sl = entry * (1 - risk) if side == 1 else entry * (1 + risk); TSL = init_sl
        hwm = H[si]; lwm = L[si]; ex = None
        td = 0.03 if trail_mode == "fix" else tp * ap        # ATR배수 트레일(진입시 atr 고정)
        for i in range(si, len(ti)):
            if side == 1 and L[i] <= TSL: ex = min(O[i], TSL); break
            if side == -1 and H[i] >= TSL: ex = max(O[i], TSL); break
            if H[i] > hwm: hwm = H[i]
            if L[i] < lwm: lwm = L[i]
            TSL = max(TSL, hwm * (1 - td)) if side == 1 else min(TSL, lwm * (1 + td))
        if ex is None: ex = C[-1]
        out.append(dict(ret=side * (ex - entry) / entry - COST, risk=risk, atr_e=ap, oi_e=tr["oi_z"],
                        side=side, year=et.year))
    return pd.DataFrame(out)


def report(nm, T, size=None):
    if len(T) < 20: print(f"{nm:<22} 표본 {len(T)}"); return
    r = T.ret.values if size is None else T.ret.values * size
    R = T.ret.values / T.risk.values
    print(f"{nm:<22}{len(T):>5}{tot(r):>+8.0f}{mdd(r):>+8.1f}{sqn(R):>7.2f}{cpcv(r):>+8.2f}")


def main():
    d = pd.read_csv(DATA, usecols=["timestamp", "open", "high", "low", "close", "oi_zscore_24h"])
    d["t"] = pd.to_datetime(d["timestamp"], utc=True, format="ISO8601").dt.tz_localize(None)
    d = d.dropna(subset=["open", "high", "low", "close"]).set_index("t").sort_index()
    doi = pd.to_numeric(d["oi_zscore_24h"], errors="coerce")
    trades = get_entries(d[["open", "high", "low", "close"]], doi)
    print(f"[TS 진입 {len(trades)}건]  {'변형':<22}{'거래':>5}{'복리%':>8}{'MDD%':>8}{'SQN':>7}{'CPCV':>8}")
    print("-" * 66)
    VAR = [("①고정3%(B대조)", "fix", 0), ("②ATR×2 트레일", "atr", 2.0),
           ("③ATR×3 트레일", "atr", 3.0), ("④ATR×4 트레일", "atr", 4.0)]
    Ts = {}
    for nm, m, p in VAR:
        T = sim(d, trades, m, p); Ts[nm] = T; report(nm, T)
    print("--- +ATR×OI 사이징 ---")
    med = None
    for nm in Ts:
        T = Ts[nm]
        if len(T) < 20: continue
        if med is None: med = np.median(T.atr_e.values)
        soi = np.clip(1 - 0.3 * np.maximum(0, T.oi_e.values - 1.5), 0.25, 1)
        sat = np.clip(med / T.atr_e.values, 0.25, 1)
        report(nm + "+사이징", T, sat * soi)
    print("\n[대조] 환상 피보 +447% · B(우리청산 고정3%) +111%/-44.6%/SQN1.71 · reversion 최선 MDD-19~21%")
    print("[판정] ATR트레일이 추세 태워 복리↑·SQN↑ / +사이징서 MDD<-20%면 두 문제 해결.")


if __name__ == "__main__":
    main()
