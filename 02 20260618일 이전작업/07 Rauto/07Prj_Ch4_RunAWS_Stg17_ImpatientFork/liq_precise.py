# -*- coding: utf-8 -*-
# [liq_precise.py] 강제청산 정밀감사 — 킹 각 거래를 1분봉 경로로 검사. (1회용)
#   질문: 보유 중 1분봉이 청산선(-hsd, lev22≈-4.1%)을 '갭으로' 통과했나(진짜청산) vs 1% 손절선만 닿았나(정상)?
#   hsd = 1/lev - MMR - SLIP. 청산 = 1분봉 시가(open)가 진입 대비 -hsd 넘어 갭(스톱이 못 막음).
#   부수: SL 발동 분(分)에서 1분 저가가 SL보다 얼마나 더 갔나(스톱 슬리피지 노출).
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "bots"))
import trendstack_signal_engine as E, trendstack_poc as P
DATA = r"D:\ML\Verify\Merged_Data.csv"
m = pd.read_csv(DATA, usecols=lambda c: c in ("timestamp", "open", "high", "low", "close"))
m["timestamp"] = pd.to_datetime(m["timestamp"], utc=True).dt.tz_convert(None)
m = m.set_index("timestamp").sort_index()
df = m[["open", "high", "low", "close"]]; df7 = E.resample_tf(df, E.TF_MIN)
d = pd.read_csv(DATA, usecols=lambda c: c in ("timestamp", "open", "high", "low", "close", "volume", "oi_zscore_24h"))
d["timestamp"] = pd.to_datetime(d["timestamp"], utc=True).dt.tz_convert(None); d = d.set_index("timestamp")
vol7 = d["volume"].resample(f"{E.TF_MIN}min", label="left", closed="left").sum().reindex(df7.index).fillna(0.0)
oi7 = d["oi_zscore_24h"].resample(f"{E.TF_MIN}min", label="left", closed="left").last().reindex(df7.index).values
sig = E.compute_signals(df7); Trend = sig["Trend"]; phc = sig["ph_conf"]; plc = sig["pl_conf"]; er = sig["er"]
H = df7["high"].values; L = df7["low"].values; Cl = df7["close"].values; idx = df7.index
COST = E.COST; SLP = E.SL_PCT; F8 = E.FUND_8H; DZ_LO, DZ_HI = E.DZ_LO, E.DZ_HI; GER = 0.45; fib = E.FIB; SLIP = 0.0005
MMR = 0.004; LEV = 22.0; HSD = 1.0 / LEV - MMR - SLIP   # 청산버퍼 거리(가격 역행 %)
print(f"청산선(hsd) = 1/{LEV:.0f} - MMR{MMR} - slip{SLIP} = {HSD*100:.2f}% 역행")


def king_trades():
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
                out.append(dict(et=idx[ei], xt=idx[i], ep=float(ep), sl=float(sl) if not np.isnan(sl) else float(ep),
                                side=int(pos), reason="sl" if slbr else "flip"))
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


KT = king_trades()
liq_gap = []; slip_over = []; liq_intrabar = 0; GAPS = []; DEEPS = []
for t in KT:
    if t["reason"] != "sl": continue
    ep = t["ep"]; side = t["side"]; sl = t["sl"]
    seg = m.loc[t["et"]: t["xt"] + pd.Timedelta(hours=7, minutes=5)]   # 진입~청산봉 끝(7h봉 내 SL체결)
    if not len(seg): continue
    # ★첫 SL-터치 1분봉 찾기 (롱: low<=sl, 숏: high>=sl)
    hit = seg[seg["low"] <= sl] if side == 1 else seg[seg["high"] >= sl]
    if not len(hit): continue
    em = hit.iloc[0]                                         # SL 터치된 그 1분봉
    eo = float(em["open"]); elow = float(em["low"]); ehigh = float(em["high"])
    gap = (eo - ep) / ep if side == 1 else (ep - eo) / ep   # 그 분봉 '시가' 역행(갭=스톱 못막음)
    deep = (sl - elow) / ep if side == 1 else (ehigh - sl) / ep  # 그 분봉이 SL보다 더 간 거리(슬리피지)
    if gap <= -HSD:                                          # 시가가 청산선 넘어 갭 = 진짜 청산
        liq_gap.append((str(t["et"])[:16], side, round(gap * 100, 2)))
    if deep >= HSD:                                          # SL봉 내에서 청산선 넘어감(그 1분 안 청산 위험)
        liq_intrabar += 1
    GAPS.append(gap); DEEPS.append(deep); slip_over.append(max(0.0, deep))
print(f"\n총 킹 거래 {len(KT)} | SL {sum(1 for t in KT if t['reason']=='sl')} / flip {sum(1 for t in KT if t['reason']=='flip')}")
print(f"\n★(A) 진짜 갭청산 — SL터치 1분봉 '시가'가 -{HSD*100:.1f}% 넘어 갭(스톱 무력): {len(liq_gap)}건 / {len(slip_over)}")
for x in liq_gap[:12]: print("   ", x)
print(f"\n★(B) SL터치 1분봉 '저가/고가'가 청산선 -{HSD*100:.1f}% 넘어감(그 1분 내 청산위험): {liq_intrabar}건 / {len(slip_over)}")
so = np.array(slip_over)
print(f"\n스톱 슬리피지(SL봉이 SL보다 더 간 거리/진입): 평균 {so.mean()*100:.2f}% · 중앙값 {np.median(so)*100:.2f}% · 95%분위 {np.percentile(so,95)*100:.2f}% · 최악 {so.max()*100:.2f}%")
print(f"  → 백테는 SL(-1%대)에 깔끔체결 가정. 현실 평균 추가 {so.mean()*100:.2f}%p 더 나쁨(레버22 곱하면 계좌타격 큼).")
# ── 레버리지 민감도: 청산버퍼를 넓히면 청산이 얼마나 주나 ──
gaps = np.array(GAPS); deeps = np.array(DEEPS)   # 각 SL거래의 (시가역행, 저가역행)
print("\n=== 레버 낮추면 청산 줄어드나 (hsd=1/lev-mmr-slip) ===")
print(f"  {'레버':>4} {'청산버퍼%':>8} {'갭청산건':>8} {'1분내 청산위험건':>14}")
for lev in (22, 15, 10, 7, 5, 3):
    hsd = 1.0 / lev - MMR - SLIP
    ng = int((gaps <= -hsd).sum()); nd = int((deeps >= hsd).sum())
    print(f"  {lev:>4} {hsd*100:>7.1f}% {ng:>8} {nd:>14}")
print("  → 레버를 낮출수록 버퍼↑·청산↓. 목표=청산 0~극소 + 슬리피지 꼬리 감내 가능한 레버 선택.")
