# -*- coding: utf-8 -*-
# [파일명] run_floor_grid_v1.py
# 코드길이: 약 200줄, 내부버전명: FLOORGRID_v1, 로직 축약/생략 없이 전체 출력
#
# [목적] "폭주 5건만 자르고 회복 거래 715건은 살리는" 파국 손절폭을 데이터로 찾는다.
#   (1) 기준 측정: 플로어 사실상 무제한(999% ROE)으로 1회 -> 각 구멍거래의 '구멍구간 최대역행 ROE(MAE)'
#       분포 + 폭주(max_hold) 거래의 MAE 확인 -> 5건과 715건이 갈리는 지점을 눈으로 본다.
#   (2) 그리드: 파국손절 15/20/25/30%(ROE)로 각각 36개월 하락장 돌려, 컷 건수·폭주잡힘·PF·순익·연도별.
#   엔진은 정정본(구멍 fib_stop=None 일 때만 플로어). 비율 50:50, 혁신1 ON, trigger15, ext0.65 고정.
#
# [용어] 구멍MAE_ROE: SHORT가 보호스탑 잡히기 전 도달한 최대 '역행' ROE%(가격상승=손실쪽). 레버5 반영.
# ==============================================================================

import os, sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
REGIME_COL = 'feat_struct_8'
NOMINAL = 50000.0
FLOORS = [15.0, 20.0, 25.0, 30.0]
BASE = {'leverage': 5, 'fib_trigger_roe': 15.0, 'fib_ext_pct': 0.65, 'split_ratio': 0.50,
        'fee_rate': 0.0004, 'funding_rate_daily': 0.0001, 'innovation1': True}


def find_labeled():
    names = ["Merged_Data_with_Regime_Features.csv", "Merged_Data.csv"]
    for d in [WORK_DIR, os.path.dirname(WORK_DIR), r"D:\ML\Verify",
              os.path.join(os.path.dirname(WORK_DIR), "Regime_PC_2026-05-21")]:
        for n in names:
            p = os.path.join(d, n)
            if os.path.exists(p):
                return p
    raise FileNotFoundError("Merged_Data_with_Regime_Features.csv 를 상위 D:\\ML\\Verify 에 두세요.")


def load_labeled(path, regime_col):
    head = pd.read_csv(path, nrows=1)
    if regime_col not in head.columns:
        raise KeyError(f"'{regime_col}' 컬럼 없음. 가진 컬럼: {list(head.columns)[:12]}")
    df = pd.read_csv(path, usecols=['timestamp', 'open', 'high', 'low', 'close', regime_col],
                     index_col='timestamp', parse_dates=True)
    if getattr(df.index, 'tz', None) is not None:
        df.index = df.index.tz_localize(None)
    return df.sort_index()


def per_entry(trades):
    d = pd.DataFrame(trades)
    if d.empty:
        return d
    g = d.groupby('진입시간').agg(net=('순수익금($)', 'sum'), 연도=('연도', 'first'),
                               mae=('구멍MAE_ROE', 'max'),
                               reason=('청산사유(Exec)', 'last'),
                               xt=('청산시간', 'max')).reset_index()
    return g


def stats(net):
    net = np.asarray(net, float)
    if len(net) == 0:
        return dict(거래=0, PF=float('nan'), 승률=0, 순익=0, MDD=0)
    w = net[net > 0].sum(); l = net[net < 0].sum()
    pf = w / abs(l) if l != 0 else float('inf')
    cum = np.cumsum(net); mdd = float((cum - np.maximum.accumulate(cum)).min())
    return dict(거래=len(net), PF=pf, 승률=float((net > 0).mean()*100), 순익=float(net.sum()), MDD=mdd)


