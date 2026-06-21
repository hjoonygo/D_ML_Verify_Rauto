# -*- coding: utf-8 -*-
# [build_package_analysis.py] C결합 패키징 분석: ①기각된 MDD-21% both모델이 CVD로 안정화됐나
#   ②36개월 수익금($) 기준 그래프+표. 기준=수익률(캡틴). $10k start, k1.0 lev22 5bp.
import os, sys
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
STG17 = r"D:\ML\Verify\02 20260618일 이전작업\07 Rauto\07Prj_Ch4_RunAWS_Stg17_ImpatientFork"
BOTS = os.path.join(STG17, "bots")
if BOTS not in sys.path: sys.path.insert(0, BOTS)
import rauto_paper_engine as PE
from rauto_contract import Signal, Action, Side
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = r"D:\ML\Verify\Merged_Data.csv"
SLIP = 0.0005; LEV = 22.0; GAIN = 0.40; W_LO = 0.55; W_HI = 1.45


def load_cvd():
    df = pd.read_csv(DATA, usecols=lambda c: c in ('timestamp', 'volume', 'taker_buy_volume'))
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True).dt.tz_convert(None)
    df = df.sort_values('timestamp').set_index('timestamp')
    df['cvd_7h'] = (2.0 * df['taker_buy_volume'] - df['volume']).rolling(420, min_periods=200).sum()
    return df[['cvd_7h']]


def prep(fn, cvd):
    led = pd.read_csv(os.path.join(HERE, fn) if not os.path.isabs(fn) else fn)
    led['entry_t'] = pd.to_datetime(led['entry_t']); led['exit_t'] = pd.to_datetime(led['exit_t'])
    led = led.drop(columns=[c for c in ('cvd_7h', 'dt') if c in led.columns])
    led['dt'] = led['entry_t'] + pd.Timedelta(minutes=420)
    led = pd.merge_asof(led.sort_values('dt'), cvd.sort_index(), left_on='dt', right_index=True, direction='backward')
    return led.sort_values('entry_t').reset_index(drop=True)


def weights(led, use_cvd):
    if not use_cvd: return np.ones(len(led))
    ab = (-led['side'].values * led['cvd_7h'].values).astype(float)
    z = np.nan_to_num((ab - np.nanmean(ab)) / (np.nanstd(ab) + 1e-9))
    w = np.clip(1.0 + GAIN * z, W_LO, W_HI); return w / w.mean()


def equity(led, w):
    a = PE.PaperAccount(10000.0); rows = []
    for i, (_, r) in enumerate(led.iterrows()):
        R = float(r['R']) - (SLIP if r['reason'] in ('sl', 'sl_intrabar') else 0.0)
        a.open(Signal(Action.ENTER, side=Side(int(r['side'])), size_pct=float(r['size_pct']) * w[i], leverage=LEV), ts=None, price=100.0)
        p = float(a.resolve_replay(R=R, mae=float(r['mae']), fund=float(r['fund'])) or 0.0)
        rows.append(dict(exit_t=pd.Timestamp(r['exit_t']), bal=a.bal, p=p))
    rdf = pd.DataFrame(rows)
    eq = rdf['bal'].values; pk = np.maximum.accumulate(eq); mdd = ((eq / pk - 1).min()) * 100
    return rdf, (eq[-1] / 10000 - 1) * 100, mdd, eq[-1]


def monthly_money(rdf):
    rdf = rdf.copy(); rdf['ym'] = rdf['exit_t'].dt.to_period('M')
    out = []
    for ym, g in rdf.groupby('ym'):
        out.append(dict(ym=str(ym), end_bal=g['bal'].iloc[-1], n=len(g)))
    mm = pd.DataFrame(out)
    mm['start_bal'] = mm['end_bal'].shift(1).fillna(10000.0)
    mm['profit'] = mm['end_bal'] - mm['start_bal']
    return mm


