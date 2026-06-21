================================================================
 Stage1 — 인프라알파 결합 1단계 (게이트+본전스탑+분할익절+4h무제한)
 100% 자동 · zip 1개 · 2026-05-22
================================================================

[이 단계가 하는 일]
 보고서 인프라알파 사양을 살려, 36개월 하락장 SHORT에 적용:
  1) 진입게이트: SL≥32bp, TP≥48bp, RR≥1.5 (SL>100bp면 100bp 클램프). OB없으면 진입거부.
  2) 1차OB 도달 시 분할익절 + 본전스탑(최초진입가±16bp) 잔량 방어.
  3) 보유: 1차OB 도달(스텝업 활성)이면 무제한, 아니면 4H(240분) 청산.
 * 3분할 진입·뉴욕폐장은 2·3단계에서 추가. 여기선 게이트통과시 전량진입.

[그리드 4종] 본전스탑 16bp 해석 2 × 분할익절 2
  bepPrice(진입가+16bp가격) / bepLev(진입가+16bp×레버=80bp) × split 55 / 60

[★결과 전량 파일저장 — 화면 복붙 불필요]
 사용자는 실행 후 D:\ML\verify\00WorkHstr 폴더(또는 그 안 파일들)만 올리면 됩니다.

[실행법 — zip 자동정리 구조]
 1) 이 zip을 D:\ML\verify 아래에 'zip파일명과 똑같은 하위폴더'로 푼다.
    예) D:\ML\verify\Rauto_Stage1_2026-05-22\
    (데이터 Merged_Data_with_Regime_Features.csv 는 상위 D:\ML\verify 에)
 2) 그 하위폴더에서 run.bat 더블클릭 (또는 python test.py → python check.py)
 3) 약 1~2분. 결과는 자동으로:
    - 거래/요약 CSV : 하위폴더에 (S1_trades_*.csv, S1_summary.csv)
    - 분석 txt + INDEX : 상위 D:\ML\verify\00WorkHstr\ 에

[check.py — 8개 오염검사 (검증완료)]
 1결과존재 2잔존섞임 3파일명 4데이터(행수/기간/해시,상위폴더) 5중복 6빔/NaN 7INDEX이중 8출력경로
 - ALL PASS면 INDEX에 정식 1줄 기록. 하나라도 FAIL이면 [FAIL 보류] 표식만(이력 오염 방지).
 - 모든 판정은 ..\00WorkHstr\(시각).txt 에 저장됨.

[회신] D:\ML\verify\00WorkHstr 폴더를 zip 1개로 업로드 (txt + INDEX + 필요시 S1_*.csv)

[파일 목록]
 test.py       Stage1 백테스트 (게이트+본전스탑+분할익절+보유)
 check.py            8오염검사 + 분석txt + INDEX (출력=상위 00WorkHstr)
 run.bat             test.py → check.py
 ob_fast.py          고속 OB(pivot 1회계산, ob_provider와 동일정의)
 ob_provider_v2.py   보고서 원본 OB(참조/교차검증용)
 README_Stage1.txt   이 파일
================================================================
