---
name: bat-cmd-ascii-only
description: .bat/.cmd·Windows셸 실행물은 100% 영어(ASCII)만 — 한글은 cp949 cmd서 깨져 명백 실패
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 7069312d-9843-4ee6-b40d-2fc5018bef04
---

**규칙(절대): Windows에서 cmd/cp949가 파싱하는 모든 것 — .bat·.cmd·set 변수값·echo·경로 — 은 100% 영어(ASCII)로만 작성한다. 한글 한 글자도 금지.**

**Why:** 2026-06-19 R3/R4 fix·R5~7 배포 bat에 한글(`set DUAL_STRAT=최적듀얼`, 한글 echo)을 넣었다가 AWS cmd(cp949)에서 `'듀얼' is not recognized`·`'�는'`·줄 깨짐으로 전부 실패. 캡틴 수시간 낭비·강한 질책. 한글 표시명이 필요하면 bat이 아니라 **python(UTF-8) 러너 내부에서** 슬롯→이름 맵으로 결정(예: `_DMAP={"R3":("최적듀얼",1.1)}`), bat은 ASCII 키(`set DUAL_SLOT=R3`)만 전달.

**How to apply:**
- bat 작성은 **bash heredoc(`<<'EOF'` = 따옴표로 리터럴, 백슬래시·내용 보존) + CRLF**(`sed 's/$/\r/'`)로. ★python으로 bat 문자열 쓰지 말 것 — 경로의 `\t`(탭)·`\b`(백스페이스)로 깨짐(C:\Rauto3\test → C:\Rauto3<탭>est).
- bat 안에서 **금지**: `chcp 65001`, `&` 명령체이닝(`set a=x& set b=y`), 한글, 멀티라인 FOR `()` 블록(깨지기 쉬움). **한 줄 = 명령 하나.**
- python은 **전체경로**로 호출(`set PY=C:\Users\...\python.exe` 후 `"%PY%" x.py`) — SYSTEM/유저 PATH 함정 회피([[aws-schtasks-system-pitfalls]]).
- 보낸 bat은 cat -A로 탭/CRLF 확인 후 전달. 관련: [[cp949-utf8-python-console]](python print는 PYTHONIOENCODING=utf-8 별개 규칙).
- CLAUDE.md §1에도 박제됨(2026-06-19).
