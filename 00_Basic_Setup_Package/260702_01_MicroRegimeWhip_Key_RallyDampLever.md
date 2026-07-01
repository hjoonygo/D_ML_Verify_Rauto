# KeyNote — 260702_01_MicroRegimeWhip · "휩소 넘기" 진단→검증→결정두뇌 반영
> 세션 2026-07-02 · 캡틴 "이번엔 휩소를 넘어갈 방법을 찾자" · 착수 A(진단 먼저) → L2 랠리억제 발견·OOS검증·PlugIn 반영.
> ★신뢰 85 · 무손상 앵커 +1851.6491% 전구간 재현 · 검증엔진 무수정·호출만(§8·§15.1).

## 0. Output of Chat (한 줄)
**"휩소 넘기"의 정답은 '휩소하락 솎기'가 아니라 '랠리 역주행 억제(L2)'** — held-out OOS 수익 2배·같은노출선 리스크리듀서. 봇무관 PlugIn `rauto_regime_sizing.py` + 신규봇 `RevoiRally@ETF`로 반영. **단 단일 REVoi로 MDD-20·매월양수100% 불가 4차확인 → 추세봇 상보가 유일한 길.**

## 1. 진단 (Stg1 손실지도) — ★가설 반전
- 방법: 검증엔진(REVoi_bot.make_trades) 원장을 **causal 미세레짐 8피처**(ER효율비·휩소율·실현변동성·점프·7일추세·ATR분위·OI충격·테이커델타, 전부 진입 직전 완성 4H봉 shift1=lookahead0)로 분해. BASE+COMBO·36mo+post2024.
- ★결과(post-2024 미세레짐별 평균R·gross손실기여):
  - 급락(SharpDrop) 승59%/+0.63%R (REVoi 최강 확정)
  - **휩소하락(WhipDown) 31거래·+0.15%R·gross손실 6%** ← 가설과 달리 **손실 무더기 아님**
  - **랠리(Rally) 245거래·+0.01%R·gross손실 39%** ← ★진짜 저EV 병목
- ★해석: net음수 레짐 0(REVoi 전체 +) → 병목은 '순손실'이 아니라 **저EV 역주행 군집**(레버·군집시 드로다운·바닥↓). ER효율비가 하락장 내부서 급락(일방)↔휩소(톱니)를 가름(+0.47 vs +0.15).

## 2. 검증 (Stg2 3지렛대 held-out+CPCV 표준6) — ★L2 채택
- 프로토콜: COMBO 위 opt-in · 폴드별 train서 M20 사이징 재선택→보류 test 채점(커닝0·purge±1M) · 현실=R−10bp시장청산 · 헤드라인=held-out OOS test(2025+).

| 지렛대 | OOS test 현실 | CPCV p25 | MDD-20위반 | 판정 |
|---|---:|---:|---:|---|
| OFF(COMBO) | +1,058% | +286% | 57% | 기준 |
| **L2 랠리억제** | **+2,155%** | +296% | 57% | ★채택(수익2배) |
| L1 하락ER솎기 | +966% | +284% | 57% | 기각(열위) |
| EX early_tp강화0.5% | +140% | +79% | 64% | 기각(승자잘림) |
- ★단일알파 MDD-20 불가 4차확인: 전 지렛대 CPCV 위반 57%(EX 64%) — 위반0 미달.

## 3. 정밀화 (Stg3) — 최종 스펙
- 강도 ×0.3(OOS 균형최선 +2778%/위반50%)~×0.5(보수) · skip(×0)=레버업 함정(위반64%). 임계 7일추세 **+3%**. **비대칭**(급락롱=REVoi 강점 절대 안건드림; 대칭은 확연히 열위).
- ★같은위험(고정 L4/75=노출3): L2가 MDD -15→-13·폴드최악 -19→-15·매월양수 14→15/16 = **순수 리스크리듀서**(수익 큰폭↑은 레버업 별건). 매월양수 100%는 미달(추세봇 상보 필요).

## 4. 결정두뇌 반영 (Stg4~5) — 모듈 + 새 슬롯봇
- **`engines/rauto_regime_sizing.py`** (봇무관 PlugIn·§25, emergency_brake 동일패턴): 진입 미세레짐(7일추세 causal)→노출배수 `size_mult` 컬럼. `rally_damp_mult`/`apply_rally_damp`. 자가검증(단건5·실원장187damp전부숏·off→무손상).
- **하위호환 배선**(무손상 핵심): `veri_edge._liq`·`rauto_live.per_trade_pnl`이 `size_mult` 컬럼 있으면 per-trade 노출에 곱하고 **없으면 100% 동일**(BASE 앵커·RevoiSafe 불변 증명).
- **RevoiRally@ETF 등록**(server BOT_REGISTRY/REG_MONTHLY): RevoiSafe 노출3(lev15/sz20) + L2(3.0,0.5). 이름표 예상월복리 15.93%OOS·OOS_MDD-12.6%(vs RevoiSafe -14.8)·강제청산0·안전점수4/8.
- 무손상 3중: BASE 앵커 +1851.6491% · RevoiSafe(컬럼없음) +26,754% 불변 · py_compile 4파일+모듈자가검증+스모크 PASS.

## 5. 산출물
- 코드: `03_IDEA4Bot/260702_01_MicroRegimeWhip/`(Stg1_LossDiag·Stg2_WhipLeverHoldoutCPCV·Stg3_L2RallyRefine·Stg4_RevoiRallyNameplate·Stg5_Smoke) + `04_공용엔진코드/engines/rauto_regime_sizing.py`
- 분석: `00_WorkHstr/BackTest_Output/260702_01_MicroRegimeWhip_Stg1/2/3_*`(분석txt·csv·png)
- 수정 엔진: `veri_edge.py`·`rauto_live.py`(size_mult 하위호환) · server(RevoiRally 등록)

## 6. 다음 1수 (정직)
- ★**추세봇 상보 포트폴리오**(REVoi 상관낮은 추세추종) = MDD-20 챔피언인증·매월양수100%의 **유일한 길**(4차확인). 최종목표 과제2.
- RevoiRally@ETF 배포(PC+AWS push, 캡틴승인) · L2 x0.3 공격변형×추세봇 조합 재타진.
- L2는 지렛대/도구(챔피언 아님) → §9 확정알파 등재는 추세봇 상보 완성 후.