def main():
    cvd = load_cvd()
    cands = [
        ("KING(base)", "led36_king.csv", False, STG17),
        ("OIstop_both(기각 MDD-21.7%)", "led_sq_both.csv", False, HERE),
        ("CVD+OIstop_both", "led_sq_both.csv", True, HERE),
        ("CVD+OIstop_rc_both(최고수익)", "led_sq_rc_both.csv", True, HERE),
        ("★CVD+OIstop_long(권장)", "led_sq_long.csv", True, HERE),
    ]
    print("=== 후보 비교 ($10k start, 5bp) — '기각 MDD-21% 모델이 CVD로 안정화됐나' ===")
    print(f"{'package':>30} | {'수익률':>9} {'최종$':>12} {'MDD':>8}")
    res = {}
    for nm, fn, uc, base in cands:
        led = prep(os.path.join(base, fn), cvd); w = weights(led, uc)
        rdf, ret, mdd, fin = equity(led, w); res[nm] = (rdf, ret, mdd, fin)
        flag = " ★-20%위반" if mdd < -20 else " ✓안전"
        print(f"{nm:>30} | {ret:>+8.0f}% ${fin:>11,.0f} {mdd:>7.1f}%{flag}")

    # 슬리피지 민감도(수익winner _both vs 견고 _long)
    print("\n=== 슬리피지 민감도 (MDD) — 수익winner _both vs 견고 _long ===")
    for nm, fn, uc in [("CVD+OIstop_both", "led_sq_both.csv", True), ("CVD+OIstop_long", "led_sq_long.csv", True)]:
        led = prep(os.path.join(HERE, fn), cvd); w = weights(led, uc)
        row = []
        for sp in (0.0005, 0.0010, 0.0020):
            a = PE.PaperAccount(10000.0)
            for i, (_, r) in enumerate(led.iterrows()):
                R = float(r['R']) - (sp if r['reason'] in ('sl', 'sl_intrabar') else 0.0)
                a.open(Signal(Action.ENTER, side=Side(int(r['side'])), size_pct=float(r['size_pct']) * w[i], leverage=LEV), ts=None, price=100.0)
                a.resolve_replay(R=R, mae=float(r['mae']), fund=float(r['fund']))
            _, mdd, _ = a.metrics(); row.append(f"{sp*1e4:.0f}bp:MDD{mdd:.1f}%")
        print(f"  {nm:>18}: " + "  ".join(row))

    rec = res["CVD+OIstop_both"]   # 수익률 기준 winner(캡틴 기준)
    mm = monthly_money(rec[0])
    mm.to_csv(os.path.join(HERE, "monthly_money_recommended.csv"), index=False, encoding="utf-8-sig")
    print(f"\n=== 수익winner 패키지(CVD+OIstop_both) 36개월 수익금($) 표 ===")
    print(f"{'월':>8} {'월말잔고$':>14} {'월수익금$':>14} {'거래':>5}")
    for _, r in mm.iterrows():
        print(f"{r['ym']:>8} {r['end_bal']:>14,.0f} {r['profit']:>+14,.0f} {int(r['n']):>5}")
    print(f"  최종 ${rec[3]:,.0f} ({rec[1]:+.0f}%) MDD{rec[2]:.1f}% | 최고월수익 ${mm['profit'].max():,.0f} 최악월 ${mm['profit'].min():,.0f}")

    # ── 그래프: 수익금($) 자산곡선 + 월수익금 막대 ──
    fig, ax = plt.subplots(1, 2, figsize=(16, 6))
    cols = {'KING(base)': '#1f77b4', 'OIstop_both(기각 MDD-21.7%)': '#d62728',
            'CVD+OIstop_rc_both(최고수익)': '#9467bd', '★CVD+OIstop_long(권장)': '#2ca02c'}
    for nm in cols:
        rdf = res[nm][0]
        ax[0].plot(rdf['exit_t'], rdf['bal'], label=f"{nm.split('(')[0]} (${res[nm][3]/1e6:.2f}M)", color=cols[nm], lw=1.4)
    ax[0].set_yscale('log'); ax[0].set_title('Equity in Dollars (log, $10k start)'); ax[0].set_ylabel('Balance $'); ax[0].legend(fontsize=8); ax[0].grid(alpha=.3)
    months = pd.to_datetime(mm['ym'] + "-01")
    barcol = ['#2ca02c' if v > 0 else '#d62728' for v in mm['profit']]
    ax[1].bar(months, mm['profit'], width=20, color=barcol)
    ax[1].set_title('Recommended Pkg: Monthly Profit ($)'); ax[1].set_ylabel('Profit $'); ax[1].axhline(0, color='k', lw=.8); ax[1].grid(alpha=.3)
    for a in ax:
        for l in a.get_xticklabels(): l.set_rotation(30); l.set_fontsize(8)
    plt.tight_layout(); fp = os.path.join(HERE, "package_money.png")
    plt.savefig(fp, dpi=110); print(f"\n[그래프] {fp}\n[표] monthly_money_recommended.csv")


if __name__ == "__main__":
    main()
