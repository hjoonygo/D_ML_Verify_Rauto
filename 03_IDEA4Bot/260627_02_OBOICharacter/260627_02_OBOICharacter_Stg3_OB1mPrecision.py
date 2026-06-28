# -*- coding: utf-8 -*-
# [260627_02_OBOICharacter_Stg3_OB1mPrecision.py]
# OB Character 3단계 — ★1m 정밀 백테 + OI 유동성게이트 직교조합 (캡틴 지시 2026-06-27).
#   1·2단계 결론: OB구조 자체 +10~12%p(실재) · OI는 OB판별 무력(0.50) · 살아남은건 가격모멘텀(0.71).
#   캡틴 통찰: OI는 '판별' 아닌 '유동성(에너지) 게이트'로 보존(§23 단짠배합). 휩소판별=거래량 담보 전제.
#   3단계 질문: ⒜OB구조·가격모멘텀이 1m 체결·비용서도 우위 살아남나 ⒝OI유동성게이트가 직교 시너지 주나.
#   변형: V0 OB단독 / V1 +가격모멘텀 / V2 +OI유동성게이트 / V3 둘다.
#   ★룩어헤드0: OB·swing 우측1확정 · 재방문봉 마감후(rev+1) 청산판정 · 모멘텀은 진입 직전봉까지.
#   ★1m 체결(환각방지·§15): entry=OB경계 limit · stop/target 1m 터치(갭 불리=open) · 동시 stop우선(낙관금지).
#   비용 §7 버전B 8bp(maker2+taker4+sprd1) + stop 1m 갭. 난수0. 검증엔진 무수정 호출(§8).
import os, sys
from itertools import combinations
import numpy as np, pandas as pd


def find_root():
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(7):
        if os.path.isdir(os.path.join(d, "08_BTC_Data")) and os.path.isdir(os.path.join(d, "04_공용엔진코드")):
            return d
        nd = os.path.dirname(d)
        if nd == d:
            break
        d = nd
    return r"D:\ML\RfRauto"


ROOT = find_root()
sys.path.insert(0, os.path.join(ROOT, "04_공용엔진코드", "engines"))
import trendstack_signal_engine as TS

DATA = os.path.join(ROOT, "08_BTC_Data", "derived", "Merged_Data.csv")
OUTDIR = os.path.join(ROOT, "00_WorkHstr", "BackTest_Output",
                      "260627_02_OBOICharacter_Stg3_OB1mPrecision")

N_SWING = 5
OB_TFS = [240, 60]
ATR_PD = 14
MAX_OB_LOOKBACK = 10
RR_ATR = 1.0                 # target=stop=1ATR(대칭, 1·2단계 공정비교 일관)
MAX_WAIT_REVISIT = 60        # 재방문 대기(OB-TF 봉)
MAX_HOLD_AFTER = 30          # 보유 윈도우(OB-TF 봉)
COST = 0.0008                # 왕복 8bp (§7 버전B: maker2+taker4+sprd1)
MOM_LB_MIN = 60              # 가격모멘텀 lookback(분)
F_RISK = 0.02                # 거래당 리스크(자본 2%) 고정사이징 → 복리
N_GROUPS, K_TEST = 6, 2      # CPCV 표준6


def load_data():
    cols = ["timestamp", "open", "high", "low", "close", "volume",
            "taker_buy_volume", "oi_sum", "oi_change_1h_pct", "oi_zscore_24h"]
    df = pd.read_csv(DATA, usecols=cols)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df.set_index("timestamp").sort_index()


def extract_obs(g, atr):
    H = g["high"].values; L = g["low"].values; C = g["close"].values; O = g["open"].values
    idx = g.index; n = len(C)
    ph, pl = TS.pivots_lr(H, L, N_SWING, 1)
    ph_at = {k: v[1] for k, v in ph.items()}; pl_at = {k: v[1] for k, v in pl.items()}
    obs = []; last_ph = last_pl = np.nan
    for i in range(n):
        if i in ph_at: last_ph = ph_at[i]
        if i in pl_at: last_pl = pl_at[i]
        if not np.isnan(last_ph) and C[i] > last_ph:
            j = i
            while j >= max(0, i - MAX_OB_LOOKBACK) and not (C[j] < O[j]):
                j -= 1
            if j >= max(0, i - MAX_OB_LOOKBACK) and C[j] < O[j]:
                obs.append(dict(conf_i=i, conf_time=idx[i], side=1, ob_lo=float(L[j]),
                                ob_hi=float(H[j]), atr=float(atr[i])))
            last_ph = np.nan
        if not np.isnan(last_pl) and C[i] < last_pl:
            j = i
            while j >= max(0, i - MAX_OB_LOOKBACK) and not (C[j] > O[j]):
                j -= 1
            if j >= max(0, i - MAX_OB_LOOKBACK) and C[j] > O[j]:
                obs.append(dict(conf_i=i, conf_time=idx[i], side=-1, ob_lo=float(L[j]),
                                ob_hi=float(H[j]), atr=float(atr[i])))
            last_pl = np.nan
    return obs


