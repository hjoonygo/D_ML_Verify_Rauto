# -*- coding: utf-8 -*-
# [파일명] run_downtrend36_v2.py
# 코드길이: 약 190줄, 내부버전명: DT36_v2_fixed, 로직 축약/생략 없이 전체 출력
#
# [목적] 통합판_v2 문서 명시 수정(하드플로어, 단 구멍일때만)을 적용한 엔진(Exec_GridD_v2)으로
#        36개월 하락장 SHORT를 돌려, 손절폭 4종 × 분할비율 2종 = 8 config를 연도별로 검증.
#        1차 확인: 옛 엔진에서 났던 '90일 폭주(max_hold)'가 0건으로 사라지는가.
#        2차 확인: 손절폭별 36개월 하락장 PF/순익/MDD — 어느 손절폭이 최선인가.
#
# [수정 출처] 통합판_v2 "1-5": 손절 구멍(첫 OB 미도달 시 손절 부재) -> 구멍(보호스탑 fib_stop=None)일 때만 하드플로어 작동.
#
# [파라미터] leverage5, fib_ext0.65, trigger15.0(고정), 혁신1 ON. hard_floor_roe = 그리드 변수.
#            * 수정으로 청산 동작이 바뀌므로 2.864 '정확 재현'은 더 이상 목표 아님(버그 교정분).
#
# [그리드] hard_floor_roe ∈ {2.4, 3.0, 5.0, 8.0}%(ROE) × split_ratio ∈ {0.50, 0.60}
# ==============================================================================

import os, sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
REGIME_COL = 'feat_struct_8'
NOMINAL = 50000.0
HARD_FLOORS = [2.4, 3.0, 5.0, 8.0]
RATIOS = [(0.50, '50:50'), (0.60, '60:40')]
BASE = {'leverage': 5, 'fib_trigger_roe': 15.0, 'fib_ext_pct': 0.65,
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
                               진입시간=('진입시간', 'first')).reset_index(drop=True)
    g['진입시간'] = pd.to_datetime(g['진입시간'])
    return g.sort_values('진입시간').reset_index(drop=True)


def stats(net):
    net = np.asarray(net, float)
    if len(net) == 0:
        return dict(거래=0, PF=float('nan'), 승률=0, 순익=0, MDD=0, Sharpe=0)
    w = net[net > 0].sum(); l = net[net < 0].sum()
    pf = w / abs(l) if l != 0 else float('inf')
    cum = np.cumsum(net); mdd = float((cum - np.maximum.accumulate(cum)).min())
    r = net / NOMINAL
    sr = float(r.mean() / r.std(ddof=1)) if len(r) > 1 and r.std(ddof=1) > 0 else 0.0
    return dict(거래=len(net), PF=pf, 승률=float((net > 0).mean()*100), 순익=float(net.sum()), MDD=mdd, Sharpe=sr)


def main():
    print("=" * 72)
    print("[36개월 하락장 손절그리드 — DT36_v2 (하드플로어 수정엔진) | 혁신1 ON]")
    print("=" * 72)
    path = find_labeled(); print(f"[데이터] {path}")
    df = load_labeled(path, REGIME_COL)
    dn = (df[REGIME_COL].astype(str) == 'downtrend')
    print(f"[로드] {len(df):,}행 | {df.index.min().date()}~{df.index.max().date()} | 하락장 {int(dn.sum()):,}봉({dn.mean()*100:.1f}%)")
    print(f"[수정] 구멍(보호스탑 fib_stop=None)일 때만 하드플로어 작동. 그리드 손절 {HARD_FLOORS}%(ROE) × 비율 {[r[1] for r in RATIOS]}\n")

    from Exec_Dynamic_TS_GridD_v2 import Exec_Dynamic_TS_GridD_v2
    from Backtest_Engine_Downtrend36_v1 import Backtest_Engine_Downtrend36_v1
    data_end = df.index.max().strftime('%Y-%m-%d %H:%M:%S')

    rows = []
    for ratio, rlabel in RATIOS:
        for hf in HARD_FLOORS:
            p = dict(BASE); p['split_ratio'] = ratio; p['hard_floor_roe'] = hf; p['fib_sl_roe'] = hf
            eng = Backtest_Engine_Downtrend36_v1(Exec_Dynamic_TS_GridD_v2(), p, df, regime_col=REGIME_COL)
            eng.run()
            trades = eng.get_trades()
            # 진짜 폭주 = 90일 max_hold 인데 '데이터 끝 경계'가 아닌 것만(경계 1건은 자료부족 아티팩트)
            blowups = sum(1 for t in trades if 'max_hold' in str(t['청산사유(Exec)']) and t['청산시간'] != data_end)
            tag = f"sl{hf}_{rlabel.replace(':','_')}"
            pd.DataFrame(trades).to_csv(os.path.join(WORK_DIR, f"DT36v2_{tag}.csv"), index=False, encoding='utf-8-sig')
            g = per_entry(trades)
            ov = stats(g['net'].values) if not g.empty else stats([])
            print("-" * 72)
            print(f"[손절 {hf}% | 비율 {rlabel}] 폭주(90일강제) {blowups}건  "
                  f"-> 진입 {ov['거래']}건 PF={ov['PF']:.3f} 승률={ov['승률']:.0f}% 순익={ov['순익']:,.0f}$ MDD={ov['MDD']:,.0f}$")
            yr_line = []
            for yr in sorted(g['연도'].unique()):
                s = stats(g[g['연도'] == yr]['net'].values)
                yr_line.append(f"{yr}:PF{s['PF']:.2f}/순익{s['순익']:,.0f}")
            print("    연도별 " + " | ".join(yr_line))
            row = {'손절%': hf, '비율': rlabel, '폭주건수': blowups, **{k: ov[k] for k in ('거래','PF','승률','순익','MDD','Sharpe')}}
            # 연도별 PF 모두 >1 인지
            yr_pfs = [stats(g[g['연도']==yr]['net'].values)['PF'] for yr in sorted(g['연도'].unique())]
            row['전연도PF>1'] = all((pf > 1) for pf in yr_pfs if pf == pf)
            rows.append(row)

    summ = pd.DataFrame(rows)
    summ.to_csv(os.path.join(WORK_DIR, "DT36v2_summary.csv"), index=False, encoding='utf-8-sig')
    print("\n" + "=" * 72)
    print("[요약]")
    print(summ.to_string(index=False))
    print("\n[판정] (1) 폭주건수 0 = 구멍 수정 성공.  (2) 전연도PF>1=True 인 손절폭 = 진짜 하락장 챔피언.")
    print("       (3) 그 중 MDD 작고 순익 큰 손절폭이 최적. (4) 50:50 vs 60:40 비교.")
    print("[저장] DT36v2_summary.csv + DT36v2_*.csv (config별 거래)")


if __name__ == "__main__":
    main()
