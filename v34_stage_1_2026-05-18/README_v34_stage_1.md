# Rauto V34 Stage 1 측정 가이드

**작성일**: 2026-05-18
**목적**: 안 X (fib_trigger ATR 기반 동적화) 36mo 실측

---

## 1. Stage 1 핵심 변경

**이전 (Phase B)**: fib_trigger = 1.2% 고정 → fib_lock 발동 0건
**Stage 1**: fib_trigger = ATR × N (N ∈ [0.5, 1.0, 1.5, 2.0]) → fib_lock 다수 발동 기대

**그리드 9개 (SL ≥ fib 조건)**:
| # | fib_trigger | SL multi | 비고 |
|---|---|---|---|
| 1 | ATR × 0.5 | ATR × 1.0 | 가장 빨리 fib_lock 발동 |
| 2 | ATR × 0.5 | ATR × 1.5 | |
| 3 | ATR × 0.5 | ATR × 2.0 | |
| 4 | ATR × 1.0 | ATR × 1.0 | SL = fib |
| 5 | ATR × 1.0 | ATR × 1.5 | |
| 6 | ATR × 1.0 | ATR × 2.0 | |
| 7 | ATR × 1.5 | ATR × 1.5 | SL = fib |
| 8 | ATR × 1.5 | ATR × 2.0 | |
| 9 | ATR × 2.0 | ATR × 2.0 | SL = fib |

---

## 2. 사용자 PC 환경 요구사항

| 항목 | 요구 |
|---|---|
| OS | Windows (BAT) 또는 Python 직접 실행 |
| Python | 3.10+ |
| 패키지 | pandas, numpy, xgboost, scipy |
| 데이터 | `D:\ML\Verify\Merged_Data.csv` |
| 디스크 | 약 1GB |
| **예상 시간** | **2~4시간** (3개 필터 신호 추출 안 함, 9개 시뮬만) |

---

## 3. 실행 방법

```
1. zip 파일을 D:\ML\Verify\v34_stage_1_2026-05-18\ 로 압축 해제
2. Merged_Data.csv가 D:\ML\Verify\ (상위 폴더)에 있는지 확인
3. run_v34_stage_1.bat 더블 클릭 (또는 python run_all.py)
4. 학습 묻는 단계: 기존 모델 재사용(Y) 권장
5. 완료 후 outputs_stage_1 폴더를 zip하여 업로드
```

**고급 옵션 (CMD에서)**:
```
python run_all.py                # 기본
python run_all.py --auto-yes     # 모든 프롬프트 자동 (재학습 강제)
python run_all.py --skip-train   # 학습 건너뛰기 (기존 모델 재사용) ★ 권장
python run_all.py --skip-test    # 단위 테스트 건너뛰기
```

---

## 4. 시간 추산

| 단계 | 시간 |
|---|---|
| 환경/데이터 체크 | 1분 |
| 학습 (skip-train 시 0) | 0~20분 |
| 단위 테스트 | 1분 |
| ATR_pct 사전 계산 | 1-3분 |
| ML 신호 추출 (filter=off 1회만) | 30-90분 (Phase B에서 80분 × 1회) |
| 9 시나리오 시뮬 | 30-60분 |
| **합계** | **약 2~4시간** |

Phase B 대비 시간 단축 — 신호 추출이 1회만 진행 (filter off만).

---

## 5. 결과 회수

측정 완료 후:
1. `D:\ML\Verify\v34_stage_1_2026-05-18\outputs_stage_1\` 폴더 통째로 zip
2. Claude에 업로드

내부 파일:
- `all_scenarios_stage_1.csv` (요약)
- `trades_*.csv` (9개)
- `measure_log.txt`

---

## 6. 확인할 핵심 지표

1. **`fib_lock_activation_rate`** — 각 시나리오의 fib_lock 발동 비율
   - 기대: fib=0.5 → 약 30-50%
   - fib=2.0 → 약 10-20%

2. **`pf` (Profit Factor)** — 각 시나리오의 수익률
   - 알파 후보: PF ≥ 1.0

3. **`n_fib_lock`** — fib_lock 청산 사유로 끝난 거래 수
   - Phase B에서 0 → Stage 1에서 다수 기대

4. **장세별 PF** — uptrend/downtrend/hivol/lovol 별 차이

---

## 7. 본인 메타 인지 (정직 한계)

- **확실**: fib_lock 발동 0 → 다수로 증가 (Phase A 합성 검증 완료)
- **추론 75%**: 실측 36mo에서도 비슷한 발동률 패턴
- **모름**: 실제 PF 1.0+ 가능 여부
- **위험**: fib=0.5 + 작은 SL 조합은 *수수료 못 갚을* 가능성 (사용자 결정 — 데이터로 검증 의도)
