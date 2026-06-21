# Pauto v3.4 통합 패키지 — v3.3 + PautoV75 진입 로직 결합

## 작업 개요

**목표**: v3.3 시스템의 SL/TP/청산 메커니즘은 그대로 사용하되, 진입 신호 로직(cRSI+WAE)을 PautoV75 ML+Regime으로 *교체*하여 알파 검증.

## 4계층 분리 구조 - 어디를 바꿨나

| 계층 | 역할 | v3.3 (기존) | v3.4 (변경) |
|---|---|---|---|
| **A** 신호 발생 | 진입 시점/방향 결정 | cRSI + WAE | **★ PautoV75 ML + Regime** |
| **B** 신호 필터 | 시간순 1개만 | single_pos_filter | 동일 (변경 없음) |
| **C** SL/TP 환산 | 가격 계산 | v3.3 정정본 | 동일 (변경 없음) |
| **D** Hit 판정 | 손익절 + net_return | v3.3 Mode A/D | **Mode A** (1m 단독) |

## 검증 완료

- `test_v34_pauto_integration.py` → **17/17 통과** (8개 시나리오, assert 17개)
- 본인 합성 데이터로 *실제 학습 + 추론 + 시뮬* 동작 확인

## 폴더 구성

```
v34_pauto/
├── pautov75_signal_wrapper.py        ★ 신규 (PautoV75 → v3.3 인터페이스 변환)
├── measure_pf_v34_pauto.py           ★ 신규 (그리드 측정 메인)
├── analyze_v34_results.py            ★ 신규 (결과 분석)
├── test_v34_pauto_integration.py     ★ 신규 (8개 시나리오 단위 테스트)
├── tbm_simulator_v4.py                 (v3.3 정정본 - 점프 ① 정정)
├── single_pos_filter.py                (v3.3 그대로)
├── intrabar_path_loader.py             (v3.3 그대로 - Mode A는 불필요)
├── liquidation_model.py                (v3.3 그대로)
├── tf_aggregator.py                    (v3.3 그대로)
├── Predict_ML_PautoV75.py              (PautoV75 - oi_sum 인식 추가, 변경 없음)
├── Regime_Master_PautoV75.py           (PautoV75 그대로)
└── README_v34.md                      본 파일
```

## 사용자 PC 실행 순서

### 사전 준비 — 사용자 폴더에 다음 파일 *반드시* 존재

```
D:\ML\Verify\Pauto_v76_2026-05-16\ (또는 사용자 작업 폴더)
├── Merged_Data.csv                              ← 36mo 1분봉 + oi_sum 데이터
├── PautoV75_XGB_1to3_Predictor.json             ← 사용자가 이미 학습한 ML 모델
└── PautoV75_XGB_1to3_Predictor_meta.json        ← 학습 메타정보
```

### Step 1 — zip 풀고 *기존 폴더에 덮어쓰기*

본인 zip 안의 모든 .py를 사용자 기존 폴더에 복사.

### Step 2 — 단위 테스트 (필수, 약 1분)

```cmd
cd D:\ML\Verify\Pauto_v76_2026-05-16
python test_v34_pauto_integration.py
```

"17/17 통과" 확인.

### Step 3 — 그리드 측정 실행 (예상 시간: 10~30분)

```cmd
python measure_pf_v34_pauto.py
```

진행:
1. Merged_Data.csv 로드 (1.58M 행)
2. OOS 12mo 슬라이싱 (2025-05-01 ~ 2026-04-30, 약 525,600봉)
3. PautoV75 신호 추출 (525,600봉 × ML 추론, *약 5.7분 예상*)
4. 그리드 측정 (336 시나리오, *예상 시간 수 분*)
5. 결과 csv 저장: `outputs_v34_pauto/`

### Step 4 — 결과 분석

```cmd
python analyze_v34_results.py
```

