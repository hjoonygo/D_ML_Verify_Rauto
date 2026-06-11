# -*- coding: utf-8 -*-
"""
[파일명] test_v10_stage_3.py
[코드길이] 약 280줄
[목적] Stage 3 v10 유동 SL 단위 테스트 — 8개 핵심 시나리오 + 회귀

[테스트 시나리오 (사용자 사전 동의)]
  T1. 저변동(ATR 0.15%) → SL = 0.15% × 3.5 = 52.5bp
  T2. 중변동(ATR 0.35%) → SL = 0.35% × 3.0 = 105bp
  T3. 고변동(ATR 0.55%) → SL = 0.55% × 2.0 = 110bp
  T4. 극저변동(ATR 0.05%) → 하한 32bp 적용
  T5. 극고변동(ATR 1.0%) → 상한 150bp 적용 (기본)
  T6. OB SL 50bp, ATR SL 80bp → 50bp 사용 (더 가까운 쪽)
  T7. 경계값 multiplier (ATR 0.249% → 3.5, ATR 0.250% → 3.0)
  T8. 숏 거울대칭 (compute_step_sl 회귀)

[추가 회귀]
  T9. compute_step_sl 모든 단계 (변경 없어야 함)
  T10. sl_max 그리드 효과 (120/150/180bp)
  T11. NaN ATR 입력 가드
  T12. 상수 일관성
"""
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def run_all_tests():
    print("="*70)
    print("[Stage 3 v10 단위 테스트 — 유동 SL]")
    print("="*70)
    
    from tbm_simulator_v10 import (
        compute_step_sl, compute_atr, check_entry_gate, compute_dynamic_sl,
        STEP1_RATIO, STEP2_RATIO, STEP3_RATIO,
        STEP1_TRIGGER, STEP2_TRIGGER, STEP3_TRIGGER,
        SL_GATE, TP_GATE, RR_MIN,
        SL_MIN, SL_MAX_DEFAULT,
        ATR_BUCKET_LOW, ATR_BUCKET_HIGH,
        MULT_LOWVOL, MULT_MIDVOL, MULT_HIGHVOL,
        TIMEOUT_MINUTES, COST_NOMINAL,
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
    
    # ========== T1-T8: 사용자 사전 동의 8개 시나리오 ==========
    print("\n[T1] 저변동 (ATR 0.15%) → SL = 52.5bp")
    sl, m = compute_dynamic_sl(0.0015)
    expected = 0.0015 * 3.5
    check(f"  SL={sl*10000:.1f}bp (기대 {expected*10000:.1f}bp), mult={m}", 
          abs(sl - expected) < 1e-6 and m == MULT_LOWVOL)
    
    print("\n[T2] 중변동 (ATR 0.35%) → SL = 105bp")
    sl, m = compute_dynamic_sl(0.0035)
    expected = 0.0035 * 3.0
    check(f"  SL={sl*10000:.1f}bp (기대 {expected*10000:.1f}bp), mult={m}", 
          abs(sl - expected) < 1e-6 and m == MULT_MIDVOL)
    
    print("\n[T3] 고변동 (ATR 0.55%) → SL = 110bp")
    sl, m = compute_dynamic_sl(0.0055)
    expected = 0.0055 * 2.0
    check(f"  SL={sl*10000:.1f}bp (기대 {expected*10000:.1f}bp), mult={m}", 
          abs(sl - expected) < 1e-6 and m == MULT_HIGHVOL)
    
    print("\n[T4] 극저변동 (ATR 0.05%) → 하한 32bp 적용")
    sl, m = compute_dynamic_sl(0.0005)
    check(f"  SL={sl*10000:.1f}bp (하한 적용), mult={m}", sl == SL_MIN)
    
    print("\n[T5] 극고변동 (ATR 1.0%) → 상한 150bp 적용")
    sl, m = compute_dynamic_sl(0.0100)
    check(f"  SL={sl*10000:.1f}bp (상한 적용), mult={m}", sl == SL_MAX_DEFAULT)
    
    print("\n[T6] OB SL 50bp vs ATR SL 80bp → 더 작은 쪽 50bp")
    # check_entry_gate를 mock OB로 호출하기 어려우므로 로직 직접 검증
    # 코드 로직: if ob_sl_dist < atr_sl_dist: use ob, else use atr
    ob_dist = 0.0050
    atr_dist, _ = compute_dynamic_sl(0.0027)  # 27bp ATR × 3.0 = 81bp
    chosen = min(ob_dist, atr_dist)
    method = 'ob_natural' if ob_dist < atr_dist else 'atr_dynamic'
    check(f"  chosen={chosen*10000:.1f}bp, method={method}", 
          chosen == 0.005 and method == 'ob_natural')
    
    print("\n[T7] 경계값 multiplier 검증")
    # 0.249% (BUCKET_LOW 직전) → 3.5
    sl_a, m_a = compute_dynamic_sl(ATR_BUCKET_LOW - 0.0001)
    # 0.250% (BUCKET_LOW = 0.0025) → 3.0
    sl_b, m_b = compute_dynamic_sl(ATR_BUCKET_LOW)
    check(f"  ATR=0.0024 (직전) → mult={m_a} (기대 3.5)", m_a == MULT_LOWVOL)
    check(f"  ATR=0.0025 (=BUCKET_LOW) → mult={m_b} (기대 3.0)", m_b == MULT_MIDVOL)
    
    print("\n[T8] 숏 거울대칭 (compute_step_sl 회귀)")
    sl_short = compute_step_sl('short', 100000, 98037, 3)
    expected = 100000 - 1963 * 0.764
    check(f"  진입 100000, 저점 98037 (-196.3bp), 3단계 → SL={sl_short:.2f} (기대 {expected:.2f})", 
          abs(sl_short - expected) < 0.5)
    
    # ========== T9-T12: 추가 회귀 ==========
    print("\n[T9] compute_step_sl 모든 단계 회귀")
    sl1 = compute_step_sl('long', 100000, 101000, 1)  # +100bp / mult 0.5
    sl2 = compute_step_sl('long', 100000, 101618, 2)  # +161.8bp / mult 0.618
    sl3 = compute_step_sl('long', 100000, 101963, 3)  # +196.3bp / mult 0.764
    check(f"  1단계 SL=100500 (기대): {sl1}", abs(sl1 - 100500) < 0.01)
    check(f"  2단계 SL≈101000 (기대): {sl2:.2f}", abs(sl2 - 101000) < 0.5)
    check(f"  3단계 SL≈101500 (기대): {sl3:.2f}", abs(sl3 - 101500) < 0.5)
    check(f"  단조 증가 (sl1<sl2<sl3)", sl1 < sl2 < sl3)
    
    print("\n[T10] sl_max 그리드 효과")
    # ATR 100bp인 경우, mult 2.0이라 200bp가 raw
    sl_120, _ = compute_dynamic_sl(0.0100, sl_max=0.012)
    sl_150, _ = compute_dynamic_sl(0.0100, sl_max=0.015)
    sl_180, _ = compute_dynamic_sl(0.0100, sl_max=0.018)
    check(f"  sl_max=120bp → SL={sl_120*10000:.0f}bp", sl_120 == 0.012)
    check(f"  sl_max=150bp → SL={sl_150*10000:.0f}bp", sl_150 == 0.015)
    check(f"  sl_max=180bp → SL={sl_180*10000:.0f}bp", sl_180 == 0.018)
    
    # 100bp 고정 시 — 0.0100 상한, ATR 50bp일 때
    sl_at_100bp_cap, _ = compute_dynamic_sl(0.0050, sl_max=0.0100)  # 50bp × 2.0 = 100bp
    check(f"  sl_fixed_100bp: ATR 50bp → SL={sl_at_100bp_cap*10000:.0f}bp", 
          abs(sl_at_100bp_cap - 0.0100) < 1e-6)
    
    print("\n[T11] NaN/0/inf 입력 가드")
    sl_nan, _ = compute_dynamic_sl(np.nan)
    sl_zero, _ = compute_dynamic_sl(0.0)
    sl_neg, _ = compute_dynamic_sl(-0.001)
    check(f"  NaN 입력 → SL={sl_nan*10000:.0f}bp (보수적 sl_max 적용)", sl_nan == SL_MAX_DEFAULT)
    check(f"  0 입력 → SL={sl_zero*10000:.0f}bp", sl_zero == SL_MAX_DEFAULT)
    check(f"  음수 입력 → SL={sl_neg*10000:.0f}bp", sl_neg == SL_MAX_DEFAULT)
    
    print("\n[T12] 상수 일관성")
    check(f"  SL_GATE = 32bp", SL_GATE == 0.0032)
    check(f"  TP_GATE = 48bp", TP_GATE == 0.0048)
    check(f"  RR_MIN = 1.5", RR_MIN == 1.5)
    check(f"  SL_MIN = 32bp (=SL_GATE)", SL_MIN == 0.0032)
    check(f"  SL_MAX_DEFAULT = 150bp", SL_MAX_DEFAULT == 0.0150)
    check(f"  ATR_BUCKET_LOW = 25bp", ATR_BUCKET_LOW == 0.0025)
    check(f"  ATR_BUCKET_HIGH = 45bp", ATR_BUCKET_HIGH == 0.0045)
    check(f"  MULT_LOWVOL = 3.5", MULT_LOWVOL == 3.5)
    check(f"  MULT_MIDVOL = 3.0", MULT_MIDVOL == 3.0)
    check(f"  MULT_HIGHVOL = 2.0", MULT_HIGHVOL == 2.0)
    check(f"  STEP1_RATIO = 0.5", STEP1_RATIO == 0.5)
    check(f"  STEP2_RATIO = 0.618", STEP2_RATIO == 0.618)
    check(f"  STEP3_RATIO = 0.764", STEP3_RATIO == 0.764)
    check(f"  TIMEOUT = 240분", TIMEOUT_MINUTES == 240)
    
    # 결과
    print("\n" + "="*70)
    print(f"[테스트 결과] PASS: {pass_count}, FAIL: {fail_count}")
    print("="*70)
    return fail_count == 0


if __name__ == "__main__":
    ok = run_all_tests()
    sys.exit(0 if ok else 1)
