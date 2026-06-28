# veri_edge.py — 사용법 (수익률·알파 검증 통합 공용엔진)

> 캡틴 지시 2026-06-28. 위치 = `04_공용엔진코드/engines/veri_edge.py`. 의존 = numpy·pandas만(자기완결).

## 1. 무엇인가
봇 거래원장(ledger)을 입력받아 **수익률(%)로** 엣지를 정직 검증하는 모듈. 이번 세션의 검증로직(앵커·기간분해·held-out OOS·post-2024 매월·MDD 4단·ON/OFF 기여·상관)을 한곳에 통합. **새 규칙 내장**: #5 post-2024만 · #6 OOS 헤드라인(천장 금지) · #7 종합+매월 · §26 MDD 4단.

## 2. 구조 원칙 (충돌·구조문제 차단 — 왜 안전한가)
- **거래생성 안 함.** 검증봇(`REVoi_bot.make_trades` / `back2tv_REVoi.rev_trades` / `bt_full.gen_trades`)이 만든 원장을 **입력만** 받음 → §8 해시엔진 무수정·§15.1 준수. veri_edge는 '검증 레이어'.
- **외부 import 0** (numpy·pandas만) → cross-grade 의존 0, 어느 폴더·AWS서도 그대로 동작(이식성).
- **앵커검증 게이트 내장**(§15.2): 사이징 모델이 틀리면 `anchor_check`가 FAIL → 모든 수치 무효 처리. 사이징 상수는 `rauto_paper_engine`/`liq_eval` 1:1(앵커 +1851.6% 재현으로 검증).
- **역할 분리** — `bot_trust_gates.py`(구조관문: 앵커·환각·CPCV·현실비용) vs `veri_edge.py`(수익률·OOS·매월·4단). 중복 없음. 둘 다 쓰면 '구조+수익률' 양면 검증.

## 3. 입력 = 봇 계약 원장
`DataFrame` 컬럼 = `{et, xt, side, entry, exit, R, mae, fund, reason}` (최소 `et, side, R, mae, fund`). R=언사이즈드(레버 안 곱한 거래수익).

## 4. 메서드 (전부 수익률 %)
| 메서드 | 용도 | 규칙 |
|---|---|---|
| `anchor_check(size_pct, lev, expect_ret)` | 사이징 모델이 알려진 앵커 재현하는지 게이트 | §15.2 |
| `returns_by_period(size_pct, lev)` | 전체 / 2023(ETF전) / post-2024(ETF후) 수익률 | #5 |
| `heldout_oos(size_pct, lev, train_end)` | train(2024)→test(2025+) **OOS 수익률(헤드라인)** | #6 |
| `monthly_post2024(size_pct, lev)` | 종합 + post-2024 매월통계 표 | #7 |
| `mdd_4gate(size_pct, lev_lo, lev_hi)` | M0/M30/M25/M20 최고수익 + 강제청산 **(천장·보조)** | §26 |
| `VeriEdge.contribution(led_on, led_off, ...)` | 기능 ON vs OFF의 **OOS 수익률 기여** (early_tp식) | #6 |
| `correlation(other_ledger, size_pct, lev)` | 두 봇 post-2024 월수익 상관 (포폴) | — |
| `report(size_pct, lev, anchor_result)` | 표준 리포트(헤드라인 OOS→종합+매월→천장 보조) | #6·#7·§26 |

## 5. 사용 예 (복붙)
```python
import sys; sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\engines")
sys.path.insert(0, r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp")
from path_finder import ensure_paths; ensure_paths()
from fib_replay_1m import load_1m, load_funding
import back2tv_REVoi as B2, json
from veri_edge import VeriEdge

d1m, fund = load_1m(), load_funding()
p_base = json.load(open(r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp\back2tv_rev_winners.json"))["REV_MDD25_36mo"]["p"]
combo_p = {**p_base, "tp_frac":0.7, "early_tp_pct":0.01, "early_frac":1.0}

base_led  = B2.rev_trades(d1m, fund, p_base)   # 앵커 원장(BASE)
combo_led = B2.rev_trades(d1m, fund, combo_p)  # 검증 대상(COMBO)

# 1) 사이징 모델 검증(BASE로) → 2) COMBO 리포트
anchor = VeriEdge(base_led).anchor_check(size_pct=75, lev=3, expect_ret=1851.6)   # PASS여야
print(VeriEdge(combo_led).report(size_pct=75, lev=3, anchor_result=anchor))

# early_tp 기여(OOS 수익률)
off_p = {**p_base, "tp_frac":0.7}                # early off
off_led = B2.rev_trades(d1m, fund, off_p)
print(VeriEdge.contribution(combo_led, off_led, size_pct=75, lev=3))
```

## 6. 출력 규칙 (정직)
- **헤드라인 = held-out OOS 수익률**. 천장(M0~M20)은 `★in-sample·실전아님` 라벨로만 보조표시.
- 매월표로 §0 '매월 양수' 점검. 모든 수치에 `live<백테` 전제.
- 앵커 FAIL = 리포트 중단(수치 신뢰 금지).

## 7. 승급(§22)
T1 반제품화 = `04_공용엔진코드/(세션ID).zip` + `(세션ID).manifest.md` (`promote_alpha.py`). 다른 봇(TS·SW)도 같은 원장 계약이면 그대로 `VeriEdge(그_봇_원장)`로 검증.
