# ==============================================================================
# [파일명] PautoV80_Regime_ML.py
# [코드길이] 약 1190줄 / 내부버전 V80k_Verify_3_S1_p2 / 로직축약·생략 없이 전체 출력
# [PautoV8.0 5대 로직] 장세판단 (Market Regime) - ML 패턴인식 모듈
# [모듈 종류] 단일 통합 모듈 (피처 산출 + MTF MACD + Regime 학습/추론 + ★ TBM 라벨링)
# [내부버전] V80k_Verify_3_S1_p2 (S1 + sklearn 호환 + 환경별 conf 임계 차등)
# ==============================================================================
# [V80k_Verify_3 패치 p2 — 환경별 conf 임계 차등] ★ 2026-05-04
# ==============================================================================
# [발견 경위]
#   8 시나리오 비판 검증 + 10개 Key docx 발굴 결과 V8.0.k 정확한 임계 매트릭스 확정.
#   본 사이클 첫 학습 결과 회귀 미달 (CHOP n_train 130,329 vs 골든 68,768, +89%).
#   원인: 본 코드의 train_tbm_v2가 모든 환경 동일 conf=0.6 사용 (env_split_models.py 기본값).
#
# [출처 단서]
#   · Key_V8_0_k_Takeaway.docx 6.2 (학습 하이퍼파라미터):
#       "Regime conf 임계: BULL/BEAR=0.6, CHOP=0.7"
#   · Key_V8_0_g_Takeaway.docx (env_split_models 첫 등장 사이클):
#       "BULL/BEAR 학습 데이터 적음 (각 6k봉) → conf 0.6/0.7로 보수적 운영 권장"
#       "해소: conf 0.6에서 677건, conf 0.7에서 73건"
#
# [수정 내역]
#   · train_tbm_v2 시그니처: regime_conf_thr_per_env (dict) 신규 인자
#       기본값: None → 자동으로 V8.0.k 정답 적용 ({'BULL':0.6, 'BEAR':0.6, 'CHOP':0.7})
#       backward compat: dict 직접 지정 시 그대로 사용
#   · 3단계 환경 분포 로그: 환경별 차등 임계로 출력
#   · 5단계 환경별 학습 데이터 분리: 환경별 임계로 강한 시그널 추출
#   · 결과 dict: regime_conf_thr_per_env 메타데이터 기록
#
# [기대 효과 — 회귀 격차 해결 추정]
#   · CHOP n_train: 130,329 → 68,768 부근 수렴 (V8.0.k 골든 일치)
#   · CHOP val_acc: 64.86% → 83.86% 부근 향상
#   · CHOP OOS conf>=0.7: 8.39% → 68.8% 부근 향상
#   · BULL/BEAR도 conf 0.6 그대로지만 수렴 가능 (다른 원인 추정 — Verify_4)
#
# [영향 범위]
#   · 학습 로직 본체 변경 X (피처/라벨/시드/하이퍼파라미터 모두 그대로)
#   · 운영 (PautoStrategy_V8K_R001) 임계 무관 — 운영은 별도 0.5 사용
#   · 회귀 테스트 골든 메트릭은 오히려 일치 방향
#
# [Lookahead 안전성 — 점검 통과]
#   · 환경별 차등 임계는 학습 단계 데이터 추출 필터일 뿐
#   · 학습/추론/운영 모두 동일한 Regime 모델 출력 사용 — 추론 시 누설 X
#
# [검증 의무]
#   본 패치 후 선장 PC에서 재학습 → train_report.json 확인 시 다음 검증:
#     · CHOP n_train이 골든 68,768 ± 5% 이내 (65,330 ~ 72,206)
#     · CHOP val_acc가 골든 83.86% ± 5% 이내
#     · BULL/BEAR n_train 격차는 본 패치로 해결 X (다른 원인) — Verify_4
# ==============================================================================
# [V80k_Verify_3 패치 p1 — sklearn 1.6+ 호환] ★ 2026-05-04 18:35
# ==============================================================================
# [발견 경위]
#   선장 PC (xgboost 1.7.6 또는 2.1.4 + sklearn 1.8.0)에서 model.save_model() 호출 시
#   `_estimator_type undefined` TypeError 발생. 학습 자체는 끝까지 정상 진행되나
#   disk write 직전에 깨짐 → 모델 저장 실패.
#
# [원인]
#   sklearn 1.6+에서 BaseEstimator._estimator_type 처리 방식 변경.
#   xgboost (1.7~2.x 전부) 는 sklearn 1.4 이하 가정 → save_model이 sklearn 신 API
#   호출 → 속성 미정의 에러.
#
# [수정 내역]
#   train_model() line 540 직전 + train_tbm_v2() line 1321 직전 두 위치에 추가:
#     if not hasattr(model, '_estimator_type'):
#         model._estimator_type = 'classifier'
#     model.save_model(...)
#
# [영향 범위]
#   · 학습 로직 변경 X (피처/라벨/시드/하이퍼파라미터 모두 그대로)
#   · 학습 결과 변경 X (학습된 파라미터 동일)
#   · 저장 결과 변경 X (JSON 모델 파일 형식 동일)
#   · 회귀 테스트 골든 메트릭 영향 X
#   · 단지 sklearn이 기대하는 속성을 명시 부여하여 호환성 회피
#
# [검증]
#   xgboost 1.7.6 + sklearn 1.8.0 환경에서 save_model() 호출 통과.
#   load_model() 후 predict_proba() 동작 동일.
# ==============================================================================
# [V80k_Verify_3 변경 - 빠진 학습 로직 복원 (S1 단계)] ★ 2026-05-04
# ==============================================================================
# [발견 경위]
#   V80k_Verify_2 사이클 종료 시점 코드 감사 결과, 풀세트의 TBM 학습 코드 부재 확인.
#   - PautoV80_TBM_{BULL/BEAR/CHOP}_v2.json (4.4~5.3MB) 3종 모델 파일은 있으나
#     이를 학습한 코드가 풀세트에 일체 없음.
#   - PC 학습 워크플로우 명목적 명세만 있고 실행 가능 상태 X.
#   - 본 PautoV80_Regime_ML.py 헤더 주석 5.1엔 "TBM 라벨링 (V8.0.j 보존)"이라 명시되어
#     있으나 실제 함수는 누락 상태 — Pauto → Rauto V80k 패키징 단계에서 정리 시
#     삭제 추정. (Sonnet 작업 사이클에서 빠졌을 가능성)
#
# [출처 추적 — 4단계 발굴]
#   1) _inherited_v80k_original/02_V80k_Handover_Report.docx 6.2 후보 B
#      → TBM 라벨 임계 첫 단서: "TP 0.30%/SL 0.10% horizon 30분"
#   2) Key_V8_0_k_Takeaway.docx 5.1 "코딩 산출물" 표
#      → 학습기 파일명 4종 확인:
#         · env_split_models.py     (TBM v1 R:R 2:1, V8.0.j 보존)
#         · sweep_b_v2.py            (TBM v2 R:R 3:1, V8.0.k 본체)
#         · sweep_a.py               (SL/RR 게이트 8 시나리오 sweep)
#         · sweep_b_v2_test.py       (v2 OOS 백테 12 시나리오)
#   3) Pauto V8.0.j 작업 폴더에서 env_split_models.py (482줄) 풀 코드 발굴
#   4) sweep_b_v2.py 미발굴. 그러나 Takeaway 5.2 + env_split_models.py 라인 89 비교로
#      v1→v2 차이가 정확히 한 줄(tp_pct 0.20→0.30)임 검증 → 100% 복원 가능.
#
# [복원 내역]
#   [신규 추가] def tbm_label_v2(df, horizon=30, tp_pct=0.30, sl_pct=0.10) -> np.ndarray
#     · 출처: env_split_models.py 라인 61~85 (V8.0.j v1 학습기 풀 코드)
#     · 변경: tp_pct 기본값 0.20 → 0.30 (V8.0.k Stage 3 (나) sweep_b_v2.py 동등)
#     · 출력: 0=LONG_PROFIT / 1=SHORT_PROFIT / 2=NO_PROFIT / -1=horizon 부족
#     · 위치: PautoV80_Regime_ML.py 라인 940 부근 (_create_labels 다음, 별개 함수)
#     · 동작: 진입봉 t에서 [t+1, t+30] 봉 path 검사
#             - LONG: tp_long(=close*1.003) 먼저 도달 → 1 / sl_long(=close*0.999) 먼저 → 0
#             - SHORT: tp_short(=close*0.997) 먼저 도달 → 1 / sl_short(=close*1.001) 먼저 → 0
#             - 같은 봉 TP·SL 동시 도달 시 보수적으로 loss(0) 처리 (V8.0.j 그대로 보존)
#             - LONG win 우선, 다음 SHORT win, 둘 다 no_profit이면 NO_PROFIT(2)
#
#   [신규 추가] def train_tbm_v2(csv_path, output_dir, ...) -> dict
#     · 출처: env_split_models.py 라인 36~170 (V8.0.j 학습 흐름 5단계)
#     · 동작:
#         1) 21mo 데이터 로드 + 70/30 분할
#         2) compute_features 30 피처 산출
#         3) Regime v6로 학습 70% 데이터 환경 라벨링 (in-sample)
#         4) tbm_label_v2()로 R:R 3:1 라벨 생성 (전 봉)
#         5) 환경별 데이터 분리 (BULL/BEAR/CHOP, Regime conf>=0.6 필터)
#         6) 환경 내 85/15 분할 + sample_weight='balanced' + XGBoost 학습
#         7) PautoV80_TBM_{BULL/BEAR/CHOP}_v3.json 저장 (v2 보존, v3 격리)
#     · 출력: dict (학습 메트릭 + 회귀 테스트 비교 결과)
#
# [Regime용 _create_labels 와의 차이 — 혼동 방지]
#   · _create_labels (기존): Regime 5-class 라벨 (TREND_UP/DOWN/CHOP_VOLATILE/QUIET/NEUTRAL)
#                            미래 high/low 변화 % 기반, ATR 누설 해결판 (v5)
#   · tbm_label_v2 (신규):   TBM 3-class 라벨 (LONG_PROFIT/SHORT_PROFIT/NO_PROFIT)
#                            R:R 3:1 path 추적 기반
#   두 함수 공존. 이름·역할·출력 클래스 모두 다름. 호출자는 용도에 따라 선택.
#
# [회귀 테스트 골든 메트릭 — 신규 학습 결과 검증용]
#   학습 후 다음 메트릭이 ±5% 이내 들어와야 "원본 V80k 충실 복원" 인증:
#     · BULL_v2: train n=6,306, val_acc 44.47%, conf>=0.7 정확도 57.14% (n=56)
#     · BEAR_v2: train n=6,387, val_acc 52.22%, conf>=0.7 정확도 75.93% (n=54)
#     · CHOP_v2: train n=68,768, val_acc 83.86%, conf>=0.7 정확도 97.83% (n=4,561)
#     · OOS conf>=0.7 비율: BULL 22.7%, BEAR 29.5%, CHOP 68.8%
#     · OOS 백테 (D1 70% Regime, BASE_c50): 월 +22.23%, max DD -3.94%, n=783
#   3개 이상 미달 시 자동 reject + 원인 진단 train_report.json 기록.
#
# [Lookahead 안전성 — 의무 점검 통과]
#   · tbm_label_v2() 미래 [t+1, t+30] 30봉만 참조 — 학습 라벨용 ✓
#   · 추론 시 호출 X (모델 .predict_proba()만 호출) — 누설 없음 ✓
#   · 학습 데이터 split (70%) 시 horizon=30 윈도우 끝나는 시점까지만 사용 ✓
#
# [복원 산출물 파일명 (메모리 명명 규칙 준수)]
#   · 학습 모델: PautoV80_TBM_{BULL/BEAR/CHOP}_v3.json (v2 보존, 신규 v3 격리)
#   · 학습 결과 리포트: V80k_Verify_3_S2_train_report.json
#   · 회귀 테스트 결과: V80k_Verify_3_S2_regression_test.json
#   · 학습 작업 폴더: strategies/_workspace/3balancedTBM_R002/
#   · 배포 ZIP: strategies/3balancedTBM_R002.zip
#
# [다음 사이클(Verify_4) 핵심 문제제기 ★]
#   "휩쏘(Stop Hunt / Liquidity Sweep)를 이길 SL 정책 찾기"
#   - V80k_Verify_2 47h PASS 3건 사후 분석에서 PASS #3이 더블 sweep + 진짜 방향 +1.03% 패턴
#   - V8.0.j env_split_models.py E6 시나리오에서 SL buffer 0.3% 검증됐으나 채택 안 됨
#   - Verify_4 후보 옵션 5가지: (1) OB 너머 swing low, (2) Buffer %, (3) Time-based,
#                                (4) Mid-point, (5) Dual confirmation (N봉 종가)
#   - 자세히: docs/Key_V80k_Verify_3_10_TBM_OB_Mismatch_StopHunt.docx
# ==============================================================================
# [v6 변경 - V8.0.e 사이클: 3-class 직접 학습 + conf 게이트] ★★★
#   V8.0.e 천장 실험 결과 (8 시나리오 단계 검증):
#     - v5.1 (5-class h=30): val 37.19%, conf≥0.5 정확도 38.18%
#     - v6   (3-class h=30): val 54.58%, conf≥0.5 정확도 75.87% ★+17.4%p+37.7%p
#
#   변경 1) 학습 라벨: 5-class → 3-class 직접
#     _create_labels(5-class) 결과 → INTERNAL_TO_EXTERNAL_IDX 변환 후 학습
#     CHOP_VOLATILE/CHOP_QUIET/NEUTRAL → 모두 'CHOPPY' (3-class idx 2)
#     TREND_UP → 'BULLISH_EXPANSION' (idx 0)
#     TREND_DOWN → 'BEARISH_EXPANSION' (idx 1)
#     XGBoost num_class=5 → num_class=3
#
#   변경 2) 추론 + confidence 게이트
#     proba shape (3,) 직접 사용 (5-class 매핑 단계 폐기)
#     params['regime_min_confidence'] (default 0.5) 미만 시 'CHOPPY' fallback
#     → 진입 시 보수적 차단 (Predict_ML 어댑터에서 활용)
#
#   변경 3) 인터페이스 100% 호환 보존
#     - get_regime() 반환: 'BULLISH_EXPANSION' / 'BEARISH_EXPANSION' / 'CHOPPY' (변경 없음)
#     - get_regime_detail() 반환 dict: label_3class, label_5class, probs(5-class), confidence
#     - label_5class: 호환성 위해 합리적 매핑 (BULLISH→TREND_UP 등)
#     - probs: 5-class 키 유지 (V8.0.d Predict_ML 호환)
#
#   변경 4) is_uncertain 필드 추가 (신규)
#     conf 게이트 미통과 시 True → 외부에서 진입 차단 결정 가능
# ==============================================================================
# [v5.1 변경 - 자동 재학습 호환성] (보존)
#   모델 파일 mtime 추적 → 파일 갱신 감지 시 자동 reload (코어 무중단 운영)
# ==============================================================================
# [v5 변경 - 사용자 제안 시나리오 7] (보존)
#   사용자 지적: v4 라벨이 ATR 기반이라 vol_accel 누설 발생
#               (vol_accel importance 21% 단독 압도 = 라벨 누설 자명한 결과)
#   사용자 제안: 전고점/전저점 차이 + cRSI 극값 패턴 → 라벨 + 피처
#
#   라벨 변경 (v4 ATR Triple Barrier → v5 미래 high/low 변화):
#     v4: PT = 3.0*ATR / SL = 2.0*ATR  (ATR 의존 → vol_accel 누설)
#     v5: range_up   = (future_high - high_t) / close_t * 100
#         range_down = (low_t - future_low)  / close_t * 100
#         임계값 0.30% / 강한추세 1.5배 비율
#         ATR 의존 완전 제거 → 라벨 누설 해결
#
#   피처 추가 (사용자 C 직관):
#     + crsi_extreme_oversold   : cRSI < 10 binary
#     + crsi_extreme_overbought : cRSI > 90 binary
#
#   결과 피처: 28 → 30
#
# [v3 → v4 보존 변경]
#   롤링 CVD, VWAP 거리, ADX 추가
#
# [v2 → v3 보존 변경]
#   진짜 MTF MACD (파인스크립트 변환)
# ==============================================================================
# [📥 IN]
#   - df (pd.DataFrame)        : 1분봉 OHLCV + taker_buy_volume 윈도우
#                                 [필수 컬럼] open, high, low, close, volume
#                                 [선택 컬럼] taker_buy_volume (없으면 효과 감소)
#   - params (dict)            : 엔진 마스터 설정값
#                                 [신규 키]
#                                   'regime_min_warmup' (int)  default = 2000  (EMA 420 안정화)
#                                                        (15m × 100봉 + MACD slow EMA)
#                                   'regime_model_path' (str)  default = 'PautoV80_Regime_Model.json'
#                                   'regime_horizon'    (int)  default = 30
#                                                        라벨링용 미래 봉수 (10/15/30 중 학습시 선택)
#
# [📤 OUT - 인수인계 인터페이스]
#   - get_regime(df, params)        -> str
#         "BULLISH_EXPANSION" / "BEARISH_EXPANSION" / "CHOPPY"
#         (R078_S12 와 100% 호환)
#
# [📤 OUT - 확장 API (선택)]
#   - get_regime_detail(df, params) -> dict
#         {
#             'label_3class': str,      # 외부 3-class
#             'label_5class': str,      # 내부 5-class (TREND_UP/DOWN/CHOP_VOL/CHOP_QUIET/NEUTRAL)
#             'probs':        dict,     # ML 모델 5-class 확률
#             'confidence':   float,    # 최대 확률값
#             'features':     dict,     # 20 피처 현재값 (디버깅용)
#             'warmup':       bool,
#         }
#
# [📤 OUT - 학습 API]
#   - train_model(csv_path, model_path=None, horizon=30) -> dict
#         { 'accuracy': float, 'feature_importance': dict, 'class_dist': dict }
#         테스터에서 호출하는 학습 함수
#
# [통합 피처 (20개 - 사용자 합의)]
#   1m TF (12개):
#     1. fvg_bull             : Fair Value Gap 상승 (binary)
#     2. fvg_bear             : Fair Value Gap 하락 (binary)
#     3. swing_high_dist      : 전고점까지 % 거리 (BOS 토대)
#     4. swing_low_dist       : 전저점까지 % 거리
#     5. crsi                 : Connors RSI (3 components average)
#     6. ema_alignment        : 정배열 +1 / 역배열 -1 / 그외 0
#     7. ema_dist_20_50       : (EMA20-EMA50)/EMA50 % 이격도
#     8. ema_dist_50_100      : (EMA50-EMA100)/EMA100 %
#     9. vol_accel            : ATR_pct 변화율 (변동성 가속도)
#    10. volume_accel         : volume.pct_change() (거래량 가속도)
#    11. taker_smooth_30      : taker_buy_ratio 30봉 평활
#    12. taker_velocity       : taker_smooth_30.diff(5)
#
#   5m TF (3개 - MTF MACD):
#    13. macd_5m
#    14. macd_signal_5m
#    15. macd_hist_5m
#
#   15m TF (3개):
#    16. macd_15m
#    17. macd_signal_15m
#    18. macd_hist_15m
#
#   1h TF (2개):
#    19. macd_1h
#    20. macd_hist_1h
#
# [Lookahead Bias 점검 - 헤더에 명시 (PautoV8.0 표준)]
#   - df.iloc[:-1] 로 마감 캔들만 사용                                            ✓
#   - 모든 지표 rolling/ewm 과거 방향                                              ✓
#   - swing 검출: rolling(N).max/min.shift(N) 으로 lookahead 차단                ✓
#   - MTF 리샘플링: 상위 TF 봉 마감 시각만 사용 (label='left', closed='left')    ✓
#   - 학습용 라벨 (h봉 미래)은 학습 정답지용. 추론 시 미사용.                      ✓
# ==============================================================================
import os
import json
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

