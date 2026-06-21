[07Prj_Ch1_stg1_IsoBounceModuleBuild]  2026-06-05

격리튕김공식 모듈 빌드. 4모드(M0/M1/M2/M3) 사전정의.

수식:
  R <= -0.0719  ->  ΔW = -0.075   (격리청산 = 테일컷)
  R >  -0.0719  ->  ΔW = R*0.975  (평시 EXPOSURE)

사용법:
  1) zip을 D:\ML\Verify\07Prj_Ch1_stg1_IsoBounceModuleBuild\ 에 풉니다.
  2) run.bat 더블클릭.
  3) 결과 csv 5종 + 분석txt (D:\ML\Verify\00WorkHstr\) 다음 채팅에 업로드.

파일:
  isolated_bounce_simulator.py - 모듈 본체
  test_*.py - 합성 격자 + 경계검증
  check_*.py - 8시나리오 오염검사
  run.bat - test → check 순차 실행

다음: stg2 SizingGridCompare (stg1 원장 292거래에 4모드 적용 후 절대잔고/MDD/CPCV 비교)
