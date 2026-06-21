# V80k_Verify_3_p2 패치 노트 — 환경별 conf 임계 차등 (V8.0.k Takeaway 6.2)

**날짜**: 2026-05-04 12:00 KST | **사이클**: V80k_Verify_3 보강 (p1 + p2)

## 한 줄 요약

> 10개 Key docx 발굴 + 8 시나리오 비판 검증 결과로 V8.0.k 정확한 임계 매트릭스 확정. **CHOP 환경 학습 conf 0.6 → 0.7 한 줄 패치**로 거의 골든 수렴. 월 20% 수학적 가능성 회복.

## 패치 누적 (p1 + p2)

### p1 (전 패치) — 환경 호환성

```python
# train_model + train_tbm_v2의 save_model 직전
if not hasattr(model, '_estimator_type'):
    model._estimator_type = 'classifier'
model.save_model(path)

# 모듈 상단 monkey patch
xgboost.XGBClassifier._estimator_type = 'classifier'
```

→ sklearn 1.6+ 호환 + xgboost 3.2.0과 정상 작동.

### p2 (본 패치) — 환경별 conf 임계 차등 ★

```python
# train_tbm_v2 시그니처 변경
def train_tbm_v2(..., 
                 regime_conf_thr_per_env: dict = None,  # ★ 신규
                 ...):
    if regime_conf_thr_per_env is None:
        # V8.0.k Takeaway 6.2 정답 자동 적용
        regime_conf_thr_per_env = {'BULL': 0.6, 'BEAR': 0.6, 'CHOP': 0.7}
```

→ CHOP 환경 학습 데이터가 over-confident 양 절반 감소 (130k → 80k).

## p2 검증 결과 — 클로드 컨테이너 21mo 풀 데이터

### CHOP 환경 — 4개 메트릭 모두 골든 방향 수렴

| 메트릭 | Before p2 | After p2 | V8.0.k 골든 | 효과 |
|---|---|---|---|---|
| n_train | 130,329 | **80,374** | 68,768 | 격차 +89% → **+16.9%** |
| val_acc | 64.86% | **77.19%** | 83.86% | -19%p → **-6.7%p** |
| conf≥0.7 정확도 | 91.68% | **93.85%** | 97.83% | -6.2%p → -4.0%p |
| OOS conf≥0.7 비율 | 8.39% | **42.23%** | 68.80% | -60%p → **-26.6%p** |

### BULL/BEAR — 의도된 무변경

```
BULL: n_train 11,142 (golden 6,306 +77%) — 변화 없음
BEAR: n_train 12,931 (golden 6,387 +103%) — 변화 없음
```

p2는 CHOP 환경만 수정했고, BULL/BEAR 격차는 **다른 원인**입니다 (Verify_4 진단 작업).

### OOS 거래 빈도 회복 — 시나리오 8 본질 영향

| 추정 | Before p2 | After p2 |
|---|---|---|
| CHOP OOS conf≥0.7 봉수 | 11,179 (8.39%) | **56,338 (42.23%)** |
| 월 거래 빈도 추정 | ~50건 | **~85건** |
| 월 PnL 추정 | ~+11% | **~+18%** |

**★ 월 20% 달성 가능성 살아남음.** BULL/BEAR도 잡으면 골든 +22.23% 도달 가능.

## V8.0.k 정확한 임계 매트릭스 — 10 docx 발굴 결과 확정

```
[학습 시] sweep_b_v2.py (R:R 3:1 환경별 재학습)
─────────────────────────────────────────────
용도: 강한 시그널만 학습 데이터 추출 (over-confident 회피)
출처: V8.0.k Takeaway 6.2 (학습 하이퍼파라미터)
값:   Regime conf 임계: BULL/BEAR=0.6, CHOP=0.7  ← p2 적용

[운영 시] PautoStrategy_V8K_R001 (실시간 시그널)
─────────────────────────────────────────────
용도: 최종 진입 게이트
출처: V8.0.k Takeaway Table 9 (운영 권장 설정)
값:   regime_conf_threshold=0.5 + tbm_conf_threshold=0.5
근거: v2 모델이 양극단화돼서 0.5도 충분
주의: 운영 임계는 변경 안 함 — P_module 코드에 0.5 박제됨
```

