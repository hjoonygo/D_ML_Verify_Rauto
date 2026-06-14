# CLAUDE.md — Rauto 자동매매봇 개발 공통 척추 (D:\ML\verify)
# 버전 v0.1 (2026-06-11) · 이 파일이 모든 규칙의 단일 출처. 다른 문서에 복붙 금지(참조만).

## 0. 프로젝트 한 줄
Binance BTC 선물 자동매매 시스템 Rauto(챔피언 아키텍처): TrendStack(추세) + SidewayDCA(횡보)
듀얼봇. 목표 = 월 +10% · 매월 양수 · 절대 MDD -20% 이내. 본진 = D:\ML\verify (데이터 전부 여기).

## 1. 절대 금지 (위반 = 작업 무효)
- 추정 코딩 금지: 파일·데이터를 직접 열어 확인하기 전엔 코딩하지 않는다. 없으면 캡틴에게 요청.
- 검증된 엔진 본문 수정 금지 (래퍼/플러그인으로만): §8 해시 목록의 파일들.
- 신호엔진 COST=0.0004(4bp) 변경 금지 — 바꾸면 +827% 전체 재검증 필요. (§7 비용 2레이어)
- label 계열(label_smc, 사후 라벨)의 실시간 사용 금지 — 룩어헤드. feat_struct만 허용.
- 한글 파일명 금지(zip 에러). 모든 산출 파일명은 영문.
- 선보고 후작업: 코딩·수정 전 "~문제가 있는데 ~방식으로 진행할까요?" 승인 필수.
- 출처 없는 수치·주장 금지(거짓 간주). 옛 결정·수치 삭제 금지('대체됨'으로 보존).

## 2. 증거 프로토콜 (— "읽었다/확인했다" 주장의 의무 증거)
파일을 읽었다고 주장하려면 아래를 제출한다. 못 대면 '안 읽음'으로 간주하고 다시 읽는다.
- 코드: ① 총 줄수 ② 핵심 상수/함수 1개를 줄번호와 함께 인용 (예: "27줄 COST=0.0014")
- 데이터: ① 행수 ② 기간(min~max) ③ 핵심 컬럼명
- 결과 재현: 기대값과 대조해 일치/불일치를 숫자로 보고 (예: "cap 24876 = best.csv 일치")
- 과거작업 참조: 00WorkHstr_INDEX.txt 해당 줄 또는 (분단위시간).txt를 인용

## 3. 작업 사이클 (Stg)
- 명명: (Proj회차)Prj_Ch(채팅회차)_(채팅창명)_Stg(이번 채팅 N번째 산출물)_(작업명)
- 흐름: 선보고·승인 → 코딩(기존코드 수정부 먼저 보여주고 핵심요약 고딩설명) →
  사전실행(컨테이너/로컬에서 PASS 확인) → 산출물 전달 → PC 실행 → 결과 분석(§5 템플릿)
- 모든 결과는 BTC 선물계좌 $10,000 복리 기준.
- PC 테스트 코드는 연산 최적화(벡터화·최소 데이터)로 빨리 끝나게 작성.

## 4. 폴더·산출물 구조
- Stg 산출물 폴더: D:\ML\verify\(Stg풀네임)\ 안에 고정 3종 + 근간:
  test_(풀네임).py (결과 주인공) / check_(풀네임).py / run.bat (군더더기 없이 실행명령만)
- run.bat 1줄째는 반드시 `set PYTHONIOENCODING=utf-8` (한글 Windows cp949 콘솔에서
  print 크래시 방지. 2026-06-11 NMultSweep 파일럿에서 확인·캡틴 승인).
  + 근간 데이터·py 반드시 동봉 (없으면 "왜 하는지 모르는 테스트"가 된다)
- 경로: 데이터는 한 단계 위(D:\ML\verify) → 상대경로 .. 또는 절대경로로 정확히.
- check.py 3역할: ① 오염검사(파일명·SHA256 대조·중복/누락) ② 분석을
  D:\ML\verify\00WorkHstr\(YYYYMMDDHHMM).txt 저장 ③ 00WorkHstr_INDEX.txt에 한 줄 추가.
- 결과는 전량 파일로만(오염검사·분석txt·INDEX). 복붙 요청 금지.