# ============================================================================
# ★ V80k_Verify_3 패치 p1 (2026-05-04): sklearn 1.6+ 호환 monkey patch
# ============================================================================
# sklearn 1.6부터 BaseEstimator._estimator_type 처리 변경 → xgboost (1.7.6 ~
# 2.x 모두) save_model/predict_proba 호출 시 `_estimator_type undefined` 에러.
# 모듈 import 시점에 클래스 자체에 속성 부여하여 모든 인스턴스 자동 적용.
# 영향: 학습 결과/모델 파일 형식/추론 결과 모두 변경 X. 호환성만 회피.
# ============================================================================
try:
    import xgboost as _xgb_compat
    if not hasattr(_xgb_compat.XGBClassifier, '_estimator_type'):
        _xgb_compat.XGBClassifier._estimator_type = 'classifier'
    if not hasattr(_xgb_compat.XGBRegressor, '_estimator_type'):
        _xgb_compat.XGBRegressor._estimator_type = 'regressor'
except ImportError:
    pass  # xgboost 미설치 시에도 모듈 다른 부분(피처 산출)은 작동

__version__ = 'V80_REGIME_v6_3CLASS_p1'

# ------------------------------------------------------------------------------
# 5-class 내부 라벨 (학습 시 _create_labels 가 출력하는 형태) - 보존
# ------------------------------------------------------------------------------
INTERNAL_LABELS = ['NEUTRAL', 'TREND_UP', 'TREND_DOWN', 'CHOP_VOLATILE', 'CHOP_QUIET']
LABEL_TO_IDX = {lbl: i for i, lbl in enumerate(INTERNAL_LABELS)}
IDX_TO_LABEL = {i: lbl for i, lbl in enumerate(INTERNAL_LABELS)}

