# 04_공용엔진코드/backtest_harness/  — 예약 슬롯 (현재 engines/ + research 통합 운영)

★캡틴 지시6(2026-06-29) 답 = 이 README가 용도·현황 단일출처. 방치 아님.

## 용도 (Rauto 5모듈 구조 §24)
**[4]분석/백테 하니스** 분리용 예약 슬롯.

## ★현재 운영
백테·검증 하니스는 두 곳에 있습니다:
- 검증 거래생성 = `03_IDEA4Bot/260623_07_RfRautoAlphaUp/` (`bt_full.py`·`bt_report.py`·`back2tv_REVoi.py`·`fib_replay_1m.py`)
- 인증·이름표·비용 = `engines/veri_edge.py`(nameplate·heldout_oos·MDD 4단) · `engines/ret_guard.py`(수익률 라벨 강제)
- 봇 신뢰 4관문 = `engines/bot_trust_gates.py`

## 향후
백테 하니스를 공용엔진으로 끌어올릴 때 여기로 이동(+ path 등록). 그 전엔 위 위치 유지(검증엔진 §8 무수정 경계 주의).
