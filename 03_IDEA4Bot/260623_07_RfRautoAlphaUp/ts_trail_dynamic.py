# -*- coding: utf-8 -*-
# [ts_trail_dynamic.py] (가) TS 진입 + 동적 ATR 트레일(Chandelier 정석: 매 봉 ATR 갱신) + ATR×OI 사이징.
#   캡틴 직감 재검증: 진입시 고정ATR(앞)이 아니라 보유중 7h봉 ATR로 트레일 갱신.
#   ★1m 실체결·낙관금지·비용8bp. 종합분석+그래프 = analyze_backtest(§5).
import sys, os
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\engines")
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\verification")
import trendstack_signal_engine as TS
import analyze_backtest as AB
import numpy as np, pandas as pd, itertools

DATA = r"D:\ML\RfRauto\08_BTC_Data\derived\Merged_Data.csv"
COST = 0.0008; SL_MULT = 1.5; TF = TS.TF_MIN
HERE = os.path.dirname(os.path.abspath(__file__))


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
    atrp = sig["atr"] / df7h["close"].values
    atr7 = pd.Series(atrp, index=df7h.index)
    oi7 = doi.reindex(df7h.index, method="ffill").values
    idx7 = df7h.index
    for tr in trades:
        ei = idx7.get_loc(tr["entry_t"])
        tr["atr_pct"] = float(atrp[ei]) if atrp[ei] > 0 else 0.02
        tr["oi_z"] = float(oi7[ei]) if not np.isnan(oi7[ei]) else 0.0
    return trades, atr7


def sim(d, trades, atr7, mode, mult):
    ti = d.index; O = d["open"].values; H = d["high"].values; L = d["low"].values; C = d["close"].values
    a7i = atr7.index.values; a7v = atr7.values
    out = []
    for tr in trades:
        side = int(tr["side"]); entry = float(tr["entry"]); ap0 = tr["atr_pct"]
        risk = float(np.clip(ap0 * SL_MULT, 0.008, 0.05))
        et = pd.Timestamp(tr["entry_t"]) + pd.Timedelta(minutes=TF)
        si = ti.searchsorted(et)
        if si >= len(ti): continue
        init_sl = entry * (1 - risk) if side == 1 else entry * (1 + risk); TSL = init_sl
        hwm = H[si]; lwm = L[si]; ex = None; tag = "trailing"
        for i in range(si, len(ti)):
            if side == 1 and L[i] <= TSL: ex = min(O[i], TSL); break
            if side == -1 and H[i] >= TSL: ex = max(O[i], TSL); break
            if H[i] > hwm: hwm = H[i]
            if L[i] < lwm: lwm = L[i]
            if mode == "fix":
                td = 0.03
            else:  # 동적 ATR: 현재 1m 시점의 7h봉 ATR
                bi = np.searchsorted(a7i, ti.values[i], side="right") - 1
                cur_atr = a7v[bi] if 0 <= bi < len(a7v) and a7v[bi] > 0 else ap0
                td = mult * cur_atr
            TSL = max(TSL, hwm * (1 - td)) if side == 1 else min(TSL, lwm * (1 + td))
        if ex is None: ex = C[-1]
        if abs(TSL - init_sl) < 1e-9: tag = "initial_SL"
        out.append(dict(ret=side * (ex - entry) / entry - COST, risk=risk, atr_e=ap0, oi_e=tr["oi_z"],
                        side=side, tag=tag, year=et.year, et=et))
    return pd.DataFrame(out)


def main():
    d = pd.read_csv(DATA, usecols=["timestamp", "open", "high", "low", "close", "oi_zscore_24h"])
    d["t"] = pd.to_datetime(d["timestamp"], utc=True, format="ISO8601").dt.tz_localize(None)
    d = d.dropna(subset=["open", "high", "low", "close"]).set_index("t").sort_index()
    doi = pd.to_numeric(d["oi_zscore_24h"], errors="coerce")
    trades, atr7 = get_entries(d[["open", "high", "low", "close"]], doi)
    print(f"[TS 진입 {len(trades)}건] 동적 ATR 트레일 비교 (사이징 후)")
    print(f"{'변형':<18}{'복리%':>8}{'MDD%':>8}{'SQN':>7}{'CPCV':>8}")
    Ts = {}
    for nm, m, p in [("고정3%", "fix", 0), ("동적ATR×2", "atr", 2.0), ("동적ATR×3", "atr", 3.0)]:
        T = sim(d, trades, atr7, m, p); Ts[nm] = T
        med = np.median(T.atr_e.values)
        soi = np.clip(1 - 0.3 * np.maximum(0, T.oi_e.values - 1.5), 0.25, 1)
        sat = np.clip(med / T.atr_e.values, 0.25, 1)
        T["ret_sized"] = T.ret.values * sat * soi
        rs = T["ret_sized"].values
        print(f"{nm:<18}{tot(rs):>+8.0f}{mdd(rs):>+8.1f}{sqn((T.ret/T.risk).values):>7.2f}{cpcv(rs):>+8.2f}")
    # 최선(고정3%+사이징 추정) 종합분석+그래프
    best = Ts["고정3%"].copy(); best["ret"] = best["ret_sized"]
    AB.analyze(best, "TS Entry + Fixed3% Trail + ATRxOI Sizing", os.path.join(HERE, "ts_report_fix3.png"))
    bd = Ts["동적ATR×2"].copy(); bd["ret"] = bd["ret_sized"]
    AB.analyze(bd, "TS Entry + Dynamic ATRx2 Trail + Sizing", os.path.join(HERE, "ts_report_dynatr2.png"))


if __name__ == "__main__":
    main()
