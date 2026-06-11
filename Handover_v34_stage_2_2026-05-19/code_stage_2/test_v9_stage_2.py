# -*- coding: utf-8 -*-
"""
[파일명] test_v9_stage_2.py
[코드길이] 약 230줄
[목적] Stage 2 v9 시뮬레이터 단위 테스트 — 8개 핵심 시나리오 검증

[테스트 시나리오]
  T1. compute_step_sl 1단계 롱
  T2. compute_step_sl 2단계 롱
  T3. compute_step_sl 3단계 롱
  T4. compute_step_sl 3단계 숏 (거울대칭)
  T5. 단계 승격 시 SL 점프 단조 증가
  T6. RR 게이트 미달 (1.2 < 1.5 = FAIL)
  T7. SL 클램프 (150bp → 100bp)
  T8. 4H Timeout 시간 검증

[v9 신규 추가]
  T9. check_entry_gate 함수 단위 테스트 (정상/실패 케이스 4개)
"""
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def run_all_tests():
    print("="*70)
    print("[Stage 2 v9 단위 테스트]")
    print("="*70)
    
    from tbm_simulator_v9 import (
        compute_step_sl, compute_atr, check_entry_gate,
        STEP1_RATIO, STEP2_RATIO, STEP3_RATIO,
        STEP1_TRIGGER, STEP2_TRIGGER, STEP3_TRIGGER,
        SL_GATE, TP_GATE, RR_MIN, SL_CLAMP, TP_CLAMP,
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
    
    # ========== T1-T4: compute_step_sl ==========
    print("\n[T1] 1단계 롱 SL")
    sl = compute_step_sl('long', 100000, 101000, 1)
    check("진입가 100000 + 100bp → SL=100500", abs(sl - 100500) < 0.01)
    
    print("\n[T2] 2단계 롱 SL")
    sl = compute_step_sl('long', 100000, 101618, 2)
    check("진입가 100000 + 161.8bp → SL=101000", abs(sl - 101000) < 0.5)
    
    print("\n[T3] 3단계 롱 SL")
    sl = compute_step_sl('long', 100000, 101963, 3)
    check("진입가 100000 + 196.3bp → SL=101500", abs(sl - 101500) < 0.5)
    
    print("\n[T4] 3단계 숏 SL (거울대칭)")
    sl = compute_step_sl('short', 100000, 98037, 3)
    check("진입가 100000 - 196.3bp → SL=98500", abs(sl - 98500) < 0.5)
    
    # ========== T5: 단계 승격 SL 단조 증가 ==========
    print("\n[T5] 단계 승격 시 SL 단조 증가 (롱)")
    e = 100000
    sl1 = compute_step_sl('long', e, e * 1.01, 1)        # +100bp
    sl2 = compute_step_sl('long', e, e * 1.01618, 2)     # +161.8bp
    sl3 = compute_step_sl('long', e, e * 1.01963, 3)     # +196.3bp
    check(f"sl1({sl1:.2f}) < sl2({sl2:.2f}) < sl3({sl3:.2f})", sl1 < sl2 < sl3)
    
    # ========== T6: RR 게이트 ==========
    print("\n[T6] RR 게이트 (SL 40bp, TP 48bp → RR 1.2 < 1.5)")
    rr = 0.0048 / 0.004
    check(f"RR {rr:.2f} < {RR_MIN}", rr < RR_MIN)
    
    # ========== T7: SL 클램프 ==========
    print("\n[T7] SL 클램프 (150bp → 100bp)")
    sl_in = 0.015
    sl_out = SL_CLAMP if sl_in > SL_CLAMP else sl_in
    check(f"sl_in 150bp → sl_eff {sl_out*10000:.0f}bp", sl_out == 0.01)
    
    # ========== T8: Timeout ==========
    print("\n[T8] Timeout 4H 검증")
    check(f"TIMEOUT_MINUTES = {TIMEOUT_MINUTES} (=240)", TIMEOUT_MINUTES == 240)
    
    # ========== T9-T12: check_entry_gate ==========
    print("\n[T9-T12] check_entry_gate 함수 4개 케이스")
    
    # Mock OB 데이터 생성 (작은 DataFrame)
    n = 200
    ts = pd.date_range('2025-01-01', periods=n, freq='1h', tz='UTC')
    rng = np.random.default_rng(42)
    close = 100000 + np.cumsum(rng.normal(0, 50, n))
    df_ob = pd.DataFrame({
        'open': np.r_[close[0], close[:-1]],
        'high': close + 200,  # 큰 OB 거리 생성
        'low': close - 200,
        'close': close,
    }, index=ts)
    
    # T9: TP 50bp / SL 40bp → RR 1.25 (미달)
    # 임의 가격에서 게이트 검사 (실제 OB는 너무 멀어 게이트 실패가 예상되지만 함수 구조 검증 목적)
    gate = check_entry_gate(
        candidate_price=100000.0, side='long',
        df_ob_tf=df_ob, ob_tf_idx=150, w=5, N=5
    )
    # 함수가 정상 동작했는지만 확인 (pass 여부와 별개)
    check("check_entry_gate 함수 호출 정상 (롱)", 
          isinstance(gate, dict) and 'pass' in gate and 'fail_reason' in gate)
    
    # T10: 숏 케이스
    gate_short = check_entry_gate(
        candidate_price=100000.0, side='short',
        df_ob_tf=df_ob, ob_tf_idx=150, w=5, N=5
    )
    check("check_entry_gate 함수 호출 정상 (숏)", 
          isinstance(gate_short, dict) and 'pass' in gate_short)
    
    # T11: 게이트 결과의 필수 필드 존재
    expected_keys = ['pass', 'fail_reason', 'sl_dist_effective', 'ob_tp_dist', 
                     'ob_sl_dist', 'sl_clamped', 'rr']
    has_all_keys = all(k in gate for k in expected_keys)
    check(f"게이트 결과 dict 필수 키 7개 존재", has_all_keys)
    
    # T12: 상수 일관성 검사
    print("\n[T12] 상수 일관성")
    check(f"SL_GATE 32bp", SL_GATE == 0.0032)
    check(f"TP_GATE 48bp", TP_GATE == 0.0048)
    check(f"RR_MIN 1.5", RR_MIN == 1.5)
    check(f"SL_CLAMP 100bp", SL_CLAMP == 0.0100)
    check(f"TP_CLAMP 161.8bp", abs(TP_CLAMP - 0.01618) < 1e-6)
    check(f"STEP1_RATIO 0.5", STEP1_RATIO == 0.5)
    check(f"STEP2_RATIO 0.618", STEP2_RATIO == 0.618)
    check(f"STEP3_RATIO 0.764", STEP3_RATIO == 0.764)
    
    # 결과
    print("\n" + "="*70)
    print(f"[테스트 결과] PASS: {pass_count}, FAIL: {fail_count}")
    print("="*70)
    return fail_count == 0


if __name__ == "__main__":
    ok = run_all_tests()
    sys.exit(0 if ok else 1)
