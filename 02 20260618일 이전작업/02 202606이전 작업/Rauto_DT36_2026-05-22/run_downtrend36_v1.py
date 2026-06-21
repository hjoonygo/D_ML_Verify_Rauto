# -*- coding: utf-8 -*-
# [파일명] run_downtrend36_v1.py
# 코드길이: 약 200줄, 내부버전명: DT36_v1, 로직 축약/생략 없이 전체 출력
#
# [목적] 36개월 하락장(feat_struct_8=downtrend) 전체에 기계적 SHORT를 순차 진입,
#        검증 청산엔진(혁신1 ON)을 비율 50:50 / 60:40 두 가지로 돌려 엣지의 '일반화'를 본다.
#        한 구간(2025-10~2026-02)이 아니라 36개월 어디서나 PF>1인지 = 진짜 하락장 챔피언인지.
#
# [데이터] Merged_Data_with_Regime_Features.csv (단계 A 산출물, 라벨 포함). 상위폴더 자동탐색.
#          필요 컬럼만 로드: open/high/low/close + feat_struct_8.
#
# [trigger] 잃어버린 fib_trigger_roe는 원본 125건(entries_fixed.csv)에 매칭 최소오차로 자동복원.
#
# [함수 In/Out]
#   find_labeled() -> 라벨CSV 경로
#   load_labeled(path, regime_col) -> tz벗긴 DataFrame(OHLC+regime_col)
#   calibrate_trigger(...) -> 복원된 trigger(float)
#   per_entry(trades) -> 진입당 순익 DataFrame(연도 포함)
#   stats(net) -> dict(PF, 승률, 순익, Sharpe, MDD)
# ==============================================================================

import os, sys, math
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
REGIME_COL = 'feat_struct_8'        # 실시간 안전 라벨(스윙 확정지연 반영)
NOMINAL = 50000.0                   # capital 10000 * leverage 5
BASE = {'leverage': 5, 'fib_trigger_roe': 15.0, 'fib_sl_roe': 3.0, 'fib_ext_pct': 0.65,
        'fee_rate': 0.0004, 'funding_rate_daily': 0.0001}
CONFIGS = [(0.50, '50:50'), (0.60, '60:40')]   # 혁신1 ON 고정


def find_labeled():
    names = ["Merged_Data_with_Regime_Features.csv", "Merged_data_with_Regime_Features.csv"]
    for d in [WORK_DIR, os.path.dirname(WORK_DIR), r"D:\ML\Verify",
              os.path.join(os.path.dirname(WORK_DIR), "Regime_PC_2026-05-21")]:
        for n in names:
            p = os.path.join(d, n)
            if os.path.exists(p):
                return p
    raise FileNotFoundError("Merged_Data_with_Regime_Features.csv 를 찾을 수 없습니다 "
                            "(단계 A의 regime_feature_extractor 산출물). 상위 D:\\ML\\Verify 등에 두세요.")


def load_labeled(path, regime_col):
    head = pd.read_csv(path, nrows=1)
    if regime_col not in head.columns:
        raise KeyError(f"'{regime_col}' 컬럼이 없습니다. 가진 컬럼: {list(head.columns)[:15]} ...")
    use = ['timestamp', 'open', 'high', 'low', 'close', regime_col]
    df = pd.read_csv(path, usecols=use, index_col='timestamp', parse_dates=True)
    if getattr(df.index, 'tz', None) is not None:
        df.index = df.index.tz_localize(None)
    df = df.sort_index()
    return df


def per_entry(trades):
    d = pd.DataFrame(trades)
    if d.empty:
        return d
    d['key'] = d['진입시간']
    g = d.groupby('key').agg(net=('순수익금($)', 'sum'), 연도=('연도', 'first'),
                             진입시간=('진입시간', 'first')).reset_index(drop=True)
    g['진입시간'] = pd.to_datetime(g['진입시간'])
    return g.sort_values('진입시간').reset_index(drop=True)


def stats(net):
    net = np.asarray(net)
    if len(net) == 0:
        return dict(거래=0, PF=float('nan'), 승률=0, 순익=0, Sharpe=0, MDD=0)
    wins = net[net > 0].sum(); loss = net[net < 0].sum()
    pf = wins / abs(loss) if loss != 0 else float('inf')
    r = net / NOMINAL
    sr = float(r.mean() / r.std(ddof=1)) if len(r) > 1 and r.std(ddof=1) > 0 else 0.0
    cum = np.cumsum(net); mdd = float((cum - np.maximum.accumulate(cum)).min())
    return dict(거래=len(net), PF=pf, 승률=float((net > 0).mean()*100), 순익=float(net.sum()),
                Sharpe=sr, MDD=mdd)


