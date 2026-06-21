# -*- coding: utf-8 -*-
# [evaluate_A.py] A 결합검증: CVD흡수(사이징) × OI손절거리, + 슬리피지 민감도 + Conditional Attribution.
#   ★실제 슬리피지 확인: stop slip ∈ {5,10,20,30bp}로 전표본 MDD·CPCV가 어떻게 변하나(특히 C-both MDD-21.7%).
#   ★Conditional Attribution(챗GPT): C개선 < A개선+B개선이면 중복. 직교면 결합가치.
#   기제: A=CVD사이징(거래불변, 재가중), B=OI손절(재실행 ledger), C=B거래 위에 CVD사이징.
import os, sys
from itertools import combinations
import numpy as np, pandas as pd
STG17 = r"D:\ML\Verify\02 20260618일 이전작업\07 Rauto\07Prj_Ch4_RunAWS_Stg17_ImpatientFork"
BOTS = os.path.join(STG17, "bots")
if BOTS not in sys.path: sys.path.insert(0, BOTS)
import rauto_paper_engine as PE
from rauto_contract import Signal, Action, Side
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = r"D:\ML\Verify\Merged_Data.csv"
LEV = 22.0; GAIN = 0.40; W_LO = 0.55; W_HI = 1.45
SLIPS = [0.0005, 0.0010, 0.0020, 0.0030]   # 5/10/20/30bp stop slip (실제 슬리피지 민감도)


def load_cvd():
    df = pd.read_csv(DATA, usecols=lambda c: c in ('timestamp', 'volume', 'taker_buy_volume'))
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True).dt.tz_convert(None)
    df = df.sort_values('timestamp').set_index('timestamp')
    df['net_taker'] = 2.0 * df['taker_buy_volume'] - df['volume']
    df['cvd_7h'] = df['net_taker'].rolling(420, min_periods=200).sum()
    return df[['cvd_7h']]


def join_cvd(led, cvd):
    led = led.copy(); led['entry_t'] = pd.to_datetime(led['entry_t'])
    led = led.drop(columns=[c for c in ('cvd_7h', 'dt') if c in led.columns])  # 기존 cvd_7h 제거(충돌방지)
    led['dt'] = led['entry_t'] + pd.Timedelta(minutes=420)
    led = led.sort_values('dt')
    led = pd.merge_asof(led, cvd.sort_index(), left_on='dt', right_index=True, direction='backward')
    return led.sort_values('entry_t').reset_index(drop=True)


def cvd_w(led, use_cvd):
    if not use_cvd: return np.ones(len(led))
    ab = (-led['side'].values * led['cvd_7h'].values).astype(float)
    z = (ab - np.nanmean(ab)) / (np.nanstd(ab) + 1e-9); z = np.nan_to_num(z)
    w = np.clip(1.0 + GAIN * z, W_LO, W_HI); return w / w.mean()


def full(led, w, slip):
    a = PE.PaperAccount(10000.0); ps = []
    for i, (_, r) in enumerate(led.iterrows()):
        R = float(r['R']) - (slip if r['reason'] in ('sl', 'sl_intrabar') else 0.0)
        a.open(Signal(Action.ENTER, side=Side(int(r['side'])), size_pct=float(r['size_pct']) * w[i], leverage=LEV), ts=None, price=100.0)
        ps.append(float(a.resolve_replay(R=R, mae=float(r['mae']), fund=float(r['fund'])) or 0.0))
    ps = np.array(ps); eq = 10000 * np.cumprod(1 + ps); pk = np.maximum.accumulate(eq)
    return (eq[-1] / 10000 - 1) * 100, ((eq / pk - 1).min()) * 100


def cpcv(led, w, slip, C=0.0008, ng=6):
    r = (led['R'].values - np.where(np.isin(led['reason'].values, ['sl', 'sl_intrabar']), slip, 0.0)
         + 0.0004 - C) * (led['size_pct'].values * w / 100.0 * LEV)
    grp = np.array_split(np.arange(len(r)), ng); rr = []
    for lv in combinations(range(ng), 2):
        idx = np.concatenate([x for j, x in enumerate(grp) if j not in lv])
        rr.append(np.prod(1.0 + r[idx]) - 1.0)
    rr = np.array(rr); return np.percentile(rr, 25) * 100, rr.min() * 100


