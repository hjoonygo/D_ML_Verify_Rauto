# Rauto V34 Phase B 측정 가이드

**작성일**: 2026-05-18  
**목적**: 안 A (동적 Hard SL) + 안 D (변동성 임계 진입 필터) 36mo 실측

---

## 1. 사용자 PC 환경 요구사항

| 항목 | 요구 |
|---|---|
| OS | Windows (BAT 실행용) |
| Python | 3.10+ |
| 패키지 | pandas, numpy, xgboost, scipy |
| 데이터 | `D:\ML\Verify\Merged_Data.csv` (36mo BTC 1m봉 + oi_sum) |
| 디스크 여유 | 약 1GB |
| 예상 시간 | 1.5~3시간 |

---

## 2. 설치 + 실행 (한 줄 요약)

```
1. zip 파일을 D:\ML\Verify\v34_phase_b_2026-05-18\ 로 압축 해제
2. Merged_Data.csv가 D:\ML\Verify\ (상위 폴더)에 있는지 확인
3. run_v34_phase_b.bat 더블 클릭 (또는 python run_all.py 직접 실행)
4. 학습 묻는 단계: 기존 모델 재사용(Y) 또는 재학습(N)
5. 완료 후 outputs_phase_b\ 폴더를 zip하여 업로드
```

**BAT 구조 (이번 수정)**: BAT은 단순히 `python run_all.py`를 호출하는 1줄짜리. 모든 분기/입력/학습/측정 로직이 run_all.py 안에 있어서 BAT 인코딩 문제 회피.

**고급 옵션 (CMD에서 직접 실행 시)**:
```
python run_all.py                # 기본
python run_all.py --auto-yes     # 모든 프롬프트 자동 (재학습 강제)
python run_all.py --skip-train   # 학습 건너뛰기 (기존 모델 재사용)
python run_all.py --skip-test    # 단위 테스트 건너뛰기
```

---

## 3. 폴더 구조

```
D:\ML\Verify\
├── Merged_Data.csv  ← 사용자 PC의 기존 데이터
└── v34_phase_b_2026-05-18\  ← 이 zip을 풀어놓는 위치
    ├── ML_Predictor_Pipeline_v2.py  (학습 파이프라인)
    ├── Predict_ML_v2.py  (추론)
    ├── Regime_Master_v2.py  (장세)
    ├── tf_aggregator_v2.py  (TF 변환)
    ├── ob_provider_v2.py  (OB 검출)
    ├── tbm_simulator_v7.py  (안 A 동적 Hard SL)
    ├── pautov75_signal_wrapper_v3.py  (안 D 변동성 필터)
    ├── train_phase_b.py  (자동 70% 학습 wrapper)
    ├── measure_v34_phase_b.py  (12 그리드 측정)
    ├── test_v7_phase_a.py  (단위 테스트 8개)
    ├── run_v34_phase_b.bat  ← 더블 클릭
    ├── Handover_v34_phase_b_2026-05-18.docx  (인수인계 보고서)
    ├── Key_Phase_A_Findings_2026-05-18.docx  (주요 발견)
    ├── PautoV75_XGB_3class_v2.json  (재학습 시 새로 생성됨)
    └── outputs_phase_b\  (실행 후 생성)
        ├── all_scenarios_phase_b.csv  ← 핵심 결과
        ├── trades_*.csv  (12개 시나리오별 거래 log)
        └── measure_log.txt
```

---

## 4. 그리드 (12 시나리오)

| 변수 | 값 |
|---|---|
| ATR multi | 1.5, 2.0, 2.5, 3.0 |
| Lev | 10 (고정) |
| Filter | off, p20_p80, p10_p90 |
| **총** | **4 x 1 x 3 = 12** |

고정: OB TF 60m, Holding 28봉, fib_trigger 1.2%, Rolling lookback 14일

---

## 5. 단계별 진행

### 5.1 학습 (선택)
- 기존 모델 PautoV75_XGB_3class_v2.json이 있으면 재사용 가능
- 재학습 시 약 10~20분 소요
- 자동으로 첫 70% IS / 나머지 30% OOS 분할

### 5.2 단위 테스트
- BAT가 자동 실행 (약 3분)
- 8/8 통과해야 측정 진행
- 실패 시 BAT가 멈추고 사용자 확인 요청

### 5.3 측정
- 12 시나리오 약 1~3시간
- 진행 상황은 콘솔에 출력
- 결과는 outputs_phase_b\ 폴더에 자동 저장

---

## 6. 결과 회수

측정 완료 후:
1. `D:\ML\Verify\v34_phase_b_2026-05-18\outputs_phase_b\` 폴더 통째로 zip
2. Claude 새 채팅창에 업로드

업로드 받는 파일:
- `all_scenarios_phase_b.csv` (요약, 핵심 결과)
- `trades_*.csv` (12개 시나리오별 거래 log)
- `measure_log.txt` (전체 로그)

---

## 7. 트러블슈팅

| 증상 | 원인 | 해결 |
|---|---|---|
| "Python을 찾을 수 없습니다" | python 미설치 / PATH 미설정 | python --version 확인 후 PATH 추가 |
| "Merged_Data.csv 없음" | 데이터 위치 오류 | D:\ML\Verify\ 에 두기 |
| 단위 테스트 실패 | 패키지 누락 | pip install pandas numpy xgboost scipy |
| 학습 실패 | 메모리 부족 | 다른 프로그램 종료 |
| 시간이 너무 오래 걸림 | CPU 성능 | 그대로 두고 기다리거나 새 채팅창에 알림 |

---

## 8. 핵심 발견 사항 (Phase A에서)

Phase A 합성 데이터 27 시나리오 결과:

| 효과 | 변화 |
|---|---|
| **안 A** (Hard SL 비율) | ATR 1.5 → 65.7%, ATR 3.0 → 38.0% (-28%p) |
| **안 D** (평균 PF) | off 0.43, p20_p80 0.66 (+53%), p10_p90 0.74 (+72%) |
| **알파 후보** | atr3.0_filterp10_p90 = PF 1.196 (n=24, 작음) |

신뢰도: 안 A/D 작동 90% 직접, 실제 36mo 동일 방향 75% 추론, 알파 임계 PF 1.3 달성 *모름*

---

## 9. 본인(Claude) 메타 인지

- **자신**: 안 A+D가 *방향성 효과*는 학술 + 합성으로 90% 입증
- **모름**: 정확한 PF 수치, 사용자 자본 ROE 허용 결정
- **위험**: 합성 ATR 분포 좁아 필터 효과 *축소 측정*됨 - 실제에선 더 큰 효과 가능성

---

자세한 내용은 `Handover_v34_phase_b_2026-05-18.docx` + `Key_Phase_A_Findings_2026-05-18.docx` 참조.
