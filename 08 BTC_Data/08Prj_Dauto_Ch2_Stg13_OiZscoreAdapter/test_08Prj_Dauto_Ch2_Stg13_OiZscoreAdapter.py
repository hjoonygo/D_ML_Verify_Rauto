# -*- coding: utf-8 -*-
# [파일명] test_08Prj_Dauto_Ch2_Stg13_OiZscoreAdapter.py
# 코드길이: 약 185줄 | 내부버전: dauto_ch2_stg13_oizadapter_v1
# ─────────────────────────────────────────────────────────────────────────────
# [목적 — 캡틴 경로B 승인(2026-06-12): 역공학-검증]
#   A. Merged_Data.csv의 원시 OI(oi_sum/oi_value)와 기준컬럼 oi_zscore_24h로 후보 수식
#      격자(창×모집단×ddof×min_periods×시프트) 전수 대조. 허용오차 1e-6.
#      '일치 수식이 정확히 1개'일 때만 채택 — 0개/복수면 중단·보고.
#   B. 채택 시: oi_zscore_adapter.py(동봉)의 동일 코드패스로
#      ① Merged 원시 OI 재계산=기준컬럼 재현(겹침구간 0행이라 이것이 대체검증 — 본문 명시)
#      ② Dauto CSV(C:\BinanceData) → z 계산. oi_src=hist/na 는 NaN 전파(캡틴 확정:
#         진입필터 통과 관성 유지). 커버리지 보고.
# [근간] (상위) Merged_Data.csv (1m, 2023-05-01~2026-04-30) / C:\BinanceData\BTCUSDT_1m_*.csv
# [Out] stg13_grid.csv / stg13_result.txt / (채택 시) stg13_dauto_aux_sample.csv
# ==============================================================================
import os, sys, glob, itertools
import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from oi_zscore_adapter import compute_oi_zscore   # noqa: E402  (동일 코드패스 검증용)

TOL = 1e-6
DAUTO_DIR = r"C:\BinanceData"
OUT_TXT = os.path.join(HERE, "stg13_result.txt")
OUT_GRID = os.path.join(HERE, "stg13_grid.csv")
OUT_AUX = os.path.join(HERE, "stg13_dauto_aux_sample.csv")


def find_merged():
    for d in [os.path.dirname(HERE), r"D:\ML\verify"]:
        p = os.path.join(d, "Merged_Data.csv")
        if os.path.exists(p):
            return p
    raise FileNotFoundError("Merged_Data.csv")