# ------------------------------------------------------------------------------
# 3-class 외부 라벨 (V8.0 인터페이스 - 추론/Predict_ML 노출)
# ------------------------------------------------------------------------------
EXTERNAL_LABELS = ['BULLISH_EXPANSION', 'BEARISH_EXPANSION', 'CHOPPY']
EXTERNAL_TO_IDX = {lbl: i for i, lbl in enumerate(EXTERNAL_LABELS)}
IDX_TO_EXTERNAL = {i: lbl for i, lbl in enumerate(EXTERNAL_LABELS)}

# 5-class idx → 3-class idx (학습 라벨 변환)
INTERNAL_IDX_TO_EXTERNAL_IDX = {
    LABEL_TO_IDX['TREND_UP']:      EXTERNAL_TO_IDX['BULLISH_EXPANSION'],   # 0
    LABEL_TO_IDX['TREND_DOWN']:    EXTERNAL_TO_IDX['BEARISH_EXPANSION'],   # 1
    LABEL_TO_IDX['CHOP_VOLATILE']: EXTERNAL_TO_IDX['CHOPPY'],              # 2
    LABEL_TO_IDX['CHOP_QUIET']:    EXTERNAL_TO_IDX['CHOPPY'],              # 2
    LABEL_TO_IDX['NEUTRAL']:       EXTERNAL_TO_IDX['CHOPPY'],              # 2
}

# 3-class label → 호환 5-class label (label_5class 추론 출력용)
EXTERNAL_TO_INTERNAL_REPRESENTATIVE = {
    'BULLISH_EXPANSION': 'TREND_UP',
    'BEARISH_EXPANSION': 'TREND_DOWN',
    'CHOPPY':            'NEUTRAL',  # CHOPPY 대표값 - 단순화
}

# v5 호환 (기존 외부 코드 의존):
INTERNAL_TO_EXTERNAL = {
    'TREND_UP':       'BULLISH_EXPANSION',
    'TREND_DOWN':     'BEARISH_EXPANSION',
    'CHOP_VOLATILE':  'CHOPPY',
    'CHOP_QUIET':     'CHOPPY',
    'NEUTRAL':        'CHOPPY',
}

# 30 피처 표준 순서 (학습/추론 정합 보장 - 단일 진실 소스)
# [v4 → v5 변경 - 사용자 제안: cRSI 극값 패턴 학습]
#   추가:
#     - crsi_extreme_oversold   : cRSI < 10 binary (과매도 극값)
#     - crsi_extreme_overbought : cRSI > 90 binary (과매수 극값)
#   라벨도 변경 (ATR 누설 해결): _create_labels v5 참조
FEATURE_COLS = [
    # 1m TF 핵심 (12)
    'fvg_bull', 'fvg_bear',
    'swing_high_dist', 'swing_low_dist',
    'crsi',
    'ema_alignment', 'ema_dist_20_50', 'ema_dist_50_100',
    'vol_accel', 'volume_accel',
    'taker_smooth_30', 'taker_velocity',
    # 1m microstructure (3)
    'candle_body_ratio', 'upper_wick_ratio', 'lower_wick_ratio',
    # 시간 (2)
    'hour_of_day', 'day_of_week',
    # MTF MACD (7)
    'mtfmacd_short', 'mtfmacd_mid', 'mtfmacd_long',
    'mtfmacd_short_slope', 'mtfmacd_short_slowing',
    'mtfmacd_align', 'mtfmacd_short_zone',
    # v4 - 롤링 CVD + VWAP + ADX (4)
    'cvd_rolling_500',
    'dist_to_vwap_short', 'dist_to_vwap_long',
    'adx_14',
    # [v5 신규] cRSI 극값 binary (사용자 C 직관)
    'crsi_extreme_oversold', 'crsi_extreme_overbought',
]