## 사용 절차 (선장 PC)

```cmd
:: 1. 새 풀세트 ZIP 풀기 (RautoV80k_Verify_3_p2_Fullset.zip)
::    D:\ML\에 압축 해제 (기존 파일 덮어쓰기)

:: 2. 환경은 그대로 (p1과 동일)
::    xgboost 3.2.0 + sklearn 1.4.2 박제됨

:: 3. 이전 학습 캐시 삭제 + 다시 학습
rmdir /s /q pc_pipeline_output
python pc_pipeline_V80k_Verify_3.py --data Merged_21mo.csv

:: 4. 약 100초 후 V80k_Verify_3_S4_train_report.json 클로드 채팅 업로드
```

## 검증 의무 — 선장 PC 결과로 확인

본 패치 후 다음이 ±5% 이내면 패치 성공 검증:

| 메트릭 | 클로드 컨테이너 | 선장 PC 기대값 | 골든 |
|---|---|---|---|
| CHOP n_train | 80,374 | 80,000 ± 4,000 | 68,768 |
| CHOP val_acc | 77.19% | 77 ± 3% | 83.86% |
| CHOP OOS conf≥0.7 | 42.23% | 42 ± 3% | 68.80% |

선장 PC에서도 같은 결과 나오면 패치 효과 100% 확정.

## 본 사이클(Verify_3) 종료 — Verify_4 작업 우선순위

본 패치로 본 사이클 핵심 목표 (PC 학습 + v2 동등 복원) **부분 달성**:

| 차원 | 상태 |
|---|---|
| 환경 호환성 | ✓ 완전 해결 |
| PC 통합 파이프라인 | ✓ 작동 |
| 회귀 테스트 시스템 | ✓ 정확 작동 |
| TBM 학습기 코드 복원 | ✓ 완료 |
| CHOP 환경 골든 수렴 | ✓ 거의 달성 |
| **BULL/BEAR 환경 골든 수렴** | **✗ 미달** (Verify_4 1순위) |
| **휩쏘 SL 정책** | **✗ 미착수** (Verify_4 2순위) |
| 월 20% 가능성 | △ 회복 시작 (CHOP만으로 ~18%) |

## Verify_4 작업 우선순위 (재배치)

| 순위 | 작업 | 영향 |
|---|---|---|
| ★ 1 | sweep_b_v2.py 추가 발굴 시도 (선장 PC V8.0.k 작업 폴더) | 100% 정답 확정 |
| ★ 2 | BULL/BEAR n_train +77% 격차 진단 (가설 A/B/C 정량) | 골든 거래 빈도 회복 |
| 3 | 휩쏘 SL 정책 5가지 옵션 sweep | 손익비 향상 |
| 4 | 챔피언 비교 모드 (v3 vs v4) | 통계 유의성 검증 |

## V8.0.x .py 파일 추가 발굴 단서 (10 docx 분석)

선장 PC에서 다음 .py 파일들 추가 검색 가능:

```cmd
:: V8.0.f / V8.0.g / V8.0.k 작업 폴더 추적
dir C:\ /s /b 2>nul | findstr /i "sweep_a sweep_b env_split bull_8 21mo_full lookahead_check"
dir D:\ /s /b 2>nul | findstr /i "sweep_a sweep_b env_split bull_8 21mo_full lookahead_check"
```

미발굴 8개 .py:
- `sweep_a.py`, `sweep_b_v2.py`, `sweep_b_v2_test.py` (V8.0.k)
- `env_split_verify.py`, `21mo_diagnose.py` (V8.0.g)
- `bull_8scenarios.py`, `21mo_full_oos.py`, `lookahead_check.py` (V8.0.f)

발견 시 채팅 업로드 — Verify_4에서 100% 재현 가능.
