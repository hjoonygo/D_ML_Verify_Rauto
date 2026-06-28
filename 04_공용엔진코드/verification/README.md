# 04_공용엔진코드/verification — 검증엔진 (재사용 마스터)
장기플랜(PIPELINE §9): 계속 업그레이드 → 최종판 Rauto(07_Rauto_System) 장착. 검증 2축 단일출처 = PIPELINE §8.
## 알파검증 (신호에 예측력 있나)
- alpha_verification_system.py : WF부호안정 → SPRT → CPCV+DSR+비용 3단
- orthogonality_analysis.py : 지표 직교성 측정(도토리 배제)
- regime_persistence_analysis.py : 레짐(추세지속 vs 회귀)
## 수익률검증 (백테 수익이 실현가능한가)
- realistic_sl_sim.py : 1m 실체결·갭반영·★낙관 트레일레벨 체결 금지
- trade_diagnostics.py : MAE/MFE·edge ratio·exit_tag(진입vs청산 문제 분리)
## 보조
- search_method_selector.py : 탐색법 자동선택(브루트 vs 캐스케이드)
