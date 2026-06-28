# -*- coding: utf-8 -*-
# [oi_vol_gate.py] A001 2단계 B — OI Spike 변동성 오버레이.
#   1단계 결과: OI Spike는 방향 예측력 0이나 변동성 트리거(vol비 1.35). → 변동성을 리스크 도구로.
#   ★가설(어제 MDD작업 연결): OI Spike 직후 고변동 구간 진입 = 초기손절 휩쏘(MDD 범인) 많다
#                              → OI Spike 게이트로 그 진입 회피/축소하면 MDD 개선?
#   대상 = V0 최강결합(mom+oi). ★1m 실체결·갭반영(낙관금지)·레버1·비용8bp. SL2%·트레일3%.
#   게이트: 진입 직전 6h 내 OI Spike(|z|>2) 발생 → 회피(avoid) 또는 사이즈0.5(half).
import os, itertools
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ANCHOR = pd.Timestamp("2023-05-01", tz="UTC")
COST = 0.0008; SL_PCT = 0.02; TRAIL = 0.03; ENTRY_Q = 0.33; MAX_HOLD = 60
ZW = 1440        # OI z 롤링 24h
SPIKE_Z = 2.0
LOOKBK = 360     # 진입 직전 6h 내 spike 탐색


def _p(*a): print(*a, flush=True)
def zr(s): return s.rank(pct=True) - 0.5


def find_data():
    for c in [r"D:\ML\RfRauto\08_BTC_Data\derived\Merged_Data.csv", r"D:\ML\Verify\Merged_Data.csv"]:
        if os.path.exists(c): return c
    raise FileNotFoundError("Merged_Data.csv")


def build(DATA):
    d = pd.read_csv(DATA, usecols=["timestamp", "open", "high", "low", "oi_zscore_24h",
                                   "oi_change_1h_pct", "oi_was_missing"])
    d["t"] = pd.to_datetime(d["timestamp"], utc=True, format="ISO8601")
    d = d.dropna(subset=["open", "high", "low"]).sort_values("t").reset_index(drop=True)
    # OI Spike 1m 플래그 (rolling z, 룩어헤드0, 결측 제외)
    oichg = pd.to_numeric(d["oi_change_1h_pct"], errors="coerce")
    miss = pd.to_numeric(d["oi_was_missing"], errors="coerce").fillna(0).values
    z = ((oichg - oichg.rolling(ZW).mean()) / oichg.rolling(ZW).std()).values
    spike = (np.abs(z) > SPIKE_Z) & (miss == 0)
    spike = np.nan_to_num(spike, nan=0).astype(bool)
    # 직전 6h 내 spike 있었나 (rolling any, 과거만)
    recent = pd.Series(spike).rolling(LOOKBK, min_periods=1).max().fillna(0).astype(bool).values
    # 8h 그리드 신호
    g = d.set_index("t").resample("480min", origin=ANCHOR)
    o8 = g["open"].first().dropna()
    oi8 = g["oi_zscore_24h"].last().shift(1)
    S = pd.DataFrame({"open8": o8}).join(oi8.rename("oi_z"))
    S["mom_24h"] = S["open8"].pct_change(3)
    S = S.dropna(subset=["mom_24h", "oi_z"])
    S["combo"] = (-zr(S["mom_24h"])) * 0.048 + (-zr(S["oi_z"])) * 0.037
    hi = S["combo"].quantile(1 - ENTRY_Q); lo = S["combo"].quantile(ENTRY_Q)
    S["side"] = np.where(S["combo"] >= hi, 1, np.where(S["combo"] <= lo, -1, 0))
    return d, S, recent


