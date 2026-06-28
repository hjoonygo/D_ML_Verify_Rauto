# Rauto 구조개혁 SPEC — 단일출처 (세션 260625_01_Rauto_Sys_Reform)
# 캡틴 승인 2026-06-25. 이 문서가 Rauto 모듈 아키텍처의 단일출처(§22). 변경 시 여기부터.

## 0. 왜 (배경)
백테 수치가 물어볼 때마다 달라지고(+1852%↔+253%↔+1483%), 비용이 "14bp냐 8bp냐 4bp냐"로 매번 재논쟁(갑/을).
근본원인 = **관심사가 안 나뉨**: 비용/체결 로직이 4곳(신호엔진 4bp·실행엔진 14bp·bt_full 8bp·fib_replay 8bp)에 흩어짐.
대책 = 기능을 모듈로 나누고, **비용·체결은 RautoCEX 한 곳에만** 둔다. = 퀀트 업계표준(DataHandler→Strategy→Portfolio→ExecutionHandler→Statistic) 재현.

## 1. 5모듈 구조
- **[0] 관제센터(Control Center)** = DataHandler+오케스트레이션. 바이낸스 API→★중앙 1m봉 단일출처→슬롯에 봇 로딩·챔피언 관리.
  - ★미래참조차단 게이트: 봉 '마감 후에만' 전달(4h봉=08:00에 공개). 룩어헤드 OFF.
- **[1] 매매신호(Signal)** = 각 봇. 1m받아 자기 TF변환→장세판별→진입/청산 Signal만(비용 모름).
- **[2] 매매결정(Decision/Portfolio)** = Rauto 두뇌. 신호 취합→진입/청산 결정+사이징+듀얼k배분+★**챔피언 인증 M20 게이트**+챔피언 선발.
  - ★MDD 4단 게이트(CLAUDE.md §26, 캡틴 2026-06-26): 'MDD−20 리스크게이트'는 곧 **챔피언 인증 게이트(실거래 자격)**. 탐색·알파상승은 MDD 무제한/−30/−25 허용(−20 족쇄 없음), **챔피언 인증에서만 MDD−20(M20) 강제**. 미달=Rauto 로딩○·챔피언 자격✕·실거래✕. 모든 백테 격리마진 강제청산 횟수 의무.
- **[3] RautoCEX(체결+비용)** = ExecutionHandler/SimulatedExchange. FillModel+SlippageModel+FeeModel+MarginModel. [Sim 백테]↔[Live 실거래소] 인터페이스 교체.
- **[4] 결과분석(Analysis)** = Back2TV(완성). 실거래용 실시간 모니터는 별도.

## 2. ★비용 2레이어 철칙 (§7 — 어기면 갑/을 부활)
- **selection_cost** = 신호엔진 4bp. '어느 봉에 진입하나' 고르는 임계값. **P&L 아님. 모듈1에 남는다.**
- **execution_cost** = RautoCEX. 진짜 P&L(maker2/taker4/스프1·슬립·펀딩·격리마진). **여기로만 모은다.**
- 둘은 다른 것. RautoCEX로 모으는 건 execution_cost만. 이름을 갈라 박는다.

## 3. ★승인 전 박은 7개 안전장치 (위험 시나리오 S1~S8 대책)
1. **앵커 회귀 관문**: 모든 추출 단계 = 같은 config→같은 수익(+1852%/+827%) 재현해야 머지. (S3·S5)
2. **FillModel 철칙**: 가격 도달 ≠ 체결 보장. 스톱=시장가+슬립, 지정가=도달해도 미체결 가능. (S2, +11397%→+39% 환상 재발방지)
3. **중앙 리샘플러 봉마감 게이트 + 룩어헤드 단위테스트**: 미래봉 주입해 게이트 검증 + 출력 verify_rev3 1m겹침. (S1·S8, 집중오염 방지)
4. **비용 이름 강제분리**: selection_cost(신호) vs execution_cost(CEX), 머지 금지. (S5)
5. **챔피언 선발 = CPCV/held-out 게이트 + 챔피언 인증 M20(MDD−20) 게이트로만**, full표본 선발 금지. 탐색은 MDD 4단(무제한/−30/−25/−20) 최대수익 + 강제청산 횟수 산출, M20 통과분만 챔피언 자격(CLAUDE.md §26, 캡틴 2026-06-26). (S6, 과적합·생존편향)
6. **단일 모델 공유**: 벡터 백테와 이벤트 라이브가 같은 Fill/Slip/Fee 코드 호출, 1회 교차검증. (S4)
7. **슬립 틱데이터 보정 예약**: RautoCEX 슬립은 가정 아닌 aggTrades 실측 보정. (S7, [[binance-tick-data-real-slippage]])