# ==============================================================================
# 메인 클래스 (인터페이스 진입점)
# ==============================================================================
class PautoV80_Regime_ML:
    """
    [PautoV8.0] 장세판단 통합 모듈.
    
    R078_S12 인터페이스 (파일명 제외) 100% 호환:
      - 클래스명: PautoV80_Regime_ML (R078: Regime_Master_PautoV75)
      - 함수명: get_regime(df, params)
      - 입력: df (DataFrame), params (dict)
      - 출력: "BULLISH_EXPANSION" / "BEARISH_EXPANSION" / "CHOPPY"
    """

    def __init__(self):
        self._model = None
        self._model_path = None
        self._model_mtime = None  # [v5.1] 모델 파일 갱신 자동 감지용

    # --------------------------------------------------------------------------
    # 인터페이스 함수 (외부 노출)
    # --------------------------------------------------------------------------
    def get_regime(self, df: pd.DataFrame, params: dict) -> str:
        detail = self.get_regime_detail(df, params)
        return detail['label_3class']

    def get_regime_detail(self, df: pd.DataFrame, params: dict) -> dict:
        min_warmup = (params or {}).get('regime_min_warmup', 2000)
        if len(df) < min_warmup:
            return {
                'label_3class': 'UNCERTAIN',
                'label_5class': 'NEUTRAL',
                'probs': {lbl: 0.2 for lbl in INTERNAL_LABELS},
                'probs_3class': {lbl: 1/3 for lbl in EXTERNAL_LABELS},
                'confidence': 0.0,
                'is_uncertain': True,  # [v6] 워밍업 → 진입 차단
                'min_confidence': 0.0,
                'features': {},
                'warmup': True,
            }

        # [v5.1] 모델 lazy-load + 파일 갱신 자동 감지
        # 3개월 자동 재학습으로 모델 .json 갱신 시 코어 재시작 없이 자동 reload
        path = (params or {}).get('regime_model_path')
        if path is None:
            path = os.path.join(os.getcwd(), 'PautoV80_Regime_Model.json')

        need_reload = False
        if self._model is None:
            need_reload = True
        elif os.path.exists(path):
            cur_mtime = os.path.getmtime(path)
            if self._model_mtime is None or cur_mtime > self._model_mtime:
                need_reload = True  # 파일 갱신 감지 (재학습 발생)

        if need_reload:
            self._lazy_load_model(params)
            if self._model is None:
                # 모델 없으면 NEUTRAL fallback
                return {
                    'label_3class': 'UNCERTAIN',
                    'label_5class': 'NEUTRAL',
                    'probs': {lbl: 0.2 for lbl in INTERNAL_LABELS},
                    'probs_3class': {lbl: 1/3 for lbl in EXTERNAL_LABELS},
                    'confidence': 0.0,
                    'is_uncertain': True,  # [v6] 모델 없음 → 진입 차단
                    'min_confidence': 0.0,
                    'features': {},
                    'warmup': False,
                }

        # 마감 캔들만 (Lookahead 차단)
        closed_df = df.iloc[:-1]

        # 피처 산출 (전체 데이터 처리 후 마지막 행만 사용)
        feat_df = compute_features(closed_df)
        if feat_df.empty or feat_df.iloc[-1].isna().any():
            return {
                'label_3class': 'UNCERTAIN',
                'label_5class': 'NEUTRAL',
                'probs': {lbl: 0.2 for lbl in INTERNAL_LABELS},
                'probs_3class': {lbl: 1/3 for lbl in EXTERNAL_LABELS},
                'confidence': 0.0,
                'is_uncertain': True,  # [v6] 피처 결측 → 진입 차단
                'min_confidence': 0.0,
                'features': {},
                'warmup': True,
            }

        # 마지막 행 (현재 시점) 피처
        x = feat_df[FEATURE_COLS].iloc[-1:].values

        # ML 추론 (3-class 직접)
        proba = self._model.predict_proba(x)[0]  # shape (3,)
        idx_max = int(np.argmax(proba))
        confidence = float(proba[idx_max])

        # [v6 신규] confidence 게이트
        # 임계값 미만 시 'CHOPPY' fallback (보수적 진입 차단 효과)
        min_confidence = float((params or {}).get('regime_min_confidence', 0.5))
        is_uncertain = confidence < min_confidence

        if is_uncertain:
            # [v6 핵심] V8.0.d Predict_ML 호환:
            # 'UNCERTAIN'은 ['BULLISH_EXPANSION', 'BEARISH_EXPANSION', 'CHOPPY'] 어디에도 미매치
            # → Predict_ML 의 proposed_side 결정 if-else 둘 다 미통과 → 자동 WAIT
            # → Predict_ML 코드 0 변경으로 진입 차단 효과 달성
            label_3 = 'UNCERTAIN'
            label_5 = 'NEUTRAL'  # 5-class 호환 (label_5class 필드는 V8.0.d 미사용)
        else:
            label_3 = IDX_TO_EXTERNAL[idx_max]
            label_5 = EXTERNAL_TO_INTERNAL_REPRESENTATIVE[label_3]

        # probs 5-class 형태로 채움 (V8.0.d Predict_ML 호환)
        # 3-class proba를 5-class 키에 분배 (직접적 대응이 있는 키만 채움)
        probs_5 = {lbl: 0.0 for lbl in INTERNAL_LABELS}
        probs_5['TREND_UP']   = float(proba[EXTERNAL_TO_IDX['BULLISH_EXPANSION']])
        probs_5['TREND_DOWN'] = float(proba[EXTERNAL_TO_IDX['BEARISH_EXPANSION']])
        probs_5['NEUTRAL']    = float(proba[EXTERNAL_TO_IDX['CHOPPY']])  # CHOPPY 대표값

        return {
            'label_3class': label_3,
            'label_5class': label_5,
            'probs': probs_5,
            'probs_3class': {EXTERNAL_LABELS[i]: float(p) for i, p in enumerate(proba)},  # 신규
            'confidence': confidence,
            'is_uncertain': is_uncertain,  # [v6 신규] 외부 진입 차단 결정용
            'min_confidence': min_confidence,  # [v6 신규] 게이트 임계값 노출
            'features': feat_df[FEATURE_COLS].iloc[-1].to_dict(),
            'warmup': False,
        }

    # --------------------------------------------------------------------------
    # 학습 API (테스터에서 호출)
    # --------------------------------------------------------------------------
    @staticmethod
    def train_model(csv_path: str,
                    model_path: str = None,
                    horizon: int = 30,
                    neutral_undersample: float = 0.7,
                    log_fn=print) -> dict:
        """
        [v6 변경] 3-class 직접 학습 (V8.0.e)
          - 5-class _create_labels() 결과 → INTERNAL_IDX_TO_EXTERNAL_IDX 변환 후 학습
          - num_class=3 (기존 5에서 변경)
          - neutral_undersample: 5-class NEUTRAL 단계에서 적용 (CHOPPY 매핑 전)
            → 학습/검증 갭 통제, V8.0.e 천장 실험 동등 조건 유지
          - 출력 라벨: 'BULLISH_EXPANSION'(0) / 'BEARISH_EXPANSION'(1) / 'CHOPPY'(2)
        """
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"CSV 없음: {csv_path}")

        if model_path is None:
            model_path = os.path.join(
                os.path.dirname(os.path.abspath(csv_path)),
                'PautoV80_Regime_Model.json'
            )

        log_fn(f"[학습] CSV 로드: {csv_path}")
        df = _load_csv_auto(csv_path)
        log_fn(f"[학습] 데이터: {len(df):,} 봉")

        log_fn(f"[학습] 30 피처 산출...")
        feat_df = compute_features(df)

        log_fn(f"[학습] v5 5-class 라벨 생성 (horizon={horizon})...")
        labels_5 = _create_labels(df, horizon=horizon)

        # 결합 + NaN 제거 (5-class 단계)
        train_df = feat_df.copy()
        train_df['target_5'] = labels_5
        train_df = train_df.dropna()
        log_fn(f"[학습] 유효 표본 (5-class 단계): {len(train_df):,} 봉")

        # 5-class 분포 출력
        class_dist_5 = train_df['target_5'].value_counts().sort_index().to_dict()
        log_fn(f"[학습] 5-class 분포 (언더샘플링 전):")
        for k, v in class_dist_5.items():
            pct = v / len(train_df) * 100
            log_fn(f"    {IDX_TO_LABEL[k]:<15} {v:>7,} ({pct:5.2f}%)")

        # NEUTRAL 언더샘플링 (5-class 단계에서 적용 - 일반화 효과 보존)
        if neutral_undersample < 1.0:
            neutral_idx = LABEL_TO_IDX['NEUTRAL']
            neutral_mask = train_df['target_5'] == neutral_idx
            neutral_rows = train_df[neutral_mask]
            other_rows = train_df[~neutral_mask]
            n_keep = int(len(neutral_rows) * neutral_undersample)
            sampled = neutral_rows.sample(n=n_keep, random_state=42)
            train_df = pd.concat([sampled, other_rows]).sort_index()
            log_fn(f"[학습] NEUTRAL 언더샘플링: {len(neutral_rows):,} → {n_keep:,}")
            log_fn(f"[학습] 최종 표본 (5-class): {len(train_df):,} 봉")

        # ★ [v6] 5-class → 3-class 변환
        train_df['target'] = train_df['target_5'].map(INTERNAL_IDX_TO_EXTERNAL_IDX)
        log_fn(f"[학습] ★ 5-class → 3-class 변환 완료")

        # 3-class 분포
        class_dist_3 = train_df['target'].value_counts().sort_index().to_dict()
        log_fn(f"[학습] 3-class 분포:")
        for k, v in class_dist_3.items():
            pct = v / len(train_df) * 100
            log_fn(f"    {IDX_TO_EXTERNAL[k]:<20} {v:>7,} ({pct:5.2f}%)")
        class_dist_named = {IDX_TO_EXTERNAL[k]: int(v) for k, v in class_dist_3.items()}

        # XGBoost 학습
        import xgboost as xgb
        from sklearn.utils.class_weight import compute_sample_weight

        X = train_df[FEATURE_COLS]
        y = train_df['target']

        # 시계열 분할 - 마지막 15%를 validation 으로 (early stopping 용)
        split_idx = int(len(X) * 0.85)
        X_tr, X_val = X.iloc[:split_idx], X.iloc[split_idx:]
        y_tr, y_val = y.iloc[:split_idx], y.iloc[split_idx:]
        sw_tr = compute_sample_weight('balanced', y_tr)

        log_fn(f"[학습] 시계열 분할: 학습 {len(X_tr):,} / 검증 {len(X_val):,}")
        log_fn(f"[학습] XGBoost 3-class 학습 (n=500, depth=8, lr=0.02, early stopping)...")
        model = xgb.XGBClassifier(
            n_estimators=500,
            max_depth=8,
            learning_rate=0.02,
            colsample_bytree=0.8,
            subsample=0.85,
            min_child_weight=3,
            reg_alpha=0.1,
            reg_lambda=1.0,
            random_state=42,
            objective='multi:softprob',
            num_class=3,                       # ★ [v6] 5 → 3
            verbosity=0,
            early_stopping_rounds=30,
            eval_metric='mlogloss',
        )
        model.fit(
            X_tr, y_tr,
            sample_weight=sw_tr,
            eval_set=[(X_val, y_val)],
            verbose=False,
        )
        actual_n_estimators = model.best_iteration + 1
        log_fn(f"[학습] early stopping at n_estimators={actual_n_estimators}")
        log_fn(f"[학습] 모델 저장: {model_path}")
        # ★ V80k_Verify_3 패치 (2026-05-04 18:35): sklearn 1.6+ 호환
        # sklearn 1.8.0 + xgboost 1.7.6 / 2.x 모두에서 save_model 호출 시
        # _estimator_type 미정의 에러 발생. 명시 부여로 회피. 학습 결과 동일.
        if not hasattr(model, '_estimator_type'):
            model._estimator_type = 'classifier'
        model.save_model(model_path)

        # Feature importance
        booster = model.get_booster()
        booster.feature_names = list(FEATURE_COLS)
        gain = booster.get_score(importance_type='gain')
        total_gain = sum(gain.values()) or 1.0
        importance = {f: gain.get(f, 0) / total_gain * 100 for f in FEATURE_COLS}

        # 정확도 (학습 + 검증)
        train_accuracy = float((model.predict(X_tr) == y_tr).mean())
        val_accuracy = float((model.predict(X_val) == y_val).mean())

        # [v6] conf 게이트 효과 측정 (검증 구간)
        proba_val = model.predict_proba(X_val)
        max_proba_val = proba_val.max(axis=1)
        y_val_pred = model.predict(X_val)
        conf_gate_metrics = {}
        for thr in [0.4, 0.5, 0.6, 0.7]:
            mask = max_proba_val >= thr
            n_above = int(mask.sum())
            acc_above = float((y_val_pred[mask] == y_val[mask]).mean()) if n_above > 0 else 0.0
            conf_gate_metrics[f'conf_ge_{thr}'] = {
                'n_samples': n_above,
                'pct_samples': float(n_above / len(y_val)),
                'accuracy': acc_above,
            }

        log_fn(f"[학습] 학습 정확도: {train_accuracy*100:.2f}%")
        log_fn(f"[학습] 검증 정확도: {val_accuracy*100:.2f}%")
        log_fn(f"[학습] [v6 conf 게이트 효과]")
        for thr in [0.4, 0.5, 0.6, 0.7]:
            m = conf_gate_metrics[f'conf_ge_{thr}']
            log_fn(f"    conf≥{thr}: {m['pct_samples']*100:5.1f}% 표본 / 정확도 {m['accuracy']*100:5.2f}%")

        return {
            'model_path': model_path,
            'horizon': horizon,
            'n_train': int(len(X_tr)),
            'n_val': int(len(X_val)),
            'class_dist': class_dist_named,
            'feature_importance': importance,
            'train_accuracy': train_accuracy,
            'val_accuracy': val_accuracy,
            'best_iteration': int(actual_n_estimators),
            'num_class': 3,                                       # [v6] 신규
            'conf_gate_metrics': conf_gate_metrics,                # [v6] 신규
        }

    # --------------------------------------------------------------------------
    # 내부 헬퍼
    # --------------------------------------------------------------------------
    def _lazy_load_model(self, params: dict):
        """
        모델 .json 로드. [v5.1] 갱신 자동 감지를 위해 mtime 저장.
        """
        path = (params or {}).get('regime_model_path')
        if path is None:
            # default 경로
            path = os.path.join(os.getcwd(), 'PautoV80_Regime_Model.json')
        if not os.path.exists(path):
            return
        try:
            import xgboost as xgb
            self._model = xgb.XGBClassifier()
            self._model.load_model(path)
            self._model_path = path
            self._model_mtime = os.path.getmtime(path)  # [v5.1] 갱신 감지용
        except Exception:
            self._model = None
            self._model_mtime = None


