# 🌅 야간작업 보고 — 2026-06-23 새벽 (캡틴 기상 시 읽기)

작업자: Claude Code · 캡틴 지시 "혼자 작업, 아침 보고, 웬만한 진행 미리 승인"

---

## 1. 작업공간 이전 Verify → RfRauto ✅ (검증 통과)
- **★작업공간 전환 규칙 박제** = `D:\ML\RfRauto\WORKSPACE_MIGRATION_Verify_to_RfRauto.md` (단일출처). **이제 신규작업은 전부 RfRauto 해당 방에 저장**(Verify 신규 금지).
- 알파연구 → `05_Alpha_Up` / 히스토리·Guide·사양서 → `00_WorkHstr`·`00_Basic_Setup_Package` / CLAUDE·AGENTS·LogicCatalog → 루트 / memory → `memory_ref_from_verify`.
- 백테 데이터 → `08_BTC_Data`: **핵심 검증 통과**(Merged_Data.csv·regime_features 크기 일치, 소스CSV 4/4).
- ⚠️ **중복 중간계보 5개**(Merged_36mo_With_OI_*)는 **미완** — D드라이브가 개당 300~700MB 파일 쓰기에 비정상적으로 느림(835MB서 정체). **작업엔 불필요한 재생성 가능 파일**이라 영향 없음. 필요하면 재시도하거나 regenerate. (백그라운드 robocopy는 계속 도는 중)

## 2. 알파상승 — ★MDD 주범 정량 확정 (야간 핵심 성과)
도구: `trade_diagnostics.py` (선행연구 Sweeney MAE/MFE·Edge Ratio, 1m 실체결·낙관금지).
- **결정증거 = 청산종류 분리**: `initial_SL`(초기2%손절) **174건(32%)·승률 0%·−362%p** vs `trailing` 372건(68%)·승률 55%·**+450%p**.
- → **MDD/손실 범인 = 진입 직후 초기손절 휩쏘**(손실 340건 중 51%가 MFE<1% 진입즉시SL). **청산 문제 아님.**
- 어제 가설 "삼각수렴 이익반납" **최종 반증**(큰수익후반납 7건 2%뿐).
- **Edge Ratio 1.57(>1 비율 57%)** = 진입 신호 자체엔 엣지 있음 → **초기손절이 그 엣지를 휩쏘로 잘라먹음.**
- 이익거래도 MFE의 **42%만 capture**(절반 반납). 레짐 무관(MDD구간 VR 0.90=전체).

## 3. 향상안 1차 탐색 — ★손절 완화는 답이 아님 (중요한 음성 결과)
도구: `sl_redesign_sweep.py` (고정 2~5% / ATR×1.5~3.0).
- 손절 넓히면 초기SL거래 174→0·**복리 +86→+138%(↑)** BUT **MDD −39→−47%(악화)**. = 휩쏘빈도↓ ↔ 손실폭↑ **트레이드오프**. 어느 변형도 −20% 미달.
- → **초기손절이 범인은 맞으나, 손절 파라미터 튜닝만으론 MDD −20% 불가**(신뢰75). 손절완화는 *수익 극대화* 레버지 *MDD* 레버 아님.
- MDD는 승률 38% 추세추종 손익비 구조의 본질.

## 4. ★다음 1수 (캡틴 방향 결정 대기)
MDD −20%의 진짜 레버 2개 (Work_Order 과제):
- **① 진입 품질(10.A)**: 휩쏘 진입 *자체*를 회피 — 되돌림 후 진입·차트패턴·멀티TF. (Edge Ratio 1.57 살리되 손절은 좁게 유지)
- **② 변동성 타게팅 사이징(10.E)**: 고변동 구간 노출↓ = MDD 직접 레버.
→ 둘 중 어디부터 갈지 캡틴 결정. (제 추천: ②사이징이 MDD 직접·빠른 검증, ①진입은 근본·시간 더 듦)

## 5. 산출물 위치 (전부 RfRauto)
- `05_Alpha_Up/AlphaIC_FundOiCvd_Stg1/`: trade_diagnostics.py·_ledger.csv·.png / sl_redesign_sweep.py / realistic_sl_sim_regime.py
- `00_WorkHstr/`: 분석 202606230245.txt / Work_Order_AlphaUp_TradeDiagnostics_20260623.docx / INDEX 갱신
- `00_Basic_Setup_Package/`: Guide §10(후속작업 박제)

## 6. 잔여 미완 (다음 세션)
- 중복계보 5개 복사(불필요·선택) / memory 디렉토리 실제 전환(settings) / CLAUDE 공통·사업 분할 / 07 Rauto(운영) 이전 / 옛 Verify 압축.

---
**한 줄 요약:** 작업공간 RfRauto 이전 완료 + MDD 범인=초기손절 휩쏘로 확정 + 손절튜닝으론 MDD 해결 불가 판명 → 다음은 진입품질 or 사이징.
