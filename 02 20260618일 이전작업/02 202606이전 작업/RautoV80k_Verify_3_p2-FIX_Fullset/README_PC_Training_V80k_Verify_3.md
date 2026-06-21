# V80k_Verify_3 PC 학습 가이드

**내부버전**: V80k_Verify_3 / **작성일**: 2026-05-04 / **사이클**: V80k_Verify_3

## 한 줄 요약

> 선장 PC에서 한 명령으로 21mo 데이터 → 학습 → OOS 검증 → ZIP 패키징까지 자동 진행. 클로드는 **`V80k_Verify_3_S4_train_report.json` (~30KB)** 만 받음.

## 사전 준비 (1회만)

### 1. 환경 설치

```cmd
pip install -r requirements_V80k_Verify_3.txt
```

### 2. 데이터 준비

선장 PC의 다음 위치에 21mo 1m raw CSV 배치:

```
C:\Pauto\data\Merged_21mo.csv   (또는 임의 경로)
```

CSV 컬럼: `timestamp, open, high, low, close, volume, taker_buy_volume`

### 3. (선택) 기존 Regime 70% 모델 활용

V80k_Verify_2 패키지에 `PautoV80_Regime_Model_v6_train70.json`(33MB)이 있으면 같은 폴더에 복사. **이 모델 재사용 시 학습 시간 15~30분 절약**.

## 실행 (한 명령)

```cmd
cd C:\<V80k_Verify_3 폴더>
python pc_pipeline_V80k_Verify_3.py --data C:\Pauto\data\Merged_21mo.csv --tag 3balancedTBM_R002
```

옵션:

| 플래그 | 설명 | 기본값 |
|---|---|---|
| `--data` | 21mo CSV 경로 | (필수) |
| `--tag` | 신규 모델 시리즈 태그 | `3balancedTBM_R002` |
| `--output-dir` | 출력 폴더 | `./pc_pipeline_output` |
| `--skip-regime` | Regime 재학습 안 함 (기존 70% 모델 사용) | False |
| `--tp-pct` | TBM TP % | 0.30 (V8.0.k) |
| `--sl-pct` | TBM SL % | 0.10 |
| `--horizon` | TBM 라벨 horizon (봉) | 30 |

## 자동 진행 9단계

```
[Step 1] 환경 검증     - Python/xgboost/pandas/RAM 검사 (5초)
[Step 2] CSV 로드     - _load_csv_auto (1~3분)
[Step 3] 30 피처 산출  - compute_features (3~5분)
[Step 4] Regime 70% 학습 - 또는 기존 사용 (15~30분 또는 skip)
[Step 5] TBM v3 환경별 학습 - BULL/BEAR/CHOP 각 ~5분 (15분)
[Step 6] 학습 메트릭 회귀 - Takeaway 3.3.2 골든 비교
[Step 7] OOS 추론 + conf 분포 회귀 - Takeaway 3.3.3 골든 비교
[Step 8] train_report.json 생성 - 클로드 업로드용 (~30KB)
[Step 9] Strategy ZIP 빌드 - 3balancedTBM_R002.zip
```

**예상 총 시간**: 30~60분 (Regime skip 시 30분, 풀 학습 시 60분)

## 산출물

```
pc_pipeline_output/
├── PautoV80_Regime_Model_v6_train70.json    (33MB, 기존 또는 신규)
├── PautoV80_TBM_BULL_v3.json                (4.5MB)
├── PautoV80_TBM_BEAR_v3.json                (4.4MB)
├── PautoV80_TBM_CHOP_v3.json                (5.3MB)
├── V80k_Verify_3_S4_train_report.json       ★ 클로드 업로드용 (~30KB)
├── 3balancedTBM_R002.zip                    ★ AWS 배포 ZIP (12~13MB)
└── pipeline.log                             상세 로그
```

## 결과 확인

### ★ PASS인 경우

```
[Step 8] 종합 판정: ★ PASS
권장: 학습 + OOS 분포 모두 골든 일치. 단계 9 ZIP 빌드 진행 → AWS 배포 가능.
```

→ `3balancedTBM_R002.zip`을 AWS Windows 서버의 `strategies/` 폴더에 복사. 챔피언 시스템 GUI에서 자동 인식.

→ 클로드 채팅에 **`V80k_Verify_3_S4_train_report.json` 한 파일만** 업로드. 클로드가 다음 사이클(Verify_4) 작업 권장.

### ⚠ FAIL인 경우

```
[Step 8] 종합 판정: ⚠ FAIL
권장: <원인 진단>
```

→ ZIP 빌드 자동 skip. 다음을 확인:
1. 데이터가 V8.0.k 학습 시점과 다른가? (CSV 끝 날짜 확인)
2. Regime 70% 모델이 정확한가? (훈련 데이터 범위 확인)
3. xgboost 버전 차이? (1.x vs 2.x — 시드 동작 다를 수 있음)

→ `V80k_Verify_3_S4_train_report.json` + `pipeline.log` 클로드 업로드. 클로드가 진단.

## 회귀 테스트 골든 메트릭

학습 후 다음이 ±5% (절대) 이내면 통과:

### 학습 메트릭 (Takeaway 3.3.2)

| 모델 | n_train | val_acc | conf≥0.7 정확도 |
|---|---|---|---|
| BULL_v2 | 6,306 | 44.47% | 57.14% |
| BEAR_v2 | 6,387 | 52.22% | 75.93% |
| CHOP_v2 | 68,768 | 83.86% | 97.83% |

### OOS conf 분포 (Takeaway 3.3.3)

| 환경 | conf≥0.7 비율 |
|---|---|
| BULL | 22.7% |
| BEAR | 29.5% |
| CHOP | 68.8% |

3개 이상 미달 시 자동 reject + 원인 진단.

## 자주 묻는 질문

### Q. 학습 시간이 너무 오래 걸려요

`--skip-regime` 옵션으로 기존 Regime 70% 모델 사용 시 15~30분 절약. 첫 시도 후 부담 크면 다음 사이클에서 incremental fine-tune 옵션 도입 검토.

### Q. xgboost OOM (메모리 부족)

```
MemoryError: ...
```

→ RAM 8GB+ 필요. 또는 `compute_features`의 chunk 옵션 사용 (다음 사이클).

### Q. 회귀 테스트 미달

골든 메트릭과 ±5% 이상 차이 → 데이터·시드·버전 차이 가능성. `train_report.json`에 정확한 격차 기록됨. 클로드 업로드하면 분석.

### Q. ZIP을 AWS에 어떻게 배포?

`3balancedTBM_R002.zip`을 AWS Windows 서버의 `strategies/` 폴더에 복사. ChampionGUI 시작 시 자동 스캔.

## 다음 사이클(V80k_Verify_4) 핵심 문제제기 ★

**"휩쏘(Stop Hunt / Liquidity Sweep)를 이길 SL 정책 찾기"**

V80k_Verify_2 47h 가동 PASS #3 사례 분석에서 더블 sweep + 진짜 방향 +1.03% 패턴 확인. 본 사이클은 v2 동등 복원이 목적이라 SL 정책 변경 안 함. Verify_4에서 5가지 옵션 sweep 검증 필요. 자세히 `docs/Key_V80k_Verify_3_10_TBM_OB_Mismatch_StopHunt.docx` 참조.

---

*선장: 사용자 / 항해사: Claude / 작성일: 2026-05-04*
