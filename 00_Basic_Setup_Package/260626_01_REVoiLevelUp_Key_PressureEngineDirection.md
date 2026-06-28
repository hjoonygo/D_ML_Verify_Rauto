# KeyNote — 260626_01_REVoiLevelUp · 장세판별 토론 검증 + 압력엔진 방향 (★미검증 방향)
> 작성 2026-06-26 · 세션 260626_01_REVoiLevelUp · 출처=제미나이 딥리서치 보고서 + ChatGPT 2차 토론 + Claude 선행연구 조건검색
> ★성격: 이 문서는 '검증 통과한 알파'가 아니라 **연구 방향 확정**이다. 채택은 Back2TV·4관문·CPCV 표준6·MDD 4단 게이트(§26) 통과 후에만. (지침2 그룹C 경계)

## 0. 한 줄
장세를 'Bull/Bear/Range 라벨로 분류'하는 대신 **연속 '압력(Pressure)'값**으로 만들어 REVoi 휩소필터(진입 솎기·사이징·피보스톱 타이트)에 꽂는다. 검증은 기존 레일(이미 보유) 그대로.

## 1. 선행연구 조건검색 — 두 AI 주장 진짜/과장 판별 (Claude WebSearch 2026-06-26)
| 주장 | 선행연구 | 판별 |
|---|---|---|
| ETF 가격발견 85% 선행(제미나이) | Springer(2025) IBIT/FBTC/GBTC ~85% 시간 현물 선행. **단** Wiley(2026)·후속 = 안정기 현물·고변동기 선물 = **시변** | ✅진짜(주도권 시변) |
| 온체인 89% 예측력 상실(제미나이) | MVRV·NUPL 2025 '침묵'은 맞으나 학계=ETF 앵커로 **압축**이지 상실 아님. ScienceDirect(2026) 여전히 사이클 유효+ETF flow 결합시 강함 | ⚠️과장(단변량·고빈도만 약화) |
| GEX 최상위 Tier S(제미나이) vs ★★★ 제한(ChatGPT) | Glassnode/MenthorQ(25-26) 딜러감마 $507M vs ETF $38M=13:1 핀닝 실재. 단 BTC 옵션 파편화·MM 선물헤지 | 🔀둘 다 부분참(데이터 없어 당장 불가) |
| 고정 Lead-Lag 위험·시변으로(ChatGPT) | MDPI(25-26) rolling Granger+구조변화탐지=시변 인과가 연구표준 | ✅진짜 |
| 검증(CPCV/SPRT) 최대 누락(ChatGPT) | López de Prado CPCV 표준. 단 워크포워드=실거래 시뮬 표준, 둘 다 써야 | ✅진짜 (★우리 이미 보유) |
| DRL 실전무용·XGBoost 압도(ChatGPT) | arXiv2209.05559 DRL 과적합 심각→과적합검정 필요. '버려라'는 아님. XGBoost 압도 강한근거 약함 | 🔀방향맞음·단정과함 |
→ ChatGPT 자평(75~80% 수긍·15% 과장)은 선행연구와 **대체로 정합**.

## 2. 우리 시스템 관점 3대 함정 (동조 말고 지적 §10)
- **함정① 데이터 가용성**: 5압력축 중 우리 36개월 검증데이터=OI·Funding·CVD·price·atr뿐. **ETF Flow·옵션GEX·L2 BookImbalance·Macro M2 없음**. 미시구조 단변량 IC<0.07=약함(지침2 E), 추세(ret_24h) 압도적. → 6레이어 풀스택 지금 불가. 가능축=Trend·Leverage·Execution 3개.
- **함정② "Pressure→Action 직접학습"=블랙박스 ML**: ChatGPT가 DRL 무용론 펴고 또 ML 다이렉트 추천=모순. 우리 4관문(환각0·앵커재현·피처룩어헤드)은 블랙박스 못 통과. → 압력은 연속피처로, 매핑은 **기계적·해석가능 규칙**(단짠배합 §23). ML은 OOS만.
- **함정③ ★검증은 우리가 앞섬**: 두 AI '최대 누락=검증'인데 우리는 §15 5관문·§25 4관문·CPCV 표준6·1m환각0·Back2TV·무손상앵커·MDD 4단게이트(§26) 가동중. ChatGPT도 "1분봉 실체결 몬테카를로가 보고서보다 앞선다" 인정. → 새로 필요한 건 검증 아니라 **압력/정보 입력피처 확장**.

