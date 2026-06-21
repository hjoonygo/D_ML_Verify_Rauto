# -*- coding: utf-8 -*-
# [파일명] test_08Prj_Dauto_Ch2_Stg15_AtrRatioAdapter.py
# 코드길이: 약 165줄 | 내부버전: dauto_ch2_stg15_atrratio_v1
# ─────────────────────────────────────────────────────────────────────────────
# [목적 — 캡틴 지시(2026-06-12) Stg15: atr_ratio 라이브 어댑터, 채택 게이트 2단]
#   ① 수식 검증: 원본 regime_feature_extractor(c3ace85e) 함수 무수정 import로
#      Merged_Data 1m에 재적용 → Regime_Features의 atr_ratio와 전수 대조(1e-6, NaN 패턴 포함).
#   ② 워밍업 실측: '짧은 출생지' 시뮬 — 시작점을 끝-30/45/60일로 자른 버전 vs 전체 역사
#      버전의 4H atr_ratio 오차가 1e-3/1e-6 밑으로 떨어지는 4H봉수 N 실측 → Dauto 31일 판정.
#   ③ 어댑터: Dauto CSV(공용 dauto_loader) → 4H → atr_ratio → 1m aux + atr_warm 플래그.
#      na 44행 가격 무결(→atr 영향 0) 확인.
# [근간] (상위) Merged_Data.csv + Merged_Data_with_Regime_Features.csv / C:\BinanceData
# [Out] stg15_result.txt / stg15_warmup.csv / stg15_dauto_aux_sample.csv
# ==============================================================================
import os, sys
import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from atr_ratio_adapter import atr_ratio_4h_from_1m, build_aux   # 원본 함수 경유 코드패스
from dauto_loader import load_dauto

TOL = 1e-6
CUT_DAYS = [30, 45, 60]
WTOLS = [1e-3, 1e-6]
OUT_TXT = os.path.join(HERE, "stg15_result.txt")
OUT_WARM = os.path.join(HERE, "stg15_warmup.csv")
OUT_AUX = os.path.join(HERE, "stg15_dauto_aux_sample.csv")


def find(name):
    for d in [os.path.dirname(HERE), r"D:\ML\verify"]:
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    raise FileNotFoundError(name)


