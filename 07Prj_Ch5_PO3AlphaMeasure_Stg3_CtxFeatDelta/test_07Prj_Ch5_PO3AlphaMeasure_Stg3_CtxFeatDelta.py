# -*- coding: utf-8 -*-
# [test_07Prj_Ch5_PO3AlphaMeasure_Stg3_CtxFeatDelta.py]
# =============================================================================
# [목적] POC 컨텍스트피처 증분검증 — Stage0(베이스라인 동결) + Stage1(델타 1줄, 없으면 중단).
#   지침: 00WorkHstr\202606141120.txt (07Prj_Ch5_..._Stg2_CtxFeatIncrPlan).
#   원칙: POC 컨텍스트피처는 OPVnN 베이스라인 대비 '증분'으로만 검증(단독 금지).
#
# [Stage0] OPVnN 명세 동결 — 베이스라인 = OPVnN 스윕 best 1행(무수정 동결, 이후 비교기준 불변).
#   OPV0.25 / n(NMULT)0.6 / N(N_BOOST)1.0 / EXP1.75 / ret+900.0% / MDD-19.74% / CPCVp25 2.7156.
#   (OPV·n·N은 CLAUDE.md §9 확정알파와 일치. EXP/수익은 업트렌드숏컷 미포함 순수 사이징본.)
#
# [Stage1] 델타 1줄 — 베이스라인은 |dev|>=0.25 단일임계로 oppo(POC서 멀어지는 모멘텀)거래를 n=0.6배 축소.
#   PO3-H1(analysis_PO3_alpha.txt): POC거리 관계는 비대칭 — 0.5~2ATR 강회귀 / >=2ATR 연속(역전).
#   → 단일임계가 놓치는 '버킷 비대칭'이 7h-거래 맥락에도 존재하면 증분신호(델타)가 있다.
#   델타 정의(1줄): meanR(oppo, >=2ATR) - meanR(oppo, 0.5~2ATR).
#     · PO3가 옳다면 >=2 oppo(연속성=수익) > 0.5~2 oppo(회귀에 역행=손실) → 델타>0.
#       이때 베이스라인의 '전구간 동일 0.6배 축소'는 >=2 구간서 수익을 깎는 실수 → 증분여지 존재.
#     · 델타가 노이즈(부트스트랩 CI가 0 포함)면 증분신호 없음 → Stage1 중단(Stage2~3 진행 금지).
#
# [입력] 근간(이 폴더에 동봉): devledger.csv(베이스라인 per-trade dev/R, 265줄) · best.csv(베이스라인 동결행).
# [출력] HERE\<NAME>_stage1_buckets.csv (버킷×방향 분해표) · 콘솔 델타 1줄.
#        분석/INDEX는 check_*.py가 00WorkHstr로.
# [무수정] 검증엔진(§8) 일절 import/수정 없음. 베이스라인 산출물(CSV)만 읽는 사후 측정.
# =============================================================================
import os
import numpy as np, pandas as pd

NAME = "07Prj_Ch5_PO3AlphaMeasure_Stg3_CtxFeatDelta"
HERE = os.path.dirname(os.path.abspath(__file__))
DEV = os.path.join(HERE, "devledger.csv")          # 근간(동봉)
BEST = os.path.join(HERE, "best.csv")              # 근간(동봉)
OUT = os.path.join(HERE, f"{NAME}_stage1_buckets.csv")

# 버킷 경계(PO3 정의 동일): <=0.5 / 0.5~1 / 1~2 / >=2 ATR
EDGES = [0.0, 0.5, 1.0, 2.0, np.inf]
LABELS = ["<=0.5", "0.5~1", "1~2", ">=2"]
OPV_GATE = 0.25                                     # 베이스라인 단일임계
BOOT_B = 5000
SEED = 42


def boot_ci(x, B=BOOT_B, seed=SEED):
    # 평균의 부트스트랩 95% CI (소표본 정직성용)
    if len(x) < 2:
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(x), size=(B, len(x)))
    means = x[idx].mean(axis=1)
    return (float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5)))


def boot_delta_ci(a, b, B=BOOT_B, seed=SEED):
    # delta = mean(a) - mean(b) 의 부트스트랩 CI (a,b 독립 재표집)
    if len(a) < 2 or len(b) < 2:
        return (np.nan, np.nan, np.nan)
    rng = np.random.default_rng(seed)
    ia = rng.integers(0, len(a), size=(B, len(a)))
    ib = rng.integers(0, len(b), size=(B, len(b)))
    d = a[ia].mean(axis=1) - b[ib].mean(axis=1)
    return (float(d.mean()), float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5)))