def main():
    print("=" * 72)
    print("[파국 손절폭 찾기 — FLOORGRID_v1 | 36개월 하락장, 구멍일때만 플로어]")
    print("=" * 72)
    path = find_labeled(); print(f"[데이터] {path}")
    df = load_labeled(path, REGIME_COL)
    data_end = df.index.max().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[로드] {len(df):,}행 | {df.index.min().date()}~{df.index.max().date()}\n")

    from Exec_Dynamic_TS_GridD_v2 import Exec_Dynamic_TS_GridD_v2
    from Backtest_Engine_Downtrend36_v1 import Backtest_Engine_Downtrend36_v1

    # ---------- (1) 기준 측정: 플로어 무제한 -> 구멍 MAE 분포 ----------
    print("[1] 기준 측정 (플로어 999% = 사실상 무제한) — 구멍 MAE 분포 확보 ...")
    p0 = dict(BASE); p0['hard_floor_roe'] = 999.0; p0['fib_sl_roe'] = 999.0
    eng0 = Backtest_Engine_Downtrend36_v1(Exec_Dynamic_TS_GridD_v2(), p0, df, regime_col=REGIME_COL)
    eng0.run()
    g0 = per_entry(eng0.get_trades())
    g0.to_csv(os.path.join(WORK_DIR, "FLOOR_ref_noFloor.csv"), index=False, encoding='utf-8-sig')
    # 폭주(max_hold, 데이터끝 제외) 거래의 MAE
    blow = g0[(g0['reason'].astype(str).str.contains('max_hold')) & (g0['xt'] != data_end)]
    ov0 = stats(g0['net'].values)
    print(f"  무제한 결과: 진입 {ov0['거래']}건  PF={ov0['PF']:.3f}  순익={ov0['순익']:,.0f}$  (폭주 {len(blow)}건)")
    print(f"  [폭주 {len(blow)}건의 구멍MAE_ROE]: " + ", ".join(f"{m:,.0f}%" for m in sorted(blow['mae'], reverse=True)))
    print("  [구멍 MAE 분포 — 구간별 진입 건수]")
    buckets = [(0,5),(5,10),(10,15),(15,20),(20,25),(25,30),(30,50),(50,100),(100,1e9)]
    for lo, hi in buckets:
        c = int(((g0['mae'] >= lo) & (g0['mae'] < hi)).sum())
        lab = f"{lo:>3.0f}~{hi:>3.0f}%" if hi < 1e8 else f"{lo:>3.0f}%+   "
        print(f"     {lab}: {c:4d}건  " + "█"*min(c, 60))
    print()

    # ---------- (2) 파국손절 그리드 ----------
    print("[2] 파국손절 그리드 (구멍일때만 작동) ...")
    rows = []
    for fl in FLOORS:
        p = dict(BASE); p['hard_floor_roe'] = fl; p['fib_sl_roe'] = fl
        eng = Backtest_Engine_Downtrend36_v1(Exec_Dynamic_TS_GridD_v2(), p, df, regime_col=REGIME_COL)
        eng.run()
        tr = eng.get_trades()
        g = per_entry(tr)
        cut = sum(1 for t in tr if '구멍 하드플로어' in str(t['청산사유(Exec)']))
        blow_left = sum(1 for t in tr if 'max_hold' in str(t['청산사유(Exec)']) and t['청산시간'] != data_end)
        ov = stats(g['net'].values)
        yr_pfs = {yr: stats(g[g['연도'] == yr]['net'].values)['PF'] for yr in sorted(g['연도'].unique())}
        pd.DataFrame(tr).to_csv(os.path.join(WORK_DIR, f"FLOOR_{int(fl)}.csv"), index=False, encoding='utf-8-sig')
        rows.append({'파국손절%': fl, '컷건수': cut, '잔여폭주': blow_left, '거래': ov['거래'],
                     'PF': round(ov['PF'],3), '승률': round(ov['승률'],1), '순익': round(ov['순익']),
                     'MDD': round(ov['MDD']), **{f'PF{y}': round(v,2) for y,v in yr_pfs.items()}})
        print(f"  파국손절 {fl:>4.0f}%: 컷 {cut}건, 잔여폭주 {blow_left}건 -> PF={ov['PF']:.3f} 순익={ov['순익']:,.0f}$ MDD={ov['MDD']:,.0f}$")

    summ = pd.DataFrame(rows)
    summ.to_csv(os.path.join(WORK_DIR, "FLOOR_grid_summary.csv"), index=False, encoding='utf-8-sig')
    print("\n[요약]")
    print(summ.to_string(index=False))
    print("\n[판정] (1) 위 MAE 분포에서 폭주 5건과 회복거래가 갈리는 빈 구간 = 거기에 손절 두면 5건만 잡힘.")
    print("       (2) 그리드에서 '잔여폭주 0 이면서 컷건수 최소(=회복거래 안 죽임)'인 손절폭이 최적.")
    print("[저장] FLOOR_ref_noFloor.csv, FLOOR_15/20/25/30.csv, FLOOR_grid_summary.csv")


if __name__ == "__main__":
    main()
