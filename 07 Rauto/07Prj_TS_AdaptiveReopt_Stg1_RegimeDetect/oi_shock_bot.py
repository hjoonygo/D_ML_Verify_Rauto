# -*- coding: utf-8 -*-
# [oi_shock_bot.py] OI Shock Reversal 봇 본검증 + 챔피언과 합성 포트폴리오 효과.
#   봇: 4H, 청산소진 반등. 롱=zOI<-1.8 & ret<-1.3ATR & zVol>1.3 / 숏 미러. 손절-1.5ATR, 12봉(48h) 시간청산.
#   비교: 챔피언 단독 vs (챔피언+OI봇) 포트폴리오 — ρ·MDD·Calmar·Sharpe 변화. 검증 led36_king 무수정.
import os, sys
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
STG17 = r"D:\ML\Verify\02 20260618일 이전작업\07 Rauto\07Prj_Ch4_RunAWS_Stg17_ImpatientFork"
BOTS = os.path.join(STG17, "bots")
if BOTS not in sys.path: sys.path.insert(0, BOTS)
import rauto_paper_engine as PE
from rauto_contract import Signal, Action, Side
HERE = os.path.dirname(os.path.abspath(__file__)); DATA = r"D:\ML\Verify\Merged_Data.csv"
OI_LEV = 10.0; OI_COST = 0.0008; HOLD = 12; ZOI = -1.8; RET = -1.3; ZVOL = 1.3; SL_ATR = 1.5


def atr(h, l, c, n=14):
    tr = np.maximum(h - l, np.maximum(np.abs(h - np.roll(c, 1)), np.abs(l - np.roll(c, 1))))
    return pd.Series(tr).ewm(alpha=1/n, adjust=False).mean().values