## 3. 방향 확정 (REVoi 휩소필터에 직접)
- 레짐 라벨분류 폐기 → **연속 압력값**. 압력축 3개(가진 재료): Trend(ret_24h)·Leverage(OI_z+funding+|롱숏쏠림|)·Execution(CVD).
- 압력→Action = 기계적 규칙(불리압력↑→솎기/사이징↓/스톱타이트, 유리↑→풀노출/느슨). opt-in(끄면 기존동일).
- 검증=기존 레일: 무손상 앵커 → 4단 MDD 게이트 → Back2TV+4관문+CPCV 표준6. 헤드라인=수익률(36개월+분기 롱숏).
- ★안 하는 것(이유): 옵션GEX·ETF Flow·BookImbalance(데이터없음=확보가 선행과제) · DRL/LLM레짐결정(블랙박스=4관문불가) · 시변 Lead-Lag 풀매트릭스(과적합, 1개만 조심).

## 4. ★캡틴 통찰 — 강제청산 = 계좌 구하는 캡 (2026-06-26)
- 격리마진+고레버+급변동: fibstop 시장가청산은 슬리피지로 증거금보다 더 깊이 잃을 수 있는데, **강제청산이 먼저 터지면 유지증거금만 날리고 끝**(수수료·슬립 무관) = 손실 캡 = "계좌를 구한다".
- → 스윕 사이징 = 캡틴 정의(강제청산 손실=증거금 size%/100, 비용·펀딩·슬립 0가산). 기존 모델(exp×(1/lev−mmr−SLIP+COST+|fund|))과 미세차 → 캡틴 정의로 통일. 앵커(레버3/청산0)는 무손상.
- 어떤 (레버·size) 영역은 **강제청산 수용이 최적** = 4단 게이트(M0~M20) 스윕으로 그 영역 발굴 + 강제청산 횟수 의무 산출.

## 5. 첫 모듈 = Leverage Pressure (캡틴 선택 2026-06-26)
- LP = z(|OI_z|)+z(|funding|)+z(|롱숏쏠림|) + 저변동(atr60) 가중. 전부 과거전용(룩어헤드0). table.csv 932거래에 이미 태깅됨=즉시 실증.
- 근거: REVoi 손실 표적(§20 저변동 횡보+OI충격·펀딩·쏠림 동시=fibstop 손실)을 직격. ChatGPT 예시(OI↑funding↑=Bull인가 Long Crowded인가)가 정확히 이것.
- 세밀 격자: TF(2/4/6/8h)·레버(2~15)·진입수량(50~100%)·LP임계(OFF/40/25/10%)·스톱타이트(1.0/0.8/0.6/0.5) × 4단 MDD 게이트.

## 6. 출처(Sources)
- ETF: link.springer.com/article/10.1007/s10614-025-10998-x · onlinelibrary.wiley.com/doi/10.1111/fire.70026
- 온체인: sciencedirect.com/science/article/pii/S0275531926002138 · arxiv.org/pdf/2411.06327
- GEX: insights.glassnode.com/gamma-exposure-heatmap · menthorq.com/guide/dealer-flow-in-btc-options
- Lead-Lag: mdpi.com/2227-7072/14/5/103 · mdpi.com/2227-7390/14/2/346
- 검증: en.wikipedia.org/wiki/Purged_cross-validation · sciencedirect.com/science/article/abs/pii/S0950705124011110 · garp.org(López de Prado 10 Reasons ML Funds Fail)
- DRL: arxiv.org/abs/2209.05559

## 7. ★실행 결과 (2026-06-26 검증 완료 — '미검증 방향' → 결과)
- **LP 진입솎기(Stg1)**: 무손상 앵커 +1851.6% 재현. 4단게이트 M20 +789→+950 처럼 보였으나 **순수효과 분리(같은 노출 고정)=노출효과**로 판명 → 진입솎기 약함.
- **압력 3축 청산연결(Stg2·3)**: Lev/Trend/Exec 연속·이산 전부 **CPCV 표준6 본선 미달(MDD−20 위반 40%)** vs 기존 이산R×2.0 +2065%/p25+107%/**위반0%**. = **압력 3축 전부 기각, 미시구조 청산연결 종결.** (선행연구·§GUIDE2 E "미시구조 약함" 3차 재확인.)
- **청산세팅 확정(Stg4·5)**: **R+P(70%)** 현실(스프1bp) **+2083%/MDD−15%/청산0**(슬립0 상한 +2592%, OFF현실 +1483%서 갱신). 측정 청산슬립~0bp. Back2TV=260626_02_REVoi_RP70_Real_Back2TV(Pine·사례6선·통합표).
- ★per_trade net 스프 미반영=상한 정정(bt_report §20⒞ 편향). SlipRealism(스프1bp 반영)이 더 정직.
- **결론**: 토론의 '압력 추론 엔진(Pressure Inference)'은 우리 36개월 데이터·CPCV에서 **검증된 이산 청산 스텝업을 못 넘는다.** 진짜 레버 = 청산(R+P). 압력엔진 방향은 옳았으나 이 데이터에선 양념조차 안 됨. = 검증이 거대담론을 거른 사례.
- **다음**: R+P held-out §9 확정 → 챔피언 인증 M20 · 4단게이트 현실 정밀 재산출(per_trade 스프 보정).
