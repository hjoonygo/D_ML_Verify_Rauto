===============================================================================
  Stage 4A Phase 1 — 실행 안내
===============================================================================
내부버전: v2.0_verified_no_estimation (검증된 코드만 사용)
작성: 2026-05-19

[변경 사항 v1 → v2]
  - 모든 외부 함수 시그니처를 인수인계 zip 코드에서 직접 확인 후 사용
  - extract_signals_v4 / batch_simulate_v11 / Predict_ML_v2.get_signal /
    Regime_Master_v2.get_regime / aggregate_ohlcv / compute_atr_15m_pct_per_1m
    모두 검증된 시그니처 그대로
  - 폴더 통합: code_stage_4a/ + outputs_stage_4a/ 2개만 (m2_models/ 별도 폴더 폐기)

-------------------------------------------------------------------------------
[폴더 구조]
-------------------------------------------------------------------------------
D:\ML\Verify\
├ Merged_Data.csv                                            (raw, 454.3 MB)
│
├ (의존 파일들 — D:\ML\Verify\ 직접 또는 code_stage_4a\에)
│   tbm_simulator_v11.py
│   Predict_ML_v2.py
│   Regime_Master_v2.py
│   pautov75_signal_wrapper_v4.py
│   tf_aggregator_v2.py
│   ob_provider_v2.py
│   ML_Predictor_Pipeline_v2.py
│   PautoV75_XGB_3class_v2.json
│   PautoV75_XGB_3class_v2_meta.json
│   signals_cache_stage_3_5.pkl                              (선택, 90분 절약)
│   trades_s0_v10_baseline_sl180.csv                         (M2 학습 필요)
│
└ Handover_v34_stage_4a_2026-05-19\
    └ code_stage_4a\                                         ← 이 zip 푼 위치
        ├ README.txt
        ├ run_all_stage_4a.py                                (메인)
        ├ measure_v34_stage_4a.py                            (측정)
        ├ train_meta_model_v1.py                             (M2 학습)
        └ outputs_stage_4a\                                  ← 자동 생성
            (시뮬 + 학습 결과 + M2 모델 8개 통합)

자동 탐색: find_file() 함수가 D:\ML\Verify\ 하위 폴더 모두 탐색하므로
의존 파일 위치는 D:\ML\Verify\ 직접이든 stage 폴더 안이든 상관없음.

-------------------------------------------------------------------------------
[실행 명령]
-------------------------------------------------------------------------------

[1단계] 사전 점검 (30초 — 환경/파일/시그니처 확인)
   cd D:\ML\Verify\Handover_v34_stage_4a_2026-05-19\code_stage_4a
   python run_all_stage_4a.py --check-only

   → 모든 ✓ 통과 확인. ❌ 있으면 안내대로 해결 후 다시.

[2단계] 본 작업 (2~4시간)
   python run_all_stage_4a.py

   → 사전 점검 자동 재실행 → "진행: y" 입력
   → Step 0 / Step 1 / M2 학습 / Step 2 / Step 3 자동 순차 실행
   → 작동 검증 → 자동 zip 압축

[빠른 모드] 사용자 확인 생략
   python run_all_stage_4a.py --skip-confirm

[검증만] 본 작업 끝난 후 결과 확인만
   python run_all_stage_4a.py --post-only

-------------------------------------------------------------------------------
[결과 업로드]
-------------------------------------------------------------------------------
파일명: outputs_stage_4a.zip (자동 생성)
위치:   code_stage_4a\ 안

내용:
   trades_*.csv (5개)                — 시나리오별 거래
   all_scenarios_stage_4a.csv        — 5 시나리오 PF/win/net 요약
   decision_tree_evaluation.csv      — 사전 의사결정 트리 자동 평가
   additional_regime_master_distribution.csv
   additional_m1_prob_distribution.csv
   regime_master_at_entry.pkl
   trades_train_phase_4a.csv         — Train 시뮬
   signal_features_train_4a.pkl      — Train features+probs
   signal_features_oos_4a.pkl        — OOS features+probs
   M2_meta_*.json + _meta.json (8개) — 학습된 M2 모델
   m2_training_log.txt               — M2 학습 로그
   measure_log_4a.txt                — 전체 로그