생성물:
- `outputs_v34_pauto/all_scenarios_summary_v34.csv` (시나리오별 통계)
- `outputs_v34_pauto/alpha_candidates_v34.csv` (ADR-W3 통과 시나리오)
- `outputs_v34_pauto/v34_analysis_report.txt` (분석 보고서)
- `outputs_v34_pauto/signal_stats.json` (신호 빈도, Regime 분포)
- `outputs_v34_pauto/run_log.txt` (실행 로그)

### Step 5 — Claude에게 결과 전달

다음 폴더 zip으로 압축해서 업로드:
```
outputs_v34_pauto/  (5~6개 파일, 수 MB)
```

## 그리드 명세

| 파라미터 | 값 | 개수 |
|---|---|---|
| TF | 1m (1분봉) | 1 |
| Lev | [5, 10, 15, 20] | 4 |
| SL_acct | [1.32, 2.6, 5, 7.24, 9, 12, 15]% | 7 |
| TP_ratio | [2.8, 3.8, 5.0] | 3 |
| Holding (분) | [60, 240, 480, 960] = 1h/4h/8h/16h | 4 |
| **합계** | | **336 시나리오** |

각 시나리오 × 4 장세 (uptrend/downtrend/hivol_range/lovol_range) + overall = 5장 → **1,680 행**

## ML 진입 조건 (PautoV75 그대로)

```python
prob = ML_model.predict(features)  # 9개 feature (rsi/ema_dist/atr/fvg/oi_delta/rvol/vol_accel/delta_streak)
regime = Regime_Master.get_regime(window)  # EMA 20/50/100 + ATR

if prob >= 0.80 and regime in ["BULLISH_EXPANSION", "CHOPPY"]:
    OPEN_LONG
elif prob <= 0.20 and regime in ["BEARISH_EXPANSION", "CHOPPY"]:
    OPEN_SHORT
```

## 알파 판단 기준

다음 모두 만족 시 *알파 확인*:
- ADR-W3 통과 시나리오 ≥ 5건
- 최고 PF ≥ 1.5
- net_return_sum > 0 시나리오 ≥ 30% (336 중 100건 이상)
- 4 장세 중 최소 2 장세에서 PF ≥ 1.3

이 기준 *모두* 미달 시 → PautoV75 진입 로직 *알파 없음* 결론.

## v3.3 핵심 점프 정정 사항 *이미 적용됨*

| 점프 | v3.3 정정 |
|---|---|
| 점프 ⓟ-1, ⓟ-2 capital 리셋 | v3.3 simulate_batch는 복리 무관, 시나리오별 net_return_sum만 측정 |
| 점프 ⓟ-9 학습=백테스트 | OOS 12mo만 측정 (학습 2023-05~2025-04 제외) |
| 점프 ⓟ-10 무한 holding | v3.3 holding_bars 강제 청산 (max 16h) |
| 점프 ⓟ-6 LONG 거래 0 | 신호 통계로 직접 측정 (signal_stats.json) |

## 미해결 (사용자 결정 우선)

본인이 *변경 안 한* 점프:
- ⓟ-3 Funding rate 0.01%/일 (Binance 실제 0.03%/일, 3배 과소)
- ⓟ-4 tick 분할 lookahead (PautoV75는 *호출 안 함* — v3.3 simulator만 사용)
- ⓟ-6 모델 학습 라벨 비대칭 (롱 성공률만 학습)
- ⓟ-8 Optimizer overfitting (사용 안 함)

이 점프들은 *v3.4 측정 결과 받은 후* 별도 정리.

## 본인 메타인지

**본인이 *모르는 것* (정직 보고)**:
1. 사용자 PC 실제 측정 시간 — 본인 합성 측정(5.7분)은 *for-loop 추론* 기준. v3.3 그리드 측정 시간은 *측정 안 함*
2. OOS 12mo 신호 빈도 — IS 4.5mo 결과로 추정 약 200~300건. *실측 필요*
3. ADR-W3 통과 시나리오 개수 — *측정 후* 알 수 있음
