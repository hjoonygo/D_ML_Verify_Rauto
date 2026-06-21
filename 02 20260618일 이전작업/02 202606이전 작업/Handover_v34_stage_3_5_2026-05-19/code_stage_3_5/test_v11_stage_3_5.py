# -*- coding: utf-8 -*-
"""
[파일명] test_v11_stage_3_5.py
[코드길이] 약 220줄
[목적] Stage 3.5 v11 단위 테스트 — regime 정책 8개 시나리오 + 회귀

[테스트 시나리오 (사용자 사전 동의)]
  T1. uptrend long 진입 거부 동작 (block_entry=True)
  T2. hivol_range long → SL 500bp 적용
  T3. hivol_range long → timeout 1080min (18H) 적용
  T4. 다른 regime은 기존 v10 정책 (SL 150bp / timeout 4H)
  T5. regime 정보 없을 때 (None) 기본값
  T6. enable_regime_policy=False → 항상 default (v10 동작)
  T7. hivol_range short → 기본 정책 (regime 정책은 long만 영향)
  T8. policy_label 정확성

[추가 회귀]
  T9. compute_dynamic_sl 변경 없음 (v10 회귀)
  T10. compute_step_sl 변경 없음 (v10 회귀)
  T11. 상수 일관성 (v11 신규)
"""
import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def run_all_tests():
    print("="*70)
    print("[Stage 3.5 v11 단위 테스트 — regime 정책]")
    print("="*70)
    
    from tbm_simulator_v11 import (
        compute_step_sl, compute_dynamic_sl, resolve_regime_policy,
        STEP1_RATIO, STEP2_RATIO, STEP3_RATIO,
        SL_GATE, TP_GATE, RR_MIN,
        SL_MIN, SL_MAX_DEFAULT,
        ATR_BUCKET_LOW, ATR_BUCKET_HIGH,
        MULT_LOWVOL, MULT_MIDVOL, MULT_HIGHVOL,
        HIVOL_LONG_SL_MAX_DEFAULT, HIVOL_LONG_TIMEOUT_DEFAULT,
        TIMEOUT_MINUTES_DEFAULT,
        COST_NOMINAL,
    )
    
    pass_count = 0
    fail_count = 0
    
    def check(label, condition):
        nonlocal pass_count, fail_count
        if condition:
            print(f"  [PASS] {label}")
            pass_count += 1
        else:
            print(f"  [FAIL] {label}")
            fail_count += 1
    
    # T1. uptrend long 진입 거부
    print("\n[T1] uptrend long → block_entry=True")
    p = resolve_regime_policy('uptrend', 'long')
    check(f"  block_entry={p['block_entry']}", p['block_entry'] == True)
    check(f"  policy_label='{p['policy_label']}'", 'uptrend' in p['policy_label'] and 'block' in p['policy_label'])
    
    # T2. hivol_range long SL 500bp
    print("\n[T2] hivol_range long → SL 500bp")
    p = resolve_regime_policy('hivol_range', 'long')
    check(f"  sl_max={p['sl_max']*10000:.0f}bp", abs(p['sl_max'] - 0.05) < 1e-6)
    check(f"  block_entry=False", p['block_entry'] == False)
    
    # T3. hivol_range long timeout 18H (1080min)
    print("\n[T3] hivol_range long → timeout 18H (1080min)")
    check(f"  timeout_min={p['timeout_min']}", p['timeout_min'] == 1080)
    
    # T4. 다른 regime 기본
    print("\n[T4] downtrend long → 기본 정책 (SL 150bp / 240min)")
    p = resolve_regime_policy('downtrend', 'long')
    check(f"  sl_max=150bp", abs(p['sl_max'] - SL_MAX_DEFAULT) < 1e-6)
    check(f"  timeout=240min", p['timeout_min'] == 240)
    
    p = resolve_regime_policy('lovol_range', 'long')
    check(f"  lovol_range long → 기본 SL", abs(p['sl_max'] - SL_MAX_DEFAULT) < 1e-6)
    
    # T5. regime None
    print("\n[T5] regime=None → 기본 정책")
    p = resolve_regime_policy(None, 'long')
    check(f"  sl_max=default", abs(p['sl_max'] - SL_MAX_DEFAULT) < 1e-6)
    check(f"  block_entry=False", p['block_entry'] == False)
    
    # T6. enable_regime_policy=False
    print("\n[T6] enable_regime_policy=False → 항상 default (v10 동작)")
    p = resolve_regime_policy('uptrend', 'long', enable_regime_policy=False)
    check(f"  uptrend long도 차단 안 함", p['block_entry'] == False)
    check(f"  sl_max=default", abs(p['sl_max'] - SL_MAX_DEFAULT) < 1e-6)
    p = resolve_regime_policy('hivol_range', 'long', enable_regime_policy=False)
    check(f"  hivol_range long도 SL 500bp 적용 안 함", abs(p['sl_max'] - SL_MAX_DEFAULT) < 1e-6)
    check(f"  hivol_range long도 timeout 240min", p['timeout_min'] == 240)
    
    # T7. hivol_range short 기본
    print("\n[T7] hivol_range short → 기본 (regime 정책은 long만)")
    p = resolve_regime_policy('hivol_range', 'short')
    check(f"  sl_max=default", abs(p['sl_max'] - SL_MAX_DEFAULT) < 1e-6)
    check(f"  timeout=default", p['timeout_min'] == 240)
    
    # T8. policy_label 정확성
    print("\n[T8] policy_label 디버깅용 정확성")
    p1 = resolve_regime_policy('uptrend', 'long')
    p2 = resolve_regime_policy('hivol_range', 'long')
    p3 = resolve_regime_policy('downtrend', 'short')
    check(f"  uptrend long label='{p1['policy_label']}'", 'uptrend' in p1['policy_label'])
    check(f"  hivol long label='{p2['policy_label']}'", 'hivol' in p2['policy_label'] and '500' in p2['policy_label'])
    check(f"  downtrend short label='{p3['policy_label']}'", p3['policy_label'] == 'default')
    
    # T9. compute_dynamic_sl 회귀
    print("\n[T9] 회귀: compute_dynamic_sl 변경 없음")
    sl, m = compute_dynamic_sl(0.0035)  # 중변동
    check(f"  ATR 35bp × 3.0 = 105bp", abs(sl - 0.0105) < 1e-6 and m == 3.0)
    sl, m = compute_dynamic_sl(0.0015)  # 저변동
    check(f"  ATR 15bp × 3.5 = 52.5bp", abs(sl - 0.00525) < 1e-6 and m == 3.5)
    sl, m = compute_dynamic_sl(0.0055)  # 고변동
    check(f"  ATR 55bp × 2.0 = 110bp", abs(sl - 0.011) < 1e-6 and m == 2.0)
    
    # T10. compute_step_sl 회귀
    print("\n[T10] 회귀: compute_step_sl 변경 없음")
    sl1 = compute_step_sl('long', 100000, 101000, 1)
    check(f"  1단계 SL=100500", abs(sl1 - 100500) < 0.01)
    sl3 = compute_step_sl('long', 100000, 101963, 3)
    check(f"  3단계 SL≈101500", abs(sl3 - 101500) < 0.5)
    sl_short = compute_step_sl('short', 100000, 98037, 3)
    check(f"  숏 거울대칭 ≈98500", abs(sl_short - 98500) < 0.5)
    
    # T11. 상수 일관성 (v11 신규)
    print("\n[T11] 상수 일관성")
    check(f"  HIVOL_LONG_SL_MAX_DEFAULT = 500bp", HIVOL_LONG_SL_MAX_DEFAULT == 0.05)
    check(f"  HIVOL_LONG_TIMEOUT_DEFAULT = 1080min (18H)", HIVOL_LONG_TIMEOUT_DEFAULT == 1080)
    check(f"  TIMEOUT_MINUTES_DEFAULT = 240min (4H)", TIMEOUT_MINUTES_DEFAULT == 240)
    check(f"  SL_MAX_DEFAULT = 150bp", SL_MAX_DEFAULT == 0.0150)
    check(f"  COST_NOMINAL = 16bp", COST_NOMINAL == 0.0016)
    
    # 결과
    print("\n" + "="*70)
    print(f"[테스트 결과] PASS: {pass_count}, FAIL: {fail_count}")
    print("="*70)
    return fail_count == 0


if __name__ == "__main__":
    ok = run_all_tests()
    sys.exit(0 if ok else 1)
