---
name: champion-exit-untouched-lever
description: 챔피언 성급왕 청산은 Fib트레일 sl_intrabar가 667/668 — 적응형 청산은 아직 아무도 안 건드린 최대 레버. 앵커 하니스·재현법·선행 sizing레버.
metadata: 
  node_type: memory
  type: project
  originSessionId: 9ebe5e70-641a-4046-8c0e-6045c18708d8
---

캡틴 아이디어(눌림+피보 전략의 청산을 바닥/천정 삼각수렴 구조에서 과감히 타이트하게)를 검증하던 중 확인한 구조.

**핵심 사실(2026-06-20 실측):**
- 챔피언 R2 성급왕 = +11397%/MDD-17.3%/668거래, 청산 reason = `sl_intrabar` 667 + `trend_flip` 1. → **청산의 거의 100%가 1분 인트라바 Fib 트레일 손절.** 캡틴이 노린 바로 그 경로.
- 선행 패키지 `06 ChampBot/06Prj_TS_CvdAbsorption_Stg1_Package`는 **SIZING(흡수=-side*cvd_7h, 챔피언 거래 |IC|~0.17)·ENTRY(fastfail음성, 풀백품질)만** 손댐. **청산 Fib트레일 (0.3,0.5,0.6)은 전부 고정.** → 적응형 청산 = 미개척 레버.
- 선행 sizing 레버 'sq': long +13030%/MDD-17.1% CPCV PASS(채택가능), both +17721%이나 MDD-21.7% (§0 -20% 위반). 적응형 청산과 직교라 **스택 가능**.

**앵커 하니스(재현법, §15.2):**
- 생성기 = `02 20260618일 이전작업/07 Rauto/07Prj_Ch4_RunAWS_Stg17_ImpatientFork/bt36_ledgers.py` (1분봉 on_bar 루프 → `led36_king.csv`).
- 재생/지표 = 같은폴더 `comprehensive_4bot.py` (led36 → PaperAccount `resolve_replay(R,mae,fund)` → +11397% 등 4봇). 실행 `python comprehensive_4bot.py` → R2≈+11397% 나오면 정상.
- 데이터 = `D:\ML\Verify\Merged_Data.csv`(OHLC) + 분석피처는 `Merged_36mo_With_OI_Funding_REPAIRED.csv`(1.58M행, OI절대값·CVD재료·Funding·롱숏비 보유 — "oi_zscore 스칼라뿐" 전제는 거짓).
- 거래별 피처 = `king_trades_pullback_feat.csv`(668행, oi_change·cvd_60m/7h·vol_contraction 등).

**적용:** 청산 실험은 절대 led36 재생만 바꾸지 말 것 — 청산은 원장 *생성기*에 박혀있으니 king봇 서브클래스로 SL트레일만 교체(진입/사이징 부모 유지=§1). 변경 후 E0가 +11397% 재현하는지 동치 자가검증 먼저.

**정직 경계:** 월 +5%p 향상 목표는 baseline 14.1%/월 → 19.1%/월 = 최종자본 ~4.7배(+54000%)라 매우 높은 바. 게다가 §0 MDD-20% 천장이 수익상향과 충돌(sq both가 이미 -21.7% 위반). 수익은 'MDD-20% 제약 하' 최대화로 봐야 함. [[fastfail-ic-tested-negative]] [[binance-tick-data-real-slippage]]

---
## ★★★ 전환점 (2026-06-20 확인, 신뢰85) — 챔피언 수익 +11397%의 99%가 환상체결
king 청산(sl_intrabar) 1m가드 65줄 `touched = pos==-1 and market.h>=self.sl`(숏) = **한쪽만 검사.** sl이 봉보다 한참 아래(낡은 피벗)여도 고가는 당연히 sl 위 → 무조건 발동 → **체결가를 sl(가격이 닿은 적 없는 곳)로 기록.** 빠진 검사 = "sl이 봉범위 안에 걸쳤는지"(`l<=sl<=h`). 근본원인: 거래 중 새 피벗 없으면 **진입 前 낡은 피벗**을 stop으로 씀.
- 실증: 2025-03-03 숏 94,222 진입, 보유내내 가격 90,601~94,971(바이낸스 실데이터), 청산기록 83,231(2/26 낡은 피벗, 한번도 안닿음)=환상 +11.6%. 상위6건중 5건 독립확인.
- 측정: sl_intrabar 667건 중 211건(32%)이 봉범위 밖, 그중 110건은 보유내내 가격이 sl에 못닿음(진짜환상). 평균230bp·최대975bp 유리체결.
- ★재측정(3모델 수렴): 환상만 시장가교정 **+66%/MDD-45.9%** · 발동봉제한(E0r) **-74%** · **걸침검사 수정(l<=sl<=h만 체결, 정식 재시뮬) -66%/MDD-70.7%, 환상 0/370 확인**. → +11397%는 거의 전부 환상, 현실=본전~손실, MDD -45~-70%(전부 -20% 위반).
- 범위: R1·R2·R5·R6·R7 동일운명. R3·R4 king-절반(SidewayDCA절반 미측정). 라이브는 환상가 체결불가→백테 재현불가.
- 하니스: `exitladder_research.py`(STRICT=걸침검사) in STG17. 독립검증=fapi.binance.com klines.
- 미완: ①SidewayDCA 측정 ②걸침수정 위 전략 재최적 ③캡틴 승인후 §14 5곳 박제(§9 '대체말고 병기'). 캡틴 확인대기.
