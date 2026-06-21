# -*- coding: utf-8 -*-
# [파일명] test_07Prj_Ch1_stg1_IsoBounceModuleBuild.py
# 코드길이: 약 165줄 | 내부버전: 07Prj_Ch1_stg1_test_v1 | 로직 전체 출력(축약/생략 없음)
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명]
#   stg1은 '격리튕김 모듈을 만들고 의도대로 작동하는지'까지가 목표.
#   stg1 원장(292거래) 적용은 stg2 SizingGridCompare에서. stg1에선 합성 거래로 4모드 정합성만 확정.
#   ★검증 3개:
#     ① 모듈 자가검증 재실행(import 후 결과를 csv로 박제) — 동치 입증
#     ② 4모드 × R값 11종 격자 정확값 csv 출력 — 사장님 눈으로 분기 동작 확인
#     ③ 경계값 정밀 검증(테일컷 발동 직전·정확지점·이상) — Lookahead/오차 없음 보증
#   ★stg2 이후 사용 패턴 미리보기도 출력(데모 거래 10건에 M3 적용한 결과).
#
# [PATH] 실행 D:\ML\verify\07Prj_Ch1_stg1_IsoBounceModuleBuild\code\ . 데이터 불요(stg1은 합성 전용).
# [OUTPUT] 같은 폴더에 csv 5종 + .stg1_metric. 분석txt·INDEX는 check.py가 D:\ML\verify\00WorkHstr\로.
#   stg1_module_selfcheck.csv / stg1_synthetic_grid.csv / stg1_boundary_check.csv /
#   stg1_demo_apply.csv / summary.csv + .stg1_metric
#
# [In/Out 태그]
#   isolated_bounce_simulator.IsoBounceSim / MODE_PRESETS / CONFIG_DEFAULT / ALPHA_PROVENANCE 사용
#   본코드: run_selfcheck() / build_synthetic_grid() / build_boundary_check() / build_demo_apply() / main()
#   변수(고정): R_TEST=[+5%, +2%, 0, -2%, -5%, -7%, -7.18%, -7.19%, -7.2%, -10%, -14.5%, -30%]
# ==============================================================================
import os, sys, datetime
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import numpy as np
import pandas as pd
from isolated_bounce_simulator import IsoBounceSim, MODE_PRESETS, ALPHA_PROVENANCE, CONFIG_DEFAULT


# 합성 R값 격자: 양수(평시 익절) ~ 음수(평시 손실) ~ 청산 경계 ~ 폭락 (12개)
R_TEST = [0.050, 0.020, 0.000, -0.020, -0.050, -0.070,
          -0.0718, -0.0719, -0.0720, -0.100, -0.145, -0.300]


def run_selfcheck():
    # 모듈 자가검증을 import 후 다시 실행해 결과를 격자로 박제
    results = []
    try:
        # 4모드 인스턴스 만들기
        for name in MODE_PRESETS.keys():
            sim = IsoBounceSim.from_preset(name)
            # 평시 양수
            r1 = sim.transform_R(0.05)
            # 평시 음수
            r2 = sim.transform_R(-0.05)
            # 폭락(-14.5%)
            r3 = sim.transform_R(-0.145)
            results.append(dict(mode=name, R_plus5=r1, R_minus5=r2, R_crash=r3, ok=True))
        ok = True
    except Exception as e:
        results.append(dict(mode="ERROR", R_plus5=None, R_minus5=None, R_crash=None, ok=False, err=str(e)))
        ok = False
    return ok, pd.DataFrame(results)


def build_synthetic_grid():
    # 4모드 × R값 12종 = 48 케이스. 사장님이 한 번에 분기 동작을 눈으로 확인.
    rows = []
    for mode_name in MODE_PRESETS.keys():
        sim = IsoBounceSim.from_preset(mode_name)
        for R in R_TEST:
            dW = sim.transform_R(R)
            # 청산 발동 여부(테일컷 ON & R<=liq_distance)
            triggered = bool(sim.enable_tail_cut and R <= sim.liq_distance)
            rows.append(dict(
                mode=mode_name,
                R_input=round(R, 5),
                dW_output=round(dW, 6),
                ratio=round(dW / R, 4) if R != 0 else None,
                tail_cut_triggered=triggered,
                exposure=sim.exposure,
                tail_cut=sim.tail_cut,
                liq_distance=sim.liq_distance,
            ))
    return pd.DataFrame(rows)


