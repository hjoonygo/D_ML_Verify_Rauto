[07Prj_Ch2_Stg4_TrendStack_LevExpScan] 레버×EXP 2D 스캔 — Ch1 정확공식 통일 + 회복죽임 정밀분해
──────────────────────────────────────────────────────────
■ 무엇: figE/figG/figH의 들쭉날쭉한 복리 숫자를 'Ch1 sim_levsweep의 정확한 하드스탑 공식'으로
   통일해 하나의 신뢰할 표로 만든다. 레버 11~30 각각에서 손실한도 7.5%+MDD-20%를 동시에 만족하는
   최대 EXP를 이분탐색하고, 회복거래 잘림을 정밀 분해한다.
■ 통일 공식(Ch1 원본과 동일):
   - 발동: MAE(1분봉) <= -hsd,  hsd = 1/L - MMR(cap별 tier) - 5bp
   - 하드스탑 손익 = -EXP×mult×(hsd + COST_RT0.0014 + fund)   ★figH에서 누락했던 비용·펀딩 포함
   - 회복죽임 판정: 정상손익 > 하드스탑손익  →  하드스탑이 손실 키움(부분회복 R-1.2% 포함)
■ OPVnN 반대0.6 유지(OPV0.25 N1.0). 엔진(7f9192e3) 무수정.

■ PC 실행:
  1) stg6_levsweep_ledger.csv(R/mae/fund/side/entry_price)와 Merged_Data_with_Regime_Features.csv(1분봉)를
     D:\ML\Verify 또는 하위에 두면 자동탐색.
  2) 이 폴더를 D:\ML\Verify 아래 두고 run.bat 실행.
■ 산출:
  - *_scan.csv : 레버별 최적EXP·복리·MDD·PF·회복죽임(rec_n)·진짜손실(dir_n)·회복보존가상복리·격차(recsave_gap)
  - *_best.csv : 최대복리 레버 + CPCV 하위25%(견고성)
■ 제약 미적용(출력만): 표를 보고 레버 상한·PF 하한·회복죽임 한도를 사장님이 결정.
■ 사전검증: 컨테이너 합성 14/0 PASS (합성은 손실데이터라 발동0; 실데이터에서 회복죽임 분해 작동).
