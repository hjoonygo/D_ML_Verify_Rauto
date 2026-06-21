# -*- coding: utf-8 -*-
# [monthly_analysis.py] 품질확인: 챔피언 king(+CVD후보) 36개월 월별 다각 분석 → PNG 그래프 + 표.
#   검증 led36_king(앵커 +11397%) 무수정 + king_trades_pullback_feat(cvd_7h 결합) 재가중.
#   영문 라벨(폰트깨짐 방지, §5.5). 월별: 수익·승률·거래수·PF·롱숏·낙폭.
import os, sys
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
STG17 = r"D:\ML\Verify\02 20260618일 이전작업\07 Rauto\07Prj_Ch4_RunAWS_Stg17_ImpatientFork"
BOTS = os.path.join(STG17, "bots")
if BOTS not in sys.path: sys.path.insert(0, BOTS)
import rauto_paper_engine as PE
from rauto_contract import Signal, Action, Side
HERE = os.path.dirname(os.path.abspath(__file__))
FEAT = os.path.join(HERE, "king_trades_pullback_feat.csv")
SLIP = 0.0005; LEV = 22.0
GAIN = 0.40; W_LO = 0.55; W_HI = 1.45


def cvd_weights(led):
    ab = (-led['side'].values * led['cvd_7h'].values).astype(float)
    z = (ab - np.nanmean(ab)) / (np.nanstd(ab) + 1e-9); z = np.nan_to_num(z)
    w = np.clip(1.0 + GAIN * z, W_LO, W_HI); return w / w.mean()


def run_pnl(led, w):
    a = PE.PaperAccount(10000.0); rows = []
    for i, (_, r) in enumerate(led.iterrows()):
        size = float(r['size_pct']) * w[i]
        R = float(r['R']) - (SLIP if r['reason'] in ('sl', 'sl_intrabar') else 0.0)
        a.open(Signal(Action.ENTER, side=Side(int(r['side'])), size_pct=size, leverage=LEV), ts=None, price=100.0)
        p = float(a.resolve_replay(R=R, mae=float(r['mae']), fund=float(r['fund'])) or 0.0)
        rows.append(dict(exit_t=pd.Timestamp(r['exit_t']), side=int(r['side']), p=p, bal=a.bal))
    return pd.DataFrame(rows)


def monthly(rows):
    rows = rows.copy(); rows['ym'] = rows['exit_t'].dt.to_period('M')
    out = []
    for ym, g in rows.groupby('ym'):
        pv = g['p'].values; nz = pv[np.abs(pv) > 1e-12]
        gp = nz[nz > 0].sum(); gl = -nz[nz < 0].sum()
        lp = g[g.side == 1]['p'].values; sp = g[g.side == -1]['p'].values
        out.append(dict(ym=str(ym), ret=(np.prod(1 + pv) - 1) * 100, n=len(nz),
                        wr=(nz > 0).mean() * 100 if len(nz) else 0,
                        pf=gp / gl if gl > 0 else np.nan,
                        long_ret=(np.prod(1 + lp) - 1) * 100 if len(lp) else 0,
                        short_ret=(np.prod(1 + sp) - 1) * 100 if len(sp) else 0,
                        bal=g['bal'].iloc[-1]))
    return pd.DataFrame(out)


def daily_dd(rows):
    s = rows.groupby(rows['exit_t'].dt.normalize())['bal'].last()
    days = pd.date_range(s.index.min(), s.index.max(), freq='D')
    eq = s.reindex(s.index.union(days)).sort_index().ffill().reindex(days).ffill()
    pk = eq.cummax(); dd = (eq / pk - 1) * 100
    return eq, dd


