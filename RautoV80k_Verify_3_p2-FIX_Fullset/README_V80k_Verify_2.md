# RautoV80k_Verify_2 풀세트 — 통합 가이드

**내부버전**: V80k_Verify_2
**작성일**: 2026-05-01
**검증 상태**: 통합 selftest 통과 / walk-forward 미실시
**풀세트 크기**: 약 27MB (모델 4개 단일 위치, JSON 중복 제거)

## 사용 시작 — 5분 안에 가동

```bash
# 1. 풀세트 압축 해제
unzip RautoV80k_Verify_2_Fullset.zip

# 2. ChampionGUI 실행
cd fullset_v80k_verify1
python V80k_ChampionGUI.py

# 3. GUI에서 슬롯에 전략 선택 (모든 슬롯 default '— 전략 선택 안 함 —')
# Bot 1: '3balancedTBM_R001 [거래]' 선택
# Bot 2: 'Observer_R001 [★ Observer]' 선택 (검증 데이터 수집)

# 4. RUNNING 시작
```

## 풀세트 구조

```
fullset_v80k_verify1/
│
├── 📄 README_V80k_Verify_2.md           ← 본 문서 (사용 가이드)
├── 📄 Handover_V80k_Verify_2.docx       ← 인수인계 보고서 (작업 히스토리 포함)
│
├── 📁 docs/                             ← 본 사이클 key문서 8개
│   ├── Key_V80k_Verify_1_01_NotifierIntegration.docx
│   ├── Key_V80k_Verify_1_02_PreScanPattern.docx
│   ├── Key_V80k_Verify_1_03_DistributionAdaptation.docx
│   ├── Key_V80k_Verify_1_04_RegimeGranularity.docx
│   ├── Key_V80k_Verify_1_05_Phase012_Empirical.docx
│   ├── Key_V80k_Verify_1_06_ColdStart_Operations.docx
│   ├── Key_V80k_Verify_1_07_ObserverFramework.docx
│   └── Key_V80k_Verify_2_08_StrategyZipSystem.docx
│
├── 📁 _inherited_v80k_original/          ← 별도 프로젝트 인수 자료 (격리)
│   ├── 01_External_Modules_Spec_R001.docx
│   ├── 02_V80k_Handover_Report.docx
│   └── README_v2/v3/v4_inherited.md
│
├── 📁 strategies/                        ← 전략 ZIP 보관소 ★ V80k_Verify_2
│   ├── 3balancedTBM_R001.zip            (V80k 원본 + 모델 4개)
│   ├── Observer_R001.zip                 (검증 전용)
│   ├── build_strategy_zips.py            (ZIP 빌더)
│   └── _workspace/                       (개발용)
│       ├── 3balancedTBM_R001/
│       │   ├── __init__.py / R/P/E_module.py / metadata.json
│       │   └── models/                   ★ JSON 단일 위치 (47MB 절감)
│       │       ├── PautoV80_Regime_Model_v6.json
│       │       ├── PautoV80_TBM_BULL_v2.json
│       │       ├── PautoV80_TBM_BEAR_v2.json
│       │       └── PautoV80_TBM_CHOP_v2.json
│       └── Observer_R001/                (모델 없음, base 참조)
│
├── (코드 .py 파일들)
│   ├── 코어: BotManager, TradingEngine, DataEngine, Logger, ChampionGUI×2, UI_Components
│   ├── Verify_2 신규: StrategyLoader, RautoV80k_Subregime
│   ├── Verify_1 검증: Observer_Logger, Observer_Analyze
│   └── 레거시: R/P/E_ML_V80k_*, R/P/E_Observer_V80k_R001 (호환용)
│
├── PautoV80_Regime_ML.py                 (compute_features 정의)
├── PautoV80k_BacktestAdapter.py          (Pauto 백테 어댑터)
└── Rauto.bat                             (Windows 가동 스크립트)
```

## 파일 명명 규칙 — 빠른 확인 가이드