def main():
    print(f"[{NAME}] POC 컨텍스트피처 증분검증 — Stage0 동결 + Stage1 델타")

    # ── Stage0: 베이스라인 동결행 확인(무수정 echo) ──
    b = pd.read_csv(BEST)
    base = b.iloc[0]
    print("\n[Stage0] OPVnN 베이스라인 동결(best.csv 1행):")
    print(f"  OPV{base['OPV']} n{base['n']} N{base['N']} EXP{base['EXP']} "
          f"ret{base['ret']*100:.1f}% MDD{base['mdd']*100:.2f}% CPCVp25 {base['cpcv_p25']}")

    # ── Stage1 입력: devledger ──
    d = pd.read_csv(DEV)
    n_all = len(d)
    valid = d['dev'].notna().values
    dev = d['dev'].values.astype(float)
    R = d['R'].values.astype(float)
    side = d['side'].values.astype(float)
    rdir = pd.to_numeric(d['regime_dir'], errors='coerce').values.astype(float)  # = -sign(dev)
    adev = np.abs(dev)
    same = valid & (side == rdir)
    oppo = valid & (side == -rdir)
    print(f"\n[Stage1] devledger {n_all}건 | dev유효 {int(valid.sum())} | "
          f"same {int(same.sum())} / oppo {int(oppo.sum())} (POC회귀방향 대비)")

    # ── 버킷×방향 분해표 ──
    bkt = np.full(n_all, -1, dtype=int)
    bkt[valid] = np.digitize(adev[valid], EDGES, right=False) - 1
    bkt[valid] = np.clip(bkt[valid], 0, len(LABELS) - 1)

    rows = []
    for grp_name, mask in [("all", valid), ("same", same), ("oppo", oppo)]:
        for k, lab in enumerate(LABELS):
            m = mask & (bkt == k)
            r = R[m]
            ci = boot_ci(r)
            rows.append(dict(group=grp_name, bucket=lab, n=int(m.sum()),
                             meanR=round(float(r.mean()), 6) if len(r) else np.nan,
                             medR=round(float(np.median(r)), 6) if len(r) else np.nan,
                             winrate=round(float((r > 0).mean()), 4) if len(r) else np.nan,
                             sumR=round(float(r.sum()), 6) if len(r) else 0.0,
                             ci_lo=round(ci[0], 6), ci_hi=round(ci[1], 6)))
    tab = pd.DataFrame(rows)
    tab.to_csv(OUT, index=False, encoding='utf-8-sig')
    print(f"\n[분해표] {os.path.basename(OUT)} 저장")
    with pd.option_context('display.width', 140, 'display.max_columns', 20):
        print(tab.to_string(index=False))

    # ── 델타 1줄: oppo 거리 비대칭 (>=2  vs  0.5~2) ──
    far = oppo & (adev >= 2.0)
    mod = oppo & (adev >= 0.5) & (adev < 2.0)
    r_far, r_mod = R[far], R[mod]
    dmean, dlo, dhi = boot_delta_ci(r_far, r_mod)
    print("\n" + "=" * 70)
    print("[DELTA 1줄] meanR(oppo,>=2ATR) - meanR(oppo,0.5~2ATR)")
    print(f"  oppo>=2 : n={int(far.sum())}  meanR={r_far.mean() if len(r_far) else float('nan'):+.5f}")
    print(f"  oppo0.5~2: n={int(mod.sum())}  meanR={r_mod.mean() if len(r_mod) else float('nan'):+.5f}")
    print(f"  DELTA = {dmean:+.5f}  (부트스트랩95% CI [{dlo:+.5f}, {dhi:+.5f}], B={BOOT_B})")
    if np.isnan(dmean):
        verdict = "표본부족 — 판단보류(Stage1 보류, 캡틴 확인 필요)"
    elif dlo > 0:
        verdict = "델타 양수·CI>0 → 증분신호 존재 → Stage2~3 진행 권고"
    elif dhi < 0:
        verdict = "델타 음수·CI<0 → PO3방향 역 → 단일임계가 오히려 보수적 적정, 증분 미발견 → 중단 권고"
    else:
        verdict = "CI가 0 포함 → 증분신호 노이즈수준 → Stage1 중단(Stage2~3 진행 금지)"
    print(f"  판정: {verdict}")
    print("=" * 70)


if __name__ == "__main__":
    main()
