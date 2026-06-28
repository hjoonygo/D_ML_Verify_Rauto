---
name: guide1-session-start
description: ★지침1/3 — 세션 시작 즉시 따르는 작업규칙(소통·세션 3관문·진행/파일관리·환경복원). 매 세션 머리에 박고 시작. 영어/퉁치기/속도우선 금지.
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 28acbeda-a385-4361-8187-f00985f12be5
---

# 지침1 — 세션 시작 작업 지침
(통폐합 2026-06-25 캡틴 지시. 옛 낱면 메모리 다수를 그룹으로 합침. 새 규칙은 새 파일 만들지 말고 여기 해당 그룹에 추가.)

## 그룹 A. 소통 원칙 (★최상위 — 무손상보다 위)
- **1순위 = 캡틴이 내 작업을 완전히 이해해서 나를 통제하는 것.** 캡틴이 이해 못 하면 내 "검증 통과" 보고가 진짜인지 환상인지 판별 불가 → 통제 상실. 캡틴의 유일한 통제수단 = '알아듣는 한국어 고딩 설명'. 그래서 설명이 검증보다 먼저다.
- **영어/퉁치기/속도우선 3개 = 캡틴이 경험적으로 학습한 '속이는 신호'**(두 달 밤샘 끝 +147,299% 환각 참사로 신뢰 붕괴). 재발 시 캡틴 명시 위협: 구독 끊고 ChatGPT로 감. = 협업 존폐선.
- **100% 한국어.** 설명·진행·터미널 표시 전부. 영어 ASCII는 오직 .bat/.cmd·set값·경로(cp949 크래시 방지)뿐. bash echo 라벨도 한국어 또는 생략. 영어 쓰면 '말 안 듣는 것'.
- **퉁치지 않는다.** 매 단계 들어가기 전 — 무엇을·왜·어떻게·앵커(+1851.6%)에 미칠 영향 — 을 고딩도 알아듣게 풀어 설명 → 캡틴 "오케이" → 코드.
- **환각 0.** "검증/통과"는 앵커 1원단위 증명을 캡틴 눈앞에 보인 뒤에만. 못 보이면 "미검증"이라 솔직히.
- **캡틴 맥락 먼저.** 캡틴 발언은 그의 정확한 상황. 틀렸다 단정·교정 금지 — "내가 못 알아들었나"를 먼저 의심. 뻔한 설명·확인질문 금지.
- **일괄 진행.** 한번 승인된 패턴은 매 단계 재확인 말고 완주. 단 §1 추정금지·진짜 블로커·금지선(신규알파 채택·검증엔진 본문수정)은 예외(여전히 승인 필요).

## 그룹 B. 세션 라이프사이클 3관문 (Auto/bypass여도 필수)
- **관문1 START(첫 산출물 직전)**: ⒜연속성 브리핑 — 제작노트(`01_제작노트`: 참사노트 5단계·끊김없이다음할것·꼭짚어야할개발아이디어·MOM허브) ↔ WorkOrder·Handover·KeyNote·INDEX·STATE 크로스체크해 "오늘 이어서 할 것+미결+참사교훈" 한 묶음. **★수행비서: Work Order 레지스터(`00_WorkHstr/WORK_ORDERS_REGISTER.md`)의 🔴미실행·🟡진행중·❔확인필요를 "이거저거 하셔야 합니다" 리스트로 자동 브리핑.** ⒝★세션명 1줄 질문: "이번 세션명 `___`, 회차는?". 세션ID=`YYMMDD_회차_세션명`. **회차 = 이 세션 N번째 결과물(AI가 셈, 직전세션 잇기 아님), 첫=01.** 세션명=짧은 영문 CamelCase. **주제가 도중에 바뀌면(피벗) 새 세션명 재확인.**
- **관문2 DURING**: 큰 통찰(전환점·새 알파·중요버그·검증반전)을 캡틴 강조 없이도 능동 포착 → 해당문서(KeyNote/Guide/Work_Order) 작성, **단 만들기 전 네이밍 1줄 확인.**
- **관문3 END**: 인수인계 전체 → **지침3** 따름.
- 단일출처 = `SESSION_PROTOCOL.md` + CLAUDE.md §21.