def simulate(d, S, recent, *, gate="none"):
    es = S["side"].to_dict(); bar8 = set(S.index)
    ti = d["t"]; O = d["open"].values; H = d["high"].values; L = d["low"].values
    trades = []; pos = 0; entry = TS = init_sl = None; et = None; hwm = lwm = None; bars = 0; size = 1.0
    for i in range(len(d)):
        t = ti.iloc[i]
        if pos == 0:
            sd = es.get(t, 0)
            if t in bar8 and sd != 0:
                espike = bool(recent[i])
                if gate == "avoid" and espike:
                    continue
                size = 0.5 if (gate == "half" and espike) else 1.0
                pos = int(sd); entry = O[i]; et = t; bars = 0; hwm = H[i]; lwm = L[i]
                init_sl = entry * (1 - SL_PCT) if pos == 1 else entry * (1 + SL_PCT); TS = init_sl
                entry_spike = espike
        else:
            if H[i] > hwm: hwm = H[i]
            if L[i] < lwm: lwm = L[i]
            ex = None; reason = None
            if pos == 1 and L[i] <= TS: ex = min(O[i], TS)
            elif pos == -1 and H[i] >= TS: ex = max(O[i], TS)
            if ex is None and t in bar8:
                bars += 1
                if bars >= MAX_HOLD: ex = O[i]; reason = "maxhold"
            if ex is not None:
                ret = (pos * (ex - entry) / entry - COST)
                moved = (TS > init_sl + 1e-9) if pos == 1 else (TS < init_sl - 1e-9)
                tag = reason or ("trailing" if moved else "initial_SL")
                trades.append(dict(ret=ret, size=size, tag=tag, spike=entry_spike,
                                   year=pd.Timestamp(et).year)); pos = 0
            else:
                TS = max(TS, hwm * (1 - TRAIL)) if pos == 1 else min(TS, lwm * (1 + TRAIL))
    return pd.DataFrame(trades)


def metrics(T):
    r = (T.ret * T["size"]).values  # 사이즈 반영 복리
    eq = np.cumprod(1 + r); tot = (eq[-1] - 1) * 100
    mdd = np.min((eq - np.maximum.accumulate(eq)) / np.maximum.accumulate(eq)) * 100
    g6 = np.array_split(np.arange(len(r)), 6); ps = []
    for c in itertools.combinations(range(6), 2):
        rr = r[np.concatenate([g6[k] for k in c])]
        ps.append(rr.mean() / rr.std() * np.sqrt(len(rr) / 3) if rr.std() > 0 else 0)
    isl = T[T.tag == "initial_SL"]
    return dict(n=len(T), tot=tot, mdd=mdd, p25=np.percentile(ps, 25),
                isl_share=100*len(isl)/len(T), win=100*(r > 0).mean())


def main():
    DATA = find_data(); _p(f"[데이터] {DATA}")
    d, S, recent = build(DATA)
    _p(f"[신호] 8h봉 {len(S)} | 진입후보 {int((S.side!=0).sum())}")

    # ── 진단: OI Spike 직후 진입 거래 vs 일반 거래 (가설: spike 진입이 더 휩쏘?) ──
    T0 = simulate(d, S, recent, gate="none")
    sp = T0[T0.spike]; nsp = T0[~T0.spike]
    _p(f"\n【진단】 베이스 {len(T0)}거래 | OI Spike직후 진입 {len(sp)}건({100*len(sp)/len(T0):.0f}%) vs 일반 {len(nsp)}건")
    for lbl, g in [("OI Spike직후 진입", sp), ("일반 진입", nsp)]:
        isl = 100*(g.tag == "initial_SL").mean(); _p(
            f"  {lbl:<16} 평균ret {g.ret.mean()*100:+.2f}% | 승률 {100*(g.ret>0).mean():.0f}% | initial_SL비중 {isl:.0f}% | 손익합 {g.ret.sum()*100:+.1f}%p")

    # ── 게이트 변형 비교 ──
    _p(f"\n【게이트 비교】{'변형':<18}{'거래':>5}{'복리%':>9}{'MDD%':>8}{'CPCVp25':>9}{'초기SL%':>8}{'-20내':>6}")
    _p("-" * 64)
    for nm, g in [("V0 무게이트", "none"), ("회피(spike진입X)", "avoid"), ("축소(spike size0.5)", "half")]:
        T = simulate(d, S, recent, gate=g)
        m = metrics(T)
        ok = "O" if (m["tot"] > 0 and m["p25"] > 0 and m["mdd"] > -20) else "X"
        _p(f"{nm:<18}{m['n']:>5}{m['tot']:>+9.1f}{m['mdd']:>+8.1f}{m['p25']:>+9.2f}{m['isl_share']:>7.0f}%{ok:>6}")
    _p("\n[판정] OI Spike직후 진입이 initial_SL↑·손익↓면 가설성립 → 게이트가 MDD↓·CPCV↑면 변동성 오버레이 채택후보.")
    _p("[정직] 미최적화(spike z>2·직전6h·SL2%). 후보면 z/윈도 민감도+CPCV 표준6 재검증.")


if __name__ == "__main__":
    main()
