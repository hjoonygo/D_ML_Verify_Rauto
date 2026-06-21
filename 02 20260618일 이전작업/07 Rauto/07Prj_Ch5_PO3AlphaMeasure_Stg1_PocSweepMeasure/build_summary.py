# -*- coding: utf-8 -*-
# [파일명] build_summary.py
# 코드길이: 약 180줄 | 내부버전: build_summary_v1
# [목적] M1/M2 측정 CSV → 레짐×방향×연도 집계 + 엣지(조건부-baseline) + 순열검정 p(seed=42).
#        summary_regime_matrix.csv 와 analysis_PO3_alpha.txt(출처/명칭/신뢰도/알파여부) 생성.
# [lookahead] 측정 단계 산출물 가공만(원데이터 미접근). shift(-) 미사용.
import os, sys, time
import numpy as np
import pandas as pd
import po3_common as pc

RNG = np.random.default_rng(42)   # 순열검정 재현(seed=42)
MIN_N = 50                        # 표본부족 임계
B_PERM = 2000                     # 순열 반복(가벼운 검정 — 본격은 Stage 6)


def perm_p(a, b, B=B_PERM):
    """두 이진배열 비율차의 양측 순열 p. a,b: 0/1 np.array."""
    a = np.asarray(a, float); b = np.asarray(b, float)
    n1 = len(a)
    if n1 < MIN_N or len(b) < MIN_N:
        return np.nan
    obs = abs(a.mean() - b.mean())
    pool = np.concatenate([a, b])
    cnt = 0
    for _ in range(B):
        RNG.shuffle(pool)
        if abs(pool[:n1].mean() - pool[n1:].mean()) >= obs:
            cnt += 1
    return round((cnt + 1) / (B + 1), 4)


def m1_summary(m1, kinds):
    rows = []
    for kind, col in kinds:
        for (reg, d, H), g0 in m1.groupby([col, "dir", "H"]):
            base = g0["reverted"].mean()          # baseline = 버킷무관 전체 회귀율
            # 연도 ALL + 연도별
            for ylab, gy in [("ALL", g0)] + [(int(y), g0[g0.year == y]) for y in sorted(g0.year.unique())]:
                for bkt, gb in gy.groupby("dist_bucket"):
                    n = len(gb)
                    rows.append(["M1", kind, reg, d, bkt, "", H, ylab, n,
                                 round(gb["reverted"].mean(), 4), round(base, 4),
                                 round(gb["reverted"].mean() - base, 4),
                                 round(gb["mfe_atr"].mean(), 3), round(gb["mae_atr"].mean(), 3), np.nan])
    cols = ["module", "regime_kind", "regime", "dir", "dist_bucket", "R", "H", "year",
            "n", "cond_rate", "baseline", "edge", "mfe_atr", "mae_atr", "perm_p"]
    df = pd.DataFrame(rows, columns=cols)
    # H1 핵심검정: ALL연도, 근거리(<=0.5) vs 원거리(>=2) 회귀율 차 — 자석이면 양(+)
    for kind, col in kinds:
        for (reg, d, H), g0 in m1.groupby([col, "dir", "H"]):
            near = g0[g0.dist_bucket == "<=0.5"]["reverted"].to_numpy()
            far = g0[g0.dist_bucket == ">=2"]["reverted"].to_numpy()
            p = perm_p(near, far)
            m = (df.module == "M1") & (df.regime_kind == kind) & (df.regime == reg) & \
                (df.dir == d) & (df.H == H) & (df.year == "ALL") & (df.dist_bucket == "<=0.5")
            df.loc[m, "perm_p"] = p
    return df