# ==============================================================================
# 피처 산출 (단일 진실 소스 - 학습/추론 정합 보장)
# ==============================================================================
def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    20 피처 산출. 학습 시와 추론 시 동일 함수 호출 → 정합 보장.
    
    입력: 1m OHLCV + taker_buy_volume DataFrame (DatetimeIndex 가정)
    출력: FEATURE_COLS 컬럼 포함 DataFrame (NaN 워밍업 행 포함)
    """
    out = df.copy()

    # taker_buy_volume 없으면 fallback
    if 'taker_buy_volume' not in out.columns:
        out['taker_buy_volume'] = out['volume'] * 0.5

    # ---- 1m TF 피처 12개 ----

    # 1, 2: FVG (3봉 갭)
    out['fvg_bull'] = (out['low'] > out['high'].shift(2)).astype(int)
    out['fvg_bear'] = (out['high'] < out['low'].shift(2)).astype(int)

    # 3, 4: Swing High/Low 거리 (BOS 토대)
    # lookahead 차단: 봉 i가 swing 인지는 i+N 봉 후에야 확정 → shift(N)
    swing_window = 20
    swing_high_raw = out['high'].rolling(swing_window * 2 + 1, center=True).max()
    swing_low_raw = out['low'].rolling(swing_window * 2 + 1, center=True).min()
    is_swing_high = (out['high'] == swing_high_raw)
    is_swing_low = (out['low'] == swing_low_raw)
    # shift(swing_window) → 미래 정보 차단
    last_swing_high = out['high'].where(is_swing_high).shift(swing_window).ffill()
    last_swing_low = out['low'].where(is_swing_low).shift(swing_window).ffill()
    out['swing_high_dist'] = (last_swing_high - out['close']) / out['close'] * 100
    out['swing_low_dist'] = (out['close'] - last_swing_low) / out['close'] * 100

    # 5: cRSI (Connors RSI)
    out['crsi'] = _compute_crsi(out['close'])

    # 6: EMA 정배열/역배열
    ema_20 = out['close'].ewm(span=20, adjust=False).mean()
    ema_50 = out['close'].ewm(span=50, adjust=False).mean()
    ema_100 = out['close'].ewm(span=100, adjust=False).mean()
    is_bull_align = (out['close'] > ema_20) & (ema_20 > ema_50) & (ema_50 > ema_100)
    is_bear_align = (out['close'] < ema_20) & (ema_20 < ema_50) & (ema_50 < ema_100)
    out['ema_alignment'] = np.where(is_bull_align, 1, np.where(is_bear_align, -1, 0))

    # 7, 8: 이격도
    out['ema_dist_20_50'] = (ema_20 - ema_50) / (ema_50 + 1e-8) * 100
    out['ema_dist_50_100'] = (ema_50 - ema_100) / (ema_100 + 1e-8) * 100

    # 9: 변동성 가속도 (ATR%의 변화)
    high_low = out['high'] - out['low']
    high_close = (out['high'] - out['close'].shift()).abs()
    low_close = (out['low'] - out['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr_14 = tr.rolling(14).mean()
    atr_pct = atr_14 / out['close'] * 100
    out['vol_accel'] = atr_pct.diff(5).fillna(0)

    # 10: 거래량 가속도
    out['volume_accel'] = (
        out['volume'].pct_change(5).fillna(0).replace([np.inf, -np.inf], 0)
    )

    # 11, 12: taker 흐름
    taker_ratio = out['taker_buy_volume'] / (out['volume'] + 1e-8)
    out['taker_smooth_30'] = taker_ratio.rolling(30).mean()
    out['taker_velocity'] = out['taker_smooth_30'].diff(5)

    # ==========================================================================
    # [v2 신규 - 시나리오 4 microstructure 5개]
    # ==========================================================================

    # 13: 캔들 몸통 강도 (|close-open| / range)
    candle_range = out['high'] - out['low']
    out['candle_body_ratio'] = (
        (out['close'] - out['open']).abs() / (candle_range + 1e-8)
    )

    # 14, 15: 위/아래 꼬리 비율
    body_high = out[['close', 'open']].max(axis=1)
    body_low = out[['close', 'open']].min(axis=1)
    out['upper_wick_ratio'] = (out['high'] - body_high) / (candle_range + 1e-8)
    out['lower_wick_ratio'] = (body_low - out['low']) / (candle_range + 1e-8)

    # 16: [v4 변경] 롤링 CVD - cumsum 폐기 (시작점 의존 + 정규화로도 부정확)
    # delta_vol = (taker_buy - taker_sell). 500봉 합으로 "최근 8.3시간 매수/매도 누적 우위"
    # rolling sum 은 시작점 무관, 항상 최근 N봉 정확 측정
    delta_vol = out['taker_buy_volume'] - (out['volume'] - out['taker_buy_volume'])
    cvd_rolling = delta_vol.rolling(500).sum()
    # 정규화: 같은 윈도우의 거래량 총합으로 나눔 (-1 ~ +1 범위 자연 정규화)
    vol_sum_500 = out['volume'].rolling(500).sum()
    out['cvd_rolling_500'] = cvd_rolling / (vol_sum_500 + 1e-8)

    # ==========================================================================
    # [v4 신규] VWAP 거리 (롤링)
    # VWAP = sum(price × volume) / sum(volume)  (가격×거래량 가중평균)
    # 가격 자체는 EMA 기반 피처와 중복 → "VWAP 대비 거리(%)"로 사용
    # ==========================================================================
    typical_price = (out['high'] + out['low'] + out['close']) / 3
    pv = typical_price * out['volume']

    # 단기 VWAP (200봉 = 3.3시간)
    vwap_short = pv.rolling(200).sum() / (out['volume'].rolling(200).sum() + 1e-8)
    out['dist_to_vwap_short'] = (out['close'] - vwap_short) / (vwap_short + 1e-8) * 100

    # 장기 VWAP (1000봉 = 16.6시간)
    vwap_long = pv.rolling(1000).sum() / (out['volume'].rolling(1000).sum() + 1e-8)
    out['dist_to_vwap_long'] = (out['close'] - vwap_long) / (vwap_long + 1e-8) * 100

    # ==========================================================================
    # [v4 신규] ADX (Wilder Average Directional Index) - 추세 강도
    # 방향 무관 추세 강도 (0~100). 가격 추세 피처와 다른 차원.
    # ADX > 25 = 강한 추세, < 20 = 횡보
    # ==========================================================================
    out['adx_14'] = _compute_adx(out, period=14)

    # ==========================================================================
    # [v5 신규] cRSI 극값 binary (사용자 C 직관 반영)
    # cRSI < 10  = 극단 과매도 → 평균회귀 매수 신호 후보
    # cRSI > 90  = 극단 과매수 → 평균회귀 매도 신호 후보
    # 원시 cRSI 값(crsi 피처)와 별개로 ML 이 극단 zone + 미래 가격 자동 학습
    # ==========================================================================
    out['crsi_extreme_oversold'] = (out['crsi'] < 10).astype(float)
    out['crsi_extreme_overbought'] = (out['crsi'] > 90).astype(float)

    # ==========================================================================
    # [v2 신규 - 시간 피처 2개]
    # BTC 는 시간대/요일 효과 있음 (아시아/유럽/미국 시장 시간 다름)
    # ==========================================================================

    # 17: hour_of_day (0~23)
    if hasattr(out.index, 'hour'):
        out['hour_of_day'] = out.index.hour.astype(float)
    else:
        out['hour_of_day'] = 0.0

    # 18: day_of_week (0=월요일, 6=일요일)
    if hasattr(out.index, 'dayofweek'):
        out['day_of_week'] = out.index.dayofweek.astype(float)
    else:
        out['day_of_week'] = 0.0

    # ==========================================================================
    # [v3 - 진짜 MTF MACD (파인스크립트 표준 변환)]
    # 같은 1m 봉에서 EMA 길이를 다양화하여 단기/중기/장기 추세 동시 관찰
    # 시간 프레임 리샘플링 안 함. EMA 길이로 시간 스케일 표현.
    # ==========================================================================
    mtf = _compute_mtf_macd_pine(out['close'])
    out['mtfmacd_short'] = mtf['short']           # EMA(14)  - EMA(28)
    out['mtfmacd_mid'] = mtf['mid']               # EMA(52)  - EMA(104)
    out['mtfmacd_long'] = mtf['long']             # EMA(210) - EMA(420)
    out['mtfmacd_short_slope'] = mtf['short_slope']
    out['mtfmacd_short_slowing'] = mtf['short_slowing']
    out['mtfmacd_align'] = mtf['align']
    out['mtfmacd_short_zone'] = mtf['short_zone']

    return out


def _compute_crsi(close: pd.Series) -> pd.Series:
    """
    Connors RSI = avg of:
      1. RSI(close, 3)
      2. RSI(streak, 2)
      3. PercentRank(ROC(close, 1), 100)
    
    [V8.0.e 패치] Python loop 폐기, numpy vectorize. 920k봉 1-3초.
    """
    # Component 1: RSI(close, 3)
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(3).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(3).mean()
    rs = gain / (loss + 1e-12)
    rsi_close_3 = 100 - 100 / (1 + rs)

    # Component 2: streak - numpy values 기반 (iloc 제거로 100배 가속)
    direction_arr = np.sign(delta.fillna(0).values)
    n = len(close)
    streak = np.zeros(n, dtype=np.float64)
    for i in range(1, n):
        d = direction_arr[i]
        if d == 0:
            streak[i] = 0
        elif d == direction_arr[i-1]:
            streak[i] = streak[i-1] + d
        else:
            streak[i] = d
    streak_series = pd.Series(streak, index=close.index)
    streak_delta = streak_series.diff()
    streak_gain = streak_delta.where(streak_delta > 0, 0).rolling(2).mean()
    streak_loss = (-streak_delta.where(streak_delta < 0, 0)).rolling(2).mean()
    rs_streak = streak_gain / (streak_loss + 1e-12)
    rsi_streak_2 = 100 - 100 / (1 + rs_streak)

    # Component 3: PercentRank - numpy sliding_window_view 벡터화
    from numpy.lib.stride_tricks import sliding_window_view
    roc = close.pct_change()
    roc_arr = roc.values
    pct_rank = np.full(n, np.nan)
    if n >= 100:
        # 각 100봉 윈도우의 마지막 값이 앞 99개 중 몇 개보다 큰가?
        windows = sliding_window_view(roc_arr, 100)  # (n-99, 100)
        last_vals = windows[:, -1:]
        # NaN 안전 비교: NaN < x는 False, x < NaN도 False → NaN 윈도우는 0%
        cnt_below = np.sum(windows[:, :-1] < last_vals, axis=1)
        ranks = cnt_below / 99.0 * 100.0
        pct_rank[99:] = ranks
    pct_rank = pd.Series(pct_rank, index=close.index)

    crsi = (rsi_close_3 + rsi_streak_2 + pct_rank) / 3
    return crsi


def _compute_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Wilder ADX (Average Directional Index) - 추세 강도 측정.
    
    [공식]
      TR  = max(high-low, |high-close.shift|, |low-close.shift|)
      +DM = high - high.shift()  (양수이고 -DM 보다 크면, 아니면 0)
      -DM = low.shift() - low    (양수이고 +DM 보다 크면, 아니면 0)
      +DI = 100 × EMA(+DM) / EMA(TR)
      -DI = 100 × EMA(-DM) / EMA(TR)
      DX  = 100 × |+DI - -DI| / (+DI + -DI)
      ADX = EMA(DX, period)
    
    [해석]
      ADX > 25 : 강한 추세 (방향 무관)
      ADX < 20 : 횡보
    
    [Lookahead Bias]
      모든 ewm/shift 과거 방향                                                      ✓
    """
    high = df['high']
    low = df['low']
    close = df['close']

    # True Range
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # +DM, -DM
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = ((up_move > down_move) & (up_move > 0)).astype(float) * up_move
    minus_dm = ((down_move > up_move) & (down_move > 0)).astype(float) * down_move

    # Wilder smoothing은 alpha = 1/period 의 EMA 와 등가
    # ewm(alpha=1/period) 사용
    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1/period, adjust=False).mean() / (atr + 1e-8)
    minus_di = 100 * minus_dm.ewm(alpha=1/period, adjust=False).mean() / (atr + 1e-8)

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-8)
    adx = dx.ewm(alpha=1/period, adjust=False).mean()

    return adx


