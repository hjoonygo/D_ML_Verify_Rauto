---
name: daily-continuity-crosscheck
description: ★매 세션 Claude가 제작노트(아이디어·참사교훈) ↔ WorkOrder·Handover·KeyNote·INDEX 크로스체크해 "이어서 할 것·미결"을 브리핑. 캡틴 연속작업 지원
metadata:
  type: feedback
---

매 세션(매일) 시작 시 Claude는 캡틴의 **제작노트 내용을 다른 작업문서와 크로스체크**해, 캡틴이 잊지 않고 집중해 연속작업하도록 짧게 브리핑한다.

**대상 크로스체크:**
- 입력: `01_제작노트`의 핵심 = ★참사노트(`#백테스팅의 구조적 신뢰성 확보` 5단계 대책)·`끊김없이 다음할것`·`#꼭짚어야할 개발아이디어`·`MOM OF future BTC 전략 제작 노트`(허브). (목록=`01_제작노트/_최근1달_수정문서_8개_수동Export대상.txt`)
- 대조: Work Order(미래 과제)·Handover(직전 산출)·KeyNote·00WorkHstr INDEX·STATE.
- 산출: 세션 시작 시 "오늘 이어서 할 것 + 미결 아이디어 + 참사 5단계 교훈 준수 여부" 한 묶음 요약.

**Why:** 캡틴의 아이디어·계획은 구글독스 제작노트에 쌓이는데 휘발·망각되기 쉽다. AI가 연속성을 관리해야 캡틴이 [[auto-filing-operating-model]]대로 "계획+검증결과"에만 집중할 수 있다. 참사(백테 환상) 재발방지 = 5단계 대책을 매일 상기.

**How to apply:** 세션 첫 응답에 1줄 브리핑. 제작노트는 캡틴이 수동 export하므로 갱신 시 반영. 관련: [[rfrauto-restructure]] [[auto-filing-operating-model]].