def attach_liquidity(obs, df, tf):
    """OB 생성시 OI/거래량 유동성 강도 부착(게이트용, 봉마감 확정값=룩어헤드0)."""
    r = df.resample(f"{tf}min", label="left", closed="left")
    f = pd.DataFrame({
        "oi_chg1h": r["oi_change_1h_pct"].last(),
        "vol": r["volume"].sum(),
    }).dropna()
    f["vol_ratio"] = f["vol"] / f["vol"].rolling(20).mean()
    for ob in obs:
        ct = ob["conf_time"]
        if ct in f.index:
            row = f.loc[ct]
            ob["liq"] = float(np.nan_to_num(abs(row["oi_chg1h"]), nan=0.0)) + float(np.nan_to_num(row["vol_ratio"], nan=0.0))
        else:
            ob["liq"] = np.nan
    vals = np.array([o["liq"] for o in obs if o["liq"] == o["liq"]])
    med = np.median(vals) if len(vals) else 0.0
    for ob in obs:
        ob["liq_hi"] = (ob["liq"] == ob["liq"]) and (ob["liq"] >= med)   # 유동성 상위50%
    return obs


def backtest_1m(obs, m_t, mO, mH, mL, mC, tf_min, variant):
    """OB 재방문 1m 정밀 체결 백테. variant: V0/V1/V2/V3. 반환 거래 리스트."""
    tf_td = np.timedelta64(tf_min, "m")
    lb = np.timedelta64(MOM_LB_MIN, "m")
    N = len(m_t)
    trades = []
    for ob in obs:
        side = ob["side"]; lo = ob["ob_lo"]; hi = ob["ob_hi"]; atr = ob["atr"]
        if not (atr > 0):
            continue
        if variant in ("V2", "V3") and not ob.get("liq_hi", False):    # OI 유동성게이트
            continue
        t_close = np.datetime64(ob["conf_time"]) + tf_td               # conf봉 마감 후부터
        a = int(np.searchsorted(m_t, t_close, "left"))
        b = int(np.searchsorted(m_t, t_close + tf_td * MAX_WAIT_REVISIT, "left"))
        rev_k = None
        for k in range(a, min(b, N)):
            if mH[k] >= lo and mL[k] <= hi:                            # 재방문 = OB zone 1m 터치
                rev_k = k; break
        if rev_k is None or rev_k + 1 >= N:
            continue
        # 가격모멘텀 필터(진입 직전봉까지=룩어헤드0)
        if variant in ("V1", "V3"):
            p = int(np.searchsorted(m_t, m_t[rev_k] - lb, "left"))
            if p < 0 or mC[p] <= 0:
                continue
            mom = (mC[rev_k] - mC[p]) / mC[p]
            if side * mom <= 0:                                        # OB방향 순행 모멘텀만
                continue
        entry = hi if side == 1 else lo                                # OB 경계 limit
        target = entry + RR_ATR * atr if side == 1 else entry - RR_ATR * atr
        stop = entry - RR_ATR * atr if side == 1 else entry + RR_ATR * atr
        d = int(np.searchsorted(m_t, m_t[rev_k] + tf_td * MAX_HOLD_AFTER, "left"))
        exit_px = None; oc = 0
        for k in range(rev_k + 1, min(d, N)):                          # rev+1부터 판정(룩어헤드0)
            if side == 1:
                if mL[k] <= stop:
                    exit_px = min(mO[k], stop); oc = -1; break          # 갭 불리(시장가)
                if mH[k] >= target:
                    exit_px = target; oc = 1; break                     # limit
            else:
                if mH[k] >= stop:
                    exit_px = max(mO[k], stop); oc = -1; break
                if mL[k] <= target:
                    exit_px = target; oc = 1; break
        if exit_px is None:
            kk = min(d, N) - 1
            if kk <= rev_k:
                continue
            exit_px = mC[kk]; oc = 0                                    # 미결=윈도우끝 청산
        raw_R = side * (exit_px - entry) / entry
        risk_price = RR_ATR * atr / entry
        net_R = raw_R / risk_price - COST / risk_price                 # R배수(비용차감)
        trades.append({"t": m_t[rev_k], "side": side, "net_R": float(net_R), "oc": oc})
    return trades


def equity_mdd(trades, f=F_RISK):
    if not trades:
        return 0.0, 0.0
    cap = 10000.0; peak = cap; mdd = 0.0
    for tr in sorted(trades, key=lambda x: x["t"]):
        cap *= (1.0 + tr["net_R"] * f)
        if cap > peak: peak = cap
        dd = cap / peak - 1.0
        if dd < mdd: mdd = dd
    return 100.0 * (cap / 10000.0 - 1.0), 100.0 * mdd


