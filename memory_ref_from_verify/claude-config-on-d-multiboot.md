---
name: claude-config-on-d-multiboot
description: 클로드 메모리는 D:/ML/Verify/memory로 이사됨(autoMemoryDirectory). 멀티부팅/C포맷 대비. 새 OS선 데이터SSD를 D로 지정해야 경로 보존
metadata:
  type: project
---

캡틴 노트북 = SSD 2개·멀티부팅 예정, 기존 C드라이브 **포맷 예정**(2026-06-21 결정). 데이터는 D 보존.

**환경 사실:** 클로드 설정/세션/메모리는 원래 전부 `C:\Users\hjoon\.claude\`(C드라이브)에 있어 포맷 시 소실. `CLAUDE_CONFIG_DIR`은 미지원(claude-code-guide 확인). 메모리만 옮기는 공식 방법 = `autoMemoryDirectory` 설정.

**적용한 안전장치(2026-06-21, 포맷 前 시행):**
- 메모리 14개 → `D:/ML/Verify/memory/` 로 이사(라이브 위치). 이제 새 메모리는 여기에 쓴다(C 아님).
- `D:/ML/Verify/.claude/settings.local.json` 최상위에 `"autoMemoryDirectory": "D:/ML/Verify/memory"` 추가(JSON검증 OK).
- 부활 키트 = **`D:/ML/00AI_SYS/`** (claude_restore/settings(전역·MCP·gitconfig)·conversations(대화 60MB)·requirements 98개 / ssh_keys(rauto_aws SSH키) / aws_inventory / docs/RESTORE_GUIDE.txt). git repo(Verify) **밖**이라 민감자료 GitHub 유출 원천차단. 인증(.credentials.json)은 보안상 미백업 → `/login` 재발급. ★폴더 비전은 [[ml-root-multi-business-layout]].

**AWS 접속 = Tailscale + SSH:** 호스트 `ec2amaz-cor6gpg.tail305e55.ts.net`, 키 `~/.ssh/rauto_aws`(키트에 백업). AWS 서버는 클라우드라 포맷과 무관하게 계속 가동 — 노트북이 잃는 건 '접속 열쇠'뿐. 부활 시 사람관문(클로드설치+/login·드라이브D지정·브라우저인증 GitHub/구글드라이브/Tailscale·런타임설치 UAC)만 캡틴이, 나머지(pip복원·git·ssh키복원+권한·AWS제어·봇실행)는 클로드가 RESTORE_GUIDE대로 수행.

**멀티부팅 핵심:** D는 포맷 안 하므로 메모리는 자동 부활. 단 **새 OS에서 데이터 SSD를 반드시 `D:`로 지정**(디스크관리)해야 `D:\ML\Verify` 절대경로(CLAUDE.md 본문·설정·봇)가 전부 무수정 작동. C로 잡히면 경로 전부 깨짐. 기존 C로 부팅 시엔 지금과 100% 동일(문제 0).

**★부활 순서 = 클로드 먼저(캡틴 지시 2026-06-21):** Claude Code는 Node·Python 불필요한 단독 바이너리(이 노트북도 native `.local/bin/claude.exe`). 그래서 **Phase1(사람~5분)** = ①SSD를 D지정 ②PowerShell `irm https://claude.ai/install.ps1 | iex` ③`restore_claude.bat` 더블클릭 ④`cd D:\ML\Verify; claude`→/login → 메모리14개 뜨면 정상화 완료. **Phase2** = 클로드에게 "RESTORE_GUIDE대로 나머지 복원·점검" 한마디 → Python설치·pip·Git·Tailscale·구글드라이브·SSH권한·AWS/Dauto/텔레그램 점검을 클로드가 수행. 진입점 = `D:\ML\START_HERE_AfterFormat.html`(클릭형 체크리스트, Phase1빨강/Phase2초록).

관련: [[save-location-and-emphasis-routing]] · [[self-locating-and-minimal-bat]]