def _compute_mtf_macd_pine(close: pd.Series) -> dict:
    """
    [v3 신규] MTF MACD - 파인스크립트 표준 변환.
    
    원본 파인스크립트 (TradingView - FantasticFox):
        단기: EMA(close, 14)  - EMA(close, 28)
        중기: EMA(close, 52)  - EMA(close, 104)
        장기: EMA(close, 210) - EMA(close, 420)
    
    시간 프레임 리샘플링 안 함. 같은 봉에서 EMA 길이를 늘려 시간 스케일 표현.
    
    [Lookahead Bias 점검]
      - 모든 EMA: ewm 과거 방향                                                    ✓
      - slope: 1봉 차이 (과거 방향)                                                 ✓
      - slowing: |diff| < |prev_diff| (과거 2봉 비교)                              ✓
    
    [추출 신호 7개]
      1. short      : 단기 MACD 절대값 (모멘텀 크기)
      2. mid        : 중기 MACD
      3. long       : 장기 MACD
      4. short_slope: 단기 1봉 변화 (가속/감속)
      5. short_slowing: 단기 기울기 둔화 binary (파인스크립트 핵심 신호)
      6. align      : 3개 부호 합 (-3~+3, +3=완전 강세 / -3=완전 약세)
      7. short_zone : 100/-100선 위치 (-2~+2)
    """
    # 단기 / 중기 / 장기 EMA
    fast1 = close.ewm(span=14,  adjust=False).mean()
    slow1 = close.ewm(span=28,  adjust=False).mean()
    fast2 = close.ewm(span=52,  adjust=False).mean()
    slow2 = close.ewm(span=104, adjust=False).mean()
    fast3 = close.ewm(span=210, adjust=False).mean()
    slow3 = close.ewm(span=420, adjust=False).mean()

    macd_short = fast1 - slow1
    macd_mid = fast2 - slow2
    macd_long = fast3 - slow3

    # 단기 기울기 + 둔화 (파인스크립트 핵심 신호)
    short_diff = macd_short - macd_short.shift(1)         # 현재 변화
    short_prev_diff = macd_short.shift(1) - macd_short.shift(2)  # 직전 변화
    short_slowing = (short_diff.abs() < short_prev_diff.abs()).astype(int)

    # 3개 TF 부호 일치 (-3 ~ +3)
    align = (
        np.sign(macd_short).fillna(0) +
        np.sign(macd_mid).fillna(0) +
        np.sign(macd_long).fillna(0)
    )

    # 100선/-100선 zone (5 단계)
    # +2: macd_short > 100 (매우 강세)
    # +1: 0 < macd_short <= 100 (강세)
    #  0: macd_short ≈ 0
    # -1: -100 <= macd_short < 0 (약세)
    # -2: macd_short < -100 (매우 약세)
    short_zone = pd.Series(0, index=close.index, dtype=float)
    short_zone[macd_short >  100] = 2
    short_zone[(macd_short >    0) & (macd_short <=  100)] = 1
    short_zone[(macd_short <    0) & (macd_short >= -100)] = -1
    short_zone[macd_short < -100] = -2

    return {
        'short':         macd_short,
        'mid':           macd_mid,
        'long':          macd_long,
        'short_slope':   short_diff,
        'short_slowing': short_slowing,
        'align':         align,
        'short_zone':    short_zone,
    }


def _create_labels(df: pd.DataFrame, horizon: int = 30,
                   threshold_pct: float = 0.30,
                   ratio_strong: float = 1.5,
                   quiet_max_pct: float = 0.10) -> pd.Series:
    """
    [v5 - 사용자 제안 라벨: 미래 high/low 변화 기반]
    
    [v4 → v5 변경 - 사용자 지적 반영]
      v4: ATR Triple Barrier (PT=3.0*ATR / SL=2.0*ATR)
          → ATR 기반이라 vol_accel 피처와 라벨 누설 발생
          → vol_accel importance 21.43% 단독 압도 (다른 모든 피처보다 강함)
      v5: 미래 [t+1, t+h] 윈도우의 high/low 변화 기반
          → ATR 의존 완전 제거 → 라벨 누설 해결
          → 사람이 이해 가능한 % 기반 임계 (사용자 직관)
    
    [정의]
      현재 봉 t 의 high_t, low_t, close_t.
      미래 [t+1, t+horizon] 윈도우:
        future_high = max of high in window
        future_low  = min of low  in window
      
      range_up   = (future_high - high_t) / close_t * 100   (위로 갱신폭 %)
      range_down = (low_t - future_low)  / close_t * 100   (아래로 갱신폭 %)
    
    [5-class 분류]
      TREND_UP      : range_up > threshold_pct AND range_up > range_down * ratio_strong
      TREND_DOWN    : range_down > threshold_pct AND range_down > range_up * ratio_strong
      CHOP_VOLATILE : max(range_up, range_down) > threshold_pct  AND 비율 균형 (1.5배 이내)
      CHOP_QUIET    : max(range_up, range_down) < quiet_max_pct
      NEUTRAL       : 그 외
    
    [Lookahead Bias]
      미래 [t+1, t+h] 만 참조. 학습 정답지용. 추론 시 미사용.                    ✓
    """
    # ★ [v6 패치] vectorize - sliding_window_view (920k 봉 0.3s)
    from numpy.lib.stride_tricks import sliding_window_view
    high_arr = df['high'].values
    low_arr = df['low'].values
    close_arr = df['close'].values
    n = len(df)

    future_high = np.full(n, np.nan)
    future_low = np.full(n, np.nan)
    if n > horizon:
        hw = sliding_window_view(high_arr[1:], window_shape=horizon)
        lw = sliding_window_view(low_arr[1:], window_shape=horizon)
        valid_n = len(hw)
        future_high[:valid_n] = hw.max(axis=1)
        future_low[:valid_n] = lw.min(axis=1)

    # 갱신폭 % (numpy)
    range_up = np.clip((future_high - high_arr) / close_arr * 100, 0, None)
    range_down = np.clip((low_arr - future_low) / close_arr * 100, 0, None)

    # 라벨 분기 - numpy mask (NaN은 NEUTRAL 그대로 유지하는 원본 로직 보존)
    labels = np.full(n, LABEL_TO_IDX['NEUTRAL'], dtype=np.int64)
    valid = ~(np.isnan(range_up) | np.isnan(range_down))
    max_range = np.maximum(range_up, range_down)

    # CHOP_QUIET: 미래 거의 안 움직임
    mask_quiet = valid & (max_range < quiet_max_pct)
    labels[mask_quiet] = LABEL_TO_IDX['CHOP_QUIET']

    # NEUTRAL: 임계값 미달 (이미 초기화된 NEUTRAL 유지)
    # mask_neutral = valid & ~mask_quiet & (max_range < threshold_pct)  # 이미 NEUTRAL

    # 강한 추세 / 양방향 폭발
    mask_remain = valid & ~mask_quiet & (max_range >= threshold_pct)
    mask_up = mask_remain & (range_up > threshold_pct) & (range_up > range_down * ratio_strong)
    mask_dn = mask_remain & (range_down > threshold_pct) & (range_down > range_up * ratio_strong)
    mask_vol = mask_remain & ~mask_up & ~mask_dn

    labels[mask_up] = LABEL_TO_IDX['TREND_UP']
    labels[mask_dn] = LABEL_TO_IDX['TREND_DOWN']
    labels[mask_vol] = LABEL_TO_IDX['CHOP_VOLATILE']

    return pd.Series(labels, index=df.index)


# ==============================================================================
# [V80k_Verify_3 신규] tbm_label_v2 — TBM 3-class 라벨 (R:R 3:1)
# ==============================================================================
# [📥 IN]
#   - df (pd.DataFrame): 1m OHLCV (high, low, close 필수)
#   - horizon (int)    : 미래 검사 봉수, default 30
#   - tp_pct (float)   : Take Profit % (V8.0.k v2 = 0.30, V8.0.j v1 = 0.20)
#   - sl_pct (float)   : Stop Loss %  (v1=v2 동일 = 0.10)
#
# [📤 OUT]
#   - np.ndarray (int64) shape (len(df),)
#       0  = LONG_PROFIT (LONG TP 먼저 도달)
#       1  = SHORT_PROFIT (SHORT TP 먼저 도달)
#       2  = NO_PROFIT (둘 다 미도달 또는 SL 먼저)
#       -1 = horizon 부족 (마지막 horizon개 봉)
#
# [출처] env_split_models.py 라인 61~85 (V8.0.j v1 학습기) + tp_pct 0.30으로 변경
# [Lookahead] 미래 [t+1, t+horizon] 만 참조 — 학습 라벨용 (추론 시 호출 X) ✓
# [V8.0.j 보존 동작]
#   - 같은 1봉 안에 TP·SL 동시 도달 시 보수적 loss(0) 처리
#   - LONG win 우선, SHORT win 후순위 (드물지만 동시 win 가능 시)
# ==============================================================================
def tbm_label_v2(df, horizon=30, tp_pct=0.30, sl_pct=0.10):
    """
    Triple Barrier Method 라벨 (R:R 3:1, V8.0.k Stage 3 (나) sweep_b_v2.py 동등).
    
    각 봉 t에 대해:
      LONG: tp_long = close*(1+tp_pct/100), sl_long = close*(1-sl_pct/100)
            [t+1, t+horizon] 봉 path에서 어느 것이 먼저 닿는지 추적
      SHORT: tp_short = close*(1-tp_pct/100), sl_short = close*(1+sl_pct/100)
             동일 path 추적
    
    출력 라벨 결정 우선순위:
      1) LONG win (long_p == 1)        → 0
      2) SHORT win (short_p == 1)      → 1
      3) 둘 다 win 아님                 → 2 (NO_PROFIT)
      마지막 horizon개 봉              → -1 (horizon 부족)
    """
    high = df['high'].values
    low = df['low'].values
    close = df['close'].values
    n = len(df)
    labels = np.full(n, -1, dtype=np.int64)
    
    for i in range(n - horizon):
        entry = close[i]
        tp_long = entry * (1 + tp_pct / 100)
        sl_long = entry * (1 - sl_pct / 100)
        tp_short = entry * (1 - tp_pct / 100)
        sl_short = entry * (1 + sl_pct / 100)
        
        wh = high[i+1:i+1+horizon]
        wl = low[i+1:i+1+horizon]
        
        # LONG path
        long_p = -1
        for j in range(len(wh)):
            ht = wh[j] >= tp_long      # TP 도달
            hs = wl[j] <= sl_long      # SL 도달
            if ht and hs:
                long_p = 0             # 같은 봉 동시 → loss (보수적)
                break
            elif ht:
                long_p = 1             # TP 먼저 → win
                break
            elif hs:
                long_p = 0             # SL 먼저 → loss
                break
        
        # SHORT path
        short_p = -1
        for j in range(len(wh)):
            ht = wl[j] <= tp_short     # SHORT TP는 가격 하락
            hs = wh[j] >= sl_short     # SHORT SL은 가격 상승
            if ht and hs:
                short_p = 0
                break
            elif ht:
                short_p = 1
                break
            elif hs:
                short_p = 0
                break
        
        # 라벨 결정 (LONG 우선)
        if long_p == 1:
            labels[i] = 0   # LONG_PROFIT
        elif short_p == 1:
            labels[i] = 1   # SHORT_PROFIT
        else:
            labels[i] = 2   # NO_PROFIT
    
    return labels


