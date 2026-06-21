[07Prj_Ch2_Stg2_TrendStack_OPVnNSweep] 추세봇 POC평균회귀 진입수량 조절 최적화
─────────────────────────────────────────────────────────
■ 무엇: 추세봇(TrendStack) 거래에 dev=(진입가-POC)/ATR 기반 수량조절을 사후 적용·ML 최적화.
   |dev|>=OPV일 때 진입방향이 POC 회귀방향과 동일=N배(늘림)/반대=n배(줄임), 그외 1배.
   수량은 R 스케일(청산·MAE 불변) → 추세봇 엔진(7f9192e3) 무수정, import만.
■ 최적화: OPV(16)x n(17)x N(21)=5712조합 -> 각 조합 노출(EXP) 동반최적화 MDD=-20% 고정 -> 총수익 최대 -> CPCV-p25.

■ PC 실행법:
  1) 아래 2개 파일이 D:\ML\Verify 또는 그 하위 어디에든 있으면 자동으로 찾습니다:
       - stg6_levsweep_ledger.csv             (추세봇 Ch1 거래원장)
       - Merged_Data_with_Regime_Features.csv (1분봉 OHLCV+volume)
     ※ 파일명이 위와 다르면 같게 바꾸거나, 채팅으로 실제 파일명을 알려주세요.
  2) 이 폴더(07Prj_Ch2_Stg2_TrendStack_OPVnNSweep)를 D:\ML\Verify 아래에 둡니다.
  3) run.bat 더블클릭 (또는 콘솔에서  run.bat  / 그냥 run 가능).

■ 데이터를 못 찾으면: test가 "DATA 트리 내 csv 목록"을 출력합니다. 그 목록을 그대로 채팅에 붙여주세요.

■ 산출물(하위폴더): *_devledger.csv / *_sweep.csv / *_best.csv / 00WorkHstr\analysis_*.txt
■ 사전검증: 컨테이너 합성검증 18/0 PASS. ※장세·매매성향 변화 시 OPV·n·N 재최적화 필요.
