# V80k_Verify_3_p1 패치 노트 — 환경 호환성 fix

**날짜**: 2026-05-04 18:35 KST | **사이클**: V80k_Verify_3 보강 (p1)

## 한 줄 요약

> 선장 PC 첫 실행 시 발생한 두 에러를 진단 + 해결. **`setup_env.bat` 한 번 실행** 후 다시 학습 시작하시면 끝까지 통과합니다.

## 진단된 두 에러

### 에러 1: `_estimator_type undefined` (TypeError)

```
File "xgboost\sklearn.py", line 765, in save_model
    meta["_estimator_type"] = self._get_type()
TypeError: `_estimator_type` undefined
```

**원인**: scikit-learn 1.6+에서 `BaseEstimator._estimator_type` 처리 방식 변경. xgboost(어느 버전이든)와 충돌.

**해결**: scikit-learn을 1.4.2로 박제 (setup_env.bat 자동) + 코드에 monkey patch 안전장치 추가.

### 에러 2: `predict_proba` 결과 형태 깨짐

```
predict_proba shape: (3, 1286226)   ← 비정상 (정상은 (643113, 3))
```

**원인**: V80k_Verify_2 풀세트의 `PautoV80_Regime_Model_v6_train70.json`은 **xgboost 3.2.0**으로 학습됨. xgboost 1.7.6 또는 2.x로 추론 시 형태 호환 깨짐.

**해결**: xgboost 3.2.0으로 박제 (setup_env.bat 자동). 절대 1.7.6/2.x로 다운그레이드 금지.

## 수정된 파일 (3개)

| 파일 | 변경 내용 |
|---|---|
| `setup_env.bat` | xgboost 3.2.0 + sklearn 1.4.2 박제 (정정판) |
| `PautoV80_Regime_ML.py` | 모듈 상단 monkey patch (`_estimator_type` 부여) + save_model 두 위치 안전장치 |
| `pc_pipeline_V80k_Verify_3.py` | Step 1 환경 검증 강화 — 부적합 버전 감지 시 즉시 abort + 안내 |

## 검증 결과 (클로드 컨테이너)

선장 PC와 동일 환경(xgboost 3.2.0 + sklearn 1.4.2)에서 21mo 풀 데이터로 풀 사이클 검증:

| Step | 결과 |
|---|---|
| 1. 환경 검증 | ✓ 통과 |
| 2~3. CSV + 피처 | ✓ 920,160봉 / 30 피처 (10초) |
| 4. Regime 70% | ✓ 기존 모델 사용 (skip) |
| 5. TBM v3 환경별 학습 | ✓ BULL/BEAR/CHOP 모두 학습 (74초) |
| 6. 학습 메트릭 회귀 | ⚠ 3/9 통과 — 골든의 2배 학습 데이터 |
| 7. OOS conf 분포 회귀 | ⚠ 0/3 통과 — conf>=0.7 비율 1/3~1/8 |
| 8. train_report.json | ✓ 자동 생성 |
| 9. ZIP 빌드 | (회귀 미달로 skip — 의도된 동작) |

**총 시간**: 92초 (선장 PC는 더 빠를 것)

## ★ 회귀 테스트 미달 — 격차 분석 (다음 사이클 작업)

본 패치로 **환경 호환성**은 100% 해결됐으나, 학습 결과가 V8.0.k 골든과 격차 큽니다:

| 메트릭 | 골든 (Takeaway 3.3.2) | 신규 학습 실측 | 격차 |
|---|---|---|---|
| BULL n_train | 6,306 | ~12,931 | +105% |
| BEAR n_train | 6,387 | 12,931 | +103% |
| CHOP n_train | 68,768 | 130,329 | +89% |
| BULL conf≥0.7 OOS | 22.7% | 9.20% | −13.5%p |
| BEAR conf≥0.7 OOS | 29.5% | 6.01% | −23.5%p |
| CHOP conf≥0.7 OOS | 68.8% | 8.39% | −60.4%p |

**원인 가설** (Verify_4 진단 작업):

1. **conf 임계 차이**: V8.0.k는 conf≥0.7로 필터링했을 가능성 (현재 train_tbm_v2 기본 0.6)
2. **학습 데이터 범위**: V8.0.k는 다른 기간 사용했을 수 있음 (env_split_models.py 미발굴 → sweep_b_v2.py 풀 코드 필요)
3. **xgboost 시드 동작**: v3.2.0과 V8.0.k 학습 시점 버전 차이

## 사용 절차 (선장님 진행 방법)

```cmd
:: 1. setup_env.bat 한 번만 실행 (3분)
cd D:\ML
setup_env.bat

:: 2. 이전 실패한 학습 캐시 삭제
rmdir /s /q pc_pipeline_output

:: 3. 다시 학습 시작 (이번엔 끝까지 통과)
python pc_pipeline_V80k_Verify_3.py --data Merged_21mo.csv
```

학습 끝나면 **`pc_pipeline_output/V80k_Verify_3_S4_train_report.json`** (~30KB) 한 파일만 채팅에 올려주세요. 회귀 미달 격차 진단부터 다음 사이클(Verify_4) 시작합니다.

## 본 사이클 한계 (인수인계 보고서 보강)

본 패치 작업으로 새로 드러난 한계 — 다음 사이클 인수인계 시 명기 필요:

- 패키지 호환성 검증을 mock dry-run에 의존 → 실데이터 save 단계 누락 (이번 사이클 발견)
- env_split_models.py만 풀 발굴, **sweep_b_v2.py 미발굴** → V8.0.k 정확한 학습 절차 100% 재현 어려움
- 학습 결과 격차 → "v2 동등 복원" 목표 부분 달성 (환경/구조는 OK, 메트릭은 미달)

