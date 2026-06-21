# -*- coding: utf-8 -*-
# [realistic_return.py] 현실 체결(측정 슬리피지+갭청산) 반영 실제 수익률 — R2(k1.0)·R4(k1.4). (1회용)
#   낙관: SL에 -1%대 깔끔체결(현 백테). 현실: SL터치 1분봉이 SL보다 더 간 거리만큼 불리체결(청산선 -hsd서 캡).
#   3버전: 낙관 / 현실-중도(슬립 50%) / 현실-보수(슬립 100%=그 1분 극단). 진짜는 중도~낙관 사이.
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "bots"))
import trendstack_signal_engine as E, trendstack_poc as P, rauto_paper_engine as PE
from rauto_contract import Signal, Action, Side
DATA = r"D:\ML\Verify\Merged_Data.csv"
m = pd.read_csv(DATA, usecols=lambda c: c in ("timestamp", "open", "high", "low", "close"))
m["timestamp"] = pd.to_datetime(m["timestamp"], utc=True).dt.tz_convert(None); m = m.set_index("timestamp").sort_index()
d = pd.read_csv(DATA, usecols=lambda c: c in ("timestamp", "open", "high", "low", "close", "volume", "oi_zscore_24h"))
d["timestamp"] = pd.to_datetime(d["timestamp"], utc=True).dt.tz_convert(None); d = d.set_index("timestamp")
df7 = E.resample_tf(m[["open", "high", "low", "close"]], E.TF_MIN)
vol7 = d["volume"].resample(f"{E.TF_MIN}min", label="left", closed="left").sum().reindex(df7.index).fillna(0.0)
oi7 = d["oi_zscore_24h"].resample(f"{E.TF_MIN}min", label="left", closed="left").last().reindex(df7.index).values
sig = E.compute_signals(df7); Trend = sig["Trend"]; phc = sig["ph_conf"]; plc = sig["pl_conf"]; er = sig["er"]
H = df7["high"].values; L = df7["low"].values; Cl = df7["close"].values; idx = df7.index; mid = (H + L) / 2.0
atr7 = E.compute_atr(H, L, Cl, E.ATR_PERIOD); poc7 = P.compute_poc(H, L, mid, vol7.values, 60, 50)
import trendstack_regime as RG
df4 = E.resample_tf(m[["open", "high", "low", "close"]], 240)
try:
    _, fs = RG.feat_struct_of(df4, 8); fs.index = df4.index
except Exception:
    fs = pd.Series("range", index=df4.index)
eh = ((idx - pd.Timestamp("1970-01-01")) / pd.Timedelta(hours=1)).values.astype("float64")
COST = E.COST; SLP = E.SL_PCT; F8 = E.FUND_8H; DZ_LO, DZ_HI = E.DZ_LO, E.DZ_HI; GER = 0.45; fib = E.FIB
SLIP = 0.0005; BASE = 7.0864; LEV = 22.0; SH = 0.0; MMR = 0.004; HSD = 1.0 / LEV - MMR - SLIP


def nf(a, b): return int(np.floor(eh[b] / 8.0) - np.floor(eh[a] / 8.0))
def opvnn(dev, rdir, side):
    if dev is None or np.isnan(dev): return 1.0
    if abs(dev) >= 0.25: return 1.0 if side == rdir else 0.6 if side == -rdir else 1.0
    return 1.0


def king():
    pos = 0; ep = np.nan; ei = -1; sl = np.nan; pb = 0; lastPH = np.nan; lastPL = np.nan; out = []
    for i in range(len(df7)):
        if i < (E.LEFT + E.RIGHT + 1): continue
        nph = i in phc; npl = i in plc
        if nph: lastPH = phc[i][1]
        if npl: lastPL = plc[i][1]
        if pos != 0:
            flip = (pos == 1 and Trend[i] == -1) or (pos == -1 and Trend[i] == 1)
            slbr = (i > ei and not np.isnan(sl)) and ((pos == 1 and L[i] <= sl) or (pos == -1 and H[i] >= sl))
            if slbr or flip:
                dev, rdir = P.dev_rdir(ep, poc7[ei], atr7[ei]) if (atr7[ei] > 0 and not np.isnan(poc7[ei])) else (np.nan, 0)
                feat = str(fs.asof(idx[ei])); cut = SH if (feat == "uptrend" and pos == -1) else 1.0
                out.append(dict(et=idx[ei], xt=idx[i], ep=float(ep), sl=float(sl) if not np.isnan(sl) else float(ep),
                                clo=float(Cl[i]), side=int(pos), reason="sl" if slbr else "flip",
                                base=BASE * opvnn(dev, rdir, pos) * cut, fund=F8 * nf(ei, i)))
                pos = 0; sl = np.nan; pb = 0; continue
            if pos == 1 and npl and not np.isnan(lastPH):
                pb += 1; r = fib[0] if pb == 1 else fib[1] if pb == 2 else fib[2]
                cand = lastPH - r * (lastPH - plc[i][1]); sl = cand if np.isnan(sl) else max(sl, cand)
            if pos == -1 and nph and not np.isnan(lastPL):
                pb += 1; r = fib[0] if pb == 1 else fib[1] if pb == 2 else fib[2]
                cand = lastPL + r * (phc[i][1] - lastPL); sl = cand if np.isnan(sl) else min(sl, cand)
        if pos == 0:
            le = Trend[i] == 1 and not np.isnan(lastPH) and not np.isnan(lastPL)
            se = Trend[i] == -1 and not np.isnan(lastPH) and not np.isnan(lastPL)
            z = oi7[i]
            if not np.isnan(z) and (DZ_LO <= z < DZ_HI) and (er[i] >= GER): le = False; se = False
            if le or se:
                dd = 1 if le else -1; ep = Cl[i]; pos = dd; ei = i; pb = 0; sl = ep * (1 - dd * SLP / 100)
    return out


