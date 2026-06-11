================================================================================
README_AWS.txt — Dauto 수집봇 v1 이전·상시구동 런북 (PC / AWS 공통)
08Prj_Dauto_Ch1_Collector_Stg1_RestPoller | 2026-06-11
================================================================================

[0] 한 줄 요약
  공개 REST(키 불필요·read-only)로 BTCUSDT 1분 데이터를 C:\BinanceData 에 상시 수집.
  주문 기능 코드 자체가 없음. API키·시크릿은 어떤 파일에도 기록하지 않는다.

[1] 요구사항
  - Python 3.9+ (표준 라이브러리만 사용 — pip 설치 불필요)
  - 아웃바운드 HTTPS(fapi.binance.com) 허용
  - 디스크: 1일 약 0.2MB × 365 ≈ 연 80MB 수준 (여유 1GB 권장)

[2] 시각 동기 (구멍 예방의 1순위)
  - 봉 경계 판정은 Binance 서버시각(/fapi/v1/time) 오프셋 보정으로 수행(시작+1시간마다).
  - OS 시계 자체도 NTP 동기 권장(관리자 PowerShell):
      w32tm /resync
    AWS Windows는 기본 Amazon Time Sync(169.254.169.123) 활성 — 추가 조치 불필요.

[3] 상시구동 등록 (Windows 작업 스케줄러 — PC·AWS 동일)
  관리자 명령프롬프트에서 (경로는 환경에 맞게 수정):
    schtasks /Create /TN "Dauto_Collector" ^
      /TR "D:\ML\verify\08Prj_Dauto_Ch1_Collector_Stg1_RestPoller\run_collector.bat" ^
      /SC ONSTART /RU SYSTEM /RL HIGHEST /F
  - 로그온 없이 부팅 시 자동 시작. run_collector.bat 내부 :loop 가 크래시 자동재시작(10초 후).
  - 즉시 시작:  schtasks /Run /TN "Dauto_Collector"
  - 상태 확인:  schtasks /Query /TN "Dauto_Collector" /V /FO LIST
  - 해제:       schtasks /Delete /TN "Dauto_Collector" /F
  - 수동 구동(테스트): run_collector.bat 더블클릭.

[4] AWS 이전 절차
  1) 이 폴더 전체를 AWS 인스턴스 임의 경로로 복사(영문 경로 권장).
  2) [2] 시각 확인 → [3] schtasks 등록(/TR 경로만 수정).
  3) G드라이브 아카이브는 G:\ 가 없으므로 자동 스킵(에러 아님 — 코드가 폴더 존재를 먼저 확인).
  4) 검증: C:\BinanceData\dauto_health.log 에 STARTUP 라인 + 수 분 후 CSV 행 증가 확인.
  5) PC→AWS 데이터 이어붙이기: PC의 C:\BinanceData CSV들을 AWS C:\BinanceData 로 복사 후
     시작하면 마지막 행 이후만 자동 백필(중복 방지 내장).

[5] 산출물 사양
  - C:\BinanceData\BTCUSDT_1m_YYYYMMDD.csv (UTC, 1분 1행, 13컬럼)
    ts_utc,open,high,low,close,volume,taker_buy_volume,open_interest,mark_price,
    index_price,funding_rate_8h,next_funding_time,oi_src
  - oi_src: live=실시간 스냅샷 / hist=5m 이력 ffill 백필 / na=30일 초과 복구불가
  - 백필 행의 mark_price·index_price 는 설계상 공란(이력 엔드포인트는 v1 범위 밖).
    funding_rate_8h: 라이브=premiumIndex 현행값, 백필=그 행이 속한 정산창의 실제 정산률.
  - 헬스로그: C:\BinanceData\dauto_health.log — STARTUP/백필/HEALTH(전일 rows·gaps)/경고.

[6] 레이트리밋 점검표 (Binance USDT-M 한도: 2,400 weight/분)
  ┌──────────────────────┬─────────┬────────┬──────────────┐
  │ 엔드포인트            │ 빈도    │ weight │ 분당 부하    │
  ├──────────────────────┼─────────┼────────┼──────────────┤
  │ /fapi/v1/klines(≤100)│ 매분 1  │ 1      │ 1            │
  │ /fapi/v1/openInterest│ 매분 1  │ 1      │ 1            │
  │ /fapi/v1/premiumIndex│ 매분 1  │ 1      │ 1            │
  │ /fapi/v1/time        │ 시간 1  │ 1      │ ~0.02        │
  │ (백필시) klines 1500 │ 일시    │ 10/콜  │ 30일≈29콜    │
  │ (백필시) fundingRate │ 일시    │ 1/콜   │ 30일≈1콜     │
  │ (백필시) oiHist 5m   │ 일시    │ 1/콜   │ 30일≈18콜    │
  └──────────────────────┴─────────┴────────┴──────────────┘
  평시 합계 ≈ 3 weight/분 = 한도의 0.125% (분당 4콜 수준, 한도의 1% 미만 확인 ✓)
  429/418 수신 시 Retry-After 만큼 자동 대기(코드 내장) — IP밴 예방.

[7] 구멍(결측) 정책
  - 시작 시 마지막 행 확인 → klines·funding 전기간 백필 / OI는 최근 30일만(oi_src=hist).
  - 30일 초과 OI 구멍 = 복구불가 → oi_src=na + 00WorkHstr_INDEX.txt(존재 시)·health에 기록.
  - 첫 구동(파일 전무)은 최근 30일 시드 백필(≈43,200행, 수 분 소요).

[8] PASS 기준 (run.bat = test + check)
  ① 30분 실측: live 30행±1·결측 0  ② kill→재시작: 3분 구멍 자동백필
  ③ check.py 오염검사(read-only 문자열 검사 포함)+INDEX 기록.
  ★실시간 API 특성상 컨테이너 사전검증 불가 — 이 PC 실측이 곧 사전실행임(캡틴 확정).
================================================================================