def main():
    led = pd.read_csv(FEAT, parse_dates=['exit_t']).sort_values('exit_t').reset_index(drop=True)
    rk = run_pnl(led, np.ones(len(led)))         # king
    rc = run_pnl(led, cvd_weights(led))          # CVD-both 후보
    mk = monthly(rk); mc = monthly(rc)
    eqk, ddk = daily_dd(rk); eqc, ddc = daily_dd(rc)

    # ── 표 저장 ──
    mk.to_csv(os.path.join(HERE, "monthly_king.csv"), index=False, encoding="utf-8-sig")
    mc.to_csv(os.path.join(HERE, "monthly_cvd.csv"), index=False, encoding="utf-8-sig")

    # ── 콘솔 표(월별 king) ──
    print("=== KING 월별 실적 (36개월) ===")
    print(f"{'month':>8} {'ret%':>8} {'trades':>7} {'win%':>6} {'PF':>6} {'long%':>8} {'short%':>8}")
    for _, r in mk.iterrows():
        pf = f"{r['pf']:.2f}" if r['pf'] == r['pf'] else " inf"
        print(f"{r['ym']:>8} {r['ret']:>+8.1f} {int(r['n']):>7} {r['wr']:>5.0f}% {pf:>6} {r['long_ret']:>+8.1f} {r['short_ret']:>+8.1f}")
    pos = (mk['ret'] > 0).sum(); neg = (mk['ret'] <= 0).sum()
    print(f"\n[월별 요약 king] 양수월 {pos} / 음수월 {neg} ({pos/len(mk)*100:.0f}% 양수)")
    print(f"  최고월 {mk['ret'].max():+.1f}% / 최악월 {mk['ret'].min():+.1f}% / 월중앙값 {mk['ret'].median():+.1f}%")
    print(f"  최대낙폭(king) {ddk.min():.1f}% / (CVD후보) {ddc.min():.1f}%")
    print(f"  최종 king ${eqk.iloc[-1]:,.0f} / CVD후보 ${eqc.iloc[-1]:,.0f}")
    # 연도 요약
    print("\n[연도별]")
    for y in (2023, 2024, 2025, 2026):
        sub = mk[mk['ym'].str.startswith(str(y))]
        if len(sub):
            yr = (np.prod(1 + sub['ret'].values / 100) - 1) * 100
            print(f"  {y}: {yr:+.0f}% ({len(sub)}개월, 양수 {(sub['ret']>0).sum()})")

    # ── 그래프 (2x3) ──
    fig, ax = plt.subplots(2, 3, figsize=(18, 9))
    months = pd.to_datetime(mk['ym'] + "-01")
    # 1) Equity (log)
    ax[0, 0].plot(eqk.index, eqk.values, label='KING', color='#1f77b4')
    ax[0, 0].plot(eqc.index, eqc.values, label='KING+CVD', color='#ff7f0e', alpha=0.8)
    ax[0, 0].set_yscale('log'); ax[0, 0].set_title('Equity Curve (log, $10k start)'); ax[0, 0].legend(); ax[0, 0].grid(alpha=.3)
    # 2) Monthly return bars (king)
    colors = ['#2ca02c' if v > 0 else '#d62728' for v in mk['ret']]
    ax[0, 1].bar(months, mk['ret'], width=20, color=colors)
    ax[0, 1].axhline(0, color='k', lw=.8); ax[0, 1].set_title('KING Monthly Return %'); ax[0, 1].grid(alpha=.3)
    # 3) Drawdown
    ax[0, 2].fill_between(ddk.index, ddk.values, 0, color='#1f77b4', alpha=.4, label='KING')
    ax[0, 2].fill_between(ddc.index, ddc.values, 0, color='#ff7f0e', alpha=.35, label='KING+CVD')
    ax[0, 2].axhline(-20, color='red', ls='--', lw=1, label='-20% limit')
    ax[0, 2].set_title('Drawdown %'); ax[0, 2].legend(); ax[0, 2].grid(alpha=.3)
    # 4) Win rate
    ax[1, 0].bar(months, mk['wr'], width=20, color='#9467bd')
    ax[1, 0].axhline(mk['wr'].mean(), color='k', ls='--', lw=.8, label=f"avg {mk['wr'].mean():.0f}%")
    ax[1, 0].set_title('KING Monthly Win Rate %'); ax[1, 0].legend(); ax[1, 0].grid(alpha=.3)
    # 5) Trades per month
    ax[1, 1].bar(months, mk['n'], width=20, color='#8c564b')
    ax[1, 1].set_title('KING Trades / Month'); ax[1, 1].grid(alpha=.3)
    # 6) Monthly return: KING vs KING+CVD (cumulative advantage)
    adv = np.cumsum(mc['ret'].values - mk['ret'].values)
    ax[1, 2].plot(months, adv, color='#e377c2')
    ax[1, 2].axhline(0, color='k', lw=.8); ax[1, 2].set_title('Cumulative Monthly Edge: CVD - KING (%p)'); ax[1, 2].grid(alpha=.3)
    for a in ax.flat:
        for lab in a.get_xticklabels(): lab.set_rotation(30); lab.set_fontsize(8)
    plt.tight_layout()
    out_png = os.path.join(HERE, "monthly_analysis.png")
    plt.savefig(out_png, dpi=110); print(f"\n[그래프] {out_png}")
    print("[표] monthly_king.csv, monthly_cvd.csv")


if __name__ == "__main__":
    main()