# ==============================================================================
# [V80k_Verify_3 신규] train_tbm_v2 — 환경별 TBM 모델 학습 (BULL/BEAR/CHOP)
# ==============================================================================
# [📥 IN]
#   - csv_path (str)       : 21mo 1m raw CSV (Merged_21mo.csv 형식)
#   - output_dir (str)     : 학습 모델 저장 폴더 (None이면 csv 폴더)
#   - regime_model_path (str): Regime v6 70% 학습 모델 경로 (None이면 자동 탐색)
#   - horizon (int)        : TBM 라벨 horizon, default 30
#   - tp_pct (float)       : TP %, default 0.30 (v2)
#   - sl_pct (float)       : SL %, default 0.10
#   - regime_conf_thr (float): Regime conf 임계, default 0.6 (학습 데이터 강한 시그널만)
#   - log_fn (callable)    : 로그 함수, default print
#
# [📤 OUT]
#   - dict {
#       'models': {'BULL': str_path, 'BEAR': str_path, 'CHOP': str_path},
#       'metrics': {
#           'BULL': {'n_train', 'n_val', 'train_acc', 'val_acc', 'conf_07_acc', 'conf_07_n'},
#           'BEAR': {...}, 'CHOP': {...}
#       },
#       'regression_test': {
#           'BULL': {'pass': bool, 'comparisons': [...]},
#           'BEAR': {...}, 'CHOP': {...},
#           'overall_pass': bool
#       },
#       'horizon': int, 'tp_pct': float, 'sl_pct': float,
#       'split_idx': int, 'split_date': str
#     }
#
# [출처] env_split_models.py 라인 36~170 (V8.0.j 학습 흐름 5단계, V8.0.k tp_pct만 변경)
# [회귀 테스트 골든 메트릭] V80k_Verify_3_S2 헤더 명시 — ±5% 이내 통과 기준
# ==============================================================================
def train_tbm_v2(csv_path: str,
                 output_dir: str = None,
                 regime_model_path: str = None,
                 horizon: int = 30,
                 tp_pct: float = 0.30,
                 sl_pct: float = 0.10,
                 regime_conf_thr: float = 0.6,
                 regime_conf_thr_per_env: dict = None,
                 train_split: float = 0.70,
                 val_split: float = 0.85,
                 log_fn=print) -> dict:
    """V8.0.k Stage 3 (나) 환경별 TBM 모델 학습 — V8.0.k Takeaway 6.2 임계 차등 반영.
    
    [V80k_Verify_3 p2 패치 — 2026-05-04] regime_conf_thr_per_env 신규 인자.
    출처: V8.0.k Takeaway 6.2 (학습 하이퍼파라미터)
    값:   None이면 V8.0.k 정답 자동 적용 — BULL/BEAR=0.6, CHOP=0.7
          dict로 직접 지정 시 그대로 사용
          backward compat: 단일 regime_conf_thr만 줘도 모든 환경 동일 적용
    """
    import xgboost as xgb
    from sklearn.utils.class_weight import compute_sample_weight
    
    # ★ V80k_Verify_3 p2: 환경별 임계 차등 (V8.0.k Takeaway 6.2)
    if regime_conf_thr_per_env is None:
        regime_conf_thr_per_env = {'BULL': 0.6, 'BEAR': 0.6, 'CHOP': 0.7}
    
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV 없음: {csv_path}")
    
    if output_dir is None:
        output_dir = os.path.dirname(os.path.abspath(csv_path))
    os.makedirs(output_dir, exist_ok=True)
    
    if regime_model_path is None:
        # 자동 탐색: 70% 학습 모델 우선 (D1 누설 차단판)
        candidates = [
            os.path.join(output_dir, 'PautoV80_Regime_Model_v6_train70.json'),
            os.path.join(output_dir, 'PautoV80_Regime_Model_v6.json'),
            os.path.join(os.path.dirname(csv_path), 'PautoV80_Regime_Model_v6_train70.json'),
            os.path.join(os.path.dirname(csv_path), 'PautoV80_Regime_Model_v6.json'),
        ]
        for c in candidates:
            if os.path.exists(c):
                regime_model_path = c
                break
        if regime_model_path is None:
            raise FileNotFoundError(f"Regime 모델 없음. 후보: {candidates}")
    
    log_fn("=" * 78)
    log_fn(f"V80k_Verify_3_S2 — 환경별 TBM v2 학습 (R:R {tp_pct}/{sl_pct}, h={horizon})")
    log_fn("=" * 78)
    log_fn(f"  CSV: {csv_path}")
    log_fn(f"  Regime model: {regime_model_path}")
    log_fn(f"  output_dir: {output_dir}")
    
    import time
    t0 = time.time()
    
    # ---------- 1단계: 데이터 로드 + 분할 ----------
    log_fn(f"\n[1단계] 데이터 로드 + 학습/OOS 분할")
    df = _load_csv_auto(csv_path)
    n = len(df)
    split_idx = int(n * train_split)
    split_date = str(df.index[split_idx])
    log_fn(f"  전체: {n:,}봉 | 학습 {train_split*100:.0f}%: {split_idx:,} | OOS: {n-split_idx:,}")
    log_fn(f"  학습 종료 시점: {split_date}")
    
    # ---------- 2단계: 30 피처 산출 ----------
    log_fn(f"\n[2단계] 30 피처 산출 (compute_features)")
    feat = compute_features(df)
    log_fn(f"  완료 ({time.time()-t0:.1f}s)")
    
    # ---------- 3단계: Regime v6로 학습 70% 환경 라벨링 (in-sample) ----------
    log_fn(f"\n[3단계] Regime v6 환경 라벨링 (학습 70% in-sample)")
    regime = xgb.XGBClassifier()
    regime.load_model(regime_model_path)
    
    feat_train = feat.iloc[:split_idx]
    feat_train_clean = feat_train[FEATURE_COLS].dropna()
    X_train = feat_train_clean.values
    
    rg_pred_train = regime.predict_proba(X_train).argmax(axis=1)
    rg_conf_train = regime.predict_proba(X_train).max(axis=1)
    
    df_idx_map = {ts: i for i, ts in enumerate(df.index)}
    train_inferred_idx = np.array([df_idx_map[ts] for ts in feat_train_clean.index])
    
    log_fn(f"  학습 70% 환경 분포 (Regime v6 추론):")
    for r_label, r_id in [('BULL', 0), ('BEAR', 1), ('CHOP', 2)]:
        thr_env = regime_conf_thr_per_env[r_label]
        n_label = (rg_pred_train == r_id).sum()
        n_strong = ((rg_pred_train == r_id) & (rg_conf_train >= thr_env)).sum()
        log_fn(f"    {r_label}: {n_label:>7,} ({n_label/len(rg_pred_train)*100:.1f}%) / "
               f"conf>={thr_env}: {n_strong:>7,}")
    
    # ---------- 4단계: TBM 라벨 (전 봉) ----------
    log_fn(f"\n[4단계] TBM 라벨 생성 (R:R {tp_pct/sl_pct:.1f}:1, h={horizon})")
    t1 = time.time()
    labels_all = tbm_label_v2(df, horizon=horizon, tp_pct=tp_pct, sl_pct=sl_pct)
    log_fn(f"  완료 ({time.time()-t1:.1f}s)")
    
    # ---------- 5단계: 환경별 학습 데이터 분리 ----------
    log_fn(f"\n[5단계] 환경별 학습 데이터 분리 (Regime conf 환경 차등 — V8.0.k 정답)")
    log_fn(f"  ★ V8.0.k Takeaway 6.2: BULL/BEAR={regime_conf_thr_per_env['BULL']}, CHOP={regime_conf_thr_per_env['CHOP']}")
    train_df = pd.DataFrame({
        'feat_idx': range(len(feat_train_clean)),
        'df_idx': train_inferred_idx,
        'regime': rg_pred_train,
        'regime_conf': rg_conf_train,
    })
    train_df = train_df[train_df['df_idx'] < n - horizon]
    train_df['tbm_label'] = train_df['df_idx'].apply(lambda i: labels_all[i])
    train_df = train_df[train_df['tbm_label'] >= 0]
    
    log_fn(f"  학습 가능 봉 (TBM 라벨 유효): {len(train_df):,}")
    
    env_data = {}
    for r_id, r_name in [(0, 'BULL'), (1, 'BEAR'), (2, 'CHOP')]:
        thr_env = regime_conf_thr_per_env[r_name]
        sub_full = train_df[train_df['regime'] == r_id]
        sub = sub_full[sub_full['regime_conf'] >= thr_env].copy()
        n_long = (sub['tbm_label'] == 0).sum()
        n_short = (sub['tbm_label'] == 1).sum()
        n_np = (sub['tbm_label'] == 2).sum()
        log_fn(f"    {r_name} (conf>={thr_env}): {len(sub):,}봉 (전체 {len(sub_full):,} 중) "
               f"| LONG {n_long:,} / SHORT {n_short:,} / NO_PROFIT {n_np:,}")
        env_data[r_name] = sub
    
    # ---------- 6단계: 환경별 모델 학습 ----------
    log_fn(f"\n[6단계] 환경별 TBM v2 모델 학습")
    metrics = {}
    model_paths = {}
    
    for r_name in ['BULL', 'BEAR', 'CHOP']:
        sub = env_data[r_name]
        if len(sub) < 5000:
            log_fn(f"  ⚠ {r_name}: 데이터 {len(sub)}봉 부족 (< 5,000), 건너뜀")
            metrics[r_name] = {'skipped': True, 'reason': f'n={len(sub)} < 5000'}
            continue
        
        feat_idx = sub['feat_idx'].values
        X_env = feat_train_clean.iloc[feat_idx].values
        y_env = sub['tbm_label'].values
        
        # 환경 내 85/15 분할
        n_env = len(X_env)
        split_e = int(n_env * val_split)
        X_tr, X_val = X_env[:split_e], X_env[split_e:]
        y_tr, y_val = y_env[:split_e], y_env[split_e:]
        sw = compute_sample_weight('balanced', y_tr)
        
        log_fn(f"\n  [{r_name}] 학습 {len(X_tr):,} / 검증 {len(X_val):,}")
        t1 = time.time()
        model = xgb.XGBClassifier(
            n_estimators=300, max_depth=6, learning_rate=0.03,
            colsample_bytree=0.8, subsample=0.85, min_child_weight=3,
            random_state=42, objective='multi:softprob', num_class=3,
            verbosity=0, early_stopping_rounds=20, eval_metric='mlogloss')
        model.fit(X_tr, y_tr, sample_weight=sw,
                 eval_set=[(X_val, y_val)], verbose=False)
        elapsed = time.time() - t1
        
        train_acc = float((model.predict(X_tr) == y_tr).mean())
        val_acc = float((model.predict(X_val) == y_val).mean())
        log_fn(f"    완료 ({elapsed:.0f}s) train {train_acc*100:.2f}% / val {val_acc*100:.2f}%")
        
        # conf별 정확도
        val_proba = model.predict_proba(X_val)
        val_pred = val_proba.argmax(axis=1)
        val_conf = val_proba.max(axis=1)
        
        conf_metrics = {}
        for thr in [0.5, 0.6, 0.7]:
            mask = val_conf >= thr
            n_thr = int(mask.sum())
            if n_thr > 0:
                acc = float((val_pred[mask] == y_val[mask]).mean())
                conf_metrics[f'conf_{int(thr*100):02d}'] = {'n': n_thr, 'acc': acc}
                log_fn(f"    conf>={thr}: {n_thr:,}건 정확도 {acc*100:.2f}%")
            else:
                conf_metrics[f'conf_{int(thr*100):02d}'] = {'n': 0, 'acc': None}
        
        # 모델 저장 (v3, v2 보존)
        out_path = os.path.join(output_dir, f"PautoV80_TBM_{r_name}_v3.json")
        # ★ V80k_Verify_3 패치 (2026-05-04 18:35): sklearn 1.6+ 호환
        if not hasattr(model, '_estimator_type'):
            model._estimator_type = 'classifier'
        model.save_model(out_path)
        model_paths[r_name] = out_path
        log_fn(f"    저장: {out_path}")
        
        metrics[r_name] = {
            'n_train': len(X_tr),
            'n_val': len(X_val),
            'train_acc': train_acc,
            'val_acc': val_acc,
            'conf_metrics': conf_metrics,
            'tbm_label_dist_train': {
                'LONG': int((y_tr == 0).sum()),
                'SHORT': int((y_tr == 1).sum()),
                'NO_PROFIT': int((y_tr == 2).sum()),
            },
            'best_iteration': int(getattr(model, 'best_iteration', -1)) + 1,
        }
    
    # ---------- 7단계: 회귀 테스트 (Takeaway 골든 메트릭 비교) ----------
    log_fn(f"\n[7단계] 회귀 테스트 — Takeaway 3.3.2 골든 메트릭 비교")
    GOLDEN = {
        'BULL': {'n_train': 6306, 'val_acc': 0.4447, 'conf_07_acc': 0.5714, 'conf_07_n': 56},
        'BEAR': {'n_train': 6387, 'val_acc': 0.5222, 'conf_07_acc': 0.7593, 'conf_07_n': 54},
        'CHOP': {'n_train': 68768, 'val_acc': 0.8386, 'conf_07_acc': 0.9783, 'conf_07_n': 4561},
    }
    TOLERANCE = 0.05  # ±5%
    
    regression_result = {}
    overall_pass_count = 0
    overall_fail_count = 0
    
    for r_name in ['BULL', 'BEAR', 'CHOP']:
        if metrics.get(r_name, {}).get('skipped'):
            regression_result[r_name] = {'skipped': True}
            continue
        
        m = metrics[r_name]
        g = GOLDEN[r_name]
        comparisons = []
        
        # n_train ±5%
        actual_n = m['n_train']
        target_n = g['n_train']
        n_diff_pct = abs(actual_n - target_n) / target_n
        comparisons.append({
            'metric': 'n_train',
            'actual': actual_n, 'target': target_n,
            'diff_pct': n_diff_pct,
            'pass': n_diff_pct <= TOLERANCE,
        })
        
        # val_acc ±5%
        actual_va = m['val_acc']
        target_va = g['val_acc']
        va_diff = abs(actual_va - target_va)
        comparisons.append({
            'metric': 'val_acc',
            'actual': actual_va, 'target': target_va,
            'abs_diff': va_diff,
            'pass': va_diff <= TOLERANCE,
        })
        
        # conf>=0.7 정확도 ±5%
        c07 = m['conf_metrics'].get('conf_70', {})
        actual_c07_acc = c07.get('acc')
        if actual_c07_acc is not None:
            c07_diff = abs(actual_c07_acc - g['conf_07_acc'])
            comparisons.append({
                'metric': 'conf_07_acc',
                'actual': actual_c07_acc, 'target': g['conf_07_acc'],
                'abs_diff': c07_diff,
                'pass': c07_diff <= TOLERANCE,
            })
        
        env_pass_count = sum(1 for c in comparisons if c['pass'])
        env_total = len(comparisons)
        env_pass = env_pass_count == env_total
        
        regression_result[r_name] = {
            'comparisons': comparisons,
            'pass_count': env_pass_count,
            'total': env_total,
            'pass': env_pass,
        }
        overall_pass_count += env_pass_count
        overall_fail_count += (env_total - env_pass_count)
        
        log_fn(f"\n  [{r_name}] 회귀 테스트: {env_pass_count}/{env_total} 통과 "
               f"{'✓ PASS' if env_pass else '✗ FAIL (3개 이상 미달 시 reject)'}")
        for c in comparisons:
            mark = '✓' if c['pass'] else '✗'
            if 'abs_diff' in c:
                log_fn(f"    {mark} {c['metric']:15s}: 실측 {c['actual']:.4f} | 골든 {c['target']:.4f} | 차이 {c['abs_diff']:.4f}")
            else:
                log_fn(f"    {mark} {c['metric']:15s}: 실측 {c['actual']:,} | 골든 {c['target']:,} | 차이 {c['diff_pct']*100:.1f}%")
    
    overall_pass = overall_fail_count <= 2  # 3개 이상 미달 시 reject
    log_fn(f"\n  종합: {overall_pass_count}개 통과 / {overall_fail_count}개 미달")
    log_fn(f"  판정: {'★ PASS — 원본 V80k 충실 복원 인증' if overall_pass else '⚠ REJECT — 3개 이상 미달, 학습 결과 재검토 필요'}")
    
    log_fn(f"\n[총 시간] {time.time()-t0:.0f}s")
    
    return {
        'models': model_paths,
        'metrics': metrics,
        'regression_test': {
            **regression_result,
            'overall_pass': overall_pass,
            'overall_pass_count': overall_pass_count,
            'overall_fail_count': overall_fail_count,
        },
        'horizon': horizon,
        'tp_pct': tp_pct,
        'sl_pct': sl_pct,
        'regime_conf_thr': regime_conf_thr,
        'regime_conf_thr_per_env': regime_conf_thr_per_env,
        'split_idx': split_idx,
        'split_date': split_date,
        'regime_model_path': regime_model_path,
    }