def calibrate_trigger(exec_cls, base, df, candidates=(15.0, 16.0, 17.0, 17.5, 18.0, 19.0, 20.0)):
    """원본 125건(entries_fixed.csv)에 매칭 최소오차로 trigger 복원."""
    ent_path = os.path.join(WORK_DIR, "entries_fixed.csv")
    if not os.path.exists(ent_path):
        print("[보정] entries_fixed.csv 없음 -> trigger 기본 15.0 사용")
        return 15.0
    e = pd.read_csv(ent_path); e['진입시간'] = pd.to_datetime(e['진입시간'])
    orig = {t: float(n) for t, n in zip(e['진입시간'], e.get('orig_net', pd.Series([0]*len(e))))}
    entries = [(t, str(s).upper(), 'downtrend') for t, s in zip(e['진입시간'], e['side'])]
    t0 = e['진입시간'].min() - pd.Timedelta(days=2); t1 = e['진입시간'].max() + pd.Timedelta(days=90)
    sub = df.loc[(df.index >= t0) & (df.index <= t1)].copy()
    from Backtest_Engine_GridD_v2 import Backtest_Engine_GridD_v2
    print("[보정] fib_trigger_roe 복원(원본 125건 매칭):")
    best = None
    for trg in candidates:
        p = dict(base); p['split_ratio'] = 0.5; p['innovation1'] = True; p['fib_trigger_roe'] = trg
        eng = Backtest_Engine_GridD_v2(exec_cls(), p, sub); eng.run_entries(entries)
        g = pd.DataFrame(eng.get_trades())
        if g.empty:
            continue
        gg = g.groupby('진입시간')['순수익금($)'].sum()
        err = np.mean([abs(v - orig.get(pd.to_datetime(t), v)) for t, v in gg.items()])
        if best is None or err < best[1]:
            best = (trg, err)
    print(f"   -> 복원 trigger = {best[0]} (평균오차 {best[1]:,.1f}$)")
    return best[0]


def main():
    print("=" * 70)
    print("[36개월 하락장 검증 — DT36_v1 | 순차 SHORT, 혁신1 ON, 비율 50:50 & 60:40]")
    print("=" * 70)
    path = find_labeled(); print(f"[데이터] {path}")
    df = load_labeled(path, REGIME_COL)
    dn = (df[REGIME_COL].astype(str) == 'downtrend')
    print(f"[로드] {len(df):,}행 | 기간 {df.index.min().date()}~{df.index.max().date()} | "
          f"하락장 봉 {int(dn.sum()):,} ({dn.mean()*100:.1f}%)")

    from Exec_Dynamic_TS_GridD_v1 import Exec_Dynamic_TS_GridD_v1
    base = dict(BASE)
    base['fib_trigger_roe'] = calibrate_trigger(Exec_Dynamic_TS_GridD_v1, base, df)
    base['innovation1'] = True
    print(f"[확정 파라미터] lev={base['leverage']} sl={base['fib_sl_roe']} ext={base['fib_ext_pct']} "
          f"trigger={base['fib_trigger_roe']} 혁신1=ON")

    from Backtest_Engine_Downtrend36_v1 import Backtest_Engine_Downtrend36_v1
    for ratio, label in CONFIGS:
        p = dict(base); p['split_ratio'] = ratio
        eng = Backtest_Engine_Downtrend36_v1(Exec_Dynamic_TS_GridD_v1(), p, df, regime_col=REGIME_COL)
        eng.run()
        trades = eng.get_trades()
        tag = label.replace(':', '_')
        pd.DataFrame(trades).to_csv(os.path.join(WORK_DIR, f"DT36_trades_{tag}.csv"), index=False, encoding='utf-8-sig')
        g = per_entry(trades)
        ov = stats(g['net'].values) if not g.empty else stats([])
        print("\n" + "-" * 70)
        print(f"[비율 {label} | 혁신1 ON] 36개월 하락장 전체")
        print(f"  진입 {ov['거래']}건  PF={ov['PF']:.3f}  승률={ov['승률']:.1f}%  "
              f"순익={ov['순익']:,.0f}$  Sharpe={ov['Sharpe']:.3f}  MDD={ov['MDD']:,.0f}$")
        print("  --- 연도별 ---")
        for yr in sorted(g['연도'].unique()):
            s = stats(g[g['연도'] == yr]['net'].values)
            print(f"    {yr}: 진입{s['거래']:4d}  PF={s['PF']:.2f}  승률={s['승률']:.0f}%  순익={s['순익']:>9,.0f}$  MDD={s['MDD']:>8,.0f}$")
    print("\n[저장] DT36_trades_50_50.csv, DT36_trades_60_40.csv")
    print("[해석] 모든 연도에서 PF>1이면 '진짜 하락장 챔피언'. 특정 해만 좋으면 한 구간 운.")


if __name__ == "__main__":
    main()