KT = king()
# 각 SL거래: SL터치 1분봉의 시가역행(open_adv, 갭판정용)·SL초과 excursion 측정
for t in KT:
    t["open_adv"] = 0.0; t["exc"] = 0.0
    if t["reason"] != "sl": continue
    seg = m.loc[t["et"]: t["xt"] + pd.Timedelta(hours=7, minutes=5)]
    hit = seg[seg["low"] <= t["sl"]] if t["side"] == 1 else seg[seg["high"] >= t["sl"]]
    if not len(hit): continue
    em = hit.iloc[0]; eo = float(em["open"])
    t["open_adv"] = (eo - t["ep"]) / t["ep"] if t["side"] == 1 else (t["ep"] - eo) / t["ep"]
    t["exc"] = max(0.0, (t["sl"] - float(em["low"])) / t["ep"] if t["side"] == 1 else (float(em["high"]) - t["sl"]) / t["ep"])


def Rof(t, lev, fix_slip):
    hsd = 1.0 / lev - MMR - SLIP; side = t["side"]; ep = t["ep"]
    if t["reason"] == "flip":
        return side * (t["clo"] - ep) / ep - COST - t["fund"]
    if t["open_adv"] <= -hsd:                       # 갭청산(시가가 청산선 너머 갭)
        return -hsd - COST - t["fund"]
    base_adv = side * (t["sl"] - ep) / ep           # SL 기본(보통 -1%대)
    adv = max(base_adv - fix_slip, -hsd)            # 고정 슬립 추가, 청산선 캡
    return adv - COST - t["fund"]


def acct(k, lev, fix_slip):
    a = PE.PaperAccount(10000.0); eq = []; nl = 0
    for t in KT:
        a.open(Signal(Action.ENTER, side=Side(t["side"]), size_pct=t["base"] * k, leverage=lev), ts=None, price=100.0)
        R = Rof(t, lev, fix_slip)
        if t["reason"] == "sl" and t["open_adv"] <= -(1.0 / lev - MMR - SLIP): nl += 1
        a.resolve_replay(R=R, mae=min(0.0, R), fund=0.0); eq.append(a.bal)
    eq = np.array(eq); pk = np.maximum.accumulate(eq); mdd = ((eq / pk - 1).min()) * 100
    return (a.bal / 1e4 - 1) * 100, mdd, nl


print(f"총 {len(KT)}거래 (SL {sum(1 for t in KT if t['reason']=='sl')}/flip {sum(1 for t in KT if t['reason']=='flip')})")
print("슬립모델: 고정 스톱슬립(SL에 추가 불리). 갭청산=시가가 청산선 너머 갭(레버별 재판정).")
print(f"\n{'슬롯/레버':>12} {'낙관(0bp)':>14} {'현실(10bp)':>14} {'보수(20bp)':>14} {'갭청산'}")
for name, k, lev in [("R2 lev22", 1.0, 22.0), ("R2 lev10", 1.0, 10.0), ("R2 lev7", 1.0, 7.0),
                     ("R4 lev22", 1.4, 22.0), ("R4 lev10", 1.4, 10.0)]:
    o = acct(k, lev, 0.0); r = acct(k, lev, 0.001); w = acct(k, lev, 0.002)
    print(f"{name:>12} {o[0]:>+8.0f}%/{o[1]:>5.0f}% {r[0]:>+8.0f}%/{r[1]:>5.0f}% {w[0]:>+8.0f}%/{w[1]:>5.0f}% {o[2]:>5}건")
print("\n(MDD=거래체결시점 기준, 일별은 더 깊을 수 있음. 갭청산=레버별 시가갭 청산 건수)")
