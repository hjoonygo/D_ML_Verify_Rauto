# v3.4_fib — PautoV75 ML 진입 + OB+Fib 청산 통합 측정 패키지

**작성일**: 2026-05-17
**작성자**: 조수 Claude (Turn 1~7 일괄 작업)
**목적**: PautoV75 3-class ML 진입 + V7.5 OB+Fib 청산 결합 시스템의 IS/OOS 알파 검증

---

## ★ 사용자 PC 실행 방법 — 한 줄 명령 2개

```bash
# 1. ML 재학습 (24mo IS 기간)
python ML_Predictor_Pipeline_v2.py 2023-05-01 2025-04-30

# 2. OOS 그리드 측정 (27 시나리오 × 4장세 = 108행)
python measure_pf_v34_fib.py
```

완료 후 `outputs_v34_fib/` 폴더 통째로 zip 압축 → Claude에 업로드.

---

## 파일 목록

| 파일 | 역할 | 변경 사항 |
|---|---|---|
| `ML_Predictor_Pipeline_v2.py` | 3-class XGBoost 학습기 | ⓟ-6/11/12 정정 |
| `Predict_ML_v2.py` | 3-class 추론기 | 임계 0.35, 양방향 |
| `Regime_Master_v2.py` | 장세 판독기 | window 120 (S1 버그 정정) + 2h 분기 |
| `ob_provider_v2.py` | OB 검출 (TF 무관) | 원본 그대로 (호출자가 TF 결정) |
| `tf_aggregator_v2.py` | 1m → 5/15/30/60/120m | 120m(2h) 추가 |
| `tbm_simulator_v6.py` | 청산 시뮬레이터 | v5 + v3.4 인터페이스 + #2 정정 + 2h 반전 |
| `pautov75_signal_wrapper_v2.py` | 신호 추출 wrapper | window 120, 3-class 임계 |
| `measure_pf_v34_fib.py` | 측정 메인 | 27 시나리오 × 4장세 |
| `test_v6_integration.py` | 통합 테스트 | 8 시나리오 |

---

## 결정 사항 반영 요약

| 결정 | 값 | 코드 위치 |
|---|---|---|
| OB TF 그리드 | 15m / 30m / 1h | `measure_pf_v34_fib.OB_TF_LIST` |
| Lev 그리드 | 10 / 15 / 20 | `measure_pf_v34_fib.LEV_LIST` |
| Holding 그리드 | 7봉 / 14봉 / 28봉 (OB TF 단위) | `measure_pf_v34_fib.HOLDING_LIST` |
| 학습 방식 | 3-class (ⓟ-6) | `ML_Predictor_Pipeline_v2.apply_triple_barrier_v2` |
| 임계값 | 0.35 (양방향) | `Predict_ML_v2.get_signal` |
| 결함 #2 정정 | Phase 1 hard_sl 활성 (자본 -3% ROE) | `tbm_simulator_v6` L150+ |
| 2h 반전 처리 | 청산 후 *반대 prob ≥ 0.35*면 반대 진입 | `tbm_simulator_v6` 2h 분기 |
| OB 재검출 | 1회만 (원본 유지) | `tbm_simulator_v6.simulate_position_v6` |
| Holding 한도 | OB TF의 7/14/28봉 = 1.75~28h | `timeout_bars_ob_tf` 인자 |

---

## 사전 조건 — 사용자 PC 환경

- **Python 3.10+**
- **패키지**: `pandas, numpy, xgboost`
  - `pip install pandas numpy xgboost`
- **데이터**: `Merged_Data.csv` (1m봉 OHLCV + oi_sum/oi_value/open_interest)
  - 컬럼: `timestamp, open, high, low, close, volume, oi_sum`
  - 본 패키지와 같은 폴더에 위치
  - 권장 기간: 2023-05-01 ~ 2026-04-30 (36mo)

---

## 통합 테스트 (실행 권장)

본인이 *합성 데이터로 *모두 통과* 확인하고 zip 전달*. 사용자 PC에서 *환경 검증*용:

```bash
python test_v6_integration.py
```

결과: `통과 8 / 실패 0`이 나와야 정상.

---

## 단계별 실행 가이드

### 단계 1: ML 재학습 (1-2분)

```bash
python ML_Predictor_Pipeline_v2.py 2023-05-01 2025-04-30
```

산출물:
- `PautoV75_XGB_3class_v2.json` (모델 가중치)
- `PautoV75_XGB_3class_v2_meta.json` (메타: 학습기간, 분포 등)

확인 사항 (출력 메시지):
- `Target 3-class 분포: {0: stay, 1: long, 2: short}` — 세 클래스 모두 존재
- `학습: 2023-05-01 ~ 2025-04-30 (N rows, X.X%)`

### 단계 2: 측정 (사용자 PC 시간 부담 무관)

