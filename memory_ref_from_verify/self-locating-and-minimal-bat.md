---
name: self-locating-and-minimal-bat
description: "서버/스크립트는 어느 폴더서 실행해도 self-locating, 배치는 실행명령만, 운영=NSSM(창없음)"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 7069312d-9843-4ee6-b40d-2fc5018bef04
---

AWS Windows 운영물은 ① **self-locating**(어느 폴더에서 실행돼도 repo·상태json·데이터·러너를 스스로 탐색) ② **배치는 군더더기 없이 실행명령만**(불필요 echo·set 환경변수 금지) ③ **운영은 NSSM 서비스**(창 없이 상시·자동재시작)가 기본 — 절대 "cmd 창 열어두세요"라고 안내하지 말 것.

**Why:** 2026-06-20, 하드코딩 절대경로(C:\RautoControl vs C:\RautoRepo) 불일치로 redeploy가 실제 도는 서버를 못 바꿔 배포가 계속 실패, 캡틴 격노. 또 NSSM(창 무관)을 줘놓고 "redeploy.bat 창 열어두라"고 모순 안내. 배치에 echo·set 잔뜩 넣어 지저분.

**How to apply:** control_server류는 env 우선 + 없으면 `os.path.splitdrive(HERE)` 기준 드라이브들과 위쪽 폴더를 marker 파일로 stat/glob 탐색해 REPO/STATE_GLOB/FLAG_DIR을 자동결정(못 찾으면 관례 폴백). 슬롯폴더는 STATE_GLOB의 *치환으로 도출. 배치는 `@echo off` + `python "%~dp0server.py"` 수준으로 최소화(§4·§1). 운영 배포는 NSSM 서비스 등록(자동재시작·부팅시작) 하나로. [[bat-cmd-ascii-only]]와 함께 적용(배치는 여전히 100% ASCII·CRLF).
