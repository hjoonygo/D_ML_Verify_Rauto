---
name: binance-tick-data-real-slippage
description: "실측 슬리피지는 바이낸스 aggTrades 틱으로 계산 — 과거는 Binance Vision 아카이브, 최근은 REST API(fromId 페이지넘김)"
metadata: 
  node_type: memory
  type: reference
  originSessionId: 5b71754e-2e36-4fda-8bf1-f43e53b080a5
---

진짜 슬리피지(스톱이 실제 체결된 가격)는 바이낸스 aggTrades(체결틱: 가격·수량·시각)로 측정 가능. 소액 주문이면 체결가 ≈ 그 순간 틱가격이라 정확(호가깊이 불필요).

**실접속 확인(2026-06-18):**
- REST `fapi/v1/aggTrades`: 최근 ~1년만 반환(2025-06 ✓, 2025-03 0개). startTime/endTime은 1시간 이내, fromId와 동시전송 금지(타임아웃).
- 과거 전체는 `https://data.binance.vision/data/futures/um/daily/aggTrades/BTCUSDT/BTCUSDT-aggTrades-YYYY-MM-DD.zip` (선물 um daily, 일별 ~16~50MB, 2023-05도 존재).
- 페이지넘김은 **fromId = 마지막틱['a']+1** (시간+1ms는 같은 ms 다중체결을 누락 — 하필 급변구간서). 컬럼: transact_time, price 등.

**용도:** 7H봇 손절 슬리피지는 보통 ~0bp(연속시장)이고 진짜 문제는 격렬 1분봉 손절뿐 → 그 이벤트의 4분 틱만 정밀 추출(7H라 거래 적어 부담 적음). 하이브리드: 과거=Vision 캐싱, 최근/라이브=API. 관련: [[sl-touch-reconstruction-lookahead]].

**★측정 함정(2026-06-19):** tick_slippage_builder/clean_slip로 격렬손절 12건(전부 macro flash-crash일: 24-08 yen·24-11 election) 측정 시 12건 전부 gapopen=Y → 측정 윈도우(mt±5분)가 SL을 이미 깬 상태서 시작해 '첫 틱(이미 깊음)'을 잡음 = 아티팩트. 결과 +1650bp는 허수, 신뢰불가. 정밀 '트리거→크로싱 갭'을 잡으려면 윈도우 앵커를 SL터치 직전 'above 확인된 틱'부터로 + 1분(Merged)↔틱(Vision) 타임스탬프 정렬 audit 필요. 그 전까지 실용 대안 = 슬리피지 민감도 스윕(5/10/20/30bp). 진짜 꼬리리스크 = flash-crash 유동성공백 스톱슬립(별도 WorkOrder, 스톱으론 못 막음→변동성 서킷브레이커 필요).
