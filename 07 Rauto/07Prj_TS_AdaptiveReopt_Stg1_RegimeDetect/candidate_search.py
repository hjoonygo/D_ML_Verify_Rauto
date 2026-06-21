# -*- coding: utf-8 -*-
# [candidate_search.py] 저상관 2nd봇 후보 다중탐색 (A·B). 각 후보: CPCV 먼저→통과분만 ρ측정.
#   합격조건: CPCV 표준6 p25>0 & 최악>0 (견고수익) AND ρ(챔피언)<0.3 (무상관). 둘다여야 채택후보.
#   A: OI shock + 캐스케이드 peak대기 진입. B1: 4H 평균회귀 z-fade. B2: 변동성 압축돌파.
#   4H, lev10, 8bp. 검증 led36_king 무수정.
import os, sys
from itertools import combinations
import numpy as np, pandas as pd
STG17 = r"D:\ML\Verify\02 20260618일 이전작업\07 Rauto\07Prj_Ch4_RunAWS_Stg17_ImpatientFork"
BOTS = os.path.join(STG17, "bots")
if BOTS not in sys.path: sys.path.insert(0, BOTS)
import rauto_paper_engine as PE
from rauto_contract import Signal, Action, Side
HERE = os.path.dirname(os.path.abspath(__file__)); DATA = r"D:\ML\Verify\Merged_Data.csv"
LEV = 10.0; COST = 0.0008; HOLD = 12


