# 260623_07_RfRautoAlphaUp — 검증 체크리스트

현재 등급: **T0** (아이디어→봇전략) · 출생 2026-06-23 · 알파: OI 다중팩터 → ATR×OI 변동성 사이징

## 등급 이력
- 2026-06-23 출생 T0 (`03_IDEA4Bot/260623_07_RfRautoAlphaUp/`)

## 졸업조건 추적 (T0 → T1)
- [x] 알파 가능성 검증: OI Spike **방향 반증**(이벤트 study p>0.1) · **변동성 실재**(vol비 1.35)
- [x] MDD 후보: **ATR×OI 변동성 사이징** → V0 MDD −39→**−19.1%**(−20%안)·CPCV +0.28·복리 +75%
- [x] 견고성: CPCV p25>0 **100%**(27조합)·연도 MDD개선 **4/4** = 칼날 아님
- [~] MDD-20% 안정: **56%**(중앙-19.7%·최악-23.6%) = 단독 빠듯, 진입품질 결합 필요
- [x] 민감도 스윕 = 견고(과적합 반증)
- [ ] WF 부호안정
- [ ] (통과 시) T1 승급 = `04_공용엔진코드/260623_07_RfRautoAlphaUp.zip` + manifest

## 산출물 (`03_IDEA4Bot/260623_07_RfRautoAlphaUp/`)
- alpha_card.md (단일출처) / oi_spike_event_study.py / oi_vol_gate.py / vol_sizing_compare.py

## 다음 조건
정식검증(민감도·WF·CPCV 표준6) 통과 → `python promote_alpha.py 260623_07_RfRautoAlphaUp T0 T1`로 승급.
