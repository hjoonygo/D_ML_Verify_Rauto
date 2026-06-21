[07Prj_Ch1_stg2_SizingGridCompare]  2026-06-06

stg1 격리튕김 모듈을 06Prj_Ch7_stg4의 best 원장에 4모드 적용 + 동치검증.

★변경: liq_distance -0.0719 → -0.0724 (K33 BTC2025 변동성 + Binance Tier1 MMR0.4%+taker0.05%).
★사장님 원래 의도 "BTC 일변동 ±7% 노이즈 견딤" 정확 반영.

사용법:
  1) zip을 D:\ML\Verify\07Prj_Ch1_stg2_SizingGridCompare\ 에 풉니다.
  2) D:\ML\Verify\06Prj_Ch7_stg4_GreedShortGuard\code\ 안에
     stg4_best_ledger.csv 와 .stg4_metric 이 있어야 합니다 (stg4 굴린 결과).
     없으면 stg4 먼저 굴리고 오십시오.
  3) run.bat 더블클릭.
  4) 결과 csv 5종 + D:\ML\Verify\00WorkHstr\(분단위).txt 다음 채팅에 업로드.

파일:
  isolated_bounce_simulator.py - 모듈 (liq_distance=-0.0724)
  test_*.py - 4모드 적용
  check_*.py - 8시나리오 오염검사
  run.bat

산출:
  stg2_summary_4modes.csv     - 4모드 최종잔고/MDD/연도별 메트릭
  stg2_balance_curve_4modes.csv - 4모드 잔고 곡선 (거래순)
  stg2_by_year_4modes.csv     - 4모드 × 4연도 R합·복리
  stg2_sanity.csv             - 합리성 검증 5건
  summary.csv                 - 한눈 요약
  .stg2_metric                - check가 읽을 메타

★ S3 동치검증: stg2 M0 == stg4 best_end. 일치하면 모듈 무변형 입증.
   불일치하면 모듈에 변형(버그)이 있다는 뜻 → 즉시 보고.

다음: stg3 CrashStressTest — 2025-10-11 폭락 + intrabar 청산검증.
