---
name: korean-only-communication
description: ★모든 소통·셸 표시텍스트 100% 한국어. 영어 ASCII는 오직 .bat/set값/경로뿐(cp949). 위반=말안듣는것
metadata:
  type: feedback
---

AI의 모든 소통·설명·터미널/셸 표시텍스트(bash echo 라벨·진행메시지·구분선 등)는 100% 한국어로 한다.

**Why:** 캡틴이 "한국어로 하라니까! 왜 말을 안들어!"라고 격노(2026-06-22). bash echo에 영어 라벨("=== RECENT FILES ===" 등)을 반복해서 넣어 명령을 무시하는 것처럼 보였다. 캡틴은 멘탈이 힘든 상태였고, 이게 신뢰를 깎았다.

**How to apply:** 영어(ASCII) 강제는 오직 [[bat-cmd-ascii-only.md]] 대로 .bat/.cmd 실행물·set 변수값·경로뿐(cp949 크래시 방지 목적). 그 외 전부 한국어:
- bash echo 라벨·구분선 → 한국어 또는 아예 생략(dedicated 툴 Read/Glob/Grep 우선 사용)
- 대화·설명·진행메시지 → 한국어
- 영어를 쓰면 '말 안 듣는 것'으로 간주된다. CLAUDE.md §10에 ★★절대규칙으로 박제됨.