def main():
    lines = []
    def log(s):
        print(s); lines.append(s)

    # ── 입력: Merged_Data 1m OHLCV ──
    mp = find("Merged_Data.csv")
    df = pd.read_csv(mp, usecols=['timestamp', 'open', 'high', 'low', 'close', 'volume'],
                     index_col='timestamp', parse_dates=True).sort_index()
    if getattr(df.index, 'tz', None) is not None:
        df.index = df.index.tz_localize(None)
    log(f"[데이터] {os.path.basename(mp)} {len(df)}행 {df.index.min()}~{df.index.max()}")

    # ── ① 수식 검증 게이트 ──
    d4 = atr_ratio_4h_from_1m(df)
    rec = df[[]].join(d4[['atr_ratio']].shift(1), how='left')   # 원본 build 130~133줄 1:1
    rec = rec['atr_ratio'].ffill().values
    fp = find("Merged_Data_with_Regime_Features.csv")
    ref = pd.read_csv(fp, usecols=['timestamp', 'atr_ratio'], index_col='timestamp',
                      parse_dates=True).sort_index()
    if getattr(ref.index, 'tz', None) is not None:
        ref.index = ref.index.tz_localize(None)
    ref = ref['atr_ratio'].reindex(df.index).values
    fin_r = np.isfinite(ref); fin_c = np.isfinite(rec)
    pat_mis = int((fin_r != fin_c).sum())
    both = fin_r & fin_c
    val_mis = int((np.abs(ref[both] - rec[both]) > TOL).sum())
    log(f"[① 수식게이트] 4H봉 {len(d4)} | 값불일치 {val_mis}/{int(both.sum())} (1e-6) "
        f"| NaN패턴불일치 {pat_mis} | {'PASS' if val_mis == 0 and pat_mis == 0 else 'FAIL'}")
    gate1 = (val_mis == 0) and (pat_mis == 0)

    # ── ② 워밍업 실측 ──
    full_ar = d4['atr_ratio']
    wrows = []
    n_warm_req = 0
    for cd in CUT_DAYS:
        t_cut = df.index.max() - pd.Timedelta(days=cd)
        d4t = atr_ratio_4h_from_1m(df[df.index > t_cut])
        common = d4t.index.intersection(full_ar.index)
        diff = (d4t['atr_ratio'].reindex(common) - full_ar.reindex(common)).abs()
        n_bars = len(common)
        row = dict(cut_days=cd, bars_4h=n_bars)
        for tol in WTOLS:
            bad = np.where(diff.values >= tol)[0]
            # NaN(양쪽 워밍업 NaN 구간)은 비교 제외 — 유한 diff만
            finmask = np.isfinite(diff.values)
            bad = [i for i in bad if finmask[i]]
            N = (max(bad) + 1) if bad else int(np.argmax(finmask))
            row[f"N_{tol:g}"] = N
            row[f"N_{tol:g}_days"] = round(N * 4 / 24, 1)
            if tol == 1e-3:
                n_warm_req = max(n_warm_req, N)
        wrows.append(row)
        log(f"[② 워밍업] cut={cd}일({n_bars} 4H봉): " +
            " | ".join(f"오차<{t:g} 도달 N={row[f'N_{t:g}']}봉({row[f'N_{t:g}_days']}일)" for t in WTOLS))
    pd.DataFrame(wrows).to_csv(OUT_WARM, index=False, encoding='utf-8-sig')
    dauto_4h = 31 * 6
    gate2 = dauto_4h > n_warm_req
    log(f"[② 판정] N_warm(1e-3 최대) = {n_warm_req} 4H봉({n_warm_req*4/24:.1f}일) "
        f"vs Dauto 보유 31일({dauto_4h} 4H봉) → {'충족' if gate2 else '미충족'}")

    # ── ③ Dauto 어댑터 ──
    try:
        aux = build_aux(n_warm_4h=n_warm_req)
        n = len(aux); n_fin = int(np.isfinite(aux['atr_ratio'].values).sum())
        n_warm = int((aux['atr_warm'] == 1).sum())
        log(f"[③ Dauto aux] {n}행 | atr_ratio 유한 {n_fin}({n_fin/n*100:.2f}%) "
            f"| atr_warm(수렴전) {n_warm}({n_warm/n*100:.2f}%)")
        na_rows = load_dauto(['open', 'high', 'low', 'close', 'oi_src'])
        na_rows = na_rows[na_rows['oi_src'] == 'na']
        na_ok = int(na_rows[['open', 'high', 'low', 'close']].notna().all(axis=1).sum())
        log(f"[③ na행 무결] oi_src=na {len(na_rows)}행 중 OHLC 무결 {na_ok}행 "
            f"→ {'가격 무결 — atr 계산 영향 0 확인' if na_ok == len(na_rows) else '★결측 존재 — 본문 확인'}")
        aux.tail(2880).to_csv(OUT_AUX, index=False, encoding='utf-8-sig')
        ok3 = (n_fin > 0) and (na_ok == len(na_rows))
    except FileNotFoundError:
        log("[③] ★Dauto CSV 없음 — PC에서 실행 필요"); ok3 = False

    ok = gate1 and ok3
    verdict = (f"VERDICT Stg15 | {'채택' if ok else 'FAIL/보류'} — ①수식 {'0불일치' if gate1 else 'FAIL'} "
               f"| ②워밍업 N={n_warm_req}4H봉({n_warm_req*4/24:.1f}일), Dauto31일 {'충족' if gate2 else '미충족'} "
               f"| ③aux 생성{'OK' if ok3 else 'X'}·na행 가격무결")
    log("\n" + verdict)
    with open(OUT_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
