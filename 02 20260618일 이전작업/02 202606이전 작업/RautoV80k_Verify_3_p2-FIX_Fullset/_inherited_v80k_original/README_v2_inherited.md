# V8.0k v2 — 자취 남기기 + 차트 강화 패치

## v2 패치 요약

선장 원칙: **"테스트의 기본은 자취를 남기는 것"**

### A. 로깅 강화 — 4종 자취 파일 자동 생성

실행 후 폴더에 자동 생성:

| 파일 | 내용 | 빈도 |
|---|---|---|
| `RautoV80k_System.log` | 시스템 이벤트 (모듈 로드/봇 상태 변화/에러) | 이벤트 시 |
| `RautoV80k_BotState_Bot_N.csv` | 봇별 매 봉 상태 (regime/conf/action/사유) | **매 봉 마감 1줄** |
| `RautoV80k_TradeLog_Bot_N.csv` | 봇별 진입/청산 이벤트 (모든 거래 정보) | 거래 발생 시 |
| `RautoV80k_Equity.csv` | 모든 봇의 자본 곡선 (통합) | 매 봉 마감 |

### B. 차트 v2 강화 — Bot ID 팝업

1. **크로스헤어**: 마우스 위치에 십자선 + 좌측 가격 + 하단 시간
2. **마커 강화**:

| 이벤트 | 마커 | 텍스트 |
|---|---|---|
| LONG 진입 | 녹색 위쪽 삼각형 | L1, L2, L3 (분할 진입 대비) |
| SHORT 진입 | 적색 아래쪽 삼각형 | S1, S2, S3 |
| LONG 익절 | 녹색 ○ | — |
| LONG 손절 | 녹색 ✕ | — |
| SHORT 익절 | 적색 ○ | — |
| SHORT 손절 | 적색 ✕ | — |
| 반익절 (CLOSE_HALF) | 다이아몬드 | — |

## 실행

```cmd
cd C:\Rauto
python RautoV80k_ChampionGUI.py
```

실행과 동시에 `RautoV80k_System.log` 생성 시작. 봇 RUNNING 상태로 들어가면 매 봉마다 봇별 CSV에 자취 기록.

## 분석 예시

### 봇 1번이 10분간 UNCERTAIN만 떴다 — 진짜인가?

```cmd
notepad RautoV80k_BotState_Bot_1.csv
```

또는 엑셀로 열어 `regime_conf` 컬럼 보기:
- 0.42 → 0.43 → 0.44 → 0.41 → 0.45 → 정상 (모델이 정직하게 모르겠다)
- 0.44 → 0.44 → 0.44 → 0.44 → 비정상 (캐시 버그 의심)

### 거래 추적

```cmd
notepad RautoV80k_TradeLog_Bot_1.csv
```

entry/exit/pnl/사유 모두 기록. 엑셀에서 PnL 합산하면 실현 수익 즉시 확인.

### 자본 곡선

```cmd
notepad RautoV80k_Equity.csv
```

엑셀에서 `total_equity`를 차트로 → 자본 곡선. 봇 ID 필터링해 비교.

## 거래 시 시스템 로그 예시

```
[Bot_1] 🟢 OPEN_LONG @ $70123.45 | BULL | SL $70053.32 TP $70263.47 | lev 7x | tbm 0.62
[Bot_1] 🎯 CLOSE_HALF LONG @ $70263.47 | PnL +$98.04 (+0.98%)
[Bot_1] 🛑 CLOSE_ALL LONG @ $70401.12 | PnL +$194.56 (+1.95%) | exit_type=TP
```

## 엑셀 충돌 방지

봇 가동 중 CSV를 엑셀로 열어도 시스템 안 멈춤. 잠긴 파일은 큐에 쌓아 다음 기회에 기록.

## 폴더 구조

```
C:\Rauto\
├── RautoV80k_*.py (6)         ← 인프라 + Logger
├── PautoV80k_BacktestAdapter.py (1)
├── R/P/E_ML_V80k_3balancedTBM_R001.py (3)
├── PautoV80_Regime_ML.py
├── PautoV80_*.json (4 모델)
├── 01_External_Modules_Spec_R001.docx
├── 02_V80k_Handover_Report.docx
└── README.md
```

## 작성

선장: 사용자 / 항해사: Claude  
사이클: V8.0.k v2 (로깅 강화 + 차트 v2) / 작성일: 2026-04-29