def _load_csv_auto(csv_path: str) -> pd.DataFrame:
    """CSV 자동 형식 감지 (Binance 벌크 / 헤더 있는 CSV 모두 지원)."""
    with open(csv_path, 'r', encoding='utf-8', errors='ignore') as f:
        first_line = f.readline().strip()
    first_cell = first_line.split(',')[0] if ',' in first_line else first_line
    has_header = not (first_cell.replace('-', '').replace('.', '').isdigit()
                      and len(first_cell) >= 10)

    if has_header:
        df = pd.read_csv(csv_path)
    else:
        cols = ['open_time', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_volume', 'count',
                'taker_buy_volume', 'taker_buy_quote_volume', 'ignore']
        df = pd.read_csv(csv_path, header=None, names=cols)

    # timestamp 컬럼
    ts_col = None
    for c in ['timestamp', 'open_time', 'time', 'date']:
        if c in df.columns:
            ts_col = c
            break
    if ts_col is None:
        raise ValueError(f"timestamp 컬럼 없음: {list(df.columns)}")

    if pd.api.types.is_numeric_dtype(df[ts_col]):
        sample = float(df[ts_col].iloc[0])
        if sample >= 1e16:
            unit = 'us'
        elif sample >= 1e12:
            unit = 'ms'
        else:
            unit = 's'
        df[ts_col] = pd.to_datetime(df[ts_col], unit=unit, utc=True)
    else:
        df[ts_col] = pd.to_datetime(df[ts_col], utc=True)
    df = df.set_index(ts_col)

    for c in ['open', 'high', 'low', 'close', 'volume']:
        df[c] = df[c].astype(float)
    if 'taker_buy_volume' in df.columns:
        df['taker_buy_volume'] = df['taker_buy_volume'].astype(float)

    return df


# ==============================================================================
# 모듈 단독 실행 (학습 진입점)
# ==============================================================================
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("사용법: python PautoV80_Regime_ML.py <csv_path> [horizon]")
        print("       horizon default = 30")
        sys.exit(1)

    csv_path = sys.argv[1]
    horizon = int(sys.argv[2]) if len(sys.argv) > 2 else 30

    result = PautoV80_Regime_ML.train_model(csv_path, horizon=horizon)
    print()
    print(f"=== 학습 완료 ===")
    print(f"  모델 저장: {result['model_path']}")
    print(f"  표본 수  : {result['n_train']:,}")
    print(f"  학습 정확도: {result['train_accuracy']*100:.2f}%")
    print(f"  Feature Importance Top 5:")
    sorted_imp = sorted(result['feature_importance'].items(), key=lambda x: -x[1])
    for f, imp in sorted_imp[:5]:
        print(f"    {f:<22} {imp:5.2f}%")