def oi_bot_trades():
    df = pd.read_csv(DATA, usecols=lambda c: c in ('timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi_sum'))
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True).dt.tz_convert(None)
    df = df.dropna(subset=['open', 'high', 'low', 'close']).set_index('timestamp').sort_index()
    d = df.resample('240min', label='right', closed='right').agg(
        {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum', 'oi_sum': 'last'}).dropna().reset_index()
    d['z_oi'] = (d['oi_sum'] - d['oi_sum'].rolling(50).mean()) / d['oi_sum'].rolling(50).std()
    d['z_vol'] = (d['volume'] - d['volume'].rolling(50).mean()) / d['volume'].rolling(50).std()
    a = atr(d['high'].values, d['low'].values, d['close'].values, 14); d['atr'] = a
    d['ret_atr'] = (d['close'] - d['close'].shift(20)) / a
    H, L, C, AT, TS = d['high'].values, d['low'].values, d['close'].values, d['atr'].values, d['timestamp'].values
    trades = []; i = 50
    while i < len(d) - 1:
        longsig = d.z_oi[i] < ZOI and d.ret_atr[i] < RET and d.z_vol[i] > ZVOL
        shortsig = d.z_oi[i] < ZOI and d.ret_atr[i] > -RET and d.z_vol[i] > ZVOL
        if not (longsig or shortsig): i += 1; continue
        side = 1 if longsig else -1; ep = C[i]; sl = ep - side * SL_ATR * AT[i]
        exit_px = C[min(i + HOLD, len(d) - 1)]; exit_i = min(i + HOLD, len(d) - 1)
        for j in range(i + 1, exit_i + 1):   # 손절 우선
            if (side == 1 and L[j] <= sl) or (side == -1 and H[j] >= sl):
                exit_px = sl; exit_i = j; break
        R = side * (exit_px - ep) / ep - OI_COST
        trades.append(dict(entry_t=pd.Timestamp(TS[i]), exit_t=pd.Timestamp(TS[exit_i]), side=side, R=R))
        i = exit_i + 1   # 중복 진입 방지
    return pd.DataFrame(trades)


def daily_eq(exit_ts, bals, days):
    s = pd.Series(bals, index=pd.to_datetime(exit_ts)).groupby(level=0).last()
    return s.reindex(s.index.union(days)).sort_index().ffill().reindex(days).ffill().fillna(10000.0)


def met(eq, base):
    r = eq.values; pk = np.maximum.accumulate(r); mdd = ((r/pk-1).min())*100
    ret = (r[-1]/base-1)*100; dr = pd.Series(r).pct_change().dropna()
    sharpe = (dr.mean()/dr.std()*np.sqrt(365)) if dr.std() > 0 else 0
    cagr = ((r[-1]/base)**(1/3.0)-1)*100
    return dict(ret=ret, mdd=mdd, cal=cagr/abs(mdd) if mdd < 0 else 0, sharpe=sharpe, final=r[-1])


def main():
    # 챔피언 일별 자산
    king = pd.read_csv(os.path.join(STG17, "led36_king.csv"), parse_dates=['entry_t', 'exit_t'])
    for c in ('entry_t', 'exit_t'): king[c] = pd.to_datetime(king[c], utc=True).dt.tz_convert(None)
    aK = PE.PaperAccount(10000.0); kb = []
    for _, r in king.iterrows():
        R = float(r['R']) - (0.0005 if r['reason'] in ('sl', 'sl_intrabar') else 0.0)
        aK.open(Signal(Action.ENTER, side=Side(int(r['side'])), size_pct=float(r['size_pct']), leverage=22.0), ts=None, price=100.0)
        aK.resolve_replay(R=R, mae=float(r['mae']), fund=float(r['fund'])); kb.append((r['exit_t'], aK.bal))
    # OI봇
    ot = oi_bot_trades()
    aO = PE.PaperAccount(10000.0); ob = []
    for _, r in ot.iterrows():
        aO.open(Signal(Action.ENTER, side=Side(int(r['side'])), size_pct=10.0, leverage=OI_LEV), ts=None, price=100.0)
        aO.resolve_replay(R=float(r['R']), mae=min(0.0, float(r['R'])), fund=0.0); ob.append((r['exit_t'], aO.bal))
    print(f"OI봇 거래 {len(ot)} | 롱 {int((ot.side==1).sum())} 숏 {int((ot.side==-1).sum())} | 승률 {(ot.R>0).mean()*100:.0f}% | 단독 {(aO.bal/10000-1)*100:+.0f}%")

    days = pd.date_range(min(king.exit_t.min(), ot.exit_t.min()).normalize(), max(king.exit_t.max(), ot.exit_t.max()).normalize(), freq='D')
    eqK = daily_eq([x[0] for x in kb], [x[1] for x in kb], days)
    eqO = daily_eq([x[0] for x in ob], [x[1] for x in ob], days)
    eqP = eqK + eqO   # 포트폴리오($20k)

    rK = eqK.pct_change().dropna(); rO = eqO.pct_change().dropna()
    common = rK.index.intersection(rO.index)
    rho = rK.loc[common].corr(rO.loc[common])
    # 거래일만(둘다 움직인 날) 상관도 — 더 보수적
    act = (rK.loc[common].abs() > 1e-9) & (rO.loc[common].abs() > 1e-9)
    rho_act = rK.loc[common][act].corr(rO.loc[common][act]) if act.sum() > 10 else float('nan')

    mK = met(eqK, 10000.0); mP = met(eqP, 20000.0); mO = met(eqO, 10000.0)
    print(f"\n=== 상관계수 ρ(챔피언, OI봇) 일별수익 = {rho:+.3f} (거래일만 {rho_act:+.3f}) ===")
    print(f"{'':>16}{'수익률':>9}{'MDD':>8}{'Calmar':>8}{'Sharpe':>8}")
    print(f"{'챔피언 단독':>14}{mK['ret']:>+8.0f}%{mK['mdd']:>7.1f}%{mK['cal']:>8.1f}{mK['sharpe']:>8.2f}")
    print(f"{'OI봇 단독':>15}{mO['ret']:>+8.0f}%{mO['mdd']:>7.1f}%{mO['cal']:>8.1f}{mO['sharpe']:>8.2f}")
    print(f"{'포트(챔+OI)':>13}{mP['ret']:>+8.0f}%{mP['mdd']:>7.1f}%{mP['cal']:>8.1f}{mP['sharpe']:>8.2f}")
    print(f"\n[변화] MDD {mK['mdd']:.1f}%→{mP['mdd']:.1f}% · Calmar {mK['cal']:.1f}→{mP['cal']:.1f} · Sharpe {mK['sharpe']:.2f}→{mP['sharpe']:.2f}")

    # CPCV(OI봇 단독 견고성)
    from itertools import combinations
    r = ot['R'].values * (10.0/100*OI_LEV); g = np.array_split(np.arange(len(r)), 6); rr = []
    for lv in combinations(range(6), 2):
        idx = np.concatenate([x for j, x in enumerate(g) if j not in lv]); rr.append(np.prod(1+r[idx])-1)
    print(f"[OI봇 CPCV 표준6] p25 {np.percentile(rr,25)*100:+.0f}% · 최악 {min(rr)*100:+.0f}% · {'PASS' if np.percentile(rr,25)>0 and min(rr)>0 else 'FAIL'}")

    # 그래프
    fig, ax = plt.subplots(1, 2, figsize=(15, 5.5))
    ax[0].plot(eqK.index, eqK.values, label=f'Champion ({mK["ret"]:+.0f}%)', color='#1f77b4')
    ax[0].plot(eqO.index, eqO.values, label=f'OI-Shock bot ({mO["ret"]:+.0f}%)', color='#ff7f0e')
    ax[0].plot(eqP.index, eqP.values, label=f'Portfolio ({mP["ret"]:+.0f}%)', color='#2ca02c', lw=2)
    ax[0].set_yscale('log'); ax[0].set_title(f'Equity (log) — rho={rho:+.2f}'); ax[0].legend(fontsize=9); ax[0].grid(alpha=.3)
    ddK = (eqK/eqK.cummax()-1)*100; ddP = (eqP/eqP.cummax()-1)*100
    ax[1].fill_between(ddK.index, ddK.values, 0, color='#1f77b4', alpha=.4, label=f'Champion MDD {mK["mdd"]:.1f}%')
    ax[1].fill_between(ddP.index, ddP.values, 0, color='#2ca02c', alpha=.4, label=f'Portfolio MDD {mP["mdd"]:.1f}%')
    ax[1].axhline(-20, color='red', ls='--', lw=1); ax[1].set_title('Drawdown: Champion vs Portfolio'); ax[1].legend(fontsize=9); ax[1].grid(alpha=.3)
    plt.tight_layout(); fp = os.path.join(HERE, "oi_shock_portfolio.png"); plt.savefig(fp, dpi=110)
    print(f"\n[그래프] {fp}")


if __name__ == "__main__":
    main()