def m2_summary(ev, base, kinds):
    rows = []
    # baseline 키별 비율 사전계산
    for kind, col in kinds:
        bkey = base.groupby([col, "dir", "R", "H"]).agg(bn=("n", "sum"), br=("reach_n", "sum"),
                                                        bf=("sum_fwd", "sum")).reset_index()
        bkey["brate"] = bkey["br"] / bkey["bn"]
        bmap = {(r[col], r["dir"], r["R"], r["H"]): (r["brate"], r["br"], r["bn"]) for _, r in bkey.iterrows()}
        for (reg, d, R, H), g0 in ev.groupby([col, "dir", "R", "H"]):
            brate, br, bn = bmap.get((reg, d, R, H), (np.nan, 0, 0))
            for ylab, gy in [("ALL", g0)] + [(int(y), g0[g0.year == y]) for y in sorted(g0.year.unique())]:
                n = len(gy)
                rate = gy["reversed"].mean()
                rows.append(["M2", kind, reg, d, "", R, H, ylab, n,
                             round(rate, 4), round(brate, 4) if np.isfinite(brate) else np.nan,
                             round(rate - brate, 4) if np.isfinite(brate) else np.nan,
                             round(gy["fwd_ret"].mean(), 6), round(gy["fwd_ret_cost"].mean(), 6), np.nan])
    cols = ["module", "regime_kind", "regime", "dir", "dist_bucket", "R", "H", "year",
            "n", "cond_rate", "baseline", "edge", "fwd_ret", "fwd_ret_cost", "perm_p"]
    df = pd.DataFrame(rows, columns=cols)
    # H2 핵심검정: 스윕 reversed vs baseline reach (ALL연도)
    for kind, col in kinds:
        bkey = base.groupby([col, "dir", "R", "H"]).agg(bn=("n", "sum"), br=("reach_n", "sum")).reset_index()
        bmap = {(r[col], r["dir"], r["R"], r["H"]): (int(r["br"]), int(r["bn"])) for _, r in bkey.iterrows()}
        for (reg, d, R, H), g0 in ev.groupby([col, "dir", "R", "H"]):
            ev_arr = g0["reversed"].to_numpy()
            br, bn = bmap.get((reg, d, R, H), (0, 0))
            base_arr = np.concatenate([np.ones(br), np.zeros(max(bn - br, 0))]) if bn else np.array([])
            p = perm_p(ev_arr, base_arr)
            m = (df.module == "M2") & (df.regime_kind == kind) & (df.regime == reg) & \
                (df.dir == d) & (df.R == R) & (df.H == H) & (df.year == "ALL")
            df.loc[m, "perm_p"] = p
    return df


def main():
    t0 = time.time()
    od = pc.ensure_out()
    m1 = pd.read_csv(os.path.join(od, "measure_M1_poc_revert.csv"), encoding="utf-8-sig")
    ev = pd.read_csv(os.path.join(od, "measure_M2_sweep_reversal.csv"), encoding="utf-8-sig")
    base = pd.read_csv(os.path.join(od, "measure_M2_baseline.csv"), encoding="utf-8-sig")
    # 레짐 두 체계: smc8(사후) / feat8(실시간). M1엔 regime/regime_feat 컬럼.
    kinds_m1 = [("smc8", "regime"), ("feat8", "regime_feat")]
    s1 = m1_summary(m1, kinds_m1)
    s2 = m2_summary(ev, base, kinds_m1)
    out = pd.concat([s1, s2], ignore_index=True)
    fp = os.path.join(od, "summary_regime_matrix.csv")
    out.to_csv(fp, index=False, encoding="utf-8-sig")
    print(f"[SUMMARY] {len(out):,}행 저장 {fp} | {time.time()-t0:.1f}s")
    # 콘솔 헤드라인
    print("\n[M1 헤드라인 — smc8, dir=above, H=60, ALL]")
    h1 = s1[(s1.regime_kind == "smc8") & (s1.dir == "above") & (s1.H == 60) & (s1.year == "ALL")]
    print(h1[["regime", "dist_bucket", "n", "cond_rate", "baseline", "edge", "perm_p"]].to_string(index=False))
    print("\n[M2 헤드라인 — smc8, R=1.5, H=60, ALL]")
    h2 = s2[(s2.regime_kind == "smc8") & (s2.R == 1.5) & (s2.H == 60) & (s2.year == "ALL")]
    print(h2[["regime", "dir", "n", "cond_rate", "baseline", "edge", "fwd_ret_cost", "perm_p"]].to_string(index=False))


if __name__ == "__main__":
    main()
