---
name: alpha-verification-system
description: 신호 알파를 3단(가능성/엣지/배포) 자동판정하는 재사용 검증 시스템. 참사 재발방지용 표준 잣대.
metadata: 
  node_type: memory
  type: project
  originSessionId: ec48189e-b63f-4522-ab31-5764a9980ea0
---

2026-06-22 구축: `D:\ML\Verify\AlphaIC_FundOiCvd_Stg1\alpha_verification_system.py` = "이 신호에 알파가 있나"를 **3단 자동판정**하는 재사용 프레임(캡틴 지시, 참사 재발방지·검증 시스템화).

- **①알파가능성** = WF(롤링) 부호안정 ≥ 62.5%. ★방향 자동발견·정렬 → *정반대 방향이어도 부호 일관이면 정보 있음*(캡틴 핵심지적: "방향 정반대면 알파가능성은 있는거다").
- **②엣지확정** = SPRT(순차확률비검정)가 연Sharpe 0.5 H1을 검출.
- **③배포가능** = ① AND CPCV(퍼지+엠바고 15경로, Lopez de Prado) p25>0 AND Deflated Sharpe(Bailey 다중검정)>0.95 AND 비용후(왕복8bp) Sharpe>0.
- 방법론 출처: WF=OOS연결(arXiv 2512.12924), CPCV/퍼지(Lopez de Prado AFML), SPRT(chessprogramming/Statsig), PBO/DSR(Bailey&LdP SSRN 2326253/2460551). ChatGPT 권고 "2020~2026 BTC선물 WF·CPCV·SPRT 통과" 반영.

**Why:** 참사(클로드 맹신→백테 신뢰도 미확보, [[microstructure-weak-for-btc-direction]])의 근본대책 = 화려한 수치를 믿지 말고 *시스템화된 잣대*로만 알파 인정. 첫 실행이 OI 룩어헤드버그(+0.115 '배포O')를 냈고 시스템 자체 점검으로 잡음(-0.037=앵커일치) → "쉽게 나오면 뻥" 작동 증명.
**How to apply:** 새 신호/조합은 이 시스템에 통과시켜 3단 판정. 첫 결과 검증 = ①룩어헤드(신호는 t직전값만) ②앵커 동치(기존 독립측정과 IC 일치) ③2각도(WF+CPCV 독립). 실측 1호: Funding_level(2020-26) ①가능성O(WF88%·netSR0.64·CPCV p25+0.51)·②③X(SPRT미결·DSR0.71·레짐의존). 펀딩/OI는 '가능성 있으나 미배포' — 레짐게이트·저회전·조합으로 증폭 후 재판정이 다음수.