이 zip 1개를 새 채팅창에 업로드.

-------------------------------------------------------------------------------
[사용자 결정 사항 — 코드에 반영됨]
-------------------------------------------------------------------------------
결정1 (Y):  5 시나리오
   base_no_meta       — M2 없음 (비교 기준)
   meta_simple        — M2 적용 (PurgedKFold 없음, Train+OOS 통합)
   meta_purged        — M2 + PurgedKFold 3-fold
   meta_regime        — meta_purged + regime feature
   meta_oos_only      — OOS만 학습 (A:b 위험 검증)

결정2 (b):  PF 임계값 1.2 / 0.95
   meta_simple ≥ 1.2  → 효과 입증
   0.95~1.2           → 효과 모호
   < 0.95             → 효과 없음

결정3:     사전 의사결정 트리 + 우선순위
   1순위 Lookahead 안전:
     - meta_purged < meta_simple × 0.85 → CV lookahead 의심
     - meta_oos_only < meta_simple × 0.7 → A:b lookahead 의심
   2순위 M2 효과 (위 PF 임계)
   3순위 Feature 확장:
     - meta_regime - meta_simple ≥ 0.15 → Regime 강력

결정4 (a):  분별력 임계 10% / 90% (Regime_Master 분포 검증)

A:b — Train + OOS 통합 학습 (단 meta_oos_only는 OOS만)
B:d — Binary 라벨 + |net_return| sample weight
C:a — Phase 1 끝나면 새 채팅창 인수인계
d:0.5 — M2 추론 임계값
e:XGBoost — binary:logistic
f:없음 — feature 정규화 안 함

-------------------------------------------------------------------------------
[예상 작업 시간]
-------------------------------------------------------------------------------
Step 0 (Regime_Master 분포):       5~10분
Step 1 (Train 시뮬 + features):    90~150분 (★ 가장 큼)
중간   (M2 학습 자동 호출):         5~15분
Step 2 (OOS 5 시나리오):           25~50분
Step 3 + 작동 검증 + zip:          5~10분
───────────────────────────────────
총                                 2~4시간

-------------------------------------------------------------------------------
[검증된 함수 호출 (추정 0%)]
-------------------------------------------------------------------------------
- extract_signals_v4(df_1m, atr_15m_pct_per_1m, threshold_long=0.35,
    threshold_short=0.35, window_size=120, filter_mode='off',
    rolling_lookback_minutes=20160, start_idx, end_idx, verbose_every)
    → (long_indices np.array, short_indices np.array, stats dict)

- process_signals_with_wait_v4(long_indices, short_indices, df_1m,
    df_ob_tf, ob_tf_minutes, w, enable_wait=True,
    wait_timeout_minutes=120, verbose=True)
    → (long_filt np.array, short_filt np.array, wait_stats dict)

- batch_simulate_v11(long_signal_indices_1m, short_signal_indices_1m,
    df_1m, df_ob_tf, df_2h, atr_ob_tf, atr_15m_pct_per_1m,
    regime_per_1m, sl_max, leverage, w, N, ob_tf_minutes,
    enable_2h_reversal, regime_master, enable_wait_entry,
    wait_timeout_minutes, verbose, enable_regime_policy,
    hivol_long_sl_max, hivol_long_timeout)
    → pd.DataFrame

- aggregate_ohlcv(df_1m_with_timestamp_column, tf_minutes) → pd.DataFrame
- Predict_ML_v2().get_signal(df_window, regime, params) → dict with probs
- Regime_Master_v2().get_regime(df_window, params=None) → str

-------------------------------------------------------------------------------
[문제 발생 시]
-------------------------------------------------------------------------------
- 사전 점검 ❌: 화면 안내대로 해결 후 다시 실행
- 작업 중간 에러: outputs_stage_4a\measure_log_4a.txt 확인 후 새 채팅창에 문의
- 작동 검증 일부 누락: python run_all_stage_4a.py --post-only

===============================================================================
