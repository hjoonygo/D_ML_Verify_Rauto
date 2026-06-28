# KeyNote — 260627_02 Rauto2 적용 (COMBO 로딩 · 봇 이름표 · 매매내역)
세션 260627_02_OBOICharacter 후반 · 2026-06-27~28
대상 = Rauto2 (RfRauto = **Reform Real Auto bot** 약자) UI/시스템
단일출처 보강: CLAUDE.md §19(이름표 의무) · server/dashboard/rauto_live · STATE · INDEX · LogicCatalog

## 1. 작업 요약 (캡틴 지시 3)
① COMBO 봇을 Rauto2 챔피언 시스템에 로딩 · ② Bot 로딩 리스트에 예상수익 이름표 · ③ 차트 '실시장'→'매매내역' 전체 표.

## 2. COMBO 봇 로딩 (server.py)
- `BOT_REGISTRY` 맨 위 추가: **COMBO청산(조기익절1%)** — lev5/sz75 · tp_frac0.7 · early_tp_pct0.01 · early_frac1.0 · mdd −19.8.
- `_BOTKEYS`에 **early_tp_pct·early_frac 추가**(REVoiBot 주입). ★없으면 early_tp가 봇에 전달 안 됨.
- `REG_MONTHLY["COMBO청산(조기익절1%)"]` = {up 30.7, down 42.6, range 29.5} (Stg11 산출·검증).
- M20 자격(mdd≥−22) → 챔피언 자동선발 풀 포함. 결과 = 9봇·COMBO 1번.

## 3. 봇 이름표 (캡틴 ② · §19 의무)
- `/bots` 응답 + dashboard `openLoad` 모달: 봇마다 **레짐별 월수익(상/하/횡) · MDD · 한줄소개(desc)**.
- 산출 = reg_monthly(7일추세 레짐 × sized 거래 복리, 격리마진). 검증 = 기존봇 대조(M20챔피언 ±1%p, Stg11).
- ★**한계(캡틴 지적)**: 이름표 = **36mo in-sample 천장**. COMBO 하락 +42.6%(2022~23 급락 받아치기 대박)인데 **최근 5/12~6/28 PF 0.8·+19%** = OOS 괴리. → "하락"을 한 덩어리로 보는 7일추세 3분류의 한계 → **미시레짐 세분 필요**(§8 Work Order).

## 4. 매매내역 표 (캡틴 ③)
- `rauto_live.reveal` trd 확장: **qty(명목/진입가) · lev · net_usdt · net_pct · gross_pct · cost_pct**.
- ★**버그수정**: `self.pnl`은 **% 단위**(R_net×exp×100). 소수로 오해 → ×100(360%)·`_bal*=(1+p)` 폭주(qty/net_usdt=inf). **/100 보정**으로 정상(net 3.6%·gross 3.75%·cost 0.15%).
- dashboard: '실시장' → **'📋 매매내역'** 탭. 시간 **MMDDHHmm~DDHHmm**. **전체 드래그 스크롤**(상한 2000·sticky 헤더). 실거래=USDT·가상=수익률%.
- ★**Rauto 부하 0**: state.trd는 이미 전체 전송 중. 표시만 12→전체로(서버 데이터 동일).

## 5. AWS 배포 (원격 막힘 → 1복붙 경로)
- ★AWS **winrm·SMB C$ 둘 다 차단** = Claude 원격 직접 제어 불가(확인됨).
- 검증된 경로: PC 변경분 zip → PC `python -m http.server 9000`(100.89.47.2) → **AWS RDP PowerShell 1복붙**(iwr pull + **파일명 기준 C:\Rauto2 덮어** + `schtasks Rauto2Server` 재시작).
- ★AWS `C:\Rauto2` = PC 폴더 구조 **미러**(07_Rauto_System·03_IDEA4Bot·04_공용엔진코드) → 파일명 매칭 덮어쓰기 정확 작동.
- **dashboard만 변경 시 재시작 불요**(server가 매 요청 `open(DASH)` 서빙) → 폰 새로고침으로 반영.

## 6. 검증 (무손상·작동 — 증거)
- BASE(tp0,early0) lev3 = **+1851.6% 앵커 재현**(엔진 early_tp opt-in 무해).
- COMBO ret_full **+3,229,453%**(Stg9 M20 일치)·9봇·trd 확장 정상(net_pct·qty·cost).
- PC :8788(PID 14364)·AWS(Rauto2Server) 둘 다 **새 dashboard 서빙 확인**(매매내역·tradesTable·예상수익/월 True).

## 7. 변경 파일 (6)
`server.py` · `dashboard.html` · `rauto_live.py` · `REVoi_bot.py`(early_tp) · `bt_full.py`(early_tp·gross_R) · `bt_report.py`(gross_R).

## 8. ★다음 (Work Order — 미시레짐 세분, 선행연구 검증완료)
이름표 괴리(하락 42.6% vs 최근 PF0.8)의 근본 = 7일추세 3분류가 거침. 선행연구(HMM·변동성레짐·크립토 점프 58%·choppy=step-aside)가 캡틴 통찰 "미시특성 세분(휩소율·짧은 급변·변동성 죽은 횡보)" 강력 지지. **REVoi=평균회귀형 → 레짐 의존 극심(급락 강·휩소 약).** → 미시레짐 분류 → REVoi 레짐적응 사이징/전환. ★held-out·CPCV 표준6 필수(WHIP_soft 과적합 전례). 등록 = WORK_ORDERS_REGISTER.