| 패턴 | 어디 보면 됨 |
|---|---|
| `Handover_V80k_Verify_<N>.docx` | **전체 흐름 + 작업 히스토리** (1페이지에 표) |
| `Key_V80k_Verify_<N>_<번호>_<주제>.docx` | 특정 발견 상세 (번호 = 시간순) |
| `README_V80k_Verify_<N>.md` | 풀세트 사용법 (본 문서) |
| `_inherited_*/...` | 별도 프로젝트 원본 (참고만) |

**암기 규칙**:
- "전체 흐름" → `Handover_*.docx` 1페이지
- "특정 발견" → `docs/Key_*_<번호>_*`
- "어떻게 쓰지?" → `README_*.md`
- "원본은?" → `_inherited_*/`

## 주요 변경 사항 (V80k_Verify_2 본 사이클)

### 1. Strategy ZIP 시스템 ★ (Hybrid F)
- `strategies/*.zip` 자동 스캔
- ZIP → `strategies_extracted/<name>/` 자동 추출 후 import
- 전략 단위 격리, 미래 무한 확장 가능
- 자세히: `docs/Key_V80k_Verify_2_08_StrategyZipSystem.docx`

### 2. 5중 안전장치 (Observer 봇 거래 X)
1. P_Observer 모듈 → 항상 `WAIT`
2. E_Observer 모듈 → 항상 `NO_ACTION`
3. Selftest 단위 검증
4. metadata.json `is_observer:true`
5. **BotManager 코어 가드** — `_is_observer_bot=True` 시 OPEN 강제 차단

### 3. JSON 중복 제거
- 이전: 풀세트 루트 + workspace 모두 → 8 사본
- 현재: workspace에만 → 4 사본 (47MB 절감)
- BASE_DIR 결정 로직: 환경변수 → workspace → strategies_extracted → 시스템 fallback

### 4. GUI 시작 시 슬롯 비움
- 모든 콤보 default `'— 선택 안 함 —'`
- 사용자 명시적 선택 강제 → 실수 방지

### 5. HUD 시장 객관 지표
- 이전: `2. 장세: BULL (0.72)` (모듈 의존)
- 현재: `2. 시장: ATR15m 0.45% | Vol↑12%` (모듈 무관)

### 6. E 모듈 청산 추적
- 거래 봇(Bot 1)의 evaluate_exit 결정 → Observer_Logger 자동 기록
- 별도 CSV: `RautoV80k_Observer_<bot_id>_E_TRACK_<date>.csv`

## 검증 데이터 수집 워크플로우

Observer 봇이 Bot 2 슬롯에서 가동되면 매봉 71컬럼 자동 기록 (12 시나리오):
- `RautoV80k_Observer_Bot_2_<YYYYMMDD>.csv`
- 24시간 가동 후 분석:
```bash
python Observer_Analyze.py --csv "RautoV80k_Observer_Bot_2_*.csv" --out report.json
```

자세히: `docs/Key_V80k_Verify_1_07_ObserverFramework.docx`

## 우려 사항

### 우려 1: 기존 V80k 가동과 호환성
- 레거시 .py 파일 유지 → 기존 import 경로 그대로
- ZIP 시스템은 추가 옵션 — 기존 운영 봇 영향 없음

### 우려 2: ZIP 추출 첫 가동 시간
- 첫 가동 ~2초 추가
- mtime 비교로 재추출 회피 → 이후 0초

### 우려 3: walk-forward 미실시
- 다음 사이클(V80k_Verify_3) 의무
- 실거래 가동 절대 금지 (선장 절대 원칙)

## 다음 사이클 (V80k_Verify_3) 출발점

상세는 `Handover_V80k_Verify_2.docx` 참조. 예상 작업:
- Observer 24~48h 데이터 분석 → 가설 A/B/C/D 결론
- 4-tier 트리거 시스템 (Tier 2 알림 / Tier 3 차단 / Tier 4 강제 청산)
- PC 학습 워크플로우 시작 (BearT12Aux 보조 모델 1회 시도)
- walk-forward 12회 백테 검증

자세한 PC 학습 시스템 명세: `docs/Key_V80k_Verify_2_09_PCTrainingWorkflow.docx` (예정)
