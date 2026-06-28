---
name: rauto-notify-telegram-phone
description: Rauto 알림·폰 연동 = 텔레그램 봇 @RautoChampBot + Gmail + Tailscale. 토큰은 AWS env, 백업은 00AI_SYS/secrets. 폰=z-fold7
metadata:
  type: project
---

Rauto 운영 알림·원격제어 연동 (2026-06-21 점검·발송테스트 OK):

**텔레그램:** 봇 `@RautoChampBot`. ops 알림 발신. 토큰/chat_id는 **AWS 서버(ec2amaz-cor6gpg) 환경변수**(`TELEGRAM_BOT_TOKEN`·`TELEGRAM_CHAT_ID`)에만 있음 — 노트북엔 없음. 토큰 유실 시 @BotFather 재발급 후 AWS env(setx) 갱신.

**Gmail 알림:** `RAUTO_GMAIL_APP_PW`(앱비번)·`RAUTO_GMAIL_USER`도 AWS env.

**★시크릿 백업:** `D:/ML/00AI_SYS/secrets/rauto_secrets_AWS.txt` (텔레그램·Gmail, git repo 밖이라 안전). AWS env는 서버 재구축 시 유실되므로 이 백업이 유일 사본 — setx /M 또는 C:\RautoControl\rauto_secrets.txt 로 복원.

**폰 연동(안드로이드 z-fold7):** Tailscale tailnet(hjoonygo@)에 노트북(grampro16-2510)·AWS(100.72.96.60)·폰(z-fold7 100.94.135.72) 3대 연결. 폰 브라우저로 `http://100.72.96.60:8787`(control_dashboard.html) 접속해 원격 제어. AWS SSH = `ssh -i ~/.ssh/rauto_aws Administrator@ec2amaz-cor6gpg.tail305e55.ts.net`(접속 확인됨).

**미결 플래그:** `RAUTO_TOKENS`(control_server RBAC) AWS 미정의 — 폰 대시보드 접속 인증 방식 별도 점검 필요(신뢰도 55, 보안 확인 권장).

관련: [[claude-config-on-d-multiboot]] · [[ml-root-multi-business-layout]]
