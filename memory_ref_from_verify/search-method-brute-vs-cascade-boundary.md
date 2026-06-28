---
name: search-method-brute-vs-cascade-boundary
description: "가격레벨 탐색 방법선택 경계 — 한 번 탐색 윈도 <40만 1m봉=브루트, >=40만 or RAM초과=캐스케이드."
metadata: 
  node_type: memory
  type: reference
  originSessionId: ec48189e-b63f-4522-ab31-5764a9980ea0
---

체결검증 등 '가격레벨이 특정 구간에 거래됐나·어디서' 탐색 시 방법선택 (캡틴 지시 2026-06-22, 봇 설계용 표준).
도구: `D:\ML\Verify\AlphaIC_FundOiCvd_Stg1\search_method_selector.py` (pick_search_method), `reexec_cascade_tf.py`(캐스케이드 구현).

**실측 크로스오버(Merged_Data 1.58M 1m봉, 이 PC·pandas):** W* ≈ **40만 1m봉 ≈ 약 9개월(0.8년)분 1m**.
- 30만봉: 브루트 0.60ms < 캐스 1.36ms (브루트승). 50만봉(1.0년): 브루트 1.45 > 캐스 1.33 (캐스승). 90만봉: 캐스 1.8x.
- 형태(머신무관): **캐스케이드(7h→1h→15m→1m)=윈도무관 ~1.3ms 상수**(드릴+조기반환·봉검사 148배↓). **브루트포스 1m=O(W)**(벡터연산이라 봉당 싸지만 전부 스캔). 작은 윈도=브루트 빠름(캐스 슬라이스 오버헤드), 큰 윈도=캐스 빠름.

**한 줄 규칙:** 핵심변수=*한 번의 탐색 윈도 W*(봇TF·거래수 아님). `W<40만봉→brute / W>=40만 or RAM초과→cascade`.

**Why:** ★per-거래 체결검증은 봇 TF 무관 거의 항상 브루트 — 7h봇 보유 30h=1,800봉, 15m봇 2h=120봉, 스윙 1달=43,200봉 전부 40만 한참아래. **짧은 TF봇일수록 보유창↓ → 브루트가 더 유리(통념과 반대).** 거래수 늘어도 윈도당 크기 그대로.
**How to apply:** 캐스케이드는 ①전기간 1쿼리 가격탐색(≥0.8년 1m) ②틱데이터(1년≈1억행, 메모리초과=무조건) ③멀티심볼·멀티년에서만 이김. W*는 하드웨어/구현 의존(numpy/searchsorted로 짜면 W* 왼쪽이동=캐스 더일찍승), 형태는 보편이라 설계판단엔 충분(신뢰80). 관련 [[champion-return-exit-fill-inflated]](이 탐색의 출처=체결검증) [[alpha-verification-system]].
