---
name: microstructure-weak-for-btc-direction
description: 펀딩·OI·CVD·다코인쏠림 모두 BTC 절대방향 예측엔 약함(IC실측). 단독신호 아닌 필터로만.
metadata: 
  node_type: memory
  type: project
  originSessionId: ec48189e-b63f-4522-ab31-5764a9980ea0
---

2026-06-22 단변량 IC 스크리닝(룩어헤드0·비중첩·Spearman, AlphaIC_FundOiCvd_Stg1)으로 실측 확정:

- **단일자산 BTC**: funding 수준/변화율 IC≈0(죽음), oi_zscore_24h만 4년 음수일관·24h IC-0.06 p0.0004(Bonferroni통과)지만 비단조·초과~6bp<14bp비용, cvd_z 약한보조(p0.056). 제미나이 "Funding+OI 역추세" 1위는 **기각**(방향 정반대=과열후 모멘텀상승, 결합조건 90~250건 표본붕괴).
- **다코인 횡단면**: 바스켓10코인 펀딩쏠림(agg/breadth/btc_rel) 6신호 전부 |IC|<0.02·p>0.15=무의미. breadth Q5(최대쏠림)서도 BTC 안내려감. → "여러코인 분석→BTC방향" **기각**. 횡단면펀딩은 *상대(어느코인이김)*지 *방향(시장오르냐)* 아님.

**Why:** 펀딩/OI/CVD는 단독 진입신호로 약함 — 기존 봇이 oi_zscore(무덤필터)·cvd_z(사이징)를 *필터/오버레이*로 쓰는 패턴과 정합. ★단 챔피언 +11,397% 등 화려한 백테수치 자체가 **2026-06-20 참사노트('클로드 맹신→백테 신뢰도 구조적 미확보, 나중에 검증한 게 문제')로 신뢰보류** 상태 — 이 수치를 '검증된 엣지'로 인용 금지(내가 이 세션서 범한 잘못). 5단계 신뢰성 프레임(백테구조·현실비용·수익률검증·테스트넷·실거래)으로 재검증 전엔 미확정.
**How to apply:** 새 알파를 미시구조 단독신호에서 찾지 말 것. IC 결론도 6/20 교훈대로 '2가지 이상 다른 측면 검증' 전엔 단일각도 스크린으로만 취급. 다코인/베이시스/DVOL 신규수집은 방향알파용으론 저효율(보류). 데이터무결성: BTCUSDT_funding_rates_23_26.csv는 fundingRate 0.0001 고정=손상, funding_history_8h.csv가 진짜. ★CLAUDE.md §15는 아직 +11397% '확정'으로 적혀 6/20 전환점 미전파=충돌(소급정정 필요). 관련 [[rfrauto-restructure]] [[daily-continuity-crosscheck]] [[sl-touch-reconstruction-lookahead]].
