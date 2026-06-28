# -*- coding: utf-8 -*-
# [sizing_validation.py] 260623_07 정식검증 — ATR×OI 변동성 사이징 (T0→T1 졸업조건).
#   질문: MDD -39→-19.1%가 '칼날(특정 파라미터만)'인가 '견고(파라미터·기간 무관)'인가?
#   ① 민감도 격자(K·임계·하한) → MDD<-20%·CPCV p25>0 유지 비율 (견고성)
#   ② CPCV 15경로 p25 (시간순 6그룹) ③ 연도별 사이징 효과 부호 일관 (WF 대용)
#   재현: vol_sizing_compare.build/simulate 재사용(1m 실체결·낙관금지). 판정 후 alpha_card·체크리스트 갱신.
import os, sys, itertools
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import vol_sizing_compare as V


def _p(*a): print(*a, flush=True)
def mdd(r): eq = np.cumprod(1 + r); pk = np.maximum.accumulate(eq); return ((eq - pk) / pk).min() * 100
def tot(r): return (np.cumprod(1 + r)[-1] - 1) * 100


def cpcv_p25(r, g=6):
    gs = np.array_split(np.arange(len(r)), g); ps = []
    for c in itertools.combinations(range(g), 2):
        rr = r[np.concatenate([gs[k] for k in c])]
        ps.append(rr.mean() / rr.std() * np.sqrt(len(rr) / 3) if rr.std() > 0 else 0)
    return np.percentile(ps, 25), np.min(ps)


def sized(ret, atr, oie, med, K, thr, fl):
    soi = np.clip(1 - K * np.maximum(0, oie - thr), fl, 1)
    sat = np.clip(med / atr, fl, 1)
    return ret * sat * soi


def main():
    d, S, oi = V.build(V.find_data())
    T = V.simulate(d, S, oi)
    ret = T.ret.values; atr = T.atr_e.values; oie = T.oi_e.values
    med = np.median(atr); yr = T.year.values
    _p(f"[거래] {len(T)} | 무사이징 복리 {tot(ret):+.0f}% MDD {mdd(ret):.1f}%")

    # ① 민감도 격자
    _p("\n① 민감도 격자 (K·임계·하한, ATR×OI) — 칼날 vs 견고")
    rows = []
    for K in [0.2, 0.3, 0.4]:
        for thr in [1.0, 1.5, 2.0]:
            for fl in [0.2, 0.25, 0.3]:
                r = sized(ret, atr, oie, med, K, thr, fl)
                p25, _ = cpcv_p25(r)
                rows.append((mdd(r), p25, tot(r)))
                if K == 0.3 and thr == 1.5 and fl == 0.25:
                    _p(f"  ★기준 K0.3/thr1.5/fl0.25: 복리 {tot(r):+.0f}% MDD {mdd(r):.1f}% CPCVp25 {p25:+.2f}")
    rows = np.array(rows)
    mdd20 = 100 * np.mean(rows[:, 0] > -20)
    cp0 = 100 * np.mean(rows[:, 1] > 0)
    _p(f"  격자 {len(rows)}조합: MDD>-20% 유지 {mdd20:.0f}% | CPCV p25>0 유지 {cp0:.0f}% "
       f"| MDD 중앙 {np.median(rows[:,0]):.1f}% | MDD 최악 {rows[:,0].min():.1f}% | 복리 중앙 {np.median(rows[:,2]):+.0f}%")

    # ② CPCV 15경로 (기준 파라미터)
    rbase = sized(ret, atr, oie, med, 0.3, 1.5, 0.25)
    p25, worst = cpcv_p25(rbase)
    _p(f"\n② CPCV 15경로(기준): p25 {p25:+.2f} | 최악경로 {worst:+.2f}")

    # ③ 연도별 사이징 효과 (WF 대용 — 무사이징 대비 MDD 개선 부호 일관?)
    _p("\n③ 연도별 MDD: 무사이징 vs ATR×OI (개선 부호 일관 = 견고)")
    cons = 0; tot_y = 0
    for y in sorted(set(yr)):
        m = yr == y
        if m.sum() < 20: continue
        m0 = mdd(ret[m]); m1 = mdd(rbase[m]); tot_y += 1
        imp = m1 > m0  # MDD 개선(덜 음수)
        cons += imp
        _p(f"  {y}: 무사이징 {m0:.1f}% → ATR×OI {m1:.1f}% {'개선' if imp else '악화'}")
    _p(f"  개선 연도 {cons}/{tot_y}")

    # 판정
    _p("\n[판정]")
    robust = (mdd20 >= 60 and cp0 >= 70 and cons >= tot_y - 1)
    if robust:
        _p(f"  ★견고 — MDD>-20% {mdd20:.0f}%·CPCV>0 {cp0:.0f}%·연도개선 {cons}/{tot_y} = 칼날 아님. T1 승급 후보.")
    else:
        _p(f"  △미달 — MDD>-20% {mdd20:.0f}%·CPCV>0 {cp0:.0f}%·연도개선 {cons}/{tot_y}. 견고성 부족=T0 유지·보강.")
    _p("[정직] CPCV는 시간순 6그룹 근사(정식 퍼지+엠바고는 별도). 노출0.54=레버1 절반(복리 그만큼). 신호=mom+oi 위 오버레이.")


if __name__ == "__main__":
    main()
