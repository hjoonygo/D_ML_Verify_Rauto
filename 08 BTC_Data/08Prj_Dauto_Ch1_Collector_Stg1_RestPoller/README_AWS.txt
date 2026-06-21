================================================================================
README_AWS.txt — Dauto 수집봇 v1 이전·상시구동 런북 (PC / AWS 공통)
08Prj_Dauto_Ch1_Collector_Stg1_RestPoller | 2026-06-11
================================================================================
★AWS 설치 최소 점검표 (4줄 — 상세는 본문 [1]~[4])
  1. python --version                       → 3.9+ 확인 (표준라이브러리만, pip 불필요)
  2. 폴더 복사(영문 경로) + C:\BinanceData 는 자동 생성됨
  3. schtasks /Create /TN "Dauto_Collector" /TR "<폴더>\run_collector.bat BOOT" /SC ONSTART /RU SYSTEM /RL HIGHEST /F
  4. schtasks /Run /TN "Dauto_Collector"  → 1분 후 확인:
     type C:\BinanceData\dauto_health.log  (STARTUP 라인 + 백필 라인이 보이면 정상)
================================================================================

[0] 한 줄 요약
  공개 REST(키 불필요·read-only)로 BTCUSDT 1분 데이터를 C:\BinanceData 에 상시 수집.
  주문 기능 코드 자체가 없음. API키·시크릿은 어떤 파일에도 기록하지 않는다.

[1] 요구사항
  - Python 3.9+ (표준 라이브러리만 사용 — pip 설치 불필요)
  - 아웃바운드 HTTPS(fapi.binance.com) 허용
  - 디스크: 1일 약 0.2MB × 365 ≈ 연 80MB 수준 (여유 1GB 권장)

[1b] 필수 pip 패키지 전수 목록 (2026-06-12 신설 — Stg14 라이브 페이퍼 등 봇 실행용.
     ※수집봇 자체는 표준라이브러리만 — 이 절은 같은 AWS에서 봇/검증 스크립트 돌릴 때만)
  - import 전수 스캔(Stg14 폴더) 추출 외부 패키지: numpy / pandas / smartmoneyconcepts
  - 설치 1줄:  pip install -q numpy pandas smartmoneyconcepts
    (Stg14 run.bat 2줄째에 내장 — 미설치 환경에서도 자동 해결. 1줄째는 §4 규칙상
     PYTHONIOENCODING 고정)
  - 새 Stg 반입 시 점검법: 폴더 내 .py에서 `import/from` 줄 전수 스캔 → 표준라이브러리·
    동봉모듈 제외 잔여가 pip 대상.

[2] 시각 동기 (구멍 예방의 1순위)
  - 봉 경계 판정은 Binance 서버시각(/fapi/v1/time) 오프셋 보정으로 수행(시작+1시간마다).
  - OS 시계 자체도 NTP 동기 권장(관리자 PowerShell):
      w32tm /resync
    AWS Windows는 기본 Amazon Time Sync(169.254.169.123) 활성 — 추가 조치 불필요.

[3] 상시구동 등록 (Windows 작업 스케줄러 — PC·AWS 동일)
  관리자 명령프롬프트에서 (경로는 환경에 맞게 수정):
    schtasks /Create /TN "Dauto_Collector" ^
      /TR "D:\ML\verify\08Prj_Dauto_Ch1_Collector_Stg1_RestPoller\run_collector.bat BOOT" ^
      /SC ONSTART /RU SYSTEM /RL HIGHEST /F
  - 기동 모드는 health.log에 [BOOT](스케줄러)/[MANUAL](더블클릭)로 구분 기록된다.
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

[6b] G드라이브 아카이브 경로 (캡틴 채택 2026-06-12 — ③ PC 주1회 백필)
  - 주1회 PC에서 Dauto 수동기동(run_collector.bat 더블클릭) → 자동 백필 + G:\ 아카이브.
    OI 이력 한도 30일의 4배 여유. rclone/S3 는 Rauto 라이브 시 재평가(Work Order).

[7] 구멍(결측) 정책
  - 시작 시 마지막 행 확인 → klines·funding 전기간 백필 / OI는 최근 30일만(oi_src=hist).
  - 30일 초과 OI 구멍 = 복구불가 → oi_src=na + 00WorkHstr_INDEX.txt(존재 시)·health에 기록.
  - 첫 구동(파일 전무)은 최근 30일 시드 백필(≈43,200행, 수 분 소요).

[8] PASS 기준 (run.bat = test + check)
  ① 30분 실측: live 30행±1·결측 0  ② kill→재시작: 3분 구멍 자동백필
  ③ check.py 오염검사(read-only 문자열 검사 포함)+INDEX 기록.
  ★실시간 API 특성상 컨테이너 사전검증 불가 — 이 PC 실측이 곧 사전실행임(캡틴 확정).
================================================================================