```bash
python measure_pf_v34_fib.py
```

내부 실행 순서:
1. 데이터 로드
2. OOS 슬라이싱 (2025-05-01 ~ 2026-04-30 기본)
3. ML 신호 추출 (windowing 120봉 단위)
4. 4장세 사후 분류
5. OB TF 변환 (15m/30m/1h/2h)
6. 27 시나리오 시뮬레이션 (각 시나리오마다 단일 포지션 필터 적용)
7. 결과 저장

산출물 폴더 `outputs_v34_fib/`:
- `all_scenarios_v34_fib.csv` (108행 = 27 × 5 [overall + 4장세])
- `trades_tf{ob}_lev{lev}_h{hold}.csv` (시나리오별 거래 로그)
- `measure_log.txt` (전체 로그)

### 단계 3: zip → Claude 회신

```bash
# Windows PowerShell 예시
Compress-Archive -Path outputs_v34_fib -DestinationPath outputs_v34_fib.zip
```

`outputs_v34_fib.zip` 통째로 Claude에 업로드.

---

## 정정 사항 — 코드 변경 흔적

### ⓟ-6 (라벨 단방향 → 3-class)
**원본**: `target = long_success.astype(int)` (binary)
**정정**: stay(0) / long(1) / short(2) 3-class
**파일**: `ML_Predictor_Pipeline_v2.py` `apply_triple_barrier_v2()`

### ⓟ-11 (rolling 방향)
**원본**: `df['high'].shift(-1).rolling(10).max()` → 미래 1봉 + 과거 9봉
**정정**: 진짜 미래 N봉 `[t+1, t+N]` 명시적 슬라이스
**파일**: `ML_Predictor_Pipeline_v2.py` `apply_triple_barrier_v2()` for 루프

### ⓟ-12 (ATR 3항)
**원본**: `max(h-l, |h-c_prev|)` (2항)
**정정**: `max(h-l, |h-c_prev|, |l-c_prev|)` (3항 — 표준 Wilder ATR)
**파일**: `ML_Predictor_Pipeline_v2.py` `calculate_internal_features()`, `tbm_simulator_v6.py` `compute_atr()`, `Predict_ML_v2.py`

### S1 (Regime_Master window 버그)
**원본**: `if len(df) < 100: return "CHOPPY"` 가드인데 wrapper가 `window_size=60`으로 호출 → 항상 CHOPPY
**정정**: `MIN_WARMUP_BARS = 120`, wrapper도 `window_size=120` 호출
**파일**: `Regime_Master_v2.py`, `pautov75_signal_wrapper_v2.py`

### #2 결함 (Phase 1 무방어)
**원본**: hard_sl이 Phase 2 분기 안에만 존재. 진입 직후 급락 시 무방어
**정정**: 매 1m봉 루프 진입부에 `hard_sl_price` 체크 (Phase 1/2 모두)
**파일**: `tbm_simulator_v6.py` `simulate_position_v6` (Z) 분기

---

## 알파 판정 기준 (ADR-W3)

- **PF ≥ 1.3**
- **n_valid ≥ 30**
- **net_sum > 0**

`outputs_v34_fib/all_scenarios_v34_fib.csv`에서 `[알파 후보]` 출력 라인이 ADR-W3 통과 시나리오.

---

## 트러블슈팅

### `ModuleNotFoundError: xgboost`
```bash
pip install xgboost
```

### `데이터 파일 없음: Merged_Data.csv`
같은 폴더에 `Merged_Data.csv` 배치. 컬럼: `timestamp, open, high, low, close, volume, oi_sum` (또는 `oi_value`, `open_interest`).

### `Target 3-class 분포: {0: N, 1: 0, 2: 0}` (long/short 모두 0)
학습 기간이 너무 짧거나 변동성 거의 없음. 학습 기간 늘림. 권장 24mo.

### 측정 시간이 너무 오래 걸림
`measure_pf_v34_fib.py` 상단의 그리드 축소:
```python
OB_TF_LIST = [60]  # 1h만
LEV_LIST = [10]
HOLDING_LIST = [14]  # 1 시나리오로 축소
```

---

## 사전 합성 데이터 통과 검증 결과 (본인 작업)

Turn 1~7 본인 작업 중 검증 통과:
- Turn 1: ML_Pipeline 단위 테스트 6/6
- Turn 2: Predict_ML + Regime_Master 단위 테스트 8/8
- Turn 4: tbm_simulator_v6 단위 테스트 8/8
- Turn 5: 전체 measure 흐름 통합 테스트 통과
- Turn 6: test_v6_integration.py 8/8

---

## 본인 (Claude) 인수인계 — 다음 채팅

본 작업의 결정 사항 + 변경 흔적은 `Handover_v34_fib_2026-05-17.docx`에 별도 기록.
사용자 user preference 단계별 작업 사이클 9번 준수.