## 5. 결과분석 템플릿 (결과 CSV가 오면 자동 적용 — 매번 지시 불필요)
1) 응답 첫머리: "데이터 출처 선언" + "사용명칭 정의" (없으면 기만의 시작)
2) 의미없음 vs 수확을 근거와 함께 구분 (절대값 근사·아티팩트는 '의미없음'으로 명시)
3) 장세별·년도별·롱숏별 분해: PF·수익률·손익비·거래수·복리수익금 — 표 + 동일 그래프
4) 알파/개선 레버 전부 나열 + 긍정/부정 시나리오 + 단계별 검증안 + 신뢰도(95/55/15/0)
5) 그래프·출력은 사전확인 후 고딩(고등학생) 수준 비교설명. 그래프 라벨은 영문(폰트 깨짐).
6) 파라미터 채택 기준: full-표본만 보지 말 것 — CPCV/워크포워드 통과만 '채택'.
7) CPCV 잣대: 표준6그룹(15경로)=본선 · 연도4그룹=참고. 관대한 잣대로 PASS 선언 금지(캡틴 확정 2026-06-12).

## 6. 인수인계 2단 읽기 (토큰 절약형)
- 1단(지도): 00WorkHstr_INDEX.txt + 인수인계보고서 'Output of Chat'만 먼저 파악.
- 2단(정밀): 이번 Stg에 필요한 파일만 정독 + §2 증거 제출. 전체 선정독 금지.
- 문서 체계(참조 맵): 인수인계보고서(채팅단위) / Key노트(채팅 내 기술) /
  00WorkHstr_INDEX.txt(시간순 Stg 기록) / Basic_Trading_Environment_Setup.docx(환경) /
  Guide_AlphaDiscovery_Method_v?.docx(TIL·방법론) / Work Order(미래 과제) /
  Hstr_Ver_Up_(봇명).docx(봇별 살아있는 사양서, 00WorkHstr\00Basic_Setup_Package).
- 확정 알파는 즉시 G:\내 드라이브\00AI개발지식DB\자산관리\유동자산\자동매매\06 ChampBot\
  00ALPHA_Confirm_Bot 에 저장 (세션 간 유실 방지). (경로 정정 2026-06-12: '06 ChampBot' 공백 포함)

## 7. 비용 2레이어 (혼동 반복 주의 — 캡틴이 매우 짜증냄)
- 신호엔진(trendstack_signal_engine/SpTrd_Fib 101줄) COST=0.0004(4bp):
  '어느 봉에 진입·청산할지' 거래선정 전용. P&L에 절대 안 씀. 절대 변경 금지.
- 실제 P&L = 실행엔진(rauto_paper_engine 27·28줄) COST=0.0014(14bp)+SLIP=0.0005(5bp)
  +MMR티어+실펀딩. 비용 의심 시 신호엔진 말고 실행엔진부터 열 것.

## 8. 검증엔진 해시 (무수정 대조 기준 — check.py와 동일)
- trendstack_signal_engine.py  c9d784bfd81e8ed4ffccbc07fd3725ee99738c5b42c71102d59ab616a1c8fa2d  (SpTrd_Fib 1:1 추출본)
- bot_trendstack_signal.py     040da0d277d166cae1456c9c2ea340fd8b8d6c1ae9d079713cef22dc30ffb08a
- rauto_paper_engine.py        f3ff3e652c2d60338ae238807aff322dd5fe632a811348d50607b1e3969c90a3
- rauto_contract.py            40b974ac7859a95fe19b31aa8d7fd503a4dee00726da75c8bd06082b6576791b
- SpTrd_Fib_V1_Champion.py     7f9192e3d50b1afd659a02b9e75764e5438ad57809c93093ab5f1973bb79ca75
- SidewayDCA_Stg7_engine.py    dfdfac4394cd780939d4b368d3ccabfbfab8d599ff1236b11f7f0d80f0823086
- dauto_collector.py           0aa01d98688f66298e4ee3e1b7372df7339a08efde9e7b6be986fab71f5428f4  (Dauto v1 수집봇 — 수정 시 Stg 오염검사 대조 기준)
- causal_ledger.csv            c4964c5566af96311059172c59ffc17d4f374ebd608f5b30b409b8fbf122b4b9  (SidewayDCA 인과 84거래 확정원장, Stg8)
- compute_oi_derived_features.py  33ecde5987c04d0f6946d28ad0c057e295060b8f64a21b45ab6970cd391af903  (OI파생 원본 v2, D:\ML — ★주의: Derived(05-07)만 일치. 실사용 Merged_Data.csv(=REPAIRED 05-11)의 oi_zscore_24h는 REPAIRED 계보(z전체shift·mp720·±10클립) — 캡틴 채택 ① 2026-06-12. 라이브 표준 = Stg13 oi_zscore_adapter.py. LINEAGE_WARNING_oi_zscore.txt 필독)
- regime_feature_extractor.py  c3ace85e44cad8b220bc051c231d2544413d1f47e634bbc1370f87210f751a28  (atr_ratio 등 feat 생성원, Regime_PC_2026-05-21 — Stg15 수식게이트 0불일치 검증. 라이브 어댑터 = Stg15 atr_ratio_adapter.py, 워밍업 N=137 4H봉 실측)
- alert_telegram.py            94649cef70658929df43b761230f89d5d60db1b70e76d5d66e63781ab98acfcd  (Stg16 ops v2 — AWS 발신불능 패치 2026-06-13: env strip·form인코딩·무프록시 우선·reason로그. 구 c8fce012... 대체됨. ops 7종 전체 해시는 check_Stg16 상수가 관리)
(2026-06-11 D:\ML\verify 전수 해시 대조로 전체 해시 확정. 구버전 주의:
 07Prj_Ch3_Stg9_TrendStackSignalBot 내 bot_trendstack_signal.py는 구버전(ae6c630a...) — 사용 금지.)

