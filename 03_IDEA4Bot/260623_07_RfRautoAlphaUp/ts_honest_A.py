# -*- coding: utf-8 -*-
# [ts_honest_A.py] TS 원본 청산(피보 트레일+trend_flip)을 1m 실체결로 정직 재구성.
#   = TS 봇이 '실제로 체결 가능했던' 진짜 성능(환상 +447% 검증). 엔진 청산 로직 복제(§1 래퍼, 엔진 무수정).
#   ★앵커: 복제 진입수 = phantom 324건 일치 확인. 청산은 1m 갭반영(낙관금지)·비용8bp.
import sys
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\engines")
import trendstack_signal_engine as TS
import numpy as np, pandas as pd, itertools

DATA = r"D:\ML\RfRauto\08_BTC_Data\derived\Merged_Data.csv"
COST = 0.0008; TF = TS.TF_MIN; FIB = (0.3, 0.5, 0.6)


def mdd(r): eq = np.cumprod(1 + r); return ((eq - np.maximum.accumulate(eq)) / np.maximum.accumulate(eq)).min() * 100
def tot(r): return (np.cumprod(1 + r)[-1] - 1) * 100
def sqn(R): return R.mean() / R.std() * np.sqrt(len(R)) if R.std() > 0 else 0
def cpcv(r, g=6):
    gs = np.array_split(np.arange(len(r)), g); ps = []
    for c in itertools.combinations(range(g), 2):
        rr = r[np.concatenate([gs[k] for k in c])]
        ps.append(rr.mean() / rr.std() * np.sqrt(len(rr) / 3) if rr.std() > 0 else 0)
    return np.percentile(ps, 25)


def ts_replay(df7h, sig, atrp=None, oi7=None, vol_sl=False, sl_mult=1.5):
    """run_strategy 복제 — 진입 + 피보 sl 궤적 + trend_flip.
       vol_sl=True면 초기SL=변동성(atr_pct*sl_mult), 진입봉 atr/oi 기록(사이징용)."""
    high = df7h["high"].values; low = df7h["low"].values
    close = df7h["close"].values; open_ = df7h["open"].values
    n = len(close); Trend = sig["Trend"]; ph_conf = sig["ph_conf"]; pl_conf = sig["pl_conf"]
    lastPH = lastPL = np.nan; pos = 0; entry_i = -1; sl = np.nan; pb = 0
    entries = []; cur = None
    for i in range(n):
        new_ph = i in ph_conf; new_pl = i in pl_conf
        if new_ph: lastPH = ph_conf[i][1]
        if new_pl: lastPL = pl_conf[i][1]
        if pos != 0:
            if (pos == 1 and Trend[i] == -1) or (pos == -1 and Trend[i] == 1):
                cur["flip_i"] = i; cur["exit_i"] = i; cur["reason"] = "flip"
                entries.append(cur); pos = 0; sl = np.nan; pb = 0; cur = None; continue
            # ★7h봉 SL 청산 (run_strategy line 312-325 복제) — 진입수 앵커 일치 필수
            if i > entry_i and not np.isnan(sl):
                o_, h_, l_, c_ = open_[i], high[i], low[i], close[i]
                ticks = (o_, h_, l_, c_) if c_ < o_ else (o_, l_, h_, c_)
                hit = any((px <= sl) if pos == 1 else (px >= sl) for px in ticks)
                if hit:
                    cur["flip_i"] = None; cur["exit_i"] = i; cur["reason"] = "sl"
                    entries.append(cur); pos = 0; sl = np.nan; pb = 0; cur = None; continue
            if pos == 1 and new_pl:
                pb += 1; ratio = FIB[0] if pb == 1 else FIB[1] if pb == 2 else FIB[2]
                if not np.isnan(lastPH):
                    cand = lastPH - ratio * (lastPH - pl_conf[i][1]); sl = cand if np.isnan(sl) else max(sl, cand)
            if pos == -1 and new_ph:
                pb += 1; ratio = FIB[0] if pb == 1 else FIB[1] if pb == 2 else FIB[2]
                if not np.isnan(lastPL):
                    cand = lastPL + ratio * (ph_conf[i][1] - lastPL); sl = cand if np.isnan(sl) else min(sl, cand)
            cur["sl_path"][i] = sl
        if pos == 0:
            le = Trend[i] == 1 and new_pl and not np.isnan(lastPH)
            se = Trend[i] == -1 and new_ph and not np.isnan(lastPL)
            if le or se:
                d = 1 if le else -1
                ep = TS.compute_split_entry(d, i, close, high, low, open_, n, pl_conf, ph_conf, lastPH, lastPL, "A", 3)
                ap = float(atrp[i]) if atrp is not None and atrp[i] > 0 else TS.SL_PCT / 100
                oz = float(oi7[i]) if oi7 is not None and not np.isnan(oi7[i]) else 0.0
                if vol_sl:
                    risk = float(np.clip(ap * sl_mult, 0.008, 0.05)); sl = ep * (1 - d * risk)
                else:
                    sl = ep * (1 - d * TS.SL_PCT / 100)
                pos = d; entry_i = i; pb = 0
                cur = {"entry_i": i, "side": d, "entry": ep, "sl_path": {i: sl}, "flip_i": None,
                       "exit_i": None, "reason": None, "atr_pct": ap, "oi_z": oz}
    if cur: entries.append(cur)
    return entries


