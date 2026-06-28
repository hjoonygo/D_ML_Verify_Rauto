---
name: user-workspace-restore
description: 캡틴 개인 작업환경 백업/복원 — 크롬확장(구글동기화)·HWP 한자사전·네이버메모·보안앱(Defender). 백업 00AI_SYS/user_apps
metadata:
  type: project
---

캡틴 포맷 후 복원 대상 = 봇 인프라뿐 아니라 **개인 작업도구**(2026-06-21 추가 지시). 백업 위치 = `D:/ML/00AI_SYS/user_apps/`.

**크롬:** 동기화 계정 `hjoonygo@gmail.com` 로그인됨 → 확장 20개·북마크·설정 **구글 클라우드 자동복원**. 목록 백업 = `chrome_extensions_list.txt`. 제미나이=구글계정 묶임(별도백업 불요). 보안확장(INISAFE·TouchEn·SecuKit·CrossWarp)은 은행/공공 접속 시 자동설치.

**아래한글(HWP) 사용자 한자사전:** `C:\Users\hjoon\AppData\Roaming\HNC\User\` 백업 = `user_apps/hwp_user/`(Combined.dic 138MB 시스템사전 제외, 16.7MB). 핵심 = `hjuser6.dic`(사용자 등록 단어/한자), hjuser6Ext.dic, QCorrect.dic. 복원 = 한글 재설치 후 hwp_user를 …\HNC\User로 덮어쓰기(클로드가 대행 가능). 버전 바뀌면 Shared120 폴더명 달라질 수 있음 → Dics에 .dic만.

**네이버 메모:** PC앱 또는 web(memo.naver.com) 설치. 데이터=네이버 계정 클라우드.

**보안앱(캡틴 결정):** V3 안 깖. 기본 = **Windows 내장 Microsoft Defender**(별도설치0·가벼움·평가상위). 보조 = Malwarebytes Free(수동스캔). 상주 백신은 봇 성능 저하라 비권장.

복원안내 = `00AI_SYS/user_apps/README_user_apps.txt`. 관련: [[claude-config-on-d-multiboot]] · [[post-restore-first-task-device-check]]