## 9. 확정 알파 (변경하려면 CPCV 재검증 + 캡틴 승인)
- TrendStack: 레버22 · EXP1.559 · OPV0.25 · NMULT0.6 · N_BOOST1.0 · 업트렌드숏컷 ON
  → +827% / MDD -16.1% / Calmar 51.3 (재구성 근사 +724.9%/-15.4%)
- SidewayDCA(인과봇 ch4s7 · Stg8 재인증 채택): 레버15 · 증거금26.67% · EXP4.0 · sl_mult1.8
  · 스톱아웃 -10% · 컷없음 → PF 2.36 / +170.2% / MDD -15.6% / CPCV-p25 +81.3% (인과 84거래)
  (대체됨: 박제 PF 2.653/+148.76%/-13.61%/+70.9% — 인트라바 선지식 포함, Stg8에서 인과로 교체)
- 듀얼 동시가동 확정 = k0.77 + SW ER>=0.40×0.5 댐핑(쿠션 용도, TS 무댐핑):
  +1097.2% / MDD -16.24% / 표준6 CPCV p25 +73.0%·최악폴드 -19.59%·-20%위반 0
  (무댐핑 최악폴드 -23.58%·위반1 대비 개선, Stg12B 게이트 충족·캡틴 조건부 승인 2026-06-12).
  k 상향(0.93 등)은 기각 — 표준6 위반 2 = 라이브 시작일 리스크. 재평가는 라이브 3개월 후(Work Order).
  (대체됨: k=0.77 단독 확정(+1059.6%/MDD -19.33%, Stg9 2026-06-11) / 잠정 k=0.7(Stg8 자체합성)
   / k=0.8 권장(박제, 인과 기준 -20.0% 경계로 보류))

## 10. 협업 톤
- 한국어 · 고딩(고등학생) 수준 · 약어 최소 · 그래프 적극 활용.
- 비논리적 요청엔 동조 말고 의도 파악·지적·대안 제시. 모르면 모른다고 한다.
- 충돌·오류 발견 시 동의 대신 플래그. 판단엔 출처와 신뢰도(95/55/15/0) 명시.
- 봇별 세부지식은 00WorkHstr\00Basic_Setup_Package의 TrendStack_CLAUDE.md /
  SidewayDCA_CLAUDE.md를 해당 봇 작업 시 읽는다.

## 11. Claude AI(웹) ↔ Claude Code(PC) 협업 프로토콜 (크로싱=토큰·시간, 최소화가 목표)
- 직접 실시간 통신 채널 없음(분리 세션). 비동기 다리 3개로만 전달:
  ① CLAUDE.md = Code 세션 자동로드(반복설명 제거) · ② STATE 1장 = 압축 핸드오버 ·
  ③ 공유 G드라이브 파일 = STATE_Rauto.txt(06 ChampBot 폴더, Code가 직접 읽기/쓰기 — 캡틴 복붙 불요).
    → 매 작업 끝에 Code가 STATE_Rauto.txt 본문 6칸(직전작업/PASS·FAIL/다음1수/미결플래그/알파변동/WorkOrder)을 최신화.
- 로그 전체 복붙 금지. 작업 끝에 STATE 1장(≤25줄)만 크로싱:
  ① 직전작업(Stg명) ② PASS/FAIL+핵심수치 ③ 다음 1수 ④ 미결 플래그(신뢰도). 터미널 로그는 분석txt에만.
- 역할 고정(한쪽서 끝낼 일 중간에 넘기지 말 것):
  · Code(PC) = 파일조작·SHA256·백테스트·AWS 직접 손이 닿는 일.
  · Claude AI(웹) = 알파분석·전략·비판검증·문서작성·웹검색.
  작은 일은 모았다 1회 크로싱(크로싱 1회 = 복붙 1회 = 토큰).
- 완료 즉시 INDEX 기록 의무: 캡틴 위임 작업(AWS schtasks 등)의 '완료 줄'을 안 남기면
  다음 세션 §6 지도엔 '미완'으로 읽혀 헛걸음 발생(2026-06-13 HOURLY 중복 런북 사고). 위임=미완 아님, 완료=INDEX 한 줄.

