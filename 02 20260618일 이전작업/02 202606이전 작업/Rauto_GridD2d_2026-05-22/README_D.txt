================================================================
 단계 D - 분할익절 비율 최적화 (GridD_v2c · trigger 자동복원판)
 100% 자동 실행 · zip 1개 · 2026-05-22
================================================================

[파라미터 처리 - 중요]
 원본 2.864 거래기록에서 직접 추출한 실제값을 씁니다:
   leverage=5, 하드손절=3.0%, 피보락인(fib_ext)=0.65
 * Pauto_Best_Params.json 은 '쓰지 않습니다'. 그 파일(lev8/손절6.0/락인0.5)은
   2.864 거래(lev5/3.0/0.65)와 불일치하고, 거래보다 1시간 뒤 저장된 다른 최적화라
   로드하면 재현이 깨집니다. (폴더에 있어도 무시하고 경고만 출력)
 * 기록에 안 찍힌 fib_trigger_roe 1개만, 실행 첫머리에서 '원본 거래와 거래별 차이가
   최소'가 되도록 후보 {15~20}를 돌려 자동 복원합니다(시스템 식별, 과최적화 아님).

[실행법 - 2단계]
 1) 이 zip을 하위 폴더에 푼다.  예) D:\ML\Verify\Rauto_GridD2c_2026-05-22\
    (Merged_Data.csv 는 상위 D:\ML\Verify 에)
 2) python run_grid_D_v2.py     (pandas, numpy 필요. scipy 있으면 DSR/PBO 더 정확)
 * 소요: 약 40~60초 (trigger 보정 7회 + 그리드 16회(8비율×혁신1 2)).

[가장 먼저 볼 것 - 재현 자가검증]
   [보정] fib_trigger_roe 복원 ... -> 복원된 fib_trigger_roe = ___
   [재현 자가검증] config 50:50 / 혁신1 ON
     진입 ___건 (목표 125)   PF=___ (목표≈2.864)   순익=___$ (목표≈+15,712$)
     [거래별 대조] 매칭 ___/125 | 순익 거의일치 ___ | ...
 -> 진입 125 & PF≈2.86 & 거의일치 다수면 충실 재현 = 다른 config 신뢰 가능.
 -> 여전히 멀면, 자가검증 줄 전체를 회신 주세요(다른 누락 파라미터 추적).

[결과물 - 회신]
 GridD_summary.csv + GridD_trades_*.csv(8개) 를 zip 1개로 업로드.

[해석 가이드]
 최고 비율은 PF만 보지 말 것. DSR 높고(>0.95) PBO 낮은(<0.5) 비율이 진짜.
 혁신1 ON/OFF 비교로 눌림목 재설정 효과 확인.

[지표 출처]
 DSR = Deflated Sharpe Ratio (Bailey & Lopez de Prado 2014).
 PBO = Combinatorially Symmetric CV proxy (8config 경량참고, 본격은 단계 C).

[파일 목록]
 run_grid_D_v2.py              오케스트레이터(trigger 자동복원+8회+자가대조)
 Backtest_Engine_GridD_v2.py   독립거래 고속 엔진 (정산식 원본 verbatim)
 Exec_Dynamic_TS_GridD_v1.py   검증 청산엔진 + 혁신1 on/off 토글
 entries_fixed.csv             고정진입 125건 (+원본 거래별순익, 대조용)
 README_D.txt                  이 파일
================================================================
