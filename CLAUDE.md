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

## 6. 인수인계 2단 읽기 (토큰 절약형)
- 1단(지도): 00WorkHstr_INDEX.txt + 인수인계보고서 'Output of Chat'만 먼저 파악.
- 2단(정밀): 이번 Stg에 필요한 파일만 정독 + §2 증거 제출. 전체 선정독 금지.
- 문서 체계(참조 맵): 인수인계보고서(채팅단위) / Key노트(채팅 내 기술) /
  00WorkHstr_INDEX.txt(시간순 Stg 기록) / Basic_Trading_Environment_Setup.docx(환경) /
  Guide_AlphaDiscovery_Method_v?.docx(TIL·방법론) / Work Order(미래 과제) /
  Hstr_Ver_Up_(봇명).docx(봇별 살아있는 사양서, 00WorkHstr\00Basic_Setup_Package).
- 확정 알파는 즉시 G:\내 드라이브\00AI개발지식DB\자산관리\유동자산\자동매매\06ChampBot\
  00ALPHA_Confirm_Bot 에 저장 (세션 간 유실 방지).

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
(2026-06-11 D:\ML\verify 전수 해시 대조로 전체 해시 확정. 구버전 주의:
 07Prj_Ch3_Stg9_TrendStackSignalBot 내 bot_trendstack_signal.py는 구버전(ae6c630a...) — 사용 금지.)

## 9. 확정 알파 (변경하려면 CPCV 재검증 + 캡틴 승인)
- TrendStack: 레버22 · EXP1.559 · OPV0.25 · NMULT0.6 · N_BOOST1.0 · 업트렌드숏컷 ON
  → +827% / MDD -16.1% / Calmar 51.3 (재구성 근사 +724.9%/-15.4%)
- SidewayDCA: 레버15 · 증거금26.67% · EXP4.0 · sl_mult1.8 · 스톱아웃 -10% · 컷없음
  → PF 2.653 / +148.76% / MDD -13.61% / CPCV-p25 +70.9%
- 듀얼 동시가동: 노출배분 k=0.8 권장(풀노출은 거래단위 MDD -23.5%로 한도 위반).

## 10. 협업 톤
- 한국어 · 고딩(고등학생) 수준 · 약어 최소 · 그래프 적극 활용.
- 비논리적 요청엔 동조 말고 의도 파악·지적·대안 제시. 모르면 모른다고 한다.
- 충돌·오류 발견 시 동의 대신 플래그. 판단엔 출처와 신뢰도(95/55/15/0) 명시.
- 봇별 세부지식은 00WorkHstr\00Basic_Setup_Package의 TrendStack_CLAUDE.md /
  SidewayDCA_CLAUDE.md를 해당 봇 작업 시 읽는다.
