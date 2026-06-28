---
name: confirm-filename-before-creating
description: 파일 만들기 전 파일명을 캡틴에게 확인받고 시작 — 임의 명명 금지
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 7069312d-9843-4ee6-b40d-2fc5018bef04
---

산출물(파일·zip·docx 등)을 **만들기 '전에' 파일명을 캡틴에게 제시·확인받고** 시작한다. AI가 멋대로 이름 짓지 않는다. 명명체계는 §16: (Proj번호)Prj_(CCproject)_Stg(횟수)_(작업명).

**Why:** 2026-06-20, 한 세션 내내 배포 zip·Work Order·마스터계획·데이터시트·인수인계 docx 등 파일명을 AI가 임의로 정함 → 캡틴이 §16 어겼다고 지적("너 멋대로 정해왔어, 엉망").

**How to apply:** 파일 만들기 직전 "이 이름으로 만들겠습니다: 07Prj_Rauto_Phone_Stg{n}_{작업명}.{ext} — 괜찮나요?"로 한 줄 확인 후 진행. **★파토/에러 Stg 승계**: 중간에 실패·에러로 결과물 못 낸 작업의 Stg횟수는 다음 작업이 그대로 이어받고(번호 안 버림), 작업명만 새로 정한다. [[save-location-and-emphasis-routing]]와 함께 적용(저장위치도 알리고 G백업).
