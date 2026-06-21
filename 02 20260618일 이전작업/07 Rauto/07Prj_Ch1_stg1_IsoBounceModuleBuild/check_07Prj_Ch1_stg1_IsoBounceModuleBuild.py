# -*- coding: utf-8 -*-
# [파일명] check_07Prj_Ch1_stg1_IsoBounceModuleBuild.py
# 코드길이: 약 145줄 | 내부버전: 07Prj_Ch1_stg1_check_v1 | 로직 전체 출력(축약/생략 없음)
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일] stg1 IsoBounceModuleBuild 오염검사 8시나리오 + 결과 전량 파일로.
#   ★분석txt·INDEX는 D:\ML\verify\00WorkHstr\로. 결과 csv는 stg1 하위폴더(test가 이미 생성).
#   ★stg1은 모듈 자체 검증 단계라 데이터·엔진 의존성 없음(합성 거래 전용).
#   ★stg2부터 stg1 원장(292거래) 적용 + 실데이터 검증으로 확장.
#
# [In] code 폴더의 isolated_bounce_simulator.py + test의 결과 csv 5종 + .stg1_metric
# [Out] D:\ML\verify\00WorkHstr\(분단위시간).txt + INDEX 한 줄. 콘솔 요약.
#
# [8시나리오 점검 항목]
#   S1 필수파일 7종 비공백   (모듈 + csv 5종 + .stg1_metric)
#   S2 모듈 자가검증 PASS    (selfcheck_ok=True)
#   S3 경계값 8/8 정확 일치  (Lookahead/오차 없음)
#   S4 4모드 정합성          (M0=R / M1=R*0.25 / M2=R*0.975 / M3 분기형)
#   S5 미래참조 가드          (모듈·test에 shift(-)/.shift(- 패턴 없음)
#   S6 CONFIG_DEFAULT=격리튕김 (exposure=0.975, tail=-0.075, liq=-0.0719, enable=True)
#   S7 데모 청산 건수 정합    (R≤-0.0719인 거래만 청산, R>−0.0719는 청산 안 됨)
#   S8 ALPHA_PROVENANCE 메타  (source/concept/inspired_by/evidence_event 키 존재)
# ==============================================================================
import os, sys, datetime
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
HSTR = os.path.join(PARENT, "00WorkHstr")
sys.path.insert(0, HERE)

NAME = "07Prj_Ch1_stg1_IsoBounceModuleBuild"
REQ_FILES = [
    "isolated_bounce_simulator.py",
    "stg1_module_selfcheck.csv", "stg1_synthetic_grid.csv",
    "stg1_boundary_check.csv", "stg1_demo_apply.csv", "summary.csv",
    ".stg1_metric",
]


def read_metric():
    d = {}
    p = os.path.join(HERE, ".stg1_metric")
    if os.path.exists(p):
        for ln in open(p, encoding="utf-8"):
            if "=" in ln:
                k, v = ln.strip().split("=", 1)
                d[k] = v
    return d


def fnum(x, dflt=None):
    try:
        return float(x)
    except Exception:
        return dflt


