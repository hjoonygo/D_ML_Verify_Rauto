# 260628_02_LiqBrakePlugin — KeyNote: 비상 안전장치 1호(강제청산 슬리피지 브레이크) + RevoiSafe@ETF

세션 260628_02_LiqBrakePlugin (2026-06-28~29) · 캡틴 향후3 → 비상 안전장치 결정·모듈화.
★수익률 표기 규칙(memory#6): 모든 수치에 (기간, in-sample 상한 / OOS) 라벨. 헤드라인=OOS.

## 1. 출발 — 캡틴 향후3
"급변동으로 못 빠져나오는 경우(청산조차 못함)가 제일 무섭다. 옛 TS에서 Lev22 진입→7.8% 강제청산을
'슬리피지 브레이크'로 만들었다. REVoi에 적용하고 모든 봇에 장착 가능한 PlugIn으로 모듈화하라."

## 2. 검증 아크 (Stg1~7) — 검증엔진만(per_trade_pnl·REVoi_bot), 무손상 앵커 +1851.6491% 전구간 재현
- **Stg1 (브레이크 1차판정)**: 동일 노출서 레버↑ = 청산 빈발 = MDD 악화(-12%→-99%). 꼬리슬립 0~100bp 전구간 고레버 열위.
  → '누적 MDD 관점'에선 REVoi(역추세, 정상역행 견뎌야 수익)에 고레버 역효과.
- **Stg2 (REVoi@ETF 안정선)**: post-2024 28mo. MDD 4단 최대수익(현실10bp·in-sample 상한). M20=노출3.0 +8,151%(in-sample 상한)/MDD-18.7%. 헤드라인 OOS(test 16mo) +1,088%/MDD-14.8%/청0.
- **Stg3 (노출고정 레버스윕)**: 노출3.0서 lev3~15 수익·MDD 동일(청산0). lev20+ 청산시작. 증거금 100%→20% 낮춰도 무손실=한방손실만↓.
- **Stg4 (강제청산0 최대레버)**: worst mae -5.0993%(2025-01-20). 강제청산0 최대 = **lev17**(보수 MMR_T2). lev18부터 청산.
- **Stg5 (2025-10 실급락 스트레스)**: 12만→10만(-17.1%). ★실제 REVoi=그순간 flat(타격0)+그달 숏 +12.9%(언사이즈드). ★가상 롱 worst: lev3 -51%(생존, 다먹음) vs lev17 -16%(청산cap). = 고레버 손실cap 증명.
- **Stg6 (순간급변동 전수)**: 36mo 순간5%+ = 4건(7%+0건). 최악 6.27%. 갭관통0 = **lev≤14**. REVoi 4건중 롱노출0.
- **Stg7 (청산손실 분해)**: lev15→lev20 수익하락 = 청산된 2건(#327 되돌아올 거래를 -4.45%서 청산해 증거금92% 소실)이 복리누적.

## 3. ★대결론 — 2진실(트레이드오프, 둘 다 맞음)
1. **정상장(역행 -1~5%)**: 고레버=청산빈발=수익잠식 → 저레버 유리(Stg1~4·7).
2. **극단 급락(롱 -17%)**: 고레버=증거금작아 청산이 손실cap → 고레버 유리(Stg5).
- → 교집합 = **lev12~17**(정상장 수익 무손실 + 극단 손실cap). lev3/증거금100%=극단급락 -51% 취약=폐기.
- 캡틴 직관('강제청산 브레이크')은 ②극단 관점에서 정확. 내 초기 '역효과'는 ①누적MDD 관점(둘 다 진실).

## 4. ★비상 안전장치 1호 — engines/emergency_brake.py (PlugIn, 봇무관)
- `liq_zero_max_lev(worst_mae)` → 강제청산0 최대레버(REVoi=17). `gap_zero_max_lev(flash)` → 갭관통0(=14).
- `recommend(worst_mae, 노출, buffer0.85)` → 권장 안전 사이징. `assess(lev,size,...)` → 안전 등급.
- `hard_loss_cap_pct(size,lev)` → 한방 최대손실(=증거금). 시장상수 MARKET_FLASH_MAX=6.27%(Stg6, 갱신단일점).
- Rauto 결정두뇌가 봇 등록·사이징 시 호출. 검증엔진 무손상(사이징 결정/진단만).

## 5. RevoiSafe@ETF (신규봇, 캡틴 확정 2026-06-29)
- 사이징 = 노출3·lev15·증거금20%·COMBO(tp0.7/early1.0%). 증거금20%로 lev3/100%와 수익·MDD 동일 + 극단급락 손실cap(한방18%).
- 등록값(veri_edge.nameplate): **예상 월복리 16.54%(OOS)** · OOS(test 16mo) +1,058%/MDD-14.8%/강제청산0 · 36mo검증 +26,754%(in-sample 상한)/MDD-18.7% · 레짐별(상13.76/하39.21/횡16.65).
- Rauto2 등록: BOT_REGISTRY+REG_MONTHLY · 챔피언 핀=RevoiSafe@ETF(캡틴) · 무손상 앵커 재현.

## 6. champion_safety.py (챔피언 가산점, 캡틴 지시2)
- 비상 안전장치 8점: 강제청산방어(lev≤17)+2·갭관통흡수(lev≤14)+1·조기익절+1·dd컷+1·gate+1·레짐적응+1·저MDD+1.
- pick_champion 동점 타이브레이커(1차 수익/레짐 동점→안전점수). 핀 우선·per_trade 무손상. _champ_report 보고.
- 점수실측: REVoi@ETF 5/RevoiSafe 4/결합 5/M0천장·R+P70 3/나머지 4.

## 7. 수익률 라벨 강제장치 (memory#6 재범방지)
- Stop hook `.claude/hooks/ret_label_guard.py` + `engines/ret_guard.py`: 라벨없는 큰 수익률(≥1000%·만/억%) 헤드라인 차단·자기수정. 오탐 예외(%p·임계어·코드·소수점·앵커). 라이브 작동·차단 실증.

## 8. 데이터 한계(정직)
- 검증데이터=36mo(2023-05~2026-04). 38mo(2026-05~06)는 12일갭+oi_zscore 재구축 미완(오염위험)=불가. 안전레버는 36mo(2023 고변동 포함=보수)로. 미래 더 큰 급변동(>6.27%) 가능→버퍼.

## 9. 산출물
- 코드: engines/emergency_brake.py·champion_safety.py·ret_guard.py · rauto_live.py(safety) · server.py(RevoiSafe·핀·보고).
- 검증: 03_IDEA4Bot/260628_02_LiqBrakePlugin/Stg1~9 + rawoutput.
- 분석txt: 00_WorkHstr/2026062819~21*_Stg1~6.txt · INDEX.
- 문서: CLAUDE.md §27·LogicCatalog D3/D7·이 KeyNote·Guide_Emergency_brake.docx.
- 배포: git push origin rfrauto(2fa8a78) → AWS autopull.
