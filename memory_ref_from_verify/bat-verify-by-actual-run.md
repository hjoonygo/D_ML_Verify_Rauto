---
name: bat-verify-by-actual-run
description: bat 만들면 추측 금지·반드시 실제 실행으로 검증. 경로/파일못찾음 사고 방지. 캡틴이 반복 지적한 신뢰 이슈
metadata:
  type: feedback
---

캡틴 피드백(2026-06-21, 강한 어조): "배치파일 작업할 때마다 쓸데없는 데 신경쓰다가 폴더 안 맞고 파일 못 찾고 개판친다. 확실한 방법 있냐."

**Why:** bat은 '잘 만든 것처럼 보이는 것'과 '실제로 폴더 찾아 도는 것'이 다르다. 경로해석(%~dp0)·winget ID·소스 존재가 틀려도 코드상으론 멀쩡해 보임 → 포맷후/운영중에 터짐 = 캡틴 신뢰 훼손.

**How to apply (bat/스크립트 산출 시 의무):**
1. ★추측으로 "문제없을 것" 보고 금지. 반드시 실제 실행해 결과파일을 눈으로 확인 후 보고(§15 앵커정신).
2. **복원/복사류 bat 검증** = 임시 타겟으로 실제 실행: PowerShell에서 `$env:USERPROFILE`를 임시폴더로 override → `"`n`n" | & "...bat" *>$null`(pause는 stdin 개행으로 통과) → Test-Path로 복사결과 확인 → `$env:USERPROFILE` 원복 → 임시폴더 삭제. (실제 C는 안 건드림)
3. **winget 설치류 검증** = 설치는 돌리지 말고 `winget show -e --id <ID>`로 ID 실재 확인. (이번에 tailscale.tailscale 오류 → Tailscale.Tailscale 로 잡음)
4. PowerShell에서 `cmd /c` **텍스트는 sandbox가 차단**('/c' 경로삭제 오탐) → `& "....bat"`로 직접 호출.
5. bat은 ASCII·CRLF 유지([[bat-cmd-ascii-only]]), 경로는 self-locating(%~dp0 기준 상대, [[self-locating-and-minimal-bat]]).
6. ★background 작업은 **완료 후에만** 결과 확인·삭제. 끝나기 전 확인하고 폴더 지우면 헛검증(2026-06-21 실제 저지른 실수).