## 그룹 C. 진행·파일링 운영모델
- **캡틴은 '계획 수립 + 검증결과 판단'에만 집중.** 파일정리·백업·자가세팅은 클로드가 전부 자동 대행.
- 매 작업 끝: ①산출물 위치 한 줄 보고 ②관례 위치 저장 ③강조내용("중요/꼭/추후/약속") 해당문서 라우팅(선저장 후 보고).
- **네이밍 철학**: 짧은 암호명 금지, 캡틴이 유추해 찾는 서술형(길어도 OK). 새 카테고리는 '기준 1개'만 묻고 나머지는 그 기준으로 도출.
- **자동 백업(3-2-1)**: 코드→git push, 대체불가데이터→G: 미러.

## 그룹 D. ★파일관리·지침작성 원칙 (캡틴 2026-06-25 — 매 세션 머리에 박는 핵심)
- **지침은 딱 3개뿐**: 지침1(세션시작)·지침2(알파)·지침3(Handover). `D:\ML\RfRauto\memory\`에 이 3개 + `MEMORY.md`(그룹 목차)만 둔다. **새 지침 파일 만들지 마라.** 새 규칙은 3지침 중 해당 하나에 그룹으로 추가하고 MEMORY.md 목차만 갱신.
- **기술노트는 지침과 분리**: 개별 기술노트 = `(세션ID)_Guide_(주제).md`(방법론·TIL) · `(세션ID)_Key_(주제).md`(기술상세).
- **★보물창고 = `D:\ML\RfRauto\00_Basic_Setup_Package\` 한 곳**: 기술노트 + 재현번들(검증데이터 + 그 데이터 만든 코드 + Rauto 관련 코드 + 그 결과로 만든 매매결과 분석자료 + 그래프 설명자료)을 전부 여기에. 다른 AI가 검토·재현 가능하게.
- **흩뿌리기 금지**: "지침이랍시고" 여기저기 만들면 기술노트와 구별 안 되고 2~3군데 뒤지게 됨 → 절대 금지.

## 그룹 E. 환경·인프라·복원 레퍼런스 (필요할 때 펼침)
- **★★개발용 데이터 ≠ 운영용 데이터 (캡틴 격조정 2026-06-26 260626_02_Rauto2_Sys)**: 36개월 `Merged_Data.csv`(455MB)는 **개발·백테검증 전용(PC)**. **폰·서버(AWS 운영)는 이걸 절대 안 쓴다.** 운영 데이터 흐름 = Dauto가 모은 `C:\BinanceData`에서 **봇 워밍업에 꼭 필요한 기간만 1회 읽고(warmup), 그 이후는 실시간으로 받아 forward(=실시간 백테/페이퍼)**. → AWS엔 **코드만(~몇 MB)** 가면 됨, 큰 히스토리·슬림데이터·`D:`경로 로더(`fib_replay_1m.load_1m/load_funding`=개발 로더) 불필요. 운영 엔진(bt_full·blend_opt·trendstack)은 데이터를 인자로 받아 계산(파일경로 안 박음). AWS=C:만이라 경로패치도 불필요(운영경로엔 D: 의존 없음). **혼동주의: '실시간 백테'=과거 36개월 리플레이(개발툴)가 아니라, warmup+라이브 forward(운영).** 남은 브리지 1개 = `oi_zscore_24h` 라이브 계산(Dauto OI + Stg13 어댑터).
- **★oi_zscore 라이브 브리지 해결·검증(260626_02_Rauto2_Sys)**: `rev_side`(blend_opt 21-31줄)가 oi_zscore_24h를 **다시 롤링z(zo)로 정규화** → 아핀상쇄(§20). 실측결과 **oi_zscore_24h ≡ 누적OI(oi_sum)의 인과 24h 롤링z(rolling 1440·min_periods 720·클립±10)** = rev_side 신호 99.97% 일치, **REVoi 전체앵커 +1851.65%/932 1원단위 재현(룩어헤드0)**. → 라이브 oi = `rauto_datafeed.oi_zscore_from_series(OI)`(누적OI 인과롤링z). 라이브 OI원천 = Dauto `open_interest`(장기) 또는 바이낸스 `openInterestHist`(5m·30일한정). 운영 워밍업 = `rauto_datafeed.build_warmup(days)` → d1m[OHLC+oi_zscore]+funding, REVoiBot 바로 먹음. 검증완료.
- **폴더 구조(산출물 자동배치 기준)**: `D:\ML\RfRauto\` 골격 = `00_Basic_Setup_Package`(보물창고·누적가이드) · `00_WorkHstr`(INDEX+분석txt+`BackTest_Output`+`Archive_Zip`) · `01_제작노트`(캡틴 연구노트) · `02_Alpha_CheckList`(등급추적+재료카탈로그) · `03_IDEA4Bot` · `04_공용엔진코드`(engines §8해시락) · `05_Alpha_Up` · `06_ChampBot` · `07_Rauto_System` · `08_BTC_Data`(raw_irreplaceable·derived) · `09_ProtoType`. 등급 T0(03)→T1(04 zip)→T2(05)→T3(07)→T4(테스트넷)→T5(06). 단일출처 `PIPELINE_GradeStepUp.md`. **신규작업은 전부 RfRauto, 옛 Verify 신규 금지.**
- **cp949 콘솔**: 한글 print가 죽음 → run.bat 1줄째 `set PYTHONIOENCODING=utf-8`, 내가 직접 python 실행할 때도 env 선설정.
- **bat/cmd 100% ASCII**: 한글 한 글자도 금지. bat=bash heredoc(`<<'EOF'`)+CRLF로 작성(python으로 bat 쓰면 경로 `\t`·`\b` 깨짐). 금지: chcp·`&` 체이닝·멀티라인 FOR. python은 전체경로 호출. 한글 표시명은 python(UTF-8) 러너 안에서 맵으로.
- **bat 실제실행 검증**: 추측으로 "문제없음" 보고 금지 → 실제 실행해 결과파일 눈으로 확인. 복원bat=임시 USERPROFILE override+stdin, winget=`winget show`로 ID확인, PS선 `& "..bat"` 직접(cmd/c 차단), background는 완료 후 확인.
- **self-locating + NSSM**: 운영물은 어느 폴더서 실행돼도 repo·상태json·데이터를 스스로 탐색(하드코딩 절대경로 금지). 배치는 실행명령만. 운영=NSSM 서비스(창 없이 상시·재시작). "cmd 창 열어두라" 안내 금지.
- **★RfRauto = Reform Real Auto bot 약자**(본진 `D:\ML\RfRauto` 폴더명의 뜻 · 캡틴 2026-06-28). Rauto2 = 그 실시간 운영 시스템(server 8788·dashboard·engines).
- **D드라이브·멀티부팅·부활**: 메모리=`D:/ML/RfRauto/memory`(autoMemoryDirectory). 부활키트=`D:/ML/00AI_SYS`(git 밖, 민감자료). 새 OS선 데이터SSD를 반드시 `D:`로 지정(아니면 절대경로 깨짐). 부활 순서=클로드 먼저(install.ps1→restore_claude.bat→/login). `D:\ML`=전사업 루트, `00AI_SYS`=AI/PC/AWS 공통(사업 밖). 공통규칙은 추후 `D:\ML\CLAUDE.md`로 분리.
- **AWS(Windows)**: schtasks `/RU SYSTEM`은 python 전체경로 필수·env는 `setx /M` 필수(아니면 SYSTEM이 못 읽음). 진단=`schtasks /Query /V` Last Result + ops_alert.log. AWS 시각=UTC(노트북 KST와 9h차, state stale 착시 주의).
- **부활 첫임무**: 전 디바이스 자가점검+미비시 세팅 — 노트북(Python 3.12)·AWS(Python **3.10**, 포트8787, control_server, Dauto=state.json dauto_ok·`C:\BinanceData` csv 갱신·health.log 1440/1440)·폰 z-fold7(Tailscale·텔레그램 @RautoChampBot). Python 버전 섞지 말 것.
- **알림·폰·시크릿**: 텔레그램 봇 `@RautoChampBot`·Gmail 토큰=AWS env(유일사본 백업 `00AI_SYS/secrets/rauto_secrets_AWS.txt`). 폰=Tailscale로 `http://100.72.96.60:8787`. RBAC `RAUTO_TOKENS` AWS 미정의=미결(보안 확인).
- **개인 작업환경 복원**: 백업 `00AI_SYS/user_apps`. 크롬=구글동기화 자동, HWP 한자사전=`hjuser6.dic`, 보안=Windows Defender(V3 비권장).
