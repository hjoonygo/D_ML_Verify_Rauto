---
name: rfrauto-restructure
description: ★진행중 — Rauto Ver2.0 재건(RfRauto). 작업폴더 D:\ML\Verify→D:\ML\RfRauto 이전, 멀티사업 구조. 옛 Verify는 보존후 압축
metadata:
  type: project
---

**Rauto "수익률 환상" 참사 → Ver2.0 재건(RfRauto = Reform Rauto). 2026-06-22 시작, 진행중.**

참사(캡틴 6/20 저녁 깨달음, 확인됨): 백테 +11397% 같은 수익이 실거래와 다른 "환상"(실행현실=체결·슬리피지·펀딩비·강제청산 누락 or 재구성버그). 대책 = 실거래 동일검증 + 신호로직/Rauto실행/비용현실 **분리 검증**. (퀀트 1순위 실패모드)

**새 멀티사업 구조 (D:\ML\ 루트):**
- `D:\ML\CLAUDE.md`(전사업 공통규칙) · `D:\ML\memory\`(공통 메모리) · `D:\ML\00_Common\`(공통 방법론·템플릿) · `00AI_SYS\`(인프라, 기존)
- `D:\ML\RfRauto\`(BTC선물 Ver2.0) — ★폴더명=캡틴 G드라이브 방 번호와 동일(그가 알아보게). 골격:
  · `00_Basic_Setup_Package`(날짜없는 누적가이드) · `00_WorkHstr`(INDEX+events+`Archive_Zip`=분기점 zip)
  · `01_제작노트`(캡틴 연구노트=전략구상일지·지표연구·ML연구, G:"00 제작노트"서 복사. ★.gdoc=구글독스 링크라 진짜백업 아님→export 필요. 01_PlugIn_Modules는 캡틴이 "쓸모없다" 폐기)
  · `03_IDEA4Bot`(①아이디어·TV·pine·py) · `05_Alpha_Up`(②후보확인·집중관리) · `06_ChampBot`(③검증→챔피언)
  · `04_공용엔진코드`(공유코드 = engines§8해시락·data_adapters·backtest_harness·rauto_core. 캡틴 '보이게 03번방' 지시)
  · `07_Rauto_System`(④시스템테스트 = execution_cost·emergency_lock) · `08_BTC_Data`(raw_irreplaceable·derived·regenerate_scripts)
  · `09_ProtoType`(배포한 매매봇시스템 압축관리)
  · ★등급 졸업 T0(03_IDEA4Bot)→T1(04_공용엔진코드 zip반제품)→T2(05_Alpha_Up 실시간)→T3(07_Rauto_System)→T4(테스트넷)→T5(06_ChampBot copy봇). 식별=세션ID(YYMMDD_횟차_세션명, ★A### 폐기·캡틴 2026-06-23) + `alpha_card.md`. 명명·등급 단일출처=`PIPELINE_GradeStepUp.md`. 02_Alpha_CheckList=등급 추적 대시보드
- 미래 자산봇 = `D:\ML\Kospi\` 등 동일골격 분기(07_Rauto_System 엔진·비용모델만 시장별 교체)

**캡틴 4단계 알파 파이프라인:** 1)TV아이디어(pine+py포팅) 2)Alpha_UP 후보확인(신호+Rauto결정·비용→월6%↑PF) 3)검증(CPCV+바이낸스실시간, 슬립·펀딩·안전락) 4)Rauto시스템 자체테스트. 목표=월12%·손실달 3년내 4달이하.

**명명규칙:** 누적가이드=날짜/버전 파일명 금지(내용에 이력). 분기점=날짜O + zip번들(/docs /code /data /collector /verify). §8엔진명 무변경.

**G백업(대체불가만, 3-2-1):** `G:\...\자동매매\RfRauto\{raw_irreplaceable,Archive,Guides}` + `00_Common_Backup`. 코드=GitHub, derived=재생성(백업안함).

**완료:** 골격 D:+G: 생성 / OI 왕관보석(BinanceData 43파일) 3중백업(AWS+D:RfRauto\20_Data\raw_irreplaceable+G:).
**미완(다음, §1 위험단계):** ①D:\ML\Verify 하드코딩 의존성 지도(CLAUDE.md·settings.local.json autoMemoryDirectory·dauto_collector INDEX경로·GitHub repo) ②핵심 이관(해시락 엔진→10_Core, SHA256 재검증) ③memory→D:\ML\memory 이사(설정수정) ④CLAUDE.md 공통/사업 분할 ⑤옛 Verify 보존→압축.

관련: [[ml-root-multi-business-layout]] [[champion-exit-untouched-lever]] [[sl-touch-reconstruction-lookahead]] [[korean-only-communication]]
