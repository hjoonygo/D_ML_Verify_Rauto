# CLAUDE.md — TrendStack (D:\ML\verify\TrendStack)
# 상위 규칙은 ..\CLAUDE.md 가 우선 척추. 여기엔 이 봇 특유만.

## 봇 한 줄
추세추종 · 7시간 타임프레임 · BotPlugin(Stg10 자립형) 완성 · 라이브 페이퍼 배선 PASS.

## 확정 알파 (변경 = CPCV 재검증 + 캡틴 승인)
레버22 · EXP1.559 · OPV0.25 · NMULT0.6 · N_BOOST1.0 · 업트렌드숏컷 ON
→ +827% / MDD -16.1% / Calmar 51.3. 원장: stg6_levsweep_ledger.csv(264거래·14bp).

## 이 봇의 함정 (TIL)
- 업트렌드 숏은 구조적 적자(PF 0.07) → 숏컷이 막는다. 끄지 말 것.
- OPVnN: dev=(진입가-POC)/ATR, |dev|>=OPV일 때 반대방향(역회귀)=NMULT배 축소,
  동일방향=N_BOOST배. N_BOOST 상향은 CPCV 기각됨(2026·dead_range를 키움) — 1.0 고정.
- OI [0,1) 구간 알파는 SidewayDCA와 부호 반대 — 이식 금지(TIL 2-4).
- MAE는 '보유 구간' 1분 극값으로만 (7h봉 전체 고저로 계산하면 가짜 강제청산 발생).
- 2025는 추세 열화의 해(전 추세장세 PF 붕괴) — 사이징 파라미터로 못 고침(3회 검증됨).

## 이중 리샘플링
1분봉 → 7h 버킷(시그널+POC) + 4h 버킷(feat_struct). label 계열 실시간 사용 금지.
