# -*- coding: utf-8 -*-
# [파일명] measure_ob_sl_v1.py
# 코드길이: 약 130줄, 내부버전명: OBSL_v1, 로직 축약/생략 없이 전체 출력
#
# [목적] 36개월 하락장 SHORT 진입(DT36 733건) 각각에서, '진입가 위쪽 가장 가까운 저항 OB'까지
#        거리를 엔진과 동일한 OB 탐지로 측정 -> 평균/중앙값/분포 출력.
#        => 사장님이 기억하는 'OB SL 평균거리'의 정확한 값 확인 + 폭주구멍 메울 Phase1 스탑폭 근거.
#
# [OB 정의] 엔진(_find_order_blocks)과 동일: 최근 100봉(여기선 60봉 윈도우) 스윙고점 중
#           진입가보다 위 = 저항(bearish) OB. 가장 가까운 것 = bottom 최소.
#           SL 후보 = 그 OB의 bottom(저항 시작)/mean(중앙)/top(저항 끝).
#
# [거리] (OB레벨 - 진입가)/진입가 *100 = 가격%.  ROE% = 가격% * leverage(5).  bp(price)=가격%*100.
#
# [미래참조] 진입 시점 '직전 60봉'만 사용(스윙은 좌우2봉이라 마지막2봉 제외 -> 사실상 과거만).
#
# [함수 In/Out]
#   find_labeled()/load_price(): 가격데이터 로드
#   nearest_resistance(window, entry): -> dict(bottom/mean/top 거리%) or None(저항없음=구멍)
# ==============================================================================

import os, sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
WINDOW = 60
LEV = 5


def find_labeled():
    names = ["Merged_Data_with_Regime_Features.csv", "Merged_Data.csv"]
    for d in [WORK_DIR, os.path.dirname(WORK_DIR), r"D:\ML\Verify",
              os.path.join(os.path.dirname(WORK_DIR), "Regime_PC_2026-05-21")]:
        for n in names:
            p = os.path.join(d, n)
            if os.path.exists(p):
                return p
    raise FileNotFoundError("Merged_Data_with_Regime_Features.csv (또는 Merged_Data.csv) 를 상위 D:\\ML\\Verify 에 두세요.")


def load_price(path):
    df = pd.read_csv(path, usecols=lambda c: c in ('timestamp', 'open', 'high', 'low', 'close'),
                     index_col='timestamp', parse_dates=True)
    if getattr(df.index, 'tz', None) is not None:
        df.index = df.index.tz_localize(None)
    return df.sort_index()


def nearest_resistance(highs, lows, entry):
    """엔진과 동일 스윙고점 탐지로 진입가 위 가장 가까운 저항 OB 거리(%). 없으면 None."""
    obs = []
    for i in range(2, len(highs) - 2):
        if highs[i] == max(highs[i - 2:i + 3]) and highs[i] > entry:
            obs.append((lows[i], highs[i]))   # (bottom, top)
    if not obs:
        return None
    obs.sort(key=lambda x: x[0])              # bottom 최소 = 가장 가까운 저항
    bottom, top = obs[0]
    mean = (bottom + top) / 2
    return {
        'bottom_pct': (bottom - entry) / entry * 100,
        'mean_pct':   (mean - entry) / entry * 100,
        'top_pct':    (top - entry) / entry * 100,
    }


def summ(arr, name):
    a = np.array(arr, float)
    if len(a) == 0:
        print(f"  {name}: 표본 0"); return
    print(f"  {name}: 평균 {a.mean():.3f}% (ROE {a.mean()*LEV:.2f}%, {a.mean()*100:.0f}bp) | "
          f"중앙값 {np.median(a):.3f}% | 25~75%: {np.percentile(a,25):.3f}~{np.percentile(a,75):.3f}% | "
          f"최소 {a.min():.3f}% 최대 {a.max():.3f}%")


def main():
    print("=" * 70)
    print("[하락장 SHORT 진입 — OB SL(위쪽 저항) 평균거리 측정 | OBSL_v1]")
    print("=" * 70)
    price = load_price(find_labeled())
    ent = pd.read_csv(os.path.join(WORK_DIR, "entries_dt36.csv"))
    ent['진입시간'] = pd.to_datetime(ent['진입시간'])
    pos_of = {t: i for i, t in enumerate(price.index)}
    H = price['high'].values; L = price['low'].values; C = price['close'].values

    bottoms, means, tops = [], [], []
    no_ob = 0; used = 0
    for _, r in ent.iterrows():
        t = r['진입시간']
        if t not in pos_of:
            continue
        e = pos_of[t]
        if e < WINDOW:
            continue
        w0 = max(0, e - WINDOW + 1)
        entry = C[e]
        res = nearest_resistance(H[w0:e+1], L[w0:e+1], entry)
        used += 1
        if res is None:
            no_ob += 1
            continue
        bottoms.append(res['bottom_pct']); means.append(res['mean_pct']); tops.append(res['top_pct'])

    print(f"[표본] 측정 진입 {used}건 (요청 {len(ent)})")
    print(f"[구멍 노출] 진입가 위에 저항 OB가 '아예 없는' 진입: {no_ob}건 ({no_ob/max(used,1)*100:.1f}%)")
    print(f"           -> 이 경우 현 엔진은 Phase1 보호스탑이 없음(폭주 구멍).")
    print("\n[OB SL 거리 — 진입가 → 가장 가까운 위쪽 저항 OB] (저항 있는 진입만)")
    summ(bottoms, "OB bottom(저항 시작)")
    summ(means,   "OB mean  (저항 중앙)")
    summ(tops,    "OB top   (저항 끝)  ")
    print("\n[해석] 'OB SL 평균거리'로 보통 mean 또는 top을 씀. 위 ROE 값이 사장님 기억(500bp=5%)과")
    print("       맞는지 확인. 그리고 이 분포가 폭주구멍 Phase1 스탑폭 결정의 데이터 근거가 됨.")
    # 저장
    out = pd.DataFrame({'bottom_pct': bottoms, 'mean_pct': means, 'top_pct': tops})
    out.to_csv(os.path.join(WORK_DIR, "OB_SL_distances.csv"), index=False, encoding='utf-8-sig')
    print("\n[저장] OB_SL_distances.csv (진입별 거리 전체)")


if __name__ == "__main__":
    main()
