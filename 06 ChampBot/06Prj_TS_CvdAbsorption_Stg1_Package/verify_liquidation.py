# -*- coding: utf-8 -*-
# [verify_liquidation.py] ★허수 역산검증: sl_intrabar이 'SL서 깔끔체결' 가정 → flash-crash 실저점 무시.
#   진짜 보유중 최저 excursion(Merged 1분, et+7H부터=§15 gate3)을 mae_true로 재계산해
#   강제청산(mae<=-hsd≈-4.1%)이 제대로 걸리면 진짜 수익/MDD가 얼마인지 = 수익 허수 규명.
#   ledger mae(원본) vs mae_true(실저점) 둘로 PaperAccount 돌려 비교.
import os, sys
import numpy as np, pandas as pd
STG17 = r"D:\ML\Verify\02 20260618일 이전작업\07 Rauto\07Prj_Ch4_RunAWS_Stg17_ImpatientFork"
BOTS = os.path.join(STG17, "bots")
if BOTS not in sys.path: sys.path.insert(0, BOTS)
import trendstack_signal_engine as E
import rauto_paper_engine as PE
from rauto_contract import Signal, Action, Side
HERE = os.path.dirname(os.path.abspath(__file__))
LED = os.path.join(STG17, "led36_king.csv")
DATA = r"D:\ML\Verify\Merged_Data.csv"
TF = pd.Timedelta(minutes=E.TF_MIN); SLIP = 0.0005; LEV = 22.0
HSD = 1.0 / LEV - 0.004 - SLIP    # ≈0.04095


def true_mae(m, et, xt, entry, side):
    """보유중(진입체결 et+7H ~ 청산 xt) 진짜 최저 excursion(1분 저/고 기준)."""
    seg = m.loc[et + TF: xt]
    if not len(seg): return 0.0
    if side == 1:
        return float(((seg['low'] - entry) / entry).min())
    else:
        return float(((entry - seg['high']) / entry).min())


def run(led, mae_col):
    a = PE.PaperAccount(10000.0)
    for _, r in led.iterrows():
        R = float(r['R']) - (SLIP if r['reason'] in ('sl', 'sl_intrabar') else 0.0)
        a.open(Signal(Action.ENTER, side=Side(int(r['side'])), size_pct=float(r['size_pct']), leverage=LEV), ts=None, price=100.0)
        a.resolve_replay(R=R, mae=float(r[mae_col]), fund=float(r['fund']))
    ret, mdd, cal = a.metrics()
    return ret, mdd, a.n_liq


def main():
    led = pd.read_csv(LED, parse_dates=['entry_t', 'exit_t']).sort_values('entry_t').reset_index(drop=True)
    for c in ('entry_t', 'exit_t'):
        led[c] = pd.to_datetime(led[c], utc=True).dt.tz_convert(None)
    m = pd.read_csv(DATA, usecols=lambda c: c in ('timestamp', 'high', 'low'))
    m['timestamp'] = pd.to_datetime(m['timestamp'], utc=True).dt.tz_convert(None)
    m = m.set_index('timestamp').sort_index()

    led['mae_true'] = [true_mae(m, r.entry_t, r.exit_t, r.entry_px, int(r.side)) for r in led.itertuples()]
    led['mae_led'] = led['mae']

    print(f"HSD(청산거리) = {HSD:.4f} ({HSD*100:.2f}% 역행 시 강제청산)\n")
    # mae 분포 비교
    print("=== mae 비교 (ledger 기록 vs 진짜 보유중 실저점) ===")
    print(f"  ledger mae : 중앙 {led['mae_led'].median():.4f} 최저 {led['mae_led'].min():.4f} | <=-hsd 건수 {(led['mae_led']<=-HSD).sum()}")
    print(f"  진짜 mae   : 중앙 {led['mae_true'].median():.4f} 최저 {led['mae_true'].min():.4f} | <=-hsd 건수 {(led['mae_true']<=-HSD).sum()}")
    print(f"  → 진짜 실저점 기준 강제청산 대상 거래: {(led['mae_true']<=-HSD).sum()}건 (ledger기준 {(led['mae_led']<=-HSD).sum()}건)\n")

    r0, d0, l0 = run(led, 'mae_led')
    r1, d1, l1 = run(led, 'mae_true')
    print("=== 수익/MDD 역산 비교 (k1.0 lev22 5bp) ===")
    print(f"  [원본 ledger mae] {r0:+.0f}% / MDD {d0:.1f}% / 청산 {l0}건  ← §15 +11397% 재현")
    print(f"  [진짜 실저점 mae] {r1:+.0f}% / MDD {d1:.1f}% / 청산 {l1}건  ← 허수 제거 후")
    print(f"  → 수익 변화 {r1-r0:+.0f}%p ({(1+r1/100)/(1+r0/100)-1:+.0%}), MDD 변화 {d1-d0:+.1f}%p, 청산 +{l1-l0}건")

    # 청산으로 바뀐 거래 표본
    flip = led[(led['mae_true'] <= -HSD) & (led['mae_led'] > -HSD)].copy()
    flip['true_pct'] = (flip['mae_true'] * 100).round(1)
    print(f"\n=== '깔끔 SL 가정→실제 청산'으로 바뀐 거래 {len(flip)}건 (상위 12, 실저점 깊은순) ===")
    for r in flip.sort_values('mae_true').head(12).itertuples():
        print(f"  {str(r.entry_t)[:10]} side{int(r.side):+d} 기록mae{r.mae_led*100:6.1f}% 실저점{r.true_pct:7.1f}% reason={r.reason}")
    led.to_csv(os.path.join(HERE, "verify_liq_king.csv"), index=False, encoding="utf-8-sig")
    print("\n저장: verify_liq_king.csv")


if __name__ == "__main__":
    main()
