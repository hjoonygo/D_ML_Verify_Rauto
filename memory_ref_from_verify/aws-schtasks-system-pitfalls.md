---
name: aws-schtasks-system-pitfalls
description: "AWS(Windows) schtasks SYSTEM 계정 함정 2종 — python 풀경로 필수, setx는 /M 필수 (2026-06-13 실측 확정)"
metadata: 
  node_type: memory
  type: project
  originSessionId: d7f7f35a-1eca-4f24-b8c7-6c5be82befbf
---

AWS Windows에서 `/RU SYSTEM` schtasks로 python 스크립트를 돌릴 때 실측으로 확정한 함정:

**Why:** 캡틴 수동 cmd(사용자 세션)에선 되는데 SYSTEM 태스크만 침묵하는 비대칭이 두 번 발생 — ① Telegram_Poll Last Result `-2147024894`(0x80070002) = SYSTEM PATH에 python 없음(사용자 설치 python은 SYSTEM이 못 찾음). ② env 토큰은 `setx /M`(Machine)이어야 SYSTEM이 읽음 — User 영역이면 수동 실행만 성공.

**How to apply:**
- 태스크 /TR엔 `python` 금지 — `where python`의 실제 풀경로(WindowsApps 스텁 제외)로 등록.
- bat 안의 python 호출은 `RAUTO_PY` 머신 env 우선 + `python` 폴백 패턴(run_daily.bat v7, PC 호환 유지).
- 토큰/경로 env는 전부 `setx ... /M`. 진단 1순위 = `schtasks /Query /V`의 Last Result와 ops_alert.log 유무 대조.
- 관련: [[cp949-utf8-python-console]] (cmd 콘솔 한글 깨짐은 표시 문제 — UTF-8 파일·API 전송은 정상)
