# Work Order 레지스터 — 수행비서 (★아직 할 것만 · 단일 기계가독 출처)
> ★규칙:
> - **세션 START(지침1)**: 이 표의 🔴미실행·🟡진행중·❔확인필요를 "이거저거 하셔야 합니다" 리스트로 **자동 브리핑**.
> - **세션 END = 핸드오버 만들 때(지침3)**: ★**완료된 WO는 이 표에서 삭제(행 제거)** — 완료기록은 INDEX·Handover에 남으니 레지스터엔 중복 안 둔다. 새 WO는 한 행 추가. = 레지스터엔 항상 **'남은 일'만**.
> - 상태: 🔴미실행 / 🟡진행중 / ❔확인필요(미확정 — 캡틴 "완료/미실행" 한 번 확정). **완료 = 행 삭제(🟢 안 남김).**
> - ★'삭제'는 **이 레지스터에서만** — 실제 WO 파일은 §1 보존규칙대로 남긴다(기록은 INDEX/Handover).

| 상태 | Work Order | 과제 요약 | 완료조건 | 출처파일 |
|---|---|---|---|---|
| 🔴 | **★★최종목표 = 다중알파+미시레짐 챔피언선발 → 매월 +**(캡틴 2026-06-28) | REVoi COMBO(역추세)와 **전혀 다른 성격(상관0/음) 알파 검색·개발** + 디테일 장세판별(미시레짐) → 챔피언시스템 레짐별 최적봇 선발 → **매월 수익 +**. 하위=추세봇포폴(과제2)·미시레짐세분(과제1)·COMBO(1번봇). | 36개월 전월 양수+CPCV 표준6+상관낮음+MDD−20+환각0 | `00_Basic_Setup_Package/Work_Order_MultiAlpha_RegimeChampion_20260628.md` |
| 🟡 진행중(260702_01) | **★실시간 미세레짐 분류 + 휩소 내성**(캡틴 지시 2026-07-01) | ★진단완료(Stg1)=휩소하락 아니라 **랠리 역주행이 진짜 저EV 병목**(gross손실39%). ★L2 랠리억제 지렛대=**폐기(Stg6 §19 정밀비교, 캡틴 지적)**: COMBO early_tp가 이미 랠리 수익화→L2 중복·같은 안전사이징선 OOS -93%p 악화 → RevoiRally 제거(엔진 PlugIn만 inert 보존). ★결론=**단일 REVoi로 수익개선·MDD-20 불가 4차확정 → 추세봇 상보 선결**(아래 행). causal 미세레짐 8피처는 확보(ER효율비=핵심, 재사용가능). | (추세봇 상보로 이관) | `03_IDEA4Bot/260702_01_MicroRegimeWhip/`(Stg1~6·KeyNote) |
| 🟡 | **★REVoi 청산 COMBO 정식化(실거래 전)** | (260627_02·★캡틴 채택승인·§9 등재 완료) tp_frac0.7+early_tp1.0% = M20천장 lev5 +322만%/MDD−19.8%/청0 · 진짜OOS(lev3) +2121%/MDD−5.5%(train=test 1.0% 일치=강건). 엔진 opt-in 내장·docx·zip 완료. 잔여=38개월(Dauto갭)·CPCV표준6 정밀(엔진내장)·실거래(testnet) | 38개월+CPCV표준6+testnet 통과 → 정식(조건부 해제) | `00_Basic_Setup_Package/260627_02_OBOICharacter_Key_OBdead_ComboTP.md` |
| 🔴**다음세션 최우선** | **추세봇 포트폴리오** | REVoi와 상관 낮은 추세추종 알파를 봇계약(make_trades)으로 제작 → REVoi와 포폴 → MDD−20 인증 재타지. **(단일 REVoi론 MDD−20·매월양수 불가 = 260627_01·260702_01 4차확인 = 유일한 구조적 길)**. L2 랠리억제(RevoiRally@ETF)와 조합도 재타진. | CPCV 표준6 전폴드 MDD≤−20·p25>0 + REVoi와 상관 낮음 입증 + 환각0 | `00_Basic_Setup_Package/260627_01_RegimeCertCard_Key_RotationWhipsawFindings.md` |
| 🟡 | **REVoi 휩소필터(월12%)** | 진척(260627_01): 휩소-회피=저변동&OI충격 size×0.5가 OOS 리스크레버(CPCV MDD−20위반 50%→36%) 확인. ★단독 MDD−20 불가(배합 더해도 위반↑)=추세봇 포폴 선결. 잔여=OB/POC·HTF→LTF·청산맵 배합 | 챔피언 인증=CPCV 표준6 전폴드 MDD≤−20(M20)·p25>0·월평균≥+12%·환각0 | `03_IDEA4Bot/260623_07_RfRautoAlphaUp/Work_Order_REVoi_20260624.md` |
| 🟡 | **Rauto 5모듈 SysReform** | ④관제센터 슬롯·챔피언선발(CPCV/held-out 게이트) · TS·SW 멀티봇 4관문 · 신호결정 deps 완전정리 | 앵커 무손상 + 챔피언선발 CPCV게이트 + 멀티봇 통과 | `07_Rauto_System/260625_01_Rauto_Sys_Reform/Work_Order_RautoSysReform_20260625.docx` |
| 🔴 | **라이브 전환/브리지** | 기존 Dauto 실시간·control_server(8787)·폰 b32 ↔ 신규 5모듈 호환. RautoCEX Live(resolve_replay≡RautoCEX 증명 후 수렴) | testnet 체결 ≡ Sim 비용오차 측정 통과 | `00_Basic_Setup_Package/Work_Order_RautoLiveTransition_20260620.docx` |
| 🔴 | **틱슬립 정밀(안전장치7)** | 격렬손절 aggTrades 틱 실체결 → RautoCEX 슬립모델 보정(현 청산슬립0=낙관) | 틱실측 슬립모델 적용·재백테 갱신(전환점) | `00_Basic_Setup_Package/Work_Order_TickSlippage_Precision_20260618.docx` |
| 🔴 | **듀얼k 상향 재평가** | k=0.93 등 표준6 위반 재평가 | 라이브 3개월 후(§9) | `00_Basic_Setup_Package/Work_Order_DualKUpReeval_20260612.txt` |
| ❔ | 레짐 감지 | → REVoi 과제0(장세판단)으로 **흡수**(중복이면 삭제 후보) | (REVoi WO에 통합) | `00_Basic_Setup_Package/Work_Order_RegimeDetection_20260617.txt` |
| ❔ | 알파적용+청산히트맵 | 알파 포폴 적용·청산맵(자석 51~53%=약함, 지침2) | 확인필요 | `00_Basic_Setup_Package/Work_Order_AlphaApply_and_LiqHeatmap_20260623.docx` |
| ❔ | 거래진단 계측(과제A) | trade_diagnostics 계측 | 확인필요 | `00_WorkHstr/Work_Order_AlphaUp_TradeDiagnostics_20260623.docx` |
| ❔ | Rauto 프로덕션 | 프로덕션 배포(라이브 미완) | 확인필요 | `00_Basic_Setup_Package/Work_Order_RautoProduction_20260615.docx` |
| ❔ | 슬롯 패키징 | 봇 슬롯 패키징(b32 대시보드에 슬롯 존재 → 완료면 삭제) | 확인필요 | `00_Basic_Setup_Package/Work_Order_RautoSlotPackaging_20260615.txt` |
| ❔ | PullbackTest(05-26) | 구버전 — 완료면 삭제 | 확인필요 | `00_Basic_Setup_Package/Work Order_PullbackTest_20260526.docx` |
| ❔ | MarketVarBoost(06-02) | 구버전 — 완료면 삭제 | 확인필요 | `00_Basic_Setup_Package/Work_Order_MarketVarBoost_20260602.docx` |

---
★2026-06-26 완료로 레지스터서 제거: OI z-score 어댑터 · AWS→G드라이브 아카이브 · V80k재건(→RfRauto로 대체). (완료기록은 INDEX, 파일은 보존.)
★❔는 캡틴이 "완료/미실행" 확정 시 → 완료면 행 삭제, 미실행이면 🔴.
