---
name: alpha-research-thread-state
description: 알파 검증·향상 연구 스레드의 현재 위치와 다음 1수(새 세션 이어가기용 라이브 상태).
metadata: 
  node_type: memory
  type: project
  originSessionId: ec48189e-b63f-4522-ab31-5764a9980ea0
---

**이 스레드 = "BTC 8h 알파를 시스템적으로 검증·향상"** (2026-06-22 세션, 폴더 D:\ML\Verify\AlphaIC_FundOiCvd_Stg1\). 새 세션은 이 메모리 + 00WorkHstr_INDEX.txt(2026-06-22 줄들) + Guide_AlphaDiscovery_Method_AlphaVerification_v1.docx로 이어간다.

**궤적(완료):**
- 검증 시스템 3단(가능성=WF부호안정 / 엣지=SPRT / 배포=CPCV+DSR+비용) 구축 = [[alpha-verification-system]].
- 제미나이·다코인·챔피언 전부 검증: 챔피언 +11397%=트레일 체결 인플레로 반증 = [[champion-return-exit-fill-inflated]].
- 미시구조 단독 약함 = [[microstructure-weak-for-btc-direction]]. 직교 측정→IC가중 덧셈 앙상블이 정석(곱셈 아님).
- ★현재 최강 결합 = **mom_24h + oi_z (IC가중 덧셈)**: WF 100%·info SR 1.25. 실체결 SL+트레일 시뮬(1m 실가·갭반영)서 **+90%/MDD-39%(레버1)·CPCV p25 +0.15 양수 = 진짜 알파 실재**(단 MDD가 §0 -20% 위반).
- 온체인(MVRV, Coin Metrics 무료)=직교하나 8h 호라이즌 불일치(IC~0)=8h엔 무력. 직교성은 호라이즌과 맞아야.
- 레짐(추세지속vs회귀=관성): VR<1 회귀레짐 게이팅 net SR 0.32→0.48·DSR→0.49(최고). ★핵심:레짐은 신호보다 *실행(트레일 청산)*을 좌우 — 2025 손실은 IC정상인데 트레일 휩쏘.

**★레짐게이트 반증(2026-06-23, realistic_sl_sim_regime.py):** VR<1 진입게이트(V1)·레짐인지 타이트트레일(V2)·둘다(V3) 전부 V0베이스(+90%/-39%/CPCV+0.15)보다 **악화**(V1 +23%/-40%/p25-0.31, V2 -15%/-52%, V3 -0.4%/-46%). V0만 CPCV 양수. 진단: ①진입게이트는 진입만 거르고 보유중 레짐전환 휩쏘 못막음(2025 -4%→-31% 악화) ②타이트트레일=더 휩쏘=MDD악화. ★교훈=**신호차원(IC/SR)향상 ≠ 실행차원(MDD)향상**(신뢰80). MDD범인=레짐 아닌 *트레일 청산 자체*.

**★다음 1수(캡틴 지시 2026-06-23, Guide §10 A~E에 박제·다음세션 의무점검):**
- **10.A(최우선)** 진입·청산 정밀화 = 전 수익고점 후 삼각수렴(변동성수축)서 이익반납이 MDD범인 → 차트패턴(스퀴즈/수축감지)·멀티TF 청산(상위TF 추세유지시 보유). 단일 트레일% 고정 폐기.
- **10.B** 레짐판별 향상 = VR/AC1 너무 구림 → HMM/Markov·Hurst동적·변동성레짐·다중지표 레짐스코어.
- **10.C** mom+oi 단독금지 → 다른 직교알파 조합 + ★장세조건 측정해 '가장 잘맞는 장세서만 부분(조건부) 적용'(전구간 일괄 금지).
- 모든 향상은 신호차원·실행차원 분리보고 + MDD주장은 반드시 1m실체결시뮬(낙관금지)로 확인. 사이징/쿨다운은 차순위(10.E 보류).

**도구(폴더 내):** alpha_verification_system.py(3단검증)·realistic_sl_sim.py(실체결시뮬,★낙관체결금지)·orthogonality_analysis.py(직교측정)·regime_persistence_analysis.py·search_method_selector.py·E1~E5. ★시뮬은 반드시 1m 실체결(낙관 트레일레벨 체결 금지, 안그러면 +11397%처럼 인플레).
