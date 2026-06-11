# V3.4 OB+Fib 측정 패키지 — 사용 안내

## 목적

PautoV75 ML 진입 + OB 분할 익절 + Fibonacci trailing 청산 **결합 시스템**의
V3.4 거래환경 측정. Key 노트가 보고한 알파 (PF 2.86, 월 15%) 가
V3.4 환경에서 재현되는지 확인 + 수익 효과성 정량화.

## 그리드 (사용자 결정)

```
TF       : [15m, 1h]
ML 임계  : [0.35, 0.40]
Lev      : [10, 15, 20]
N_ob     : [3, 5]
Side     : [long, short]
H (TF봉) : [4, 8, 16]
= 144 시나리오
```

청산 파라미터 (Key 노트 합의, 고정):
- fib_ext_pct = 0.618
- fib_trigger_roe = 24.0% (Lev 20 의 자본 ROE = 가격 +1.2%)
- fib_sl_pct = 5.73%
- 비용 = 16bp 왕복 명목가
- Tier 1 MMR 0.4% Liq

측정 기간: 2025-05-01 ~ 2026-04-30 (12mo OOS, V3.4 Stage 1 과 동일)

## 실행 환경 확인

이 zip 의 폴더 안에 다음 파일이 **사용자 PC 에서 추가로** 있어야 합니다:

1. `Merged_Data.csv` — 1m OHLCV (사용자 PC 에 이미 있음)
2. `PautoV75_XGB_3class_v3.json` — 24mo 학습 모델 (사용자 PC 에 이미 있음)

이 두 파일은 사용자 PC 측에서 **이전 V3.4 Stage 1 측정**에 사용하던 그 파일입니다.
zip 안에는 들어 있지 않으니, 사용자 PC 의 V3.4 Stage 1 작업 폴더에서
복사해서 이 폴더에 넣어 주세요.

## 실행 방법

### 1. 단위 테스트 (선택, 약 5초)

```
cd v34_obfib
python test_obfib_unit.py
```

7/7 통과 확인. 통과 안 하면 측정 중단 후 보고.

### 2. 본 측정 (약 30~90분 추정, 사용자 PC 사양 따라)

```
cd v34_obfib
python measure_v34_obfib.py
```

### 3. 결과 zip 압축

측정 완료 후 `outputs_v34_obfib/` 폴더 전체를 zip 으로 압축해
채팅에 업로드.

## 출력 파일

`outputs_v34_obfib/`:
- `all_scenarios_summary.csv` — 144 시나리오 통계 한 행씩
- `alpha_candidates.csv` — ADR-W3 통과 시나리오
- `trades_{scen_id}.csv` — Top 3 알파 시나리오의 거래별 디테일
- `signals_TF{tf}_th{threshold}.npz` — 신호 캐시 (재실행 시 활용)
- `run_log.txt` — 실행 로그

### CSV 컬럼 정의

| 컬럼 | 의미 |
|---|---|
| n_trades | 거래 수 |
| win_rate | 승률 (%) |
| pf | Profit Factor |
| net_return_sum_pct | 누적 수익률 (자본 대비 %, 단순합) |
| mdd_pct | 최대 drawdown (%) |
| sharpe | Sharpe Ratio (거래 단위, 연환산 252) |
| avg_trade_pct | 거래당 평균 수익률 (%) |
| n_fib | Fibonacci 계단식 스탑 청산 거래 수 |
| n_ob_edge | OB 엣지 스탑 청산 거래 수 |
| n_hard_sl | 초기 하드 손절 거래 수 |
| n_liq | 청산 (Liq) 거래 수 |
| avg_fib_pct | Fib 청산 거래의 평균 수익률 (%) |
| pct_fib_of_total_profit | Fib 청산이 전체 수익에서 차지하는 비율 (%) |
| pct_used_reduce | 50% 익절 작동 비율 (%) |
| adr_w3_pass | ADR-W3 알파 통과 여부 (PF≥1.3 + n≥30 + net>0) |

## Key 노트 비교 기준점

사용자 직접 측정 (Pauto_TradeLog_260418_160542.csv):
- 기간: 2025-10-01 ~ 2026-02-06 (4.2mo)
- 진입: PautoV75 ML (임계 정보 없음 — 사용자 봇 기본)
- 청산: OB+Fib (이번 측정과 같은 로직)
- 결과: **PF 2.864, 월 15.04%, MDD 2.28%**

본 측정 (12mo OOS) 의 일부 그리드 시나리오가 위 결과와 *유사*하게 나오면
Key 노트 알파가 V3.4 환경에서 *재현 확인*. 차이 크면 *원인 분석 필요*.

## 알려진 한계

1. 본 측정은 1분봉 close 기준 check_exit 호출 (보수적 가정)
2. 원본 봇은 0.1초 틱 호출 — 측정 PF 는 실거래 PF 보다 *약간 보수*
3. 분할 익절 시 REDUCE 가격은 OB.mean 으로 가정 (1분봉 close 와 다를 수 있음)
4. SHORT 100% 편향 (사용자 TradeLog 와 동일 시장 조건) 가능

## 문제 발생 시

`run_log.txt` 와 `outputs_v34_obfib/` 폴더 zip 으로 보내 주시면
조수가 *직접 분석* 합니다.
