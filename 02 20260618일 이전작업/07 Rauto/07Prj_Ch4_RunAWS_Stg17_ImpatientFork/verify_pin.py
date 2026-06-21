# -*- coding: utf-8 -*-
# [verify_pin.py] 봉경계 핀고정 검증: 핀고정 킹 on_bar(라이브) ≡ 배치 킹(resample 백테)? (1회용)
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "bots"))
import trendstack_signal_engine as E, trendstack_poc as P
from bot_trendstack_impatient_king import TrendStackImpatientKingBot
from rauto_contract import MarketBar, Action
DATA = r"D:\ML\Verify\Merged_Data.csv"
df = pd.read_csv(DATA, usecols=lambda c: c in ("timestamp", "open", "high", "low", "close", "volume", "oi_zscore_24h"))
df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert(None)
rows = list(df.itertuples(index=False))

# 라이브 경로(핀고정 킹)
bot = TrendStackImpatientKingBot(); bot.on_init({}); n = 0
for r in rows:
    oz = r.oi_zscore_24h; oz = float(oz) if oz == oz else float("nan")
    bot.on_bar(MarketBar(ts=r.timestamp, o=r.open, h=r.high, l=r.low, c=r.close, v=r.volume, aux={"oi_zscore": oz}))
live = bot._trades
print(f"라이브(on_bar 핀고정) 거래: {len(live)}")
lset = set((pd.Timestamp(t["entry_t"]).floor("h"), int(t["side"])) for t in live)

# 배치 경로(resample) — 킹 로직 1:1
d = df.set_index("timestamp"); ohlc = d[["open", "high", "low", "close"]]; df7 = E.resample_tf(ohlc, E.TF_MIN)
vol7 = d["volume"].resample(f"{E.TF_MIN}min", label="left", closed="left").sum().reindex(df7.index).fillna(0.0)
oi7 = d["oi_zscore_24h"].resample(f"{E.TF_MIN}min", label="left", closed="left").last().reindex(df7.index).values
sig = E.compute_signals(df7); Trend = sig["Trend"]; phc = sig["ph_conf"]; plc = sig["pl_conf"]; er = sig["er"]
H = df7["high"].values; L = df7["low"].values; Cl = df7["close"].values; idx = df7.index
COST = E.COST; SLP = E.SL_PCT; DZ_LO, DZ_HI = E.DZ_LO, E.DZ_HI; GER = 0.45; fib = E.FIB
pos = 0; ep = np.nan; ei = -1; sl = np.nan; pb = 0; lastPH = np.nan; lastPL = np.nan; batch = []
for i in range(len(df7)):
    if i < (E.LEFT + E.RIGHT + 1): continue
    nph = i in phc; npl = i in plc
    if nph: lastPH = phc[i][1]
    if npl: lastPL = plc[i][1]
    if pos != 0:
        flip = (pos == 1 and Trend[i] == -1) or (pos == -1 and Trend[i] == 1)
        slbr = (i > ei and not np.isnan(sl)) and ((pos == 1 and L[i] <= sl) or (pos == -1 and H[i] >= sl))
        ex = ("sl", sl) if slbr else (("flip", Cl[i]) if flip else None)
        if ex:
            batch.append((idx[ei], pos)); pos = 0; sl = np.nan; pb = 0; continue
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
print(f"배치(resample) 거래: {len(batch)}")
bset = set((pd.Timestamp(t).floor("h"), t2) for t, t2 in batch)
common = len(lset & bset)
print(f"진입(시각±시간,방향) 일치: {common}/{len(bset)} (배치) · {common}/{len(lset)} (라이브)")
print(f"→ 핀고정 {'성공(거의 일치)' if common >= 0.9 * min(len(lset), len(bset)) else '불일치 잔존'}")
