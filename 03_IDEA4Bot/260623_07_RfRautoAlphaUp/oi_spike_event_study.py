# -*- coding: utf-8 -*-
# [oi_spike_event_study.py] A001 1단계 — OI Spike 이벤트 study (제미나이 의뢰서 H1 핵심을 우리 데이터로 직접 검정).
#   질문: OI delta가 '드문 이벤트(spike)'일 때, 그 순간 이후 forward 수익률 분포가 baseline 대비 이동하는가?
#         그리고 그 이동이 '방향(예측력)'인가 '변동성(위치설명)'인가? (웹근거: spike=헤지가능·변동성 위치)
#   ★우리 연속IC(oi_change_1h IC~0.005~0.046 부호불안정)는 약했음 — 이벤트 조건부는 미검증 각도.
#   정의: OI Spike = oi_change_1h_pct의 rolling z-score(과거 24h=1440봉, 룩어헤드0). 양 z>2 / 음 z<-2.
#   이벤트 비중첩(쿨다운 6h). forward = +1h·3h·6h·12h·24h·48h(1m 인덱스). baseline=전체 동일k 분포.
import os
import numpy as np, pandas as pd
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
W = 1440          # z-score 롤링창 24h
COOLDOWN = 360    # 이벤트 비중첩 6h
KS = [60, 180, 360, 720, 1440, 2880]  # forward 분(1·3·6·12·24·48h)
KLAB = ["1h", "3h", "6h", "12h", "24h", "48h"]


def _p(*a): print(*a, flush=True)


def find_data():
    for c in [r"D:\ML\RfRauto\08_BTC_Data\derived\Merged_Data.csv", r"D:\ML\Verify\Merged_Data.csv"]:
        if os.path.exists(c): return c
    raise FileNotFoundError("Merged_Data.csv")


def events(mask, n, maxk):
    idx = np.where(mask)[0]; out = []; last = -10**9
    for i in idx:
        if i - last >= COOLDOWN and i + maxk < n:
            out.append(i); last = i
    return np.array(out)


def main():
    DATA = find_data(); _p(f"[데이터] {DATA}")
    d = pd.read_csv(DATA, usecols=["timestamp", "close", "oi_change_1h_pct", "oi_was_missing"])
    d["t"] = pd.to_datetime(d["timestamp"], utc=True, format="ISO8601")
    d = d.dropna(subset=["close"]).reset_index(drop=True)
    # 1m 연속성 점검(인덱스+k ≈ k분 후 가정 검증)
    dt = d["t"].diff().dt.total_seconds().dropna()
    gap = (dt != 60).mean()
    _p(f"[봉] {len(d)}개 | 1분간격 비율 {100*(dt==60).mean():.1f}% | 비정상간격 {100*gap:.1f}% "
       f"| 기간 {d['t'].min().date()}~{d['t'].max().date()}")
    c = d["close"].values
    oichg = pd.to_numeric(d["oi_change_1h_pct"], errors="coerce")
    miss = pd.to_numeric(d["oi_was_missing"], errors="coerce").fillna(0).values
    _p(f"[OI] oi_change_1h_pct 유효 {oichg.notna().sum()} | oi_was_missing {int(miss.sum())}건 "
       f"| 분포 p50 {oichg.median():.4f} p99 {oichg.quantile(.99):.4f} p01 {oichg.quantile(.01):.4f}")
    # rolling z (과거만, 룩어헤드0)
    mu = oichg.rolling(W).mean(); sd = oichg.rolling(W).std()
    z = ((oichg - mu) / sd).values
    z[miss == 1] = np.nan  # OI 결측보간 구간 제외
    n = len(d); maxk = max(KS)

    # baseline: 전체 시점 forward return (k별 평균·std)
    base = {}
    for k in KS:
        fr = c[k:] / c[:-k] - 1.0
        base[k] = (np.nanmean(fr), np.nanstd(fr))

    _p("\n==== OI Spike 이벤트 forward return (baseline 대비) ====")
    _p("해석: Δmean이 baseline과 유의(p<0.05)하게 +/− 면 '방향 예측력', vol비 >1이면 '변동성 위치'")
    for lbl, mask in [("◆ 양 spike (z>+2, OI 급증)", z > 2), ("◆ 음 spike (z<-2, OI 급감)", z < -2)]:
        ev = events(mask & ~np.isnan(z), n, maxk)
        _p(f"\n{lbl} — 이벤트 {len(ev)}건 (비중첩 6h)")
        if len(ev) < 20:
            _p("  표본부족(<20) — 판정보류"); continue
        _p(f"  {'k':>5}{'이벤트평균':>11}{'baseline':>11}{'Δmean':>10}{'p값':>8}{'상승%':>7}{'vol비':>7}")
        for k, kl in zip(KS, KLAB):
            fr = c[ev + k] / c[ev] - 1.0
            bm, bs = base[k]
            t, p = stats.ttest_1samp(fr, bm)        # 이벤트평균 ≠ baseline?
            up = 100 * (fr > 0).mean(); volr = np.std(fr) / bs
            _p(f"  {kl:>5}{fr.mean()*100:>+10.3f}%{bm*100:>+10.3f}%{(fr.mean()-bm)*100:>+9.3f}%"
               f"{p:>8.3f}{up:>6.0f}%{volr:>7.2f}")

    # 방향 조건부: spike 시점 직전 6h 추세(상승/하락중)별 분리 — OI급증이 추세지속? 반전?
    _p("\n==== 양 spike를 '진입시 추세'로 분리 (OI급증 후 추세지속 vs 반전?) ====")
    ev = events((z > 2) & ~np.isnan(z), n, maxk)
    if len(ev) >= 40:
        trend = c[ev] / c[ev - COOLDOWN] - 1.0   # 직전 6h 수익률(룩어헤드0)
        for tl, tm in [("상승중 진입", trend > 0), ("하락중 진입", trend < 0)]:
            sub = ev[tm]
            if len(sub) < 15: continue
            _p(f"  [{tl}] {len(sub)}건")
            for k, kl in zip([180, 720, 2880], ["3h", "12h", "48h"]):
                fr = c[sub + k] / c[sub] - 1.0; bm, _ = base[k]
                _p(f"    {kl}: 평균 {fr.mean()*100:+.3f}% (baseline {bm*100:+.3f}%) 상승 {100*(fr>0).mean():.0f}%")

    # 연도별 안정성(양spike 12h)
    _p("\n==== 연도별 양spike 12h forward (안정성) ====")
    ev = events((z > 2) & ~np.isnan(z), n, maxk)
    yr = d["t"].dt.year.values
    for y in sorted(set(yr[ev])):
        sub = ev[yr[ev] == y]
        if len(sub) < 8: continue
        fr = c[sub + 720] / c[sub] - 1.0
        _p(f"  {y}: {len(sub)}건 | 12h 평균 {fr.mean()*100:+.3f}% | 상승 {100*(fr>0).mean():.0f}%")

    _p("\n[판정틀] ①Δmean 유의+부호일관 = 방향 예측력(알파가능성). ②vol비≫1·Δmean무의미 = 변동성위치(방향X).")
    _p("[정직] 단변량 연속IC는 약했음. 이벤트 조건부가 살면 다음=alpha_verification_system 3단(WF·CPCV·SPRT).")
    _p("[데이터무결성] z는 과거1440봉 롤링(룩어헤드0)·oi_was_missing 제외·forward는 미래 close.")


if __name__ == "__main__":
    main()
