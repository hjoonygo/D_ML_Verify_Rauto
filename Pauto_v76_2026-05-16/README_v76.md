# Pauto v7.6 패키지 — 복리 구조 + 학습기간 분리 정정판

## v7.6 = v7.5 + 2가지 점프 정정

| 점프 | v7.5 (원본) | v7.6 (정정) |
|---|---|---|
| **점프 ⓟ-1, ⓟ-2** capital 리셋 | 수익 시 spot_wallet 인출 → capital $10K 리셋. 복리 효과 0 | spot_wallet 인출 제거. 순수 복리. + 자본 0 도달 시 강제청산 안전장치 |
| **점프 ⓟ-9** 학습=백테스트 동일 데이터 | 36mo 전체로 학습 → 36mo 전체로 백테스트 (IS 결과, look-ahead) | 학습기간 인자 추가. 24mo 학습 + 12mo OOS 권장 |

## 검증 완료

- `test_pauto_v76_compounding.py` → **8/8 통과** (복리 + 강제청산 + 분할익절)
- `test_train_period_separation.py` → **5/5 통과** (학습기간 분리)
- xgboost 통합 테스트 → 진짜 학습 + 추론 정상 작동 확인

## 폴더 구성

```
pauto_v76/
├── Backtest_Engine_PautoV75.py          ★ v7.6 정정 (복리)
├── ML_Predictor_Pipeline_PautoV75.py    ★ v7.6 정정 (학습기간 인자)
├── Exec_Dynamic_TS_PautoV75.py            (변경 없음)
├── Historical_DataEngine_PautoV75.py      (변경 없음)
├── Optimizer_PautoV75.py                  (변경 없음)
├── PastBackTest_PautoV75.py               (변경 없음 — GUI entry)
├── Predict_ML_PautoV75.py                 (변경 없음)
├── Regime_Master_PautoV75.py              (변경 없음)
├── Pauto_Best_Params.json               ★ v7.6 신규 (Lev 5 강제)
├── test_pauto_v76_compounding.py        ★ 단위 테스트 (복리)
├── test_train_period_separation.py      ★ 단위 테스트 (학습기간)
├── analyze_pauto_v76.py                 ★ 결과 분석
└── README_v76.md                          본 파일
```

## 사용자 PC 실행 순서 (★ 정확함)

### Step 0 — 데이터 기간 확인 (선택, 30초)

```cmd
cd D:\ML\Verify\Pauto_v76_2026-05-16
python -c "import pandas as pd; df=pd.read_csv('Merged_Data.csv', usecols=['timestamp']); print('Start:', df.iloc[0,0]); print('End:', df.iloc[-1,0]); print('Rows:', len(df))"
```

### Step 1 — 단위 테스트 (필수, 1분)

복리 검증:
```cmd
python test_pauto_v76_compounding.py
```
"8/8 통과" 확인.

학습기간 분리 검증:
```cmd
python test_train_period_separation.py
```
"5/5 통과" 확인.

### Step 2 — AI 학습 (★ 핵심 변경, 약 30초~2분)

**v7.5 방식 (점프 ⓟ-9 포함)**: GUI 2번 버튼 → 36mo 전체 학습. **사용 금지**.

**v7.6 권장**: CMD에서 학습기간 *명시*. tz-aware 인자는 **반드시 큰따옴표**로 감싸기.

사용자 데이터: 2023-05-01 ~ 2026-04-30 (36mo). 24mo 학습 + 12mo OOS 권장:

```cmd
python ML_Predictor_Pipeline_PautoV75.py "2023-05-01 00:00:00+00:00" "2025-04-30 23:59:00+00:00"
```

- 인자 1: 학습 시작일 (큰따옴표 필수)
- 인자 2: 학습 종료일 (큰따옴표 필수)
- 결과: `PautoV75_XGB_1to3_Predictor.json` + `*_meta.json` 생성
- 예상 시간: 약 30초~2분 (합성 8mo/351K행 7.4초 기준 추정)

**참고**: 따옴표 빼먹어도 인자 4개로 들어오면 *자동 조립* 처리 (v7.6 정정). 그래도 따옴표 권장.

### Step 3 — 백테스트 실행 (GUI, 36mo 시뮬 시간 가변)

```cmd
python PastBackTest_PautoV75.py
```

GUI 열리면:
- **시작일**: 학습 종료일 다음 날 = **2025-05-01** (OOS 12mo 시작)
- **종료일**: 데이터 끝 = **2026-04-30**
- 1번 데이터 병합 SKIP, 2번 AI 학습 SKIP, 3번 Optuna SKIP
- **4️⃣ Pauto 백테스트 실전 가동** 클릭

### Step 4 — 결과 분석 (1분)

```cmd
python analyze_pauto_v76.py
```
인자 없이 실행 시 자동으로 최신 TradeLog 선택.

생성물:
- `Pauto_TradeLog_*.csv`
- `Pauto_TradeLog_*_analysis.txt`
- `Pauto_Report_*.html`

### Step 5 — Claude에게 결과 전달

다음 4개 파일 zip으로:
- `Pauto_TradeLog_*.csv`
- `Pauto_TradeLog_*_analysis.txt`
- `PautoV75_XGB_1to3_Predictor_meta.json` (학습 메타 — 재현성)
- (선택) `Pauto_Report_*.html`

## 알파 판단 기준

다음 모두 만족 시 *알파 확인*:
- 총 수익률 > 0
- 강제청산 발생 안 함
- Max DD > −50% (사용자 트라우마 임계)
- 12mo OOS 월평균 ≥ 8%

## 본인이 *변경 안 한* 점프 (사용자 결정 우선)

- ⓟ-3 Funding rate 0.01%/일 (Binance 실제 0.03%/일, 3배 과소)
- ⓟ-4 tick 분할 시 high/low 순서 양봉/음봉 의존
- ⓟ-6 ML 모델 학습 라벨이 *롱 성공률만*
- ⓟ-8 Optimizer overfitting

## 본인 메타인지 — 미확인 사항

- xgboost / PyQt6 사용자 PC 설치 여부 (본인 통합 테스트는 xgboost 3.2.0으로 통과)
- 36mo 데이터 실제 시작/종료일 → Step 0 확인 필수
