[stg1 인수인계 — 07Prj_Ch1_stg1_IsoBounceModuleBuild]  2026-06-05

■ Output of stg1: 사장님 격리튕김공식을 모듈로 박제. 4모드(M0~M3) 사전정의. 자가검증·합성격자·경계검증 8/8 PASS.

■ 핵심 한 줄: 한 거래의 가격변동률 R을 잔고변화율 ΔW로 변환.
   R <= -0.0719  →  ΔW = -0.075     (격리청산 = 증거금 전액 손실, 테일컷)
   R >  -0.0719  →  ΔW = R * 0.975  (평시: EXPOSURE만 적용)

■ 파일
- code/isolated_bounce_simulator.py : ★격리튕김 모듈 본체 (자가검증 포함)
- code/test_07Prj_Ch1_stg1_IsoBounceModuleBuild.py : 합성 격자 + 경계검증 + 데모 적용
- code/check_07Prj_Ch1_stg1_IsoBounceModuleBuild.py : 8시나리오 오염검사
- run_07Prj_Ch1_stg1_IsoBounceModuleBuild.bat : 순차 실행

■ 실행 방법
1) 이 zip을 D:\ML\verify\07Prj_Ch1_stg1_IsoBounceModuleBuild\ 폴더에 풉니다.
2) run_07Prj_Ch1_stg1_IsoBounceModuleBuild.bat 더블클릭.
3) code/ 폴더에 CSV 5종 생성 + D:\ML\verify\00WorkHstr\(분단위).txt 생성 + INDEX 1줄 추가.
4) 결과 CSV·분석txt를 다음 채팅에 업로드해 stg2 진행.

■ 4모드 의미
- M0_base       : EXPOSURE=1.000, 테일컷 OFF — 기존 백테 암묵 가정 ($51,184 동치검증 기준선)
- M1_cross_now  : EXPOSURE=0.250, 테일컷 OFF — 사장님 현 cross 운용 (실제 운용 기준선)
- M2_iso_notail : EXPOSURE=0.975, 테일컷 OFF — EXPOSURE만 올린 가상 cross (M3와 차이=테일컷 알파)
- M3_iso_tailcut: EXPOSURE=0.975, 테일컷 ON (-7.5%) — ★사장님 격리튕김공식 본체

■ stg1 검증 통과 사항 (8/8)
- S1 필수파일 7종 비공백 / S2 모듈 자가검증 PASS / S3 경계값 8/8 정확 일치
- S4 4모드 정합성 (M0=R / M1=R*0.25 / M2=R*0.975 / M3 분기) / S5 미래참조 가드
- S6 CONFIG_DEFAULT=격리튕김 / S7 데모 청산 정합 4/10 / S8 ALPHA_PROVENANCE 메타

■ ★stg1에서 사장님이 확인할 것 (검토 필요값 — 사장님 PC에서만 가능)
- liq_distance=-0.0719: Binance BTC/USDT Tier1 MMR 0.5% 가정.
  실측 권장: Binance 공식 → Futures → Trading Rules → BTC/USDT Brackets 표 확인 후 정확값 박기.
- tail_cut=-0.075: 격리증거금 비율(7.5%)에 음수. 청산수수료(약 0.5%) 보수적으로 무시.
  실제는 -0.075 ~ -0.085 사이 가능 — 보수적 -0.08로 박을지 검토.

■ stg2 진행 기준점
stg1 모듈을 import해 stg1 원장(292거래, ④스택+탐욕숏가드 적용 결과)에 4모드 적용.
M0 결과가 인수인계 보고서의 $51,184와 일치하면 모듈 무변형 입증.
이후 M3가 M0/M1/M2 대비 MDD·CPCV·연속청산에서 어떻게 갈리는지 측정.

■ Q&A
Q. stg1에서 실데이터·엔진은 왜 안 씀?
A. 모듈 자체의 분기 동작·경계값 정확성을 합성으로 먼저 확정해야 stg2에서 신뢰 가능.
   같은 패턴: 06Prj_Ch7 fng_greed_guard.py도 자가검증 합성 통과 후 stg4에서 실데이터 적용.

Q. 청산수수료는 왜 무시?
A. 보수적 측정 우선. stg3 CrashStressTest에서 청산수수료 0.5% 추가한 민감도 분석 예정.

Q. M3가 stg2에서 M0보다 잔고 적게 나오면 어떻게?
A. 정상일 수 있음 — M3는 평시엔 M0보다 약간 작은 EXPOSURE(0.975 vs 1.0)고,
   2025-10-11 같은 폭락이 백테 기간에 없으면 M3의 테일컷이 발동 안 함.
   stg3에서 폭락 구간 전용 분석으로 M3의 진짜 가치 확인.
