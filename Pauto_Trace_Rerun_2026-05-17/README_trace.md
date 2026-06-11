# Pauto v3.4 Trace 재실행 패키지 — 새 채팅 Claude 요청 1

## 목적

새 채팅 Claude(5-pass)가 발견한 점프 ⓟ-12 (ATR 학습/추론 불일치) 검증.
OOS 12mo 525,540봉의 *prob/regime/action trace*를 csv로 저장 → 분석.

## 사용자 PC 실행 순서

### Step 1 — 폴더 준비

zip을 풀면 `v34_pauto_trace/` 폴더 생성. 이 폴더를 *기존 v3.4 작업 폴더 옆*에 둠:

```
D:\ML\Verify\
├── Pauto_v76_2026-05-16\              ← Merged_Data.csv 있는 곳
└── v34_pauto_trace_2026-05-17\        ← 본 패키지
```

### Step 2 — 필요 파일 복사

본 패키지 폴더 안으로 다음 3개 파일 복사:

```cmd
cd D:\ML\Verify\v34_pauto_trace_2026-05-17

copy ..\Pauto_v76_2026-05-16\Merged_Data.csv .
copy ..\Pauto_v76_2026-05-16\PautoV75_XGB_1to3_Predictor.json .
copy ..\Pauto_v76_2026-05-16\PautoV75_XGB_1to3_Predictor_meta.json .
```

### Step 3 — 실행 (예상 70~90분)

```cmd
python pautov75_signal_wrapper_trace.py
```

**예상 시간**: 약 70분 (기존 신호 추출 69.66분 + trace 저장 약간).
**출력 파일**:
- `outputs_v34_pauto_trace/trace.csv` (약 30MB, 525,540행)
- `outputs_v34_pauto_trace/trace_stats.json`

### Step 4 — 결과 압축해서 Claude에 업로드

`outputs_v34_pauto_trace/` 폴더 통째로 zip 압축 후 업로드.

## 본 패키지 파일

| 파일 | 설명 |
|---|---|
| `pautov75_signal_wrapper_trace.py` | trace 로깅 wrapper + 분석 함수 |
| `Predict_ML_PautoV75.py` | 추론 모듈 (변경 없음, 기존 v3.4와 동일) |
| `Regime_Master_PautoV75.py` | regime 모듈 (변경 없음) |
| `README_trace.md` | 본 파일 |

## 본인 검증

합성 데이터 1000봉으로 동작 확인 완료. 작동 사실:
- trace.csv가 525,540행 × 5컬럼 (bar_idx/timestamp/prob/regime/action) 생성됨
- 분석 함수가 prob 분포 buckets + regime/action 교차 자동 출력
- WAIT 봉은 prob=NaN (Predict_ML이 reason에 prob 안 적음). 정상.
- OPEN_LONG/SHORT 봉만 prob 분포 분석에 사용됨

## 새 채팅 Claude 검증할 내용

다음 분석 결과로 ⓟ-12 가설 검증:
1. **prob 평균 (OPEN_SHORT 봉)**: 학습 ATR이 *낮으면* 학습 모델이 long_success 자주 봤음 → OOS에선 *정상 ATR로 ATR_14 값이 학습 시보다 큼* → prob *시프트* 가능
2. **prob 분포의 좌측 꼬리**: 0.0~0.2 사이가 얼마나 두꺼운지 정량 확인
3. **regime 분포**: 100% CHOPPY인지 직접 검증
4. **prob의 시간 변화**: trace.csv를 시계열로 보면 *분포 drift* 확인 가능
