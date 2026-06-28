# CLAUDE.md — SidewayDCA (D:\ML\verify\SidewayDCA)
# 상위 규칙은 ..\CLAUDE.md 가 우선 척추. 여기엔 이 봇 특유만.

## 봇 한 줄
횡보(레인지) 헤지그리드 · 8시간 타임프레임 · 평균회귀 · 가끔·짧게 작동(86거래/35개월).

## 확정 알파 (변경 = CPCV 재검증 + 캡틴 승인)
레버15 · 증거금 26.67% · EXP4.0 · dist_max1.5 · nDCA1 · sl_mult1.8 · SHORT_SIZE0.5
· POC_LB60 · BINS50 · 손실컷 없음(best) → PF 2.653 / +148.76% / MDD -13.61% / CPCV-p25 +70.9%
엔진: SidewayDCA_Stg7_engine.py (SHA256 dfdfac43… · 수정 절대금지 · 래퍼만).
원장: 07Prj_Ch2_SidewayDCARebuild_Stg1_ExpCutLiqSweep_ledger.csv (86거래).

## 이 봇의 함정 (TIL)
- 최대 위험 = 레인지 돌파(추세 전환) 청산 — 자기자본 스톱아웃(피크 대비 플로팅 -10%
  전체청산)이 1순위 안전장치. 끄지 말 것. 마틴게일 금지.
- OI 부호가 TrendStack과 정반대: z<-1 우대(승률75%) / z>+1 위험(승률17%). 이식 금지.
- OPVnN 역이식은 측정 기각(ADR11): 이 봇은 이미 POC 네이티브 + 발동부호 반대로 무효.
- 정밀필터: regime_shift AND atr_ratio<0.9 만 콕 집어 차단(전체차단은 알짜까지 죽임).
- 엔진은 배치 백테스트 — 라이브는 신호로직 1:1 스트리밍 추출(TrendStack Stg9 패턴) 필요.
- ★인트라바 청산 봇의 선지식 함정(2026-06-11, Ch4 Stg7~8): 박제엔진은 봉 j의 1분 경로청산에
  '봉 j가 끝나야 아는 값' 2개(자기봉 ATR 기여 1/14 — 513·532줄, 자기봉 포함 피벗확정창 — 327~338줄)를
  쓴다. 봉마감 청산 봇(TrendStack)엔 없는 문제. 따라서 라이브 1:1 100% 재현은 원리상 불가 →
  인과(causal) 봇으로 추출 후 알파 재인증으로 해소: 인과 84건 ret 170.2%/MDD -15.6%/PF 2.36/
  CPCV-p25 +81.3% (박제 86건 148.8/-13.61/2.653/+70.9 대비 게이트 PASS, 채택은 캡틴 결정).
- 듀얼 동시보유 시 합산노출 5.56x 스파이크 → 노출배분 k=0.8 (ADR: Ch4 Stg6).
- ★oi_zscore_24h 계보 분기(2026-06-12 Stg13): 라이브 표준 = REPAIRED 계보(z 전체 1봉 지연·
  min_periods 720·±10클립, oi_zscore_adapter.py). 원본 v2 스크립트 수식과 다름 — D:\ML\
  LINEAGE_WARNING_oi_zscore.txt 필독. 무덤필터가 보던 값이 바로 이 계보다.
