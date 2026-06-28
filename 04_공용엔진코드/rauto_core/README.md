# 04_공용엔진코드/rauto_core/  — 예약 슬롯 (현재 engines/ 통합 운영)

★캡틴 지시6(2026-06-29) "빈 폴더 제대로 관리하냐" 답 = 이 README가 용도·현황 단일출처. 방치 아님.

## 용도 (Rauto 5모듈 구조 §24)
**[0]관제센터 + [2]결정두뇌(사이징·리스크·챔피언)** 분리용 예약 슬롯.

## ★현재 운영 = engines/ 통합 (import 일관성·path_finder)
관련 모듈은 전부 `04_공용엔진코드/engines/`에 있습니다:
- 관제센터/구동 = `rauto_orchestrator.py` · `rauto_live.py`(BotSlot·Rauto2Live·pick_champion)
- 결정두뇌(안전·챔피언) = `emergency_brake.py`(비상 안전장치1호) · `champion_safety.py`(챔피언 가산점)
- 계약/봇 = `rauto_contract.py` · `REVoi_bot.py`

## 향후
모듈 수가 많아져 분리가 필요하면 여기로 이동 + `path_finder.ensure_paths`에 경로 추가. 그 전엔 engines/ 단일 폴더 운영(분리는 import 리스크라 별도 작업·캡틴 승인).