## 4. 착수 순서 (④ 점진 — 한 번에 다 안 함, 각 단계 앵커 회귀 통과해야 다음)
- **① RautoCEX 떼기** ← ★착수 1순위. 비용 4곳→1곳. **[완료 2026-06-25] 앵커 +1851.6%/MDD-24.6% 1원단위 재현(무손상 추출 PASS).** → `04_공용엔진코드/engines/rauto_cex.py` 승급.
- **② 중앙 1m + 룩어헤드 게이트** = `rauto_datahub.py`(DataHub). **[완료 2026-06-25] ⒜무손상(resample==기존 6576봉) ⒝룩어헤드 누수 0/1000(게이트없는 라벨접근은 100% 누수) ⒞진행중 미래봉 차단 ⒟경계 PASS = ALL PASS.** 규칙: 봉마감(라벨+TF) ≤ now인 봉만 공개. → `04_공용엔진코드/engines/rauto_datahub.py`.
- **③ 신호/결정 분리** = `rauto_signal.py`(SignalModule, rev_side 래퍼) + `rauto_decision.py`(DecisionModule, 좁은범위'가'=사이징·SL만, 챔피언/k배분 없음). **[완료 2026-06-25] 전체체인(DataHub→신호→결정→CEX) 앵커 +1851.6%/MDD-24.6% 차이 0.000%p(PASS).** 래퍼만·검증엔진 무수정(§8·§15.1). 결정모듈 범위=캡틴 (가)채택.
- ④ 관제센터 **[진행 2026-06-25 세션 260625_01_RautoSysReform2]**: 봇무관 오케스트레이터 v0(`engines/rauto_orchestrator.py`) + ★봇 계약(`make_trades(d1m,fund,capture_fills)→원장{et,xt,xt_fill,side,entry,exit,R,mae,fund,reason,fills}`) + 신호/결정 → `REVoi_bot.py`(봇별) engines 승급(self-locating `path_finder.py`). 앵커 +1851.6%/MDD-24.6% **0.000%p**(검증엔진 7개 SHA256 무수정).
  · ★책임 경계 표준확정(Alpha→Portfolio→Execution, LEAN·QuantStart): **봇=알파 / Rauto=사이징·리스크·배분·챔피언 / RautoCEX=체결·비용**. 네이밍 = 봇별 `(봇명)_*` / 시스템 `rauto_*`.
  · ★봇 신뢰 4관문 `engines/bot_trust_gates.py`(①앵커 ②환각 1m겹침[봇무관] ③CPCV ④현실비용) — REVoi ✅통과(진입2796/2796·청산932/932·환각0·p25+41.7%·현실+1483.3%).
  · 남은: 슬롯·챔피언선발(CPCV/held-out 게이트=안전장치5) · TS·SW 멀티봇 검증 · 라이브 브리지(Work_Order). 상세 = CLAUDE.md §25.

## 5. ① RautoCEX v0 현황 (이 세션 산출)
- 파일: `rauto_cex.py`(FeeModel·SlipModel·FillModel·MarginModel·RautoCEX) + `260625_01_Rauto_Sys_Reform_AnchorTest.py`.
- 검증: 기존 `back2tv_REVoi.liq_eval` ≡ 새 `RautoCEX(슬립0)` = +1851.6%/MDD-24.6%/청산0, **차이 0.000%p**(관문1 PASS). 스프1bp=+1483%(SlipRecheck 일치).
- 설계: bt_full이 R에 박은 기본비용(MK+TK+펀딩)을 gross로 복원→CEX가 자기 모델로 재차감 → '비용 단일출처' 달성. selection_cost 미유입(구조적).
- 한계: v0는 Sim 모드만. Live 구현체 미작성. 슬립모델 계수는 측정갭0+스프1bp(틱 실측보정은 안전장치7).
- 다음: 검증 통과 → `04_공용엔진코드/engines/rauto_cex.py`로 승급(§22 T1), 또는 ②착수.

## 6. 변경이력
- 2026-06-25 신설. 캡틴 승인. 5모듈 + 7안전장치 + RautoCEX v0 앵커 PASS.
- 2026-06-25(세션2 260625_01_RautoSysReform2): ④관제센터 봇무관 v0 + 봇 계약 경계(Alpha→Portfolio→Execution 표준) + REVoi_bot 승급(self-locating) + bot_trust_gates 4관문(REVoi PASS). 매 단계 앵커 0.000%p·엔진 SHA256 무수정. 상세 CLAUDE.md §25.
