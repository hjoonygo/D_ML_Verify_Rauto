# AWS 위기대응 메뉴얼 — 관리지침

> `Guide_AWS_Contingency_Plan.docx` (AWS 서버 관리 및 위기대응 메뉴얼)의 관리·갱신 규칙.
> 작성 2026-06-22 · 보관 `D:\ML\Verify\00WorkHstr\00Basic_Setup_Package\`

---

## 1. 정본 (1권 원칙)
- **정본 메뉴얼 = `D:\ML\Verify\00WorkHstr\00Basic_Setup_Package\Guide_AWS_Contingency_Plan.docx`** — 이 한 권만 존재한다.
- **새 내용은 이 정본에 "추가"한다. 새 파일/다른 명칭/버전번호로 따로 저장하지 않는다. (1권 유지)**
- 재생성·수정 소스: `D:\ML\00AI_SYS\docs\_src\Guide_AWS_Contingency_Plan.generate.js` (node + `npm i docx`로 재빌드)

## 2. ★ 핵심 원칙 (정리 원칙)
**작업 중 캡틴이 위기관리·위기대응·응급상황을 언급하고, 그것이 작업 결과(분석·구현·발견·실제 사고 경험)로 이어지면 → 관련된 모든 내용을 빠짐없이 정본에 정리·통합한다.**
- 일회성 대화로 끝내지 않는다. 결과가 나온 위기 관련 사항은 반드시 정본 문서화로 마감한다.
- "정리"는 단순 메모가 아니라 해당 범주의 표준 틀(**감지 → 즉시대응 → 구조적 방지 → 로직 대응**)에 맞춰 정돈하는 것.
- 클로드는 위기 관련 작업 종료 시 이 원칙에 따라 정본 갱신을 자동 수행하고 보고한다. (매번 지시 불필요)

## 3. 적용 트리거
- **키워드:** 위기·위급·응급·사고·장애·프리징·다운·끊김·데이터손실·복구·킬스위치·백업·재발방지
- **상황:** 시스템/봇 프리징 · 서버 전원·리부팅·인스턴스 장애 · 거래소 점검·레이트리밋·연결단절·시계오류 · 데이터 결손·삭제 · 통로(Tailscale) 단절 · 그 외 새 사고 유형

## 4. 갱신 절차
1. 정본의 해당 범주(①Rauto 시스템 프리징 ②AWS 서버 문제 ③거래소 문제) 본문 갱신. 기존 범주에 안 맞으면 새 범주 추가.
2. 구현 현황(§7) 갱신 — 완료/미구현 반영.
3. 개정 이력(§9)에 `날짜 · 변경내용 · 작성자` 한 줄 추가.
4. 소스(generate.js) 수정 후 `node`로 재빌드.
5. **★ 검증:** 한글 문서이므로 반드시 UTF-8 모드 — `PYTHONUTF8=1 python <docx스킬>/scripts/office/validate.py 파일.docx` (기본 cp949는 오탐).

## 5. 시점·책임
- **반영 시점:** 사고 발생 또는 관련 작업 완료 즉시. 미루지 않는다.
- **작성:** 캡틴 / 클로드 공동.

## 6. 관련 자료
- 정본 `Guide_AWS_Contingency_Plan.docx` · 소스 `_src\Guide_AWS_Contingency_Plan.generate.js`
- 부활 키트 `D:\ML\00AI_SYS` (RESTORE_GUIDE, aws_inventory, restore_scripts)
- 클로드 메모리: incident-playbook, aws-rdp-access, dauto-gdrive-backup

## 7. 개정 이력
| 날짜 | 내용 | 작성 |
|---|---|---|
| 2026-06-22 | 최초 작성. 1권 원칙 + 위기/응급 내용의 정본 통합 원칙 + 갱신 절차·검증 규칙 정립. | Claude/캡틴 |