## 12. 작업 적용방법 · AI 이식성 (작업방식 단일정의 — 캡틴 지시 2026-06-15)
- 실행주체: Claude(앱의 Claude Code)가 PC에서 D:·G: 드라이브 파일을 직접 읽기·생성·수정·저장하고,
  Bash·PowerShell·Python·node·git을 실행하며 docx·zip·png·csv까지 만든다. STATE_Rauto.txt(G드라이브)도
  직접 읽고 덮어쓴다. → 캡틴 복붙 불요, AI가 손으로 전부 수행. (이번 세션 전체가 그 증거.)
- 단일출처: 이 CLAUDE.md가 자동로드되는 규칙 단일출처. 새 세션은 이 파일부터 펼친다.
- ★저장위치 확인 규칙(상시 — 매 작업 끝마다 적용): ① 산출물 위치를 캡틴에게 한 줄로 알리고
  ② 관례/합의 위치에 저장한다. 관례 위치:
  · 확정/유력 알파 = G:\내 드라이브\...\06 ChampBot\00ALPHA_Confirm_Bot
  · 인수인계 패키지 = D:\ML\Verify\(Stg풀네임).zip (+ 봇 사양서·Guide·Basic은 00Basic_Setup_Package)
  · 분석·오염검사 txt = D:\ML\Verify\00WorkHstr\(시각).txt + INDEX 한 줄
  애매하면 저장 전 위치를 묻는다. 아웃바운드·덮어쓰기는 §1대로 확인.
- AI 이식성(다른 AI로 교체해도 동일 작업): 새 AI 온보딩 5단계 —
  ① CLAUDE.md 정독(규칙) ② STATE_Rauto.txt(현황 1장) ③ 00WorkHstr_INDEX.txt(시간순 Stg)
  ④ Basic/Guide/Hstr 문서맵(§6) ⑤ §8 해시로 무수정 엔진 확인. 드라이브 직접접근만 되면 어떤 AI든 동일 산출 가능.
- GitHub: origin = https://github.com/hjoonygo/D_ML_Verify_Rauto.git 연결됨(자격증명 helper=manager, 인증 작동).
  백업·이력은 git commit/push로(캡틴 승인 후). gh CLI는 미설치(PR자동화용 선택, push엔 불필요).

## 13. 강조 자동 라우팅 · 문서 작성지침 (캡틴 지시 2026-06-15)
- 가능 여부(정직): 완전 무인 자동(훅)은 판단이 필요해 제한적. 실효 방식 = AI가 매 턴 따르는 '라우팅
  프로토콜'(이 절). 캡틴이 강조하면 AI가 유형 판별 → 해당 문서에 즉시 기록(선저장 후 한 줄 보고).
- 강조 트리거어: "중요/꼭/반드시/추후·나중에/계속(연구·토론)/잊지마/약속". 이 말이 나오면 휘발 금지.
- 라우팅 표 (강조 유형 → 저장 문서):
  ① 즉시 사실·완료 → 00WorkHstr_INDEX.txt (한 줄: 시각|Stg|내용|src)
  ② 범용 규칙·환경 변화 → Basic_Trading_Environment_Setup.docx (표지 버전·날짜·이력 갱신)
  ③ 방법론·노하우(TIL) → Guide_AlphaDiscovery_Method_v?.docx (수렁↔밧줄/TIL 양식 + 출처·신뢰도태그)
  ④ 이번 챗 산출·기술 → 인수인계보고서 Handover_*.docx + KeyNote_*.docx (코드전문·신뢰도표)
  ⑤ 미래 과제·재검토 → Work Order_(작업명)_(YYYYMMDD).docx 신규 + STATE [6]칸 + INDEX
- 각 문서 작성지침(요약):
  · INDEX: 한 줄=한 Stg, 영문 파일명, 끝 줄바꿈 보장(이어붙기 사고 방지), UTF-8.
  · Basic.docx: 모든 봇 공통 '범용 규칙'만. 특정봇 수치 금지(그건 인수인계로). 변경 시 버전·이력.
  · Guide.docx: 방법론만. TIL은 출처(채팅·날짜·Stg)+신뢰도. 기존 보존, 틀린 건 '대체됨'.
  · Handover/KeyNote: Output of Chat 부각, 7섹션, 코드전문, 신뢰도표, 영문명, 1 zip.
  · Work Order: 미래 할 일 — 맥락→과제→완료조건→재평가시점. 완료 시 INDEX '완료줄'.
  · 봇 사양서 Hstr_Ver_Up_(봇명).docx: ADR·공란색인·편집규약(0장) 준수, 지우지 말고 대체.
- 원칙: 강조는 한 곳이라도 기록 안 하면 다음 세션에 유실. 'STATE 미결플래그(신뢰도)에도 같이' 남긴다.
