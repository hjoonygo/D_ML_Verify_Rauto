# 04_공용엔진코드/data_adapters/  — 예약 슬롯 (현재 engines/ 통합 운영)

★캡틴 지시6(2026-06-29) 답 = 이 README가 용도·현황 단일출처. 방치 아님.

## 용도 (Rauto 5모듈 구조 §24)
**[0]중앙 1m DataHub + 라이브/리플레이 데이터 어댑터** 분리용 예약 슬롯.

## ★현재 운영 = engines/ 통합
- 중앙 1m 단일출처 = `engines/rauto_datahub.py`
- 라이브/Dauto 교신 = `engines/rauto_datafeed.py`(바이낸스 공개REST·Dauto CSV·oi_zscore 브리지)
- 1m·펀딩 로더 = `03_IDEA4Bot/260623_07_RfRautoAlphaUp/fib_replay_1m.py` (load_1m·load_funding)
- 경로 자동탐색 = `engines/path_finder.py`(self-locating)

## 향후
실거래소 Live 어댑터(testnet→실주문)나 멀티심볼 추가 시 여기로 분리(+ path 등록). 그 전엔 engines/ 단일 운영.
