# -*- coding: utf-8 -*-
# [ts_honest_B.py] TS 진입(무수정 §15-1) + 우리 검증 청산(변동성SL+트레일) 1m 정직 재구성.
#   = TS 진입신호의 '순수 알파'(피보 트레일 환상 제거). reversion서 검증된 청산 적용.
#   ★1m 실체결·갭반영(낙관금지)·비용8bp. 엔진은 무수정 재사용.
import sys, os
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\engines")
import trendstack_signal_engine as TS
import numpy as np, pandas as pd, itertools

DATA = r"D:\ML\RfRauto\08_BTC_Data\derived\Merged_Data.csv"
COST = 0.0008; SL_MULT = 1.5; TRAIL = 0.03; MAXHOLD_MIN = 30 * 24 * 60  # 30일 백업


def mdd(r): eq = np.cumprod(1 + r); return ((eq - np.maximum.accumulate(eq)) / np.maximum.accumulate(eq)).min() * 100
def tot(r): return (np.cumprod(1 + r)[-1] - 1) * 100
def sqn(R): return R.mean() / R.std() * np.sqrt(len(R)) if R.std() > 0 else 0
def cpcv(r, g=6):
    gs = np.array_split(np.arange(len(r)), g); ps = []
    for c in itertools.combinations(range(g), 2):
        rr = r[np.concatenate([gs[k] for k in c])]
        ps.append(rr.mean() / rr.std() * np.sqrt(len(rr) / 3) if rr.std() > 0 else 0)
    return np.percentile(ps, 25)


def main():
    d = pd.read_csv(DATA, usecols=["timestamp", "open", "high", "low", "close"])
    d["t"] = pd.to_datetime(d["timestamp"], utc=True, format="ISO8601").dt.tz_localize(None)
    d = d.dropna(subset=["open", "high", "low", "close"]).set_index("t").sort_index()
    df7h = TS.resample_tf(d[["open", "high", "low", "close"]], TS.TF_MIN)
    sig = TS.compute_signals(df7h)
    trades = TS.run_strategy(df7h, sig, 0, "none", 0.8, gate_mode="er", gate_er=0.45,
                             split_mode="A", split_n=3, fib=(0.3, 0.5, 0.6))
    atr = sig["atr"]; c7 = df7h["close"].values; idx7 = df7h.index
    # 진입시 7h ATR%
    for tr in trades:
        ei = idx7.get_loc(tr["entry_t"])
        tr["atr_pct"] = float(atr[ei] / c7[ei]) if c7[ei] > 0 else 0.02
    # 1m 정직 청산
    ti = d.index; O = d["open"].values; H = d["high"].values; L = d["low"].values; C = d["close"].values
    out = []
    for tr in trades:
        side = int(tr["side"]); entry = float(tr["entry"]); ap = tr["atr_pct"]
        risk = float(np.clip(ap * SL_MULT, 0.008, 0.05))
        et = pd.Timestamp(tr["entry_t"]) + pd.Timedelta(minutes=TS.TF_MIN)  # 진입체결 = 7h봉 종가시점
        si = ti.searchsorted(et)
        if si >= len(ti): continue
        init_sl = entry * (1 - risk) if side == 1 else entry * (1 + risk); TSL = init_sl
        hwm = H[si]; lwm = L[si]; bars = 0; ex = None
        for i in range(si, len(ti)):
            # 청산 체크 먼저(직전 TSL) — 룩어헤드0
            if side == 1 and L[i] <= TSL: ex = min(O[i], TSL); break
            if side == -1 and H[i] >= TSL: ex = max(O[i], TSL); break
            bars += 1
            if bars >= MAXHOLD_MIN: ex = O[i]; break
            # 트레일 갱신(현재봉 고저 → 다음봉용)
            if H[i] > hwm: hwm = H[i]
            if L[i] < lwm: lwm = L[i]
            TSL = max(TSL, hwm * (1 - TRAIL)) if side == 1 else min(TSL, lwm * (1 + TRAIL))
        if ex is None: ex = C[-1]
        ret = side * (ex - entry) / entry - COST
        out.append(dict(ret=ret, risk=risk, side=side, year=et.year))
    T = pd.DataFrame(out)
    r = T.ret.values; R = T.ret.values / T.risk.values
    print(f"[TS 진입 {len(trades)}건 → 정직청산 {len(T)}건]")
    print(f"  ★B(TS진입+변동성SL+트레일3%·1m정직): 복리 {tot(r):+.0f}% / MDD {mdd(r):.1f}% / "
          f"SQN {sqn(R):.2f} / CPCV {cpcv(r):+.2f} / 승률 {100*(r>0).mean():.0f}%")
    print(f"  (대조: 환상 피보청산 +447%/-25.9% / 우리 reversion 최선 SQN1.6~1.78)")
    for y in sorted(T.year.unique()):
        s = T[T.year == y]; print(f"    {int(y)}: {len(s)}건 합 {((1+s.ret).prod()-1)*100:+.0f}%")
    T.to_csv("ts_honest_B_ledger.csv", index=False, encoding="utf-8-sig")
    print("[저장] ts_honest_B_ledger.csv")


if __name__ == "__main__":
    main()