def stats(trades):
    if not trades:
        return dict(n=0, wr=float("nan"), pf=float("nan"), rr=float("nan"), avg=float("nan"))
    R = np.array([t["net_R"] for t in trades])
    win = R[R > 0]; lose = R[R < 0]
    pf = win.sum() / abs(lose.sum()) if len(lose) and lose.sum() != 0 else float("inf")
    rr = (win.mean() / abs(lose.mean())) if len(win) and len(lose) else float("nan")
    return dict(n=len(R), wr=100.0 * np.mean(R > 0), pf=pf, rr=rr, avg=R.mean())


def quarterly(trades):
    if not trades:
        return pd.DataFrame()
    d = pd.DataFrame(trades)
    d["t"] = pd.to_datetime(d["t"], utc=True)
    d["q"] = d["t"].dt.to_period("Q").astype(str)
    out = []
    for q, gq in d.groupby("q"):
        row = {"분기": q, "거래": len(gq), "수익R합": gq["net_R"].sum()}
        for nm, s in [("롱", 1), ("숏", -1)]:
            sub = gq[gq["side"] == s]
            row[f"{nm}_거래"] = len(sub); row[f"{nm}_R합"] = round(sub["net_R"].sum(), 2)
        out.append(row)
    return pd.DataFrame(out)


def cpcv_R(trades):
    """net_R 시퀀스 시간순 6그룹 → test 2그룹(15경로) OOS 평균R·PF."""
    if len(trades) < 60:
        return None
    d = sorted(trades, key=lambda x: x["t"])
    R = np.array([t["net_R"] for t in d])
    groups = np.array_split(np.arange(len(R)), N_GROUPS)
    avgs, pfs = [], []
    for tg in combinations(range(N_GROUPS), K_TEST):
        idx = np.concatenate([groups[g] for g in tg])
        rr = R[idx]
        avgs.append(rr.mean())
        w = rr[rr > 0].sum(); l = abs(rr[rr < 0].sum())
        pfs.append(w / l if l else float("inf"))
    return np.array(avgs), np.array(pfs)


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    df = load_data()
    print(f"[데이터] {len(df):,}행 | {df.index[0]} ~ {df.index[-1]}", flush=True)
    print(f"[설정] 1m체결·비용{COST*1e4:.0f}bp·리스크{F_RISK*100:.0f}%·RR{RR_ATR}ATR·CPCV표준{N_GROUPS}", flush=True)
    m_t = df.index.values
    mO = df["open"].values; mH = df["high"].values; mL = df["low"].values; mC = df["close"].values
    VARIANTS = ["V0", "V1", "V2", "V3"]
    LABEL = {"V0": "OB단독", "V1": "+가격모멘텀", "V2": "+OI유동성게이트", "V3": "+모멘텀&OI"}
    all_q = []
    for tf in OB_TFS:
        g = TS.resample_tf(df, tf)
        atr = TS.compute_atr(g["high"].values, g["low"].values, g["close"].values, ATR_PD)
        obs = extract_obs(g, atr)
        obs = attach_liquidity(obs, df, tf)
        tfh = f"{tf}m({tf // 60}h)"
        print("\n" + "=" * 78, flush=True)
        print(f"### OB-TF {tfh}  (OB {len(obs)}개)", flush=True)
        print(f"  {'변형':16s} {'거래':>5s} {'승률':>6s} {'PF':>5s} {'손익비':>5s} {'평균R':>6s} "
              f"{'36mo수익':>9s} {'MDD':>7s} {'CPCV평균R(p25)':>14s}", flush=True)
        for v in VARIANTS:
            tr = backtest_1m(obs, m_t, mO, mH, mL, mC, tf, v)
            st = stats(tr); ret, mdd = equity_mdd(tr)
            cp = cpcv_R(tr)
            cps = f"{np.median(cp[0]):+.3f}({np.percentile(cp[0],25):+.3f})" if cp else "n/a"
            print(f"  {v}:{LABEL[v]:13s} {st['n']:5d} {st['wr']:5.1f}% {st['pf']:5.2f} {st['rr']:5.2f} "
                  f"{st['avg']:+6.3f} {ret:+8.1f}% {mdd:6.1f}% {cps:>14s}", flush=True)
            q = quarterly(tr); q.insert(0, "변형", v); q.insert(0, "OB_TF", tf); all_q.append(q)
    out = pd.concat(all_q, ignore_index=True) if all_q else pd.DataFrame()
    csv = os.path.join(OUTDIR, "260627_02_OBOICharacter_Stg3_quarterly.csv")
    out.to_csv(csv, index=False, encoding="utf-8-sig")
    print("\n" + "=" * 78, flush=True)
    print(f"[산출] 분기별 수익표: {csv}", flush=True)
    print("[해석] V0가 비용後 평균R>0·CPCV p25>0 = OB구조 1m서도 우위. V1>V0 = 모멘텀 가치.", flush=True)
    print("       V2>V0 또는 V3>V1 = ★OI 유동성게이트 직교 시너지(캡틴 가설). 아니면 OI 유동성도 무력.", flush=True)


if __name__ == "__main__":
    main()
