---
name: cp949-utf8-python-console
description: "Captain's PC console is cp949 — always set PYTHONIOENCODING=utf-8 before running any Python that prints Korean/em-dash"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: ea81935b-488d-4607-b749-3c26f49b88b5
---

캡틴 PC(한글 Windows 11)의 콘솔 기본 인코딩은 cp949라서, 한글·em-dash(—)를 print하는 Python 스크립트가 UnicodeEncodeError로 죽는다 (2026-06-11 NMultSweep 파일럿에서 확인).

**Why:** 프로젝트의 test/check 스크립트는 한글 출력이 표준이라 cp949 콘솔에서 항상 재발한다.

**How to apply:** 캡틴 승인(2026-06-11, "앞으로 모든 작업에 추가하도록")에 따라 (1) 모든 새 run.bat 1줄째에 `set PYTHONIOENCODING=utf-8` 고정 — CLAUDE.md §4에도 명문화됨, (2) 내가 PowerShell/cmd로 Python을 직접 실행할 때도 동일하게 env를 먼저 설정. 스크립트 본문 수정은 불필요(래퍼 원칙 부합).
