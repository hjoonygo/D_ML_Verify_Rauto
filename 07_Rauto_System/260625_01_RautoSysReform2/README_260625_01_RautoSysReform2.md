# 260625_01_RautoSysReform2 — 재현 패키지 README
(세션 2026-06-25. ④관제센터 봇무관 구조개편 + 봇 신뢰 4관문. 다른 AI가 이 zip만으로 검토·재현 가능하게.)

## 1. 이 세션이 한 것
- **봇 계약 경계 확정**(퀀트 표준 Alpha→Portfolio→Execution, 출처 QuantConnect LEAN·QuantStart):
  봇=알파(신호+진입/청산) · Rauto=사이징·리스크·배분·챔피언 · RautoCEX=체결·비용.
- **네이밍 원칙**: 봇별 `(봇명)_*` (REVoi_bot.py) · 시스템 `rauto_*`. `rauto_decision`은 미래 사이징·리스크 두뇌용 예약.
- **봇 계약**: `make_trades(d1m, fund, capture_fills=False) → 거래원장{et,xt,xt_fill,side,entry,exit,R,mae,fund,reason,fills}` (R=언사이즈드).
- **봇 신뢰 4관문**(bot_trust_gates.py): ①앵커·재현 ②환각검증(1m 전수겹침=봇무관) ③CPCV 표준6 ④현실비용.

## 2. 파일 (/code · /verify · /docs · /data)
- `/code` (= engines, 04_공용엔진코드/engines 사본):
  - `path_finder.py` — self-locating 폴더 길찾기(하드코딩 경로 제거).
  - `REVoi_bot.py` — REVoi 봇(신호+진입/청산 알파). 계약 make_trades.
  - `rauto_orchestrator.py` — [0]관제센터(봇 무관 지휘자). 봇→RautoCEX 구동.
  - `rauto_cex.py` · `rauto_datahub.py` — [3]체결+비용 · [0]중앙1m+룩어헤드게이트(참고, 본 세션 무수정).
  - `bot_trust_gates.py` — 봇 신뢰 4관문(run_gates).
- `/verify`:
  - `..._OrchestratorAnchorTest.py` (+ _run.log) — 관제센터 앵커 회귀(+1851.6% 0.000%p).
  - `..._BotTrustGates_REVoi.py` (+ _run.log) — REVoi 4관문(✅통과).
- `/docs`: SPEC.md(reform 단일출처) · GUIDE1/2/3(memory 지침 3개).
- `/data`: `back2tv_rev_winners.json`(config) · `BTCUSDT_funding_history_8h.csv`(실펀딩) · `DATA_MANIFEST.txt`(Merged_Data 위치·해시).

## 3. 재현 방법 (PYTHONIOENCODING=utf-8 선설정)
검증된 research 엔진(blend_opt.rev_side, bt_full.gen_trades 등)과 1m 데이터(Merged_Data.csv)는 원위치(03_IDEA4Bot/260623_07_RfRautoAlphaUp, 08_BTC_Data/derived)에 있어야 함(DATA_MANIFEST 참조). 그 환경에서:
```
set PYTHONIOENCODING=utf-8
python 260625_01_RautoSysReform2_OrchestratorAnchorTest.py   # 기대: +1851.6% / MDD-24.6% / 차이 0.000%p PASS
python 260625_01_RautoSysReform2_BotTrustGates_REVoi.py      # 기대: 4관문 ✅ (환각0·현실+1483.3%)
```

## 4. 검증된 사실 (이 세션)
- 매 단계 앵커 +1851.6%/MDD-24.6% **0.000%p** 재현. 검증엔진 7개 SHA256 **무수정**(호출만).
- REVoi 4관문: ①앵커 ✅재현 ②환각0(진입2796/2796·청산932/932·미도달0) ③CPCV p25+41.7%·음수폴드0 ④현실(스프1bp) +1483.3%.

## 5. 경계·다음 (정직)
- 이건 **'신뢰의 구조적 레일'**. 환각0(verify)≠미래보장. ②피처 룩어헤드는 봇별 1회, ③held-out 재최적은 봇별 심화 남음.
- 다음 = TS·SW를 같은 봇 계약으로 끼워 멀티봇 검증(TS +11397%는 ②환각에 걸림 = 레일 작동 증거). 슬롯·챔피언선발(CPCV 게이트). 라이브 브리지.
- 단일출처 = CLAUDE.md §25 · SPEC.md §4 ④.