def main():
    cvd = load_cvd()
    # 후보 ledger들 (run_stopquality 산출). king/A는 feat csv.
    specs = [
        ("king(base)", "king_trades_pullback_feat.csv", False),
        ("A:CVD",       "king_trades_pullback_feat.csv", True),
        ("B:OIstop_long", "led_sq_long.csv",  False),
        ("B:OIstop_both", "led_sq_both.csv",  False),
        ("Brc:OIstop_rc_both", "led_sq_rc_both.csv", False),
        ("C:CVD+OIstop_long", "led_sq_long.csv", True),
        ("C:CVD+OIstop_rc_both", "led_sq_rc_both.csv", True),
    ]
    print("=== A 결합 + 슬리피지 민감도 (전표본 ret/MDD + CPCV p25/worst @8bp) ===")
    print(f"{'variant':>22} {'slip':>5} | {'ret%':>9} {'MDD%':>7} | {'p25%':>8} {'worst%':>8}")
    res = {}
    for name, fn, uc in specs:
        fp = os.path.join(HERE, fn)
        if not os.path.exists(fp):
            print(f"{name:>22} : (ledger 없음: {fn} — run_stopquality 먼저)"); continue
        led = join_cvd(pd.read_csv(fp), cvd); w = cvd_w(led, uc)
        res[name] = {}
        for slip in SLIPS:
            ret, mdd = full(led, w, slip); p25, worst = cpcv(led, w, slip)
            res[name][slip] = (ret, mdd, p25, worst)
            flag = " ★MDD위반" if mdd < -20 else ""
            print(f"{name:>22} {slip*1e4:>4.0f}bp | {ret:>+8.0f}% {mdd:>6.1f}% | {p25:>+7.0f}% {worst:>+7.0f}%{flag}")
        print()
    # Conditional Attribution @ 5bp, CPCV p25 기준 (vs king)
    try:
        base = res["king(base)"][0.0005][2]
        impA = res["A:CVD"][0.0005][2] - base
        impB = res["B:OIstop_long"][0.0005][2] - base
        impC = res["C:CVD+OIstop_long"][0.0005][2] - base
        print(f"[Conditional Attribution @5bp, CPCV p25 vs king]")
        print(f"  A(CVD) 개선 {impA:+.0f}%p | B(OIstop_long) 개선 {impB:+.0f}%p | A+B={impA+impB:+.0f}%p | C(둘다) 개선 {impC:+.0f}%p")
        print(f"  → {'중복(C<A+B): OI는 조건부로만' if impC < impA+impB else '직교/시너지(C>=A+B): 결합가치'}")
    except Exception as e:
        print("attribution skip:", e)

    # ── 그래프: 슬리피지 vs MDD / CPCV p25 (핵심 변종) ──
    try:
        import matplotlib
        matplotlib.use("Agg"); import matplotlib.pyplot as plt
        keys = ["king(base)", "A:CVD", "B:OIstop_long", "C:CVD+OIstop_long"]
        cols = {"king(base)": "#1f77b4", "A:CVD": "#ff7f0e", "B:OIstop_long": "#2ca02c", "C:CVD+OIstop_long": "#d62728"}
        xs = [s * 1e4 for s in SLIPS]
        fig, ax = plt.subplots(1, 2, figsize=(13, 5))
        for k in keys:
            if k not in res: continue
            mdd = [res[k][s][1] for s in SLIPS]; p25 = [res[k][s][2] for s in SLIPS]
            ax[0].plot(xs, mdd, 'o-', label=k, color=cols[k])
            ax[1].plot(xs, p25, 'o-', label=k, color=cols[k])
        ax[0].axhline(-20, color='red', ls='--', lw=1, label='-20% limit')
        ax[0].set_xlabel('Stop slippage (bp)'); ax[0].set_ylabel('Max Drawdown %'); ax[0].set_title('MDD vs Slippage'); ax[0].legend(fontsize=8); ax[0].grid(alpha=.3)
        ax[1].set_xlabel('Stop slippage (bp)'); ax[1].set_ylabel('CPCV p25 %'); ax[1].set_title('CPCV p25 vs Slippage'); ax[1].legend(fontsize=8); ax[1].grid(alpha=.3)
        plt.tight_layout(); fp = os.path.join(HERE, "slippage_sensitivity.png")
        plt.savefig(fp, dpi=110); print(f"\n[그래프] {fp}")
    except Exception as e:
        print("plot skip:", e)


if __name__ == "__main__":
    main()
