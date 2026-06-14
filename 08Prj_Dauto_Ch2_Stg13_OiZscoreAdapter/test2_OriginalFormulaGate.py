# -*- coding: utf-8 -*-
# [파일명] test2_OriginalFormulaGate.py (Stg13 v2 — 경로B 폐기, 원본 기준)
# 코드길이: 약 110줄 | 내부버전: dauto_ch2_stg13_origgate_v1
# ─────────────────────────────────────────────────────────────────────────────
# [목적 — 캡틴 지시(2026-06-12) 2)항 채택 게이트]
#   원본 compute_oi_derived_features.py(33ecde59, 동봉)의 compute_zscore_rolling을
#   '무수정 import'로 Merged_Data.csv 원시 oi_sum에 적용 → 기존 oi_zscore_24h 컬럼과
#   전수 대조(허용오차 1e-6). NaN 위치 포함 일치율 보고. 불일치 0이어야 채택.
# [참고 대조] 경로B 역공학 유일해(= z 전체 shift(1)·min_periods=720·±10클립)도 같은 잣대로
#   재출력 — 게이트 실패 시 원인 분리용(원본 vs 실제컬럼의 생성계보 차이 진단).
# [Out] stg13_origgate_result.txt
# ==============================================================================
import os, sys
import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import compute_oi_derived_features as ORIG     # 원본(33ecde59) 무수정 import
from oi_zscore_adapter import compute_oi_zscore  # 경로B 코드패스(참고 대조)

TOL = 1e-6
OUT_TXT = os.path.join(HERE, "stg13_origgate_result.txt")


def compare(ref, z, tag, lines):
    fin_r = np.isfinite(ref); fin_z = np.isfinite(z)
    pat_mis = int((fin_r != fin_z).sum())
    both = fin_r & fin_z
    val_mis = int((np.abs(ref[both] - z[both]) > TOL).sum())
    n_ref = int(fin_r.sum())
    agree = int(both.sum()) - val_mis + int((~fin_r & ~fin_z).sum())
    total = len(ref)
    lines.append(f"[{tag}] 값불일치 {val_mis}/{int(both.sum())} | NaN패턴불일치 {pat_mis} "
                 f"| 전체일치율(NaN위치 포함) {agree/total*100:.4f}% "
                 f"| 첫 유한행 ref={int(np.argmax(fin_r))} vs cand={int(np.argmax(fin_z)) if fin_z.any() else -1}")
    if val_mis:
        idx = np.where(both & (np.abs(ref - z) > TOL))[0][:5]
        for i in idx:
            lines.append(f"    예시 행{i}: ref={ref[i]:.6f} cand={z[i]:.6f} diff={abs(ref[i]-z[i]):.6f}")
    return val_mis, pat_mis


def main():
    lines = []
    def log(s):
        print(s); lines.append(s)

    for d in [os.path.dirname(HERE), r"D:\ML\verify"]:
        p = os.path.join(d, "Merged_Data.csv")
        if os.path.exists(p):
            break
    df = pd.read_csv(p, usecols=['oi_sum', 'oi_zscore_24h'])
    ref = df['oi_zscore_24h'].astype(float).values
    log(f"[데이터] Merged_Data.csv {len(df)}행 | 기준 유한 {int(np.isfinite(ref).sum())}행")
    log(f"[원본] compute_oi_derived_features.py 33ecde59 | 564줄 | 238~239줄 "
        f"rolling(min_periods=window).mean/.std(ddof기본).shift(1) | 클립 ±{ORIG.Z_CLIP_LIMIT} | 창 {ORIG.WINDOW_24H}")

    # ── 게이트: 원본 함수 무수정 적용 ──
    z_orig = ORIG.compute_zscore_rolling(df['oi_sum'].astype(float), window=ORIG.WINDOW_24H).values
    vm_o, pm_o = compare(ref, z_orig, "게이트: 원본 v2 수식(무수정 import)", lines)

    # ── 참고: 경로B 역공학 유일해 ──
    z_revb = compute_oi_zscore(df['oi_sum'].astype(float), win=1440, ddof=1, minp=720,
                               shift=1, clip=10.0).values
    vm_b, pm_b = compare(ref, z_revb, "참고: 경로B 유일해(z전체shift·mp720·클립10)", lines)

    ok = (vm_o == 0) and (pm_o == 0)
    if ok:
        verdict = "VERDICT Stg13v2 | 채택 — 원본 v2 수식이 기준컬럼과 전수일치(불일치 0)"
    else:
        verdict = (f"VERDICT Stg13v2 | 게이트 FAIL — 원본 v2 수식 ≠ 기준컬럼(값불일치 {vm_o}·패턴불일치 {pm_o}). "
                   f"경로B 유일해는 값불일치 {vm_b}·패턴불일치 {pm_b} → 기준컬럼의 실제 생성계보는 원본 v2가 아닌 "
                   f"별도 변형(z전체shift·mp720)으로 판정. 채택 보류·캡틴 보고")
    log("\n" + verdict)
    with open(OUT_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