def exit_A(entries, df7h, d1m):
    ti = d1m.index; O = d1m["open"].values; H = d1m["high"].values
    L = d1m["low"].values; C = d1m["close"].values; idx7 = df7h.index
    out = []
    for e in entries:
        side = e["side"]; entry = e["entry"]; ei = e["entry_i"]; flip_i = e["flip_i"]
        keys = sorted(e["sl_path"].keys())
        last_i = e["exit_i"] if e.get("exit_i") is not None else (keys[-1] if keys else ei)
        ex = None; prev_sl = e["sl_path"].get(ei, entry * (1 - side * TS.SL_PCT / 100))
        for bi in range(ei + 1, last_i + 1):
            b_start = idx7[bi]
            sl_b = e["sl_path"].get(bi, prev_sl); prev_sl = sl_b
            si = ti.searchsorted(b_start); sj = ti.searchsorted(b_start + pd.Timedelta(minutes=TF))
            if flip_i is not None and bi == flip_i:
                if si < len(ti): ex = (O[si], "flip")  # 추세반전 봉 시가 체결
                break
            for k in range(si, min(sj, len(ti))):
                if side == 1 and L[k] <= sl_b: ex = (min(O[k], sl_b), "sl"); break
                if side == -1 and H[k] >= sl_b: ex = (max(O[k], sl_b), "sl"); break
            if ex: break
        if ex is None:
            si = ti.searchsorted(idx7[last_i] + pd.Timedelta(minutes=TF))
            ex = (C[min(si, len(ti) - 1)], "end")
        expx, reason = ex
        ret = side * (expx - entry) / entry - COST
        out.append(dict(ret=ret, side=side, reason=reason, year=int(idx7[ei].year),
                        atr_e=e.get("atr_pct", 0.02), oi_e=e.get("oi_z", 0.0),
                        tag="initial_SL" if reason == "sl" else "trailing", et=idx7[ei]))
    return pd.DataFrame(out)


def main():
    d = pd.read_csv(DATA, usecols=["timestamp", "open", "high", "low", "close"])
    d["t"] = pd.to_datetime(d["timestamp"], utc=True, format="ISO8601").dt.tz_localize(None)
    d = d.dropna(subset=["open", "high", "low", "close"]).set_index("t").sort_index()
    df7h = TS.resample_tf(d[["open", "high", "low", "close"]], TF)
    sig = TS.compute_signals(df7h)
    entries = ts_replay(df7h, sig)
    print(f"[앵커] 복제 진입 {len(entries)}건 (phantom 324건과 일치해야)")
    T = exit_A(entries, df7h, d)
    r = T.ret.values; risk = np.full(len(T), TS.SL_PCT / 100); R = r / risk
    print(f"  ★A(TS 원본 피보청산·1m 정직): 복리 {tot(r):+.0f}% / MDD {mdd(r):.1f}% / "
          f"SQN {sqn(R):.2f} / CPCV {cpcv(r):+.2f} / 승률 {100*(r>0).mean():.0f}%")
    print(f"  청산사유: {dict(T.reason.value_counts())}")
    print(f"  (대조: 환상 피보 +447%/-25.9% · B(우리청산) +111%/-44.6%/SQN1.71)")
    for y in sorted(T.year.unique()):
        s = T[T.year == y]; print(f"    {y}: {len(s)}건 합 {((1+s.ret).prod()-1)*100:+.0f}%")
    T.to_csv("ts_honest_A_ledger.csv", index=False, encoding="utf-8-sig")
    print("[저장] ts_honest_A_ledger.csv")


if __name__ == "__main__":
    main()
