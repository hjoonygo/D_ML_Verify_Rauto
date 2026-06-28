# 재현 manifest — 260627_01_RegimeCertCard (2026-06-27)
세션: 캡틴 제안1(레짐별×설정별 챔피언 인증카드) + 전환점(현실 비용 단일모델 재인증) + 레짐 챔피언교체·휩소 오버레이 정직검증.

## 코드 (/code — 03_IDEA4Bot/260627_01_RegimeCertCard/)
- `260627_01_RegimeCertCard_Stg1_RegimeConfigCert.py` — 8봇×비용3×레짐4 인증카드 + R+P70 §26 4단 레버스윕. 무손상 앵커3 자체검증.
- `260627_01_RegimeCertCard_Stg2_ChampSwitchReturn.py` — M20 5봇풀 레짐 챔피언 로테이션(즉시청산없음) vs 고정·병행.
- `260627_01_RegimeCertCard_Stg3_WhipsawRiskOverlay.py` — 휩소-회피 로직별 §26 4단 최대수익(수익률 우선).
- `260627_01_RegimeCertCard_Stg4_WhipsawHoldoutCPCV.py` — WHIP_soft held-out+CPCV 정직검증(거래단위 MDD).
- `260627_01_RegimeCertCard_Stg5_LeverBlendMDD20.py` — 휩소+진입품질 배합 §26 4단+OOS CPCV.

## 산출물 (/output — 00_WorkHstr/BackTest_Output/)
- `260627_01_RegimeCertCard/` — 인증카드.csv · 4단레버스윕.csv · 분석.txt · 레짐DNA.png
- `260627_02_ChampSwitchReturn/` — 비교표.csv · 로테A_분기별.csv · 분석.txt · 곡선.png
- `260627_03_WhipsawRiskOverlay/` — 4단최대수익.csv · 분석.txt
- `260627_04_WhipsawHoldoutCPCV/` — heldout.csv · cpcv.csv · 분석.txt
- `260627_05_LeverBlendMDD20/` — 배합표.csv · 분석.txt

## 문서 (/docs — 00_Basic_Setup_Package/)
- `260627_01_RegimeCertCard_Key_RealCostRecert.md` — 전환점 ADR-003(현실 비용 단일모델) 6단계.
- `260627_01_RegimeCertCard_Key_RotationWhipsawFindings.md` — Stg2~5 분석 아크 + TIL 5개.

## 검증 데이터 (재현 의존 — self-locating 스크립트가 탐색)
- `08_BTC_Data/derived/Merged_Data.csv` (36mo 1m OHLC + oi_zscore_24h) ← load_1m.
- `BTCUSDT_funding_history_8h.csv` (실펀딩) ← load_funding.
- `08_BTC_Data/derived/_regime_features.parquet` (ls_s 롱숏쏠림) ← Stg5.
- `03_IDEA4Bot/260623_07_RfRautoAlphaUp/back2tv_rev_winners.json` (REV_MDD25_36mo 파라미터).
- 검증엔진(무수정 §8): REVoi_bot·bt_full·trendstack_signal_engine·rauto_cex (04_공용엔진코드/engines).

## 재현 방법
`set PYTHONIOENCODING=utf-8 & python 260627_01_RegimeCertCard_Stg{N}_*.py` — 난수0·같은 config→항상 동일.
무손상 게이트: 각 스크립트 시작 시 OFF(R+P70 lev6/55) 현실 +8669%/−21% 또는 앵커 tp0 +1851.65% 자체검증(불일치=중단).

## 핵심 결론
단일 REVoi 알파로는 (레짐 챔피언교체·휩소·진입품질 배합 아무리 해도) MDD−20 챔피언 인증 불가 → **상관 낮은 추세봇 포트폴리오가 다음 최우선**. + 전환점: REVoi 현실 수익률 단일출처=§24 RautoCEX(현실 M20챔피언 +7670%).
