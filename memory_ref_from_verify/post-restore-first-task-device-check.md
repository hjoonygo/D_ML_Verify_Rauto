---
name: post-restore-first-task-device-check
description: 클로드 부활 후 첫 임무 = 전 디바이스(노트북·AWS·폰) 작업가능 자가점검 + 미비시 세팅. 캡틴 지시
metadata:
  type: feedback
---

캡틴 지시(2026-06-21): "클로드코드를 깔면 첫 번째 할 일 = 모든 디바이스에 작업가능한 세팅이 됐는지 확인, 안 돼있으면 세팅하는 것."

**Why:** 부활/포맷 후 클로드가 살아나도 노트북만 보면 안 됨 — AWS·폰까지 '전부 작업가능'해야 운영 재개. 일부만 되면 봇·알림·제어가 반쪽.

**How to apply (부활 후 또는 요청 시 자동 실행):**
1. **노트북**: D드라이브=D / Python 3.12.7 / Node / Git / Claude / 메모리14개 자동로드 / G드라이브.
2. **AWS 서버** (`ssh -i ~/.ssh/rauto_aws Administrator@ec2amaz-cor6gpg.tail305e55.ts.net`):
   SSH접속 / Python **3.10.11** / 포트 8787 LISTENING / 대시보드 http 200 / control_server(작업스케줄러 RautoControlServer) / 봇 state.json 신선도.
   - **Dauto(08Prj_Dauto_Ch1_Collector 수집봇, 창 없음)** 점검 = ① state.json `dauto_ok=True`·`dauto_stale_min<5` ② `C:\BinanceData\BTCUSDT_1m_<오늘UTC>.csv` 가 현재분과 같이 갱신 ③ `dauto_health.log` HEALTH `rows=1440/1440 gaps=0`. 창 띄우지 말고 이 흔적으로 판정(state.json은 Windows 경로로 받아 파싱 — /tmp는 win파이썬이 못 읽음).
3. **폰 z-fold7**: `tailscale status`에 online / 대시보드 https://<aws>.ts.net / 텔레그램 @RautoChampBot 수신.
4. 미비 시 세팅: 노트북=RESTORE_GUIDE 단계 / AWS=00AI_SYS/aws_inventory/AWS_SETUP_Rauto_ControlApp.txt.

**★주의(실측 교훈 2026-06-21):**
- Python 버전 분리: 노트북 3.12(requirements_backup 98개) ≠ AWS 3.10(requirements_AWS_py310 27개). 섞지 말 것.
- ★AWS 시각 = **UTC**(노트북 KST와 9시간차). state.json '오래돼 보임'은 시각착시 — 반드시 AWS now와 비교 후 stale 판단([[bat-verify-by-actual-run]] 정신: 실측·정정).

관련: [[claude-config-on-d-multiboot]] · [[rauto-notify-telegram-phone]] · [[ml-root-multi-business-layout]]
