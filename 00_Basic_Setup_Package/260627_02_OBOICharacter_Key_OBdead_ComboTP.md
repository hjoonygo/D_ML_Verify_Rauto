# KeyNote — 260627_02_OBOICharacter (OB/OI 5중사망 + REVoi 청산 COMBO 본알파)
세션ID: 260627_02_OBOICharacter · 2026-06-27 · 전환점(알파)
단일출처 보강: memory `00_GUIDE2_Alpha.md`(그룹 C/D/E) · INDEX · STATE_Rauto.txt · CLAUDE.md §23(단짠배합)

## 0. 세션 목표(캡틴)
"OI 데이터로 OB(오더블록)의 성격을 판별 — 돌파 / 지지저항 / 휩소후 변동성소멸 / 휩소후 반대방향 유동성탐색"을 가려 진입취소·증량·분할진입·분할청산·손익절에 쓴다. (스윙용)
- 선행 토론: 제미나이·ChatGPT → "OI=방향 아닌 에너지", "Response Engine→Magnitude(크기)", "OB Character(생존평가)"로 수렴. ChatGPT 'OB생존 85% 유망'·제미나이 'data.binance.vision 청산 무료'는 검증서 기각.

## 1. ★결론 두 줄
- **OB/OI = 5중 사망**: OB의 OI 성격판별은 진입·청산 어디서도 고유가치 없음. OI 방향판별 5차 확인.
- **부수발견 = 본알파**: REVoi fibstop이 이익을 늦게 청산 → **COMBO(tp_frac 구조부분익절 + early_tp 고정조기익절) = M20 +98,018%/MDD−16.8%/강제청산0** 챔피언 인증후보.

## 2. 5단계 검증 (Stg1~9, 전부 무손상·룩어헤드0)
| Stg | 검증 | 결과 |
|---|---|---|
| 1 OBCharacterStudy | OB(ICT 임펄스직전 반대색봉) 추출+기저 Bounce | zone기준 69% but **착시**: 추세편향 기각(순행65≈역행65)·진입가기준 대칭 +10~12%p(미약) |
| 2 OICVDFilter | OI/CVD가 OB 돌파/저지 가르나(CPCV·RankIC) | **OI AUC 0.50 무력** · CVD AUC0.62지만 가격중복(cvd+ret≤ret) · 진짜는 rev_ret(가격모멘텀0.71)·rev_depth(stop근접 동어반복) |
| 3 OB1mPrecision | OB 단독 1m체결+비용 | **적자**(손익비 0.74~0.88<1 = stop 1m갭) |
| 4 REVoiOBOverlay | REVoi 진입에 전방OB 사이징 | **레버효과**: BOOST_near +4132%(p25/노출86) ≈ 노출통제 BASE_x1.34 +4513%(87) → OB선택 무가치 |
| 5 REVoiOBExit | REVoi 청산에 전방OB 익절 | OB_TP +3741%/MDD−13.5% 좋아보임 → **고정익절 FIX_1% +9785%/MDD−10%가 우위 = OB 위치 무관** |
| 6 REVoiEarlyTP | 부수발견(일찍익절) 과적합? | **과적합 아님**: 스윕 plateau(0.5~1% 전부 +9000~11000%)·held-out(train0.75%→test 최상권)·미도달손실 작음(평균−0.33%/최악−2%). ★대칭손절 폭락(−81%)=REVoi 손절로직이 핵심 |
| 7 EarlyTPvsTPfrac | 조기익절 vs tp_frac(후처리) | COMBO 압도 but **§26 레버스윕 폭주(+10^18%)** = 후처리 보유기간/mae 부정확 |
| 8 ComboEngineGate4 | 엔진내장 정확 §26 4단 | **무손상(BASE +1851.6%)** + COMBO lev3 +18052%/MDD−12.8%/p25+443%/test+902% · **§26 정상화**: M20 +98018%@L4 /M25 +2.67e6%@L6 /M30 +1.35e7%@L7 (강제청산0) |
| 9 ComboBack2TV | Back2TV 생성 | M20 챔피언 +98018%/MDD−16.8%/청0/승률71%/PF2.25 · Pine v6·사례6선·통합표 + 비용 gross_R 수정 |

## 3. 엔진 수정(공용엔진, 전부 opt-in·앵커 무손상)
- `bt_full.gen_trades`: `early_tp_pct`·`early_frac` 파라미터(tp_frac 패턴 미러) + 진입시 `early_target=ep*(1±early_tp_pct)` + 청산시 early 부분익절 블렌드 + **`gross_R`(블렌드 무비용, 비용분해 §19)** 컬럼. early_tp_pct=0 → 기존 완전동일.
- `REVoi_bot`: early_tp_pct/early_frac p.get 전달.
- `bt_report.per_trade`: gross를 `gross_R`(블렌드 무비용) 사용 — 기존 x_int(fibstop)는 early_tp 블렌드 미반영이라 gross<net 버그였음(tp_frac에도 잠재). 하위호환 폴백.
- `back2tv_REVoi.rev_trades`: tp_frac/early_tp/early_frac p.get 전달 → make_back2tv 그대로 COMBO Pine·사례 생성.

## 4. COMBO 확정 config (M20 챔피언 인증후보)
```
REV_MDD25_36mo.p + tp_frac=0.7, early_tp_pct=0.0075, early_frac=1.0
사이징(M20): size_pct=75, lev=4 (exp 3.0)
→ +98,018% / MDD −16.8% / 강제청산0 / 승률71% / PF2.25 / 단일최고월+44% (36개월·현실비용8bp)
검증: 무손상 BASE +1851.6% / held-out test +902%(vs BASE +304%) / CPCV 표준6 p25 +443% / §26 4단
Back2TV: 00_WorkHstr/BackTest_Output/260627_15_COMBO_M20_tp07e075_L4/ (Pine v6·사례6선·통합표·분석txt)
```

## 5. ★방법론 교훈 (재사용)
**"더 단순한 대조가 알파 환상을 깬다."** 화려한 수치 나오면 ⒜사이징 효과는 **노출정규화(p25÷노출)**로, ⒝위치/선택 알파는 **같은거리 고정대조(FIX)**로 분리. Stg4 노출통제·Stg5 FIX대조가 "OB 청산 알파!" 오판을 막고 진짜(REVoi 청산 파라미터)를 드러냄.

## 6. 데이터 현황 (38개월 미완)
- 백테 36개월(2023-05~2026-04) = 앵커 데이터(무손상).
- Dauto `08_BTC_Data/raw_irreplaceable/BinanceData/`에 2026-05-12~06-22 1m(OHLCV+OI+taker+funding) 있음. ★단 **12일갭(04-30~05-12)+OI일부결측+oi_zscore 38개월 재구축** = 데이터 파이프라인 작업(오염위험) → 별도 Stg.

## 7. 미결(다음)
- ★진짜 held-out: early_tp_pct를 train서 재탐색→test (현재 0.75%는 36mo 최적, train→test는 통과).
- 38개월 데이터 확장(Dauto 병합·oi_zscore 재구축·갭처리).
- CPCV 표준6 정밀(엔진내장 거래로)·실거래.
- §9 정식 확정알파 등재 = 캡틴 최종 '채택' 승인 後.
- (OB는 종료. OB 청산 분할/손익절도 5중사망에 포함 — FIX 대조로 OB무관 확정.)
