# 작업공간 이전 — D:\ML\Verify → D:\ML\RfRauto (단일출처 MD)

작성: 2026-06-23 · 작성자: Claude Code · 지시: 캡틴 ("6/20 이후 작업·백테데이터·히스토리·작업이어가기 파일 모두 RfRauto로 copy, 이후는 RfRauto에 저장")

---

## 0. 왜 (배경)
"수익률 환상" 참사(백테 +11397% 등이 트레일 체결 인플레로 반증) → **Rauto Ver2.0 재건 = RfRauto(Reform Rauto)**.
2026-06-22 RfRauto 골격(00~09 방)만 만들고 **실제 이관은 미완으로 방치** → 이번(6/23)에 캡틴 지시로 완전 이전.
관련 메모리: `rfrauto-restructure`, `ml-root-multi-business-layout`.

## 1. ★★작업공간 전환 규칙 (이후 모든 작업 — 절대규칙)
- **신규 작업 산출물은 전부 `D:\ML\RfRauto\(해당 방)\` 에 저장한다. `D:\ML\Verify`에 새로 만들지 않는다.**
- 방(폴더) 선택 기준 (rfrauto-restructure 골격):
  - `03_IDEA4Bot` = ① 아이디어·TradingView·pine·py 포팅
  - `05_Alpha_Up` = ② 후보확인·집중관리 (알파 검증·향상 연구는 여기)
  - `06_ChampBot` = ③ 검증 통과 → 챔피언 졸업
  - `04_공용엔진코드` = 공유코드(engines §8해시락 / data_adapters / backtest_harness / rauto_core)
  - `07_Rauto_System` = ④ 시스템테스트(execution_cost·emergency_lock)
  - `08_BTC_Data` = 데이터(raw_irreplaceable / derived / regenerate_scripts)
  - `09_ProtoType` = 배포한 매매봇 시스템 압축관리
  - `00_WorkHstr` = INDEX + events + Archive_Zip(분기점 zip)
  - `00_Basic_Setup_Package` = 날짜없는 누적 가이드·사양서
  - `01_제작노트` = 캡틴 연구노트 + 인수인계 + KeyNote + Hstr_Ver_Up
  - `02_Alpha_CheckList` = 알파 체크리스트
- 알파는 `04 → 05 → 06`으로 졸업하며 고정ID `A###_name` + `alpha_card.md` 단일출처로 추적.
- 명명: §16 (NN Prj_CCproject_Stg(횟수)_작업명). 누적가이드는 날짜/버전 파일명 금지(내용에 이력).
- Verify는 **삭제하지 않고 보존**(원본 안전망). copy 방식(비파괴)으로 이전.

## 2. 이전 매핑 표 (Verify 원본 → RfRauto 목적지)

### 2-A. 백테 데이터 (캡틴 "36개월 등 중요 백테데이터 모두 복사")
| Verify 원본 | → RfRauto 목적지 | 분류 |
|---|---|---|
| Merged_Data.csv (476MB, ★현 알파연구 실사용) | 08_BTC_Data/derived/ | 병합 파생 |
| Merged_36mo.csv / _OIMetrics / _With_OI / _With_OI_Derived / _Derived_REPAIRED / _Funding_REPAIRED / _Funding_REPAIRED_v2 | 08_BTC_Data/derived/ | 36개월 백테 |
| Merged_Data_with_Regime_Features.csv (698MB) / _regime_features.parquet (169MB) | 08_BTC_Data/derived/ | 레짐 피처 |
| Pauto_Continuous_Merged_Dataset.csv | 08_BTC_Data/derived/ | 연속 병합 |
| merged_data_sample.csv / sample_*.csv / sample_*.xlsx | 08_BTC_Data/derived/samples/ | 샘플 |
| BTCUSDT_funding_history_8h.csv (★진짜 펀딩) | 08_BTC_Data/raw_irreplaceable/ | 외부소스 |
| BTCUSDT_funding_rates_23_26.csv (손상=0.0001고정, 경고용 보존) | 08_BTC_Data/raw_irreplaceable/ | 외부소스(손상) |
| CVD_15m_BTCUSDT.csv (10MB) | 08_BTC_Data/raw_irreplaceable/ | 외부소스 |
| Fear_Greed_Index_2018to20260602.csv | 08_BTC_Data/raw_irreplaceable/ | 외부소스 |
| (기존) raw_irreplaceable/BinanceData/ 1m OI 43파일 | 이미 복사됨(6-22) | 왕관보석 |

### 2-B. 6/20 이후 작업 산출물
| Verify 원본 | → RfRauto 목적지 | 분류 |
|---|---|---|
| AlphaIC_FundOiCvd_Stg1/ (알파 검증·향상 연구 전체) | 05_Alpha_Up/AlphaIC_FundOiCvd_Stg1/ | 알파 후보 |

### 2-C. 히스토리 + 작업 이어가기
| Verify 원본 | → RfRauto 목적지 | 분류 |
|---|---|---|
| 00WorkHstr/00WorkHstr_INDEX.txt + 분석 *.txt | 00_WorkHstr/ | 시간순 기록 |
| 00WorkHstr/00Basic_Setup_Package/ (Guide·Hstr_Ver_Up·사양서·docx 전체) | 00_Basic_Setup_Package/ | 가이드·사양서 |
| CLAUDE.md (규칙 단일출처) | RfRauto/ (루트) | 규칙 |
| AGENTS.md | RfRauto/ (루트) | 규칙 |
| LogicCatalog_ByDomain.md | RfRauto/ (루트) | 분야별 로직 |
| memory/ (참고 복사본) | RfRauto/memory_ref_from_verify/ | 작업 이어가기 ※실제 메모리 디렉토리 전환은 §3 별도 |

## 3. 미이전·보류 항목 (근거 명시 — 침묵=누락 방지)
- **6/18 이전 흩어진 ledger** (s7_trades.csv·trades_s0_*·stg6_levsweep·signals_cache·events_returns_*): 과거 산출물 = `02 20260618일 이전작업` 체계로 이미 보존. 백테 핵심데이터 아님 → 미이전.
- **_v80k_*.csv/.txt** (6/21 임시 슬라이스·out 로그, 최대 92MB): Merged에서 재생성 가능한 임시 작업물 → 미이전(derived=재생성 원칙).
- **`07 Rauto`** (제어앱·운영 트랙): 운영/라이브 전환 트랙으로 알파연구와 평행. 09_ProtoType or 07_Rauto_System 이전은 운영 세션에서 별도 판단 → 이번 보류(플래그).
- **memory 디렉토리 실제 전환**: `autoMemoryDirectory` settings 변경 필요(현재 D:/ML/Verify/memory). settings 수정은 별도 단계 → 이번엔 참고복사만, 전환은 Work_Order.
- **CLAUDE.md 공통/사업 분할** (D:\ML\CLAUDE.md 공통 + RfRauto\CLAUDE.md 사업): 미완 → Work_Order.

## 4. 검증 결과
(복사 실행 후 채움 — 파일 개수·핵심파일 존재·해시 대조)