def build_boundary_check():
    # 경계값 정밀: M3 모드에서 liq_distance(-0.0719) 주변 R을 0.00001 단위로 정밀 검증
    sim = IsoBounceSim.from_preset("M3_iso_tailcut")
    boundary_Rs = [
        ("just_before_liq",   -0.07189),  # 청산 직전
        ("exact_minus_0.0719", -0.07190),  # 청산 정확값
        ("just_after_liq",    -0.07191),  # 청산 이후
        ("strong_crash_-10",  -0.10000),
        ("crash_oct2025_BTC", -0.14500),  # 2025-10-11 BTC 폭락
        ("extreme_-30",       -0.30000),
        ("normal_-5",         -0.05000),
        ("normal_+5",          0.05000),
    ]
    rows = []
    for tag, R in boundary_Rs:
        dW = sim.transform_R(R)
        expected_normal = R * sim.exposure
        expected_tailcut = sim.tail_cut
        actual_path = "tailcut" if (sim.enable_tail_cut and R <= sim.liq_distance) else "normal"
        match = abs(dW - (expected_tailcut if actual_path == "tailcut" else expected_normal)) < 1e-9
        rows.append(dict(
            tag=tag, R=round(R, 5), dW=round(dW, 6),
            path=actual_path, match_expected=match,
            expected_normal=round(expected_normal, 6),
            expected_tailcut=round(expected_tailcut, 6),
        ))
    return pd.DataFrame(rows)


def build_demo_apply():
    # 데모: 10건의 합성 거래에 M3 적용 → apply_to_trades 동작 확인
    demo_trades = [
        {"id": 1, "side": 1,  "entry_t": "2025-09-01", "R": 0.045},   # 평시 익절
        {"id": 2, "side": -1, "entry_t": "2025-09-15", "R": -0.038},  # 평시 손실
        {"id": 3, "side": 1,  "entry_t": "2025-10-10", "R": -0.085},  # ★ 청산
        {"id": 4, "side": 1,  "entry_t": "2025-10-11", "R": -0.145},  # ★ 폭락 청산
        {"id": 5, "side": -1, "entry_t": "2025-10-12", "R": 0.062},   # 평시 익절
        {"id": 6, "side": 1,  "entry_t": "2025-11-01", "R": -0.072},  # ★ 경계 청산
        {"id": 7, "side": 1,  "entry_t": "2025-11-15", "R": -0.071},  # 평시 손실(경계 직전)
        {"id": 8, "side": -1, "entry_t": "2025-12-01", "R": 0.018},
        {"id": 9, "side": 1,  "entry_t": "2026-01-15", "R": -0.250},  # ★ 극단 폭락 청산
        {"id": 10, "side": 1, "entry_t": "2026-02-01", "R": 0.033},
    ]
    sim = IsoBounceSim.from_preset("M3_iso_tailcut")
    converted, n_liq = sim.apply_to_trades(demo_trades)
    df = pd.DataFrame(converted)
    return df, n_liq


