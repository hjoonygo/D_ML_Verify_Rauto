# -*- coding: utf-8 -*-
# [diag_revswitch_flipcensus.py]  ★선보고용 읽기전용 진단(코딩-Stage2 아님): 엔진 무수정 import로
#   2023~2026 7h 슈퍼트렌드 trend_flip 이벤트 수 + 강신호 후보필터별 N + 대기봉수만 집계. P&L·채택 없음.
import os, sys
import numpy as np, pandas as pd

HERE = r"D:\ML\Verify"
ENG_DIR = os.path.join(HERE, "07Prj_Ch3_Stg10_TrendStackSelfContainedSizing")
if ENG_DIR not in sys.path: sys.path.insert(0, ENG_DIR)
import trendstack_signal_engine as eng

def find_data():
    for nm in ["Merged_Data_with_Regime_Features.csv", "Merged_Data.csv"]:
        p = os.path.join(HERE, nm)
        if os.path.exists(p): return p
    raise SystemExit("no data")

def main():
    mp = find_data()
    print(f"[in] {mp}")
    df1 = pd.read_csv(mp, usecols=lambda c: c in ('timestamp','open','high','low','close'))
    df1['timestamp'] = pd.to_datetime(df1['timestamp']); df1 = df1.set_index('timestamp')
    df7 = eng.resample_tf(df1, eng.TF_MIN)
    sig = eng.compute_signals(df7)
    T = sig['Trend']; er = sig['er']; adx = sig['adx']; chop = sig['chop']
    ph = sig['ph_conf']; pl = sig['pl_conf']
    n = len(T)
    yrs = df7.index.year.values
    print(f"[7h] {n}봉 | {df7.index.min()} ~ {df7.index.max()}")

    # ── trend_flip 이벤트(둘 다 nonzero, 방향 반전) ──
    flips = [i for i in range(1, n) if T[i] != 0 and T[i-1] != 0 and T[i] != T[i-1]]
    to_long  = [i for i in flips if T[i] == 1]
    to_short = [i for i in flips if T[i] == -1]
    print(f"\n[전체 슈퍼트렌드 flip] N={len(flips)}  (→롱 {len(to_long)} / →숏 {len(to_short)})")
    # 연도별
    import collections
    cy = collections.Counter(yrs[i] for i in flips)
    print("  연도별:", dict(sorted(cy.items())))

    # ── 강신호 후보 필터별 N (flip봉 i의 과거값) ──
    def cnt(mask_fn):
        return sum(1 for i in flips if mask_fn(i))
    print("\n[강신호 후보필터별 flip N]")
    for label, fn in [
        ("er>=0.40",        lambda i: er[i] >= 0.40),
        ("er>=0.45",        lambda i: er[i] >= 0.45),
        ("adx>=25",         lambda i: adx[i] >= 25.0),
        ("er>=0.40 & adx>=25", lambda i: er[i] >= 0.40 and adx[i] >= 25.0),
        ("er>=0.45 & adx>=25", lambda i: er[i] >= 0.45 and adx[i] >= 25.0),
        ("chop<=38.2 (추세)",  lambda i: chop[i] != 0 and chop[i] <= 38.2),
    ]:
        print(f"  {label:24s} N={cnt(fn)}")

    # ── 대기봉수(A의 시간손실 근사): flip봉 i 이후 '새 방향 피벗확정' 첫 봉까지 ──
    #   롱전환=다음 new_pl, 숏전환=다음 new_ph (엔진 진입조건의 피벗요소). 손익 아님, 봉수만.
    waits = []
    for i in flips:
        d = T[i]; target = pl if d == 1 else ph   # 롱=pl확정 / 숏=ph확정
        w = None
        for j in range(i+1, min(i+200, n)):
            if j in target and (T[j] == d):       # 같은 방향 유지 중 첫 확정
                w = j - i; break
        if w is not None: waits.append(w)
    if waits:
        wq = np.percentile(waits, [25,50,75,90])
        print(f"\n[대기봉수(flip→새방향 피벗확정)] 측정가능 {len(waits)}/{len(flips)}건 "
              f"| 중앙{wq[1]:.0f}봉(=7h×{wq[1]:.0f}={wq[1]*7:.0f}h) p25/75/90 {wq[0]:.0f}/{wq[2]:.0f}/{wq[3]:.0f}")
    # 강신호(er>=0.45 & adx>=25) 한정 N + 대기
    strong = [i for i in flips if er[i] >= 0.45 and adx[i] >= 25.0]
    sw = []
    for i in strong:
        d = T[i]; target = pl if d == 1 else ph
        for j in range(i+1, min(i+200, n)):
            if j in target and (T[j] == d): sw.append(j-i); break
    print(f"\n[★강신호 er45&adx25 한정] flip N={len(strong)} | 피벗확정 대기 측정 {len(sw)}건 "
          f"중앙 {np.median(sw) if sw else float('nan'):.0f}봉")
    print("\n(주의: 위는 이벤트 수·대기봉수 센서스일 뿐. A/B 실현손익 Δ는 캡틴 정의승인 후 Stage2에서 측정.)")

if __name__ == "__main__":
    main()