def load4h():
    df = pd.read_csv(DATA, usecols=lambda c: c in ('timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi_sum'))
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True).dt.tz_convert(None)
    df = df.dropna(subset=['open', 'high', 'low', 'close']).set_index('timestamp').sort_index()
    d = df.resample('240min', label='right', closed='right').agg(
        {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum', 'oi_sum': 'last'}).dropna().reset_index()
    tr = np.maximum(d.high - d.low, np.maximum((d.high - d.close.shift(1)).abs(), (d.low - d.close.shift(1)).abs()))
    d['atr'] = tr.ewm(alpha=1/14, adjust=False).mean()
    d['z_oi'] = (d.oi_sum - d.oi_sum.rolling(50).mean()) / d.oi_sum.rolling(50).std()
    d['z_vol'] = (d.volume - d.volume.rolling(50).mean()) / d.volume.rolling(50).std()
    d['ret_atr'] = (d.close - d.close.shift(20)) / d.atr
    d['ema20'] = d.close.ewm(span=20, adjust=False).mean()
    d['ret10'] = d.close.pct_change(10)
    d['zret'] = (d.ret10 - d.ret10.rolling(50).mean()) / d.ret10.rolling(50).std()
    mid = d.close.rolling(20).mean(); sd = d.close.rolling(20).std()
    d['bbw'] = (2 * sd) / mid; d['bbw_pct'] = d.bbw.rolling(50).rank(pct=True)
    d['bbu'] = mid + 2 * sd; d['bbl'] = mid - 2 * sd
    return d


def trade_from_signals(d, sig_fn):
    """sig_fn(d,i)->+1/-1/0. 진입 close[i], 청산 HOLD봉 또는 EMA20 회귀. 비중첩."""
    H, L, C, EMA, TS = d.high.values, d.low.values, d.close.values, d.ema20.values, d.timestamp.values
    trades = []; i = 50
    while i < len(d) - 1:
        s = sig_fn(d, i)
        if s == 0: i += 1; continue
        ep = C[i]; xi = min(i + HOLD, len(d) - 1)
        for j in range(i + 1, min(i + HOLD, len(d) - 1) + 1):   # EMA20 회귀 조기청산
            if (s == 1 and C[j] >= EMA[j]) or (s == -1 and C[j] <= EMA[j]): xi = j; break
        R = s * (C[xi] - ep) / ep - COST
        trades.append(dict(entry_t=pd.Timestamp(TS[i]), exit_t=pd.Timestamp(TS[xi]), side=s, R=R))
        i = xi + 1
    return pd.DataFrame(trades)


# ── 후보 신호 ──
def sig_oi_peak(d, i):
    # OI shock(최근 3봉내) + 캐스케이드 peak대기(현재봉 저점 > 직전봉 저점 = 신저점 멈춤)
    win = d.iloc[max(0, i-3):i+1]
    shock = ((win.z_oi < -1.8) & (win.ret_atr < -1.3) & (win.z_vol > 1.3)).any()
    if shock and d.low[i] > d.low[i-1] and d.z_vol[i] < d.z_vol[i-1]:   # 저점 멈춤 + 볼륨 꺾임
        return 1
    return 0
def sig_mr_zfade(d, i):
    if d.zret[i] > 2.0: return -1   # 과열 → 페이드 숏
    if d.zret[i] < -2.0: return 1   # 과매도 → 페이드 롱
    return 0
def sig_volbreak(d, i):
    if d.bbw_pct[i-1] < 0.2:        # 압축 후
        if d.close[i] > d.bbu[i]: return 1
        if d.close[i] < d.bbl[i]: return -1
    return 0


def bot_daily(trades, days):
    a = PE.PaperAccount(10000.0); rows = []
    for _, r in trades.iterrows():
        a.open(Signal(Action.ENTER, side=Side(int(r.side)), size_pct=10.0, leverage=LEV), ts=None, price=100.0)
        a.resolve_replay(R=float(r.R), mae=min(0.0, float(r.R)), fund=0.0); rows.append((r.exit_t, a.bal))
    s = pd.Series([x[1] for x in rows], index=pd.to_datetime([x[0] for x in rows])).groupby(level=0).last()
    return s.reindex(s.index.union(days)).sort_index().ffill().reindex(days).ffill().fillna(10000.0), a.bal


def cpcv(R, exp=10.0/100*LEV):
    r = np.asarray(R) * exp; g = np.array_split(np.arange(len(r)), 6); rr = []
    for lv in combinations(range(6), 2):
        idx = np.concatenate([x for j, x in enumerate(g) if j not in lv]); rr.append(np.prod(1+r[idx])-1)
    return np.percentile(rr, 25)*100, min(rr)*100


def champ_daily(days):
    k = pd.read_csv(os.path.join(STG17, "led36_king.csv"), parse_dates=['entry_t', 'exit_t'])
    for c in ('entry_t', 'exit_t'): k[c] = pd.to_datetime(k[c], utc=True).dt.tz_convert(None)
    a = PE.PaperAccount(10000.0); rows = []
    for _, r in k.iterrows():
        R = float(r.R) - (0.0005 if r.reason in ('sl', 'sl_intrabar') else 0.0)
        a.open(Signal(Action.ENTER, side=Side(int(r.side)), size_pct=float(r.size_pct), leverage=22.0), ts=None, price=100.0)
        a.resolve_replay(R=R, mae=float(r.mae), fund=float(r.fund)); rows.append((r.exit_t, a.bal))
    s = pd.Series([x[1] for x in rows], index=pd.to_datetime([x[0] for x in rows])).groupby(level=0).last()
    return s.reindex(s.index.union(days)).sort_index().ffill().reindex(days).ffill().fillna(10000.0)


def main():
    d = load4h()
    days = pd.date_range(d.timestamp.iloc[50].normalize(), d.timestamp.iloc[-1].normalize(), freq='D')
    eqK = champ_daily(days); rK = eqK.pct_change().dropna()
    cands = [("A: OI_peak대기", sig_oi_peak), ("B1: MR z-fade", sig_mr_zfade), ("B2: 변동성돌파", sig_volbreak)]
    print(f"{'후보':>16} {'거래':>5} {'승률':>5} {'단독%':>7} {'CPCV p25':>9} {'최악':>7} {'CPCV':>5} {'ρ챔피언':>7} {'채택?':>6}")
    passers = []
    for nm, fn in cands:
        t = trade_from_signals(d, fn)
        if len(t) < 10:
            print(f"{nm:>16} {len(t):>5}  (표본부족)"); continue
        eqO, finO = bot_daily(t, days)
        p25, worst = cpcv(t.R.values)
        rO = eqO.pct_change().dropna(); rho = rK.loc[rK.index.intersection(rO.index)].corr(rO.loc[rK.index.intersection(rO.index)])
        cpcv_ok = p25 > 0 and worst > 0; rho_ok = abs(rho) < 0.3
        ok = "★YES" if (cpcv_ok and rho_ok) else ("ρ만" if rho_ok else "CPCV만" if cpcv_ok else "NO")
        print(f"{nm:>16} {len(t):>5} {(t.R>0).mean()*100:>4.0f}% {(finO/10000-1)*100:>+6.0f}% {p25:>+8.0f}% {worst:>+6.0f}% {'PASS' if cpcv_ok else 'FAIL':>5} {rho:>+7.2f} {ok:>6}")
        if cpcv_ok and rho_ok: passers.append((nm, t, eqO))
    print(f"\n[기준] 채택후보=CPCV PASS(p25>0&최악>0) AND |ρ|<0.3. 둘다 통과해야 '36개월 심층검증' 진행.")
    if not passers:
        print("★결과: A·B 후보 중 두 관문(견고수익+무상관) 동시통과 = 없음. 36개월 심층검증 대상 없음 → C(챔피언+CVD 단독)로.")
    else:
        for nm, t, eqO in passers: print(f"  → 통과: {nm} (다음턴 36개월 심층검증: 알파·MDD·장세편차)")


if __name__ == "__main__":
    main()