def main():
    os.makedirs(HSTR, exist_ok=True)
    M = read_metric()
    res = []

    # S1 필수파일
    miss = [f for f in REQ_FILES if not (os.path.exists(os.path.join(HERE, f))
                                          and os.path.getsize(os.path.join(HERE, f)) > 0)]
    res.append(("S1 필수파일/비공백(7종)", len(miss) == 0, f"누락 {miss}" if miss else "7종 OK"))

    # S2 모듈 자가검증
    self_ok = (M.get("selfcheck_ok", "False") == "True")
    res.append(("S2 모듈 자가검증 PASS", self_ok, f"selfcheck_ok={M.get('selfcheck_ok','?')}"))

    # S3 경계값 정확 일치
    n_b = int(fnum(M.get("n_boundary_cases", 0)) or 0)
    n_m = int(fnum(M.get("n_boundary_match", 0)) or 0)
    boundary_ok = (n_b > 0 and n_b == n_m)
    res.append(("S3 경계값 일치(테일컷 분기)", boundary_ok, f"{n_m}/{n_b}"))

    # S4 4모드 정합성: synthetic_grid.csv를 다시 열어 핵심 셀 확인
    grid_ok = True
    grid_detail = ""
    grid_path = os.path.join(HERE, "stg1_synthetic_grid.csv")
    if os.path.exists(grid_path):
        g = pd.read_csv(grid_path)
        # M0: R=-0.05 → dW=-0.05 (1:1)
        m0_row = g[(g["mode"] == "M0_base") & (abs(g["R_input"] - (-0.05)) < 1e-6)]
        # M1: R=-0.05 → dW=-0.0125 (R*0.25)
        m1_row = g[(g["mode"] == "M1_cross_now") & (abs(g["R_input"] - (-0.05)) < 1e-6)]
        # M2: R=-0.05 → dW=-0.04875 (R*0.975, 테일컷 OFF)
        m2_row = g[(g["mode"] == "M2_iso_notail") & (abs(g["R_input"] - (-0.05)) < 1e-6)]
        # M3: R=-0.145 → dW=-0.075 (테일컷 발동)
        m3_row = g[(g["mode"] == "M3_iso_tailcut") & (abs(g["R_input"] - (-0.145)) < 1e-6)]
        checks = [
            (len(m0_row) and abs(m0_row.iloc[0]["dW_output"] - (-0.05)) < 1e-6, "M0(-5%→-5%)"),
            (len(m1_row) and abs(m1_row.iloc[0]["dW_output"] - (-0.0125)) < 1e-6, "M1(-5%→-1.25%)"),
            (len(m2_row) and abs(m2_row.iloc[0]["dW_output"] - (-0.04875)) < 1e-6, "M2(-5%→-4.875%)"),
            (len(m3_row) and abs(m3_row.iloc[0]["dW_output"] - (-0.075)) < 1e-6, "M3(-14.5%→-7.5% 테일컷★)"),
        ]
        grid_ok = all(c[0] for c in checks)
        grid_detail = " / ".join(f"{c[1]}={'OK' if c[0] else 'FAIL'}" for c in checks)
    else:
        grid_ok = False
        grid_detail = "stg1_synthetic_grid.csv 없음"
    res.append(("S4 4모드 정합성(M0/M1/M2/M3)", grid_ok, grid_detail))

    # S5 미래참조 가드
    src = ""
    for fn in ["isolated_bounce_simulator.py", "test_07Prj_Ch1_stg1_IsoBounceModuleBuild.py"]:
        p = os.path.join(HERE, fn)
        if os.path.exists(p):
            src += open(p, encoding="utf-8").read()
    look = ("shift(-" in src) or (".shift(-" in src)
    res.append(("S5 미래참조 가드(shift- 없음)", not look, "없음" if not look else "★발견"))

    # S6 CONFIG_DEFAULT 격리튕김
    exp = fnum(M.get("exposure_default"))
    tc = fnum(M.get("tail_cut_default"))
    ld = fnum(M.get("liq_distance_default"))
    en = (M.get("enable_tail_cut_default", "False") == "True")
    cfg_ok = (exp == 0.975 and tc == -0.075 and ld == -0.0719 and en)
    res.append(("S6 CONFIG_DEFAULT=격리튕김", cfg_ok,
                f"exposure={exp} tail={tc} liq={ld} enable={en}"))

    # S7 데모 청산 건수 정합 (R<=-0.0719인 거래만 청산됐는지)
    demo_ok = True
    demo_detail = ""
    demo_path = os.path.join(HERE, "stg1_demo_apply.csv")
    if os.path.exists(demo_path):
        d = pd.read_csv(demo_path)
        # R_original이 -0.0719 이하인 거래만 _iso_mode=='tailcut'이어야 함
        d["should_tail"] = d["R_original"] <= -0.0719
        d["actual_tail"] = d["_iso_mode"] == "tailcut"
        mismatch = (d["should_tail"] != d["actual_tail"]).sum()
        demo_ok = (mismatch == 0)
        n_tail_expected = int(d["should_tail"].sum())
        n_tail_actual = int(d["actual_tail"].sum())
        demo_detail = f"기대 청산 {n_tail_expected}건 / 실제 {n_tail_actual}건 / 불일치 {mismatch}건"
    else:
        demo_ok = False
        demo_detail = "stg1_demo_apply.csv 없음"
    res.append(("S7 데모 청산건수 정합", demo_ok, demo_detail))

    # S8 ALPHA_PROVENANCE 메타
    prov_ok = False
    prov_detail = ""
    try:
        from isolated_bounce_simulator import ALPHA_PROVENANCE
        required_keys = ["source", "concept", "inspired_by", "evidence_event", "asymmetry_note"]
        missing = [k for k in required_keys if k not in ALPHA_PROVENANCE]
        prov_ok = (len(missing) == 0)
        prov_detail = "5키 모두 존재" if prov_ok else f"누락 {missing}"
    except Exception as e:
        prov_detail = f"import 실패: {e}"
    res.append(("S8 ALPHA_PROVENANCE 메타", prov_ok, prov_detail))

    # ── VERDICT ───────────────────────────────────────────────────────────
    passed = sum(1 for _, ok, _ in res if ok)
    verdict = "PASS" if passed == len(res) else "FAIL"
    summary = (f"VERDICT {NAME} | 8시나리오 {passed}/{len(res)} {verdict} | "
               f"격리튕김 모듈 빌드(엔진무수정 사후필터) | "
               f"4모드[M0_base/M1_cross_now/M2_iso_notail/M3_iso_tailcut] | "
               f"CONFIG_DEFAULT=M3(exp=0.975,tail=-0.075,liq=-0.0719) | "
               f"경계검증 {M.get('n_boundary_match','?')}/{M.get('n_boundary_cases','?')} | "
               f"데모청산 {M.get('n_demo_liquidations','?')}/10 | check:{verdict}")

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    with open(os.path.join(HSTR, f"{stamp}.txt"), "w", encoding="utf-8") as f:
        f.write(summary + "\n\n[8시나리오 상세]\n")
        for nm, ok, memo in res:
            f.write(f"  [{'OK' if ok else 'X '}] {nm} : {memo}\n")
        f.write("\n[stg1 메모] 격리튕김 모듈 빌드 + 자가검증 + 합성 격자 + 경계 정밀검증.\n"
                "  데이터·엔진 의존성 없음(합성 전용). stg2 SizingGridCompare부터 stg1 원장(292거래) 적용.\n"
                "  ★분기형: R<=-0.0719→tail_cut(-0.075) / else→R*0.975. 롱·숏 동일.\n"
                "  ★기준점: stg2에서 M0 결과가 docx의 $51,184와 동치되어야 모듈 무변형 입증.\n")

    idx = os.path.join(HSTR, "00WorkHstr_INDEX.txt")
    with open(idx, "a", encoding="utf-8") as f:
        f.write(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} | {NAME} | 분석:{stamp}.txt | {summary}\n")

    print(summary)
    for nm, ok, memo in res:
        print(f"  [{'OK' if ok else 'X '}] {nm} : {memo}")
    print(f"[check] 분석txt -> {os.path.join(HSTR, stamp+'.txt')}")
    print(f"[check] INDEX 추가 -> {idx}")


if __name__ == "__main__":
    main()