def main():
    lines = []
    def log(s):
        print(s); lines.append(s)

    mp_path = find_merged()
    df = pd.read_csv(mp_path, usecols=['timestamp', 'oi_sum', 'oi_value', 'oi_zscore_24h'])
    n = len(df)
    ref = df['oi_zscore_24h'].astype(float).values
    n_ref = int(np.isfinite(ref).sum())
    log(f"[데이터] {os.path.basename(mp_path)} {n}행 | 기간 {df.timestamp.iloc[0]}~{df.timestamp.iloc[-1]} "
        f"| 기준 oi_zscore_24h 유한 {n_ref}행({n_ref/n*100:.2f}%)")

    # A. 격자 전수 대조 ────────────────────────────────────────────────
    # clip 축 추가 근거(1차 격자 진단): 최우수 후보 불일치 22행 전부 기준값=-10.0 정밀일치
    #   → 원 파이프라인의 ±10 클립으로 판정.
    # min_periods 축 {1,720,win} 근거(2차 진단): 기준컬럼 NaN이 정확히 앞 720행(12h) —
    #   워밍업 관측가능 단서. 일치 기준을 '값 불일치 0 + NaN 패턴 완전일치'로 엄격화(완화 아님).
    grid_rows, passes = [], []
    fin_ref = np.isfinite(ref)
    for src, win, ddof, mp, sh, cl in itertools.product(
            ['oi_sum', 'oi_value'], [1440, 1441], [0, 1], ['1', '720', 'win'], [0, 1], [None, 10.0]):
        x = df[src].astype(float)
        if sh:
            x = x.shift(1)
        minp = {'1': 1, '720': 720, 'win': win}[mp]
        mu = x.rolling(win, min_periods=minp).mean()
        sd = x.rolling(win, min_periods=minp).std(ddof=ddof)
        z = (x - mu) / sd
        if cl is not None:
            z = z.clip(-cl, cl)
        z = z.values
        pat_mis = int((np.isfinite(z) != fin_ref).sum())
        both = np.isfinite(ref) & np.isfinite(z)
        n_both = int(both.sum())
        mis = int((np.abs(ref[both] - z[both]) > TOL).sum()) if n_both else -1
        cover = n_both / n_ref * 100 if n_ref else 0.0
        ok = (mis == 0) and (pat_mis == 0)
        tag = f"{src}|w{win}|ddof{ddof}|mp{mp}|sh{sh}|cl{cl}"
        grid_rows.append(dict(candidate=tag, n_both=n_both, mismatch=mis, pattern_mis=pat_mis,
                              cover_pct=round(cover, 3), match=ok))
        if ok:
            passes.append((tag, dict(src=src, win=win, ddof=ddof, minp=minp, shift=sh, clip=cl)))
    pd.DataFrame(grid_rows).to_csv(OUT_GRID, index=False, encoding='utf-8-sig')
    log(f"\n[A 격자] 후보 {len(grid_rows)}개 | 일치(값불일치0+NaN패턴 완전일치) {len(passes)}개")
    for g in sorted(grid_rows, key=lambda r: ((r['mismatch'] if r['mismatch'] >= 0 else 10**9)
                                              + r['pattern_mis']))[:6]:
        log(f"  {g['candidate']:>38} | 공통 {g['n_both']} | 값불일치 {g['mismatch']} | 패턴불일치 {g['pattern_mis']}")

    if len(passes) != 1:
        verdict = (f"VERDICT Stg13 | 중단 — 일치 수식 {len(passes)}개(채택조건=정확히 1개). "
                   f"격자 전수표 stg13_grid.csv 보고, 캡틴 판단 대기")
        log("\n" + verdict)
        with open(OUT_TXT, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return

    tag, P = passes[0]
    log(f"\n[채택 수식] {tag} → z = clip((x - mean_{P['win']}) / std_{P['win']}(ddof={P['ddof']}), ±{P['clip']}), "
        f"min_periods={P['minp']}, shift={P['shift']}, x={P['src']}")

    # B-① 어댑터 코드패스로 기준 재현 (겹침 0행 대체검증) ───────────────
    x = df[P['src']].astype(float)
    z_ad = compute_oi_zscore(x, win=P['win'], ddof=P['ddof'], minp=P['minp'],
                             shift=P['shift'], clip=P['clip']).values
    both = np.isfinite(ref) & np.isfinite(z_ad)
    mis = int((np.abs(ref[both] - z_ad[both]) > TOL).sum())
    log(f"[B-① 어댑터=기준 재현] 공통 {int(both.sum())}행 | 불일치 {mis} (허용오차 {TOL}) "
        f"| {'PASS' if mis == 0 else 'FAIL'}")
    log("  ※ Merged(~2026-04-30)와 Dauto(2026-05-12~) 겹침 0행 — 본 재현이 겹침검증의 대체(캡틴 보고).")

    # B-② Dauto CSV → aux (캡틴 v2 정책: live/hist 사용+oi_blunt 플래그, na만 NaN 전파) ──
    from oi_zscore_adapter import build_aux
    try:
        aux = build_aux(params=dict(win=P['win'], ddof=P['ddof'], minp=P['minp'],
                                    shift=P['shift'], clip=P['clip']))
        n_d = len(aux); n_fin = int(np.isfinite(aux['oi_zscore_24h'].values).sum())
        src_cnt = aux['oi_src'].value_counts().to_dict()
        n_blunt = int((aux['oi_blunt'] == 1).sum())
        log(f"[B-② Dauto aux] {n_d}행({aux.ts_utc.iloc[0]}~{aux.ts_utc.iloc[-1]}) | oi_src {src_cnt}")
        log(f"  z 유한 {n_fin}행({n_fin/n_d*100:.2f}%) | oi_blunt(hist 뭉툭화) {n_blunt}행({n_blunt/n_d*100:.2f}%) "
            f"| na만 NaN 전파(무덤필터 통과 관성)")
        aux.tail(2880).to_csv(OUT_AUX, index=False, encoding='utf-8-sig')   # 최근 2일 샘플
        ok_b2 = n_fin > 0
    except FileNotFoundError:
        log(f"[B-②] ★Dauto CSV 없음({DAUTO_DIR}) — PC에서 실행 필요")
        ok_b2 = False

    verdict = (f"VERDICT Stg13 | 채택 — 유일일치 {tag} | 기준재현 불일치 {mis}/{int(both.sum())} "
               f"| Dauto aux {'생성OK' if ok_b2 else '미생성(데이터/커버 확인)'} | 겹침0행→재현검증 대체")
    log("\n" + verdict)
    with open(OUT_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
