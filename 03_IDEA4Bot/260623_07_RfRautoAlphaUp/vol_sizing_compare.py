# -*- coding: utf-8 -*-
# [vol_sizing_compare.py] A001 분수령 — OI Spike 사이징 vs ATR 사이징 (OI 고유가치 판정).
#   2단계 결과: OI Spike size축소로 MDD -39→-28%. 질문: OI가 단순 ATR(가격변동성) 타게팅보다 나은가?
#   방법: V0 무게이트 1회 시뮬 → 거래별 진입맥락(atr_pct·oi강도) 기록 → 사후 4사이징 비교.
#   ★트레일 청산은 가격레벨이라 size 무관 → 사후 ret×size 적용 타당. 1m실체결·비용8bp.
#   판정: ATR×OI가 ATR단독보다 MDD↓·CPCV유지면 OI 증분가치 有(승격). 동급이면 OI=ATR로 흡수(졸업실패).
import os, itertools
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ANCHOR = pd.Timestamp("2023-05-01", tz="UTC")
COST = 0.0008; SL_PCT = 0.02; TRAIL = 0.03; ENTRY_Q = 0.33; MAX_HOLD = 60
ZW = 1440; LOOKBK = 360; ATR_N = 14


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
    oichg = pd.to_numeric(d["oi_change_1h_pct"], errors="coerce")
    miss = pd.to_numeric(d["oi_was_missing"], errors="coerce").fillna(0).values
    z = ((oichg - oichg.rolling(ZW).mean()) / oichg.rolling(ZW).std())
    absz = z.abs().where(miss == 0)
    oi_int = absz.rolling(LOOKBK, min_periods=1).max().fillna(0).values  # 직전6h max|z|(과거)
    g = d.set_index("t").resample("480min", origin=ANCHOR)
    o8 = g["open"].first(); h8 = g["high"].max(); l8 = g["low"].min()
    oi8 = g["oi_zscore_24h"].last().shift(1)
    S = pd.DataFrame({"open8": o8, "high8": h8, "low8": l8}).dropna(subset=["open8"]).join(oi8.rename("oi_z"))
    S["mom_24h"] = S["open8"].pct_change(3)
    S["atr_pct"] = ((S["high8"] - S["low8"]).rolling(ATR_N).mean() / S["open8"]).shift(1)  # 룩어헤드0
    S = S.dropna(subset=["mom_24h", "oi_z", "atr_pct"])
    S["combo"] = (-zr(S["mom_24h"])) * 0.048 + (-zr(S["oi_z"])) * 0.037
    hi = S["combo"].quantile(1 - ENTRY_Q); lo = S["combo"].quantile(ENTRY_Q)
    S["side"] = np.where(S["combo"] >= hi, 1, np.where(S["combo"] <= lo, -1, 0))
    return d, S, oi_int


def simulate(d, S, oi_int):
    es = S["side"].to_dict(); atr_of = S["atr_pct"].to_dict(); bar8 = set(S.index)
    ti = d["t"]; O = d["open"].values; H = d["high"].values; L = d["low"].values
    tr = []; pos = 0; entry = TS = init_sl = None; et = None; hwm = lwm = None; bars = 0
    atr_e = oi_e = None
    for i in range(len(d)):
        t = ti.iloc[i]
        if pos == 0:
            sd = es.get(t, 0)
            if t in bar8 and sd != 0:
                pos = int(sd); entry = O[i]; et = t; bars = 0; hwm = H[i]; lwm = L[i]
                init_sl = entry * (1 - SL_PCT) if pos == 1 else entry * (1 + SL_PCT); TS = init_sl
                atr_e = atr_of.get(t, np.nan); oi_e = oi_int[i]
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
                ret = pos * (ex - entry) / entry - COST
                tr.append(dict(ret=ret, atr_e=atr_e, oi_e=oi_e, year=pd.Timestamp(et).year)); pos = 0
            else:
                TS = max(TS, hwm * (1 - TRAIL)) if pos == 1 else min(TS, lwm * (1 + TRAIL))
    return pd.DataFrame(tr)


def met(ret, size):
    r = ret.values * size
    eq = np.cumprod(1 + r); tot = (eq[-1] - 1) * 100
    pk = np.maximum.accumulate(eq); mdd = np.min((eq - pk) / pk) * 100
    g6 = np.array_split(np.arange(len(r)), 6); ps = []
    for c in itertools.combinations(range(6), 2):
        rr = r[np.concatenate([g6[k] for k in c])]
        ps.append(rr.mean() / rr.std() * np.sqrt(len(rr) / 3) if rr.std() > 0 else 0)
    return tot, mdd, np.percentile(ps, 25), size.mean()


def main():
    DATA = find_data(); _p(f"[데이터] {DATA}")
    d, S, oi_int = build(DATA)
    T = simulate(d, S, oi_int)
    _p(f"[거래] {len(T)} | atr_pct 중앙 {T.atr_e.median():.4f} | oi강도 중앙 {T.oi_e.median():.2f}")
    n = len(T)
    # 사이징 정의 (고변동·고OI강도 → 축소, 하한0.25)
    med_atr = T.atr_e.median()
    s_atr = np.clip(med_atr / T.atr_e.values, 0.25, 1.0)
    s_oi = np.clip(1.0 - 0.30 * np.maximum(0, T.oi_e.values - 1.5), 0.25, 1.0)
    sizes = {"무사이징(size1)": np.ones(n), "ATR타게팅": s_atr,
             "OI강도": s_oi, "ATR×OI": s_atr * s_oi}
    _p(f"\n{'사이징':<16}{'복리%':>9}{'MDD%':>8}{'CPCVp25':>9}{'평균노출':>8}{'-20내':>6}")
    _p("-" * 56)
    base = None
    for nm, sz in sizes.items():
        tot, mdd, p25, ms = met(T["ret"], sz)
        if nm == "ATR타게팅": base = (mdd, p25)
        ok = "O" if (tot > 0 and p25 > 0 and mdd > -20) else "X"
        _p(f"{nm:<16}{tot:>+9.1f}{mdd:>+8.1f}{p25:>+9.2f}{ms:>8.2f}{ok:>6}")
    # 공정대조: 같은 평균노출로 정규화한 MDD (변동성 '타이밍' 품질만 비교)
    _p("\n[공정대조] 평균노출 0.60 고정 정규화 — 변동성 타이밍 품질만 비교(누가 같은 노출서 MDD 낮나)")
    _p(f"{'사이징':<16}{'복리%':>9}{'MDD%':>8}{'CPCVp25':>9}")
    _p("-" * 44)
    for nm, sz in sizes.items():
        szn = sz / sz.mean() * 0.60
        szn = np.clip(szn, 0, 1.5)
        tot, mdd, p25, ms = met(T["ret"], szn)
        _p(f"{nm:<16}{tot:>+9.1f}{mdd:>+8.1f}{p25:>+9.2f}")
    _p("\n[판정] ATR×OI가 ATR단독보다 (정규화)MDD↓·CPCV유지 = OI 증분가치 有 → A001 05_Alpha_Up 승격.")
    _p("       동급/열위 = OI 변동성정보는 ATR에 흡수 = OI 고유가치 없음(A001 변동성축 졸업실패, 방향도 1단계 사망).")
    _p("[정직] 사이징 공식 미최적화(K0.3·임계1.5·하한0.25). 후보면 민감도+CPCV 표준6.")


if __name__ == "__main__":
    main()