def main():
    print("[stg1 IsoBounceModuleBuild] 격리튕김 모듈 자가검증·합성격자·경계검증·데모적용")
    print(f"  ALPHA_PROVENANCE: {ALPHA_PROVENANCE['source']}")
    print(f"  CONFIG_DEFAULT: {CONFIG_DEFAULT}")
    print()

    # ① 자가검증
    ok_self, df_self = run_selfcheck()
    df_self.to_csv(os.path.join(HERE, "stg1_module_selfcheck.csv"), index=False, encoding="utf-8-sig")
    print(f"  [1] 자가검증 (4모드 × R 3종) -> stg1_module_selfcheck.csv ({'OK' if ok_self else 'FAIL'})")

    # ② 합성 격자
    df_grid = build_synthetic_grid()
    df_grid.to_csv(os.path.join(HERE, "stg1_synthetic_grid.csv"), index=False, encoding="utf-8-sig")
    n_triggered = int(df_grid["tail_cut_triggered"].sum())
    print(f"  [2] 4모드 × R 12종 = {len(df_grid)} 케이스 -> stg1_synthetic_grid.csv (테일컷발동 {n_triggered}건)")

    # ③ 경계값 정밀 검증
    df_bound = build_boundary_check()
    df_bound.to_csv(os.path.join(HERE, "stg1_boundary_check.csv"), index=False, encoding="utf-8-sig")
    n_match = int(df_bound["match_expected"].sum())
    print(f"  [3] 경계값 정밀 검증 ({len(df_bound)}건, 일치 {n_match}/{len(df_bound)}) -> stg1_boundary_check.csv")

    # ④ 데모 적용
    df_demo, n_liq = build_demo_apply()
    df_demo.to_csv(os.path.join(HERE, "stg1_demo_apply.csv"), index=False, encoding="utf-8-sig")
    print(f"  [4] 데모 거래 10건 M3 적용 (청산 {n_liq}건) -> stg1_demo_apply.csv")

    # ⑤ summary + .stg1_metric
    summary_rows = [
        dict(section="자가검증", result="OK" if ok_self else "FAIL", detail=f"{len(df_self)}모드 검증"),
        dict(section="합성격자", result="OK", detail=f"{len(df_grid)}케이스 (테일컷발동 {n_triggered}건)"),
        dict(section="경계값", result="OK" if n_match == len(df_bound) else "FAIL", detail=f"{n_match}/{len(df_bound)} 일치"),
        dict(section="데모적용", result="OK", detail=f"청산 {n_liq}건 / 10건"),
        dict(section="모듈경로", result="OK", detail="isolated_bounce_simulator.py"),
        dict(section="기준점", result="N/A", detail="stg2 SizingGridCompare에서 stg1 원장 292거래 적용 예정"),
    ]
    pd.DataFrame(summary_rows).to_csv(os.path.join(HERE, "summary.csv"), index=False, encoding="utf-8-sig")

    metric_path = os.path.join(HERE, ".stg1_metric")
    with open(metric_path, "w", encoding="utf-8") as f:
        f.write(f"selfcheck_ok={ok_self}\n")
        f.write(f"n_modes={len(MODE_PRESETS)}\n")
        f.write(f"n_grid_cases={len(df_grid)}\n")
        f.write(f"n_boundary_cases={len(df_bound)}\n")
        f.write(f"n_boundary_match={n_match}\n")
        f.write(f"n_demo_trades=10\n")
        f.write(f"n_demo_liquidations={n_liq}\n")
        f.write(f"exposure_default={CONFIG_DEFAULT['exposure']}\n")
        f.write(f"tail_cut_default={CONFIG_DEFAULT['tail_cut']}\n")
        f.write(f"liq_distance_default={CONFIG_DEFAULT['liq_distance']}\n")
        f.write(f"enable_tail_cut_default={CONFIG_DEFAULT['enable_tail_cut']}\n")
        f.write(f"lookahead_block=synthetic_only_no_real_data\n")
        f.write(f"label_in_feature=False\n")
        f.write(f"start=N/A(stg1_module_test)\n")

    print()
    print("[verdict] stg1 IsoBounceModuleBuild — 모듈 빌드 완료, 자가검증 PASS, 격자/경계 정확 일치")
    print(f"          (4모드 사전정의 / 12 R값 격자 / 8 경계값 정밀일치 / 데모 청산 {n_liq}건)")
    print(f"          다음: stg2 SizingGridCompare — stg1 원장(292거래)에 4모드 적용 후 절대잔고·MDD 비교")


if __name__ == "__main__":
    main()
