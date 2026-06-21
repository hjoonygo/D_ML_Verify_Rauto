[stg4 탐욕숏가드 실행 결과 6종 — 07Prj stg2 작업자용]  2026-06-02
원작성자(reframeWork) 제공. 07Prj 작업자가 stg4_best_ledger.csv를 못 찾던 문제 해결용.

■ 이 파일들은 무엇인가
- 사장님 PC에서 실제 실행된 06Prj_Ch7_stg4(탐욕숏가드) 결과.
- ★사장님 PC 실행 증거: stg4_coverage.csv 의 regime_source=label_smc_8
  (합성 사전실행이면 regime_classifier 폴백됨. label_smc_8 = 진짜 157만행 데이터로 실행됨)
- 챔피언 케이스 greed55_smult0 잔고 = $56,017 (인수인계 docx와 일치, 검증됨)

■ 무결성 (sha256 앞12자리)
  stg4_best_ledger.csv    274거래  58cf8e6e3b7c
  stg4_greed_grid.csv     10케이스 1deb4e95069c
  stg4_by_month.csv       36개월   208c76390038
  stg4_by_regime.csv      4장세    6425d78dd804
  stg4_by_year_side.csv   연도롱숏 2792dea6cde4
  stg4_coverage.csv       메타     0cce9fd7c428

■ 사용법
- 이 6개를 stg2 코드의 find_file이 보는 폴더(D:\ML\verify 또는 stg2 code 폴더)에 복사.
- stg4를 다시 굴릴 필요 없음. 이미 결과가 여기 있음.

■ ★중요 — M0 동치 기준값 해석 주의
- $56,017은 "자본전액 1배" 사이징 가정의 결과 (백테 코드 cap*=(1+R), 레버리지 안 곱함).
- 사장님 실제 운용(5배×5%=실효25%)으로 환산하면 같은 원장이 $15,613(+56%).
- 격리튕김 측정 시: "$56,017"이 아니라 "어떤 EXPOSURE 기준값인지" 명시할 것.
  → M0 동치는 EXPOSURE=1.0 기준으로 $56,017 일치를 확인하면 됨.

■ greed_grid 핵심 (참고)
- 기준선(④스택 단독): $51,184, MDD -23.57%, CPCV 1.570
- 챔피언(greed55_smult0): $56,017, MDD -15.82%, CPCV 1.758, Calmar 1747->2909
- 9/9 케이스 전부 '잔고↑ & MDD↓ & CPCV↑ & 전연도+' 동시충족
