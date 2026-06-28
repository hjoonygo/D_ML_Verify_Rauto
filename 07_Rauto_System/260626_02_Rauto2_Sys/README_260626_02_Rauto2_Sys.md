# 260626_02_Rauto2_Sys — Rauto2 (서버+폰 REVoi 실시간 백테)

세션 2026-06-26. **옛 b32 라이브시스템을 개조 + 신규 5모듈 코어(DataHub·CEX·오케스트레이터)에 연결**해
서버(포트 8788)와 스마트폰(PWA)에서 **REVoi 봇을 로딩하고 실시간 백테(리플레이)**를 돌린다.
캡틴 역할분담 기준: **봇 = 신호/진입/청산(원장)** · **Rauto = 체결·비용(CEX)·데이터교신(DataHub/datafeed)·사이징** · **서버 = 관제/표시**.

## 1. 이 세션이 한 것
- ★캡틴 지시대로 **검증 먼저**: 옛 b32 `control_server.py`(642줄)+`control_dashboard.html`(547줄) 직접 정독·건전 확인.
- ★**매칭 시뮬레이션 3관문 PASS** 후 진행: A 무손상(+1851.65% 0.000%p) · B 거래오버레이(최종잔고 차 $0.000000) · C 중앙 px(캔들 동일).
- ★신규 엔진 2개(`04_공용엔진코드/engines/`):
  - `rauto_live.py` — 리플레이/라이브 구동기. **검증된 batch 원장을 시각순으로 '드러내기'**(재계산·재구현 0 = 무손상). 룩어헤드 차단(now까지 마감봉·거래만). **중앙 px 1개 최상위 공유**.
  - `rauto_datafeed.py` — 바이낸스 공개REST/Dauto CSV 라이브 교신(현재가·1m). 의존성0.
- ★서버/폰(이 폴더):
  - `260626_02_Rauto2_Sys_server.py` — 옛 b32 개조. 외부 슬롯러너 대신 **rauto_live 인프로세스 구동 + 리플레이 클록**. 포트 8788.
  - `260626_02_Rauto2_Sys_dashboard.html` — b32 차트 재사용 + **최상위 state.px 공유** + 리플레이 컨트롤(일시정지/속도/처음/끝) + **실시장 토글**.
  - `run.bat` / `nssm_setup_rauto2.bat` — 실행 / 무인 서비스화(ASCII·CRLF).

## 2. ★해결한 버그 — "봇마다 실시간 차트가 다르게 나타남"
- 근본원인: 옛 시스템은 슬롯(C:\Rauto1~8)마다 러너가 **각자 px(캔들)를 따로 기록** → 같은 BTC인데 봇별 캔들 상이.
- 해소: Rauto2는 **중앙 1m(DataHub) 단일출처 → state["px"] 최상위 1개**를 전 봇이 공유. 봇은 거래(trd)만 다름. (역할분담 = 데이터는 Rauto가 한 곳서 공급.)

## 3. 실행 / 폰 접속
```
set PYTHONIOENCODING=utf-8
python 260626_02_Rauto2_Sys_server.py          # 또는 run.bat
```
- 폰: 같은 와이파이/Tailscale에서 `http://<PC_IP>:8788` 접속(브라우저→홈화면 추가=PWA).
- 환경변수: `RAUTO2_PORT`(8788) · `RAUTO2_STEP_MIN`(리플레이 1틱 전진 분,240) · `RAUTO2_TICK_SEC`(틱 간격,0.4) · `RAUTO2_LIVE_SEC`(라이브 갱신,15) · `RAUTO2_TOKENS`("tok:admin" 공개망 노출 시).
- 무인 운영: `nssm_setup_rauto2.bat`(NSSM 설치 후).

## 4. 검증 재현
```
python 260626_02_Rauto2_Sys_MatchSim.py        # 매칭 3관문(A무손상·B거래오버레이·C중앙px)
python 260626_02_Rauto2_Sys_LiveAnchorTest.py  # rauto_live 4관문(무손상·룩어헤드0·단조·중앙px)
python ..\..\04_공용엔진코드\engines\rauto_datafeed.py   # 라이브 교신 스모크(현재가·1m봉)
```
모두 앵커 **+1851.6%/MDD-24.6%/932거래** 무손상 기준. 데이터=08_BTC_Data/derived/Merged_Data.csv·raw_irreplaceable/funding, config=back2tv_rev_winners.json(REV_MDD25_36mo).

## 5. 경계·다음(정직)
- **리플레이(실시간 백테)** = 완전 작동·검증. **라이브 데이터(실시장 캔들·현재가)** = 작동(datafeed).
- ★**라이브 REVoi 신호생성**은 미완 = 다음 브리지: ① oi_zscore_24h 라이브 파이프라인(Dauto OI + 어댑터 Stg13) ② 2026-05~06 데이터갭 메움. (`rauto_live.append_1m`/`rebuild_slot`은 이미 구비.)
- 실주문(RautoCEX Live)·슬립 틱실측(안전장치7)은 별도 Work Order. MDD 4단게이트 정밀재산출(현실비용)도 후속.
- 단일출처 = CLAUDE.md §24·§25 · SPEC=07_Rauto_System/260625_01_Rauto_Sys_Reform_SPEC.md.
