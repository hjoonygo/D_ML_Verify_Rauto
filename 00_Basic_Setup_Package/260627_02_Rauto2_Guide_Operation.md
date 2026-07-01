# Guide — Rauto2 (RfRauto) 운영·개발 가이드 v1
2026-06-28 · RfRauto = **Reform Real Auto bot** 약자. Rauto2 = 옛 b32 개조 + 5모듈 코어 = 실시간 백테/라이브 멀티봇 운영 시스템.
단일출처 보강: `260625_01_Rauto_Sys_Reform_SPEC.md` §4 · CLAUDE.md §24/§25/§19 · KeyNote 260627_02_Rauto2

## 1. 구조 (어디에 뭐가 있나)
| 부품 | 위치 | 역할 |
|---|---|---|
| server | `07_Rauto_System/260626_02_Rauto2_Sys/260626_02_Rauto2_Sys_server.py` (포트 8788) | BOT_REGISTRY·REG_MONTHLY·챔피언선발·HTTP API(/bots·/state.json·/load) |
| dashboard | 같은 폴더 `..._dashboard.html` | 차트·슬롯·봇리스트·매매내역·챔피언선정Sys (★server가 매 요청 `open(DASH)`로 서빙) |
| rauto_live | `04_공용엔진코드/engines/rauto_live.py` | Rauto2Live(중앙 1m·슬롯·`reveal` trd)·BotSlot·per_trade_pnl |
| REVoi_bot | `04_공용엔진코드/engines/REVoi_bot.py` | 봇 알파 `make_trades` (→ bt_full 거래생성, bt_report 비용) |
| 운영처 | PC :8788(dev·serve `ai-ml`) / **AWS `C:\Rauto2`(본방·`Rauto2Server` SYSTEM 태스크 24/7·serve `ec2amaz`)** | |

## 2. ★봇 추가법 (이름표 의무 §19)
`BOT_REGISTRY`에 한 줄 추가하면 끝 — 3가지를 반드시 함께:
1. **레지스트리 항목**: `{name, key, lev, sz, [tp_frac, early_tp_pct, early_frac, regime_factor, gate, dd_cut], mdd, desc}`
   - ★알파파라미터(tp_frac·early_tp_pct·early_frac·regime_factor·gate)는 `_BOTKEYS`에 있어야 REVoiBot로 전달됨.
2. **REG_MONTHLY[name]** = `{up, down, range}` (레짐별 월수익 = 예상수익 이름표). 산출 = 7일추세 레짐 × sized 거래 복리, ★검증=기존봇 대조(Stg11 방식).
3. **desc**(한줄소개) · **mdd**(검증 MDD, M20 자격 = mdd≥−22 → 챔피언 풀).
→ Bot 로딩 리스트에 **레짐별수익·MDD·소개 이름표 자동** 표시.

## 3. UI
- ★**폰 GUI 전체 설명·색범례·조작·변경이력 = 단일출처 `Rauto2_Phone_GUI_Guide.md`**(살아있는 문서, GUI 바뀌면 거기 누적). 아래는 요약만.
- **⬇ Bot 로딩**: 챔피언시스템 8슬롯(1번=챔피언 샛노랑·트로피) + 하단 미로딩 대기열. 최대8·최신로딩순·이머전시시 편집. (260629 재설계)
- **슬롯 리스트**: 챔피언 1번줄 포함 · 현 레짐 예상수익(녹)/실현수익(`+X% N일`)·순위정렬. (260629)
- **차트 색**: 롱/이익=쨍한청색 `#22a7ff` · 숏/손실=짙은핑크 `#ff2d78` · 캔들 초록/빨강. 세로85%·4H=10일(CHN60). 리플레이 버튼 제거. (260629)
- **📋 매매내역**(차트 탭): 선택 슬롯 전체 거래 표 — `진입~청산 / 방향@가·수량 / 레버 / 수익−비용=실수익`. 실거래=USDT·가상=%. 드래그 스크롤(상한 2000).
- **챔피언선정Sys**(diagbox): 현 레짐 · 기대수익 1위 · 현 레짐 수익 1위 (M20 풀만).

## 4. 배포 (PC → AWS)
- **PC**: 파일 수정 → `run_live.bat`로 서버 재시작. ★dashboard만 바꿨으면 **재시작 불요**(새로고침).
- **AWS**(원격 winrm·SMB 차단 = Claude 직접 불가): ⒜PC에서 변경분 zip + `python -m http.server 9000` ⒝AWS RDP PowerShell **1복붙**(pull + 파일명 기준 `C:\Rauto2` 덮어 + `schtasks /End,/Run /TN Rauto2Server`). [상세 = KeyNote §5]
- **폰**: AWS `https://ec2amaz-cor6gpg.tail305e55.ts.net`(본방·24/7). PC `ai-ml`은 dev(절전死 주의).
- ★`Rauto2Server`는 SYSTEM 태스크라 RDP 창/로그아웃과 독립 24/7 가동.

## 5. 운영 모드 (env)
- `RAUTO2_MODE` = live(워밍업+forward) / replay. `RAUTO2_WARMUP_DAYS` · `RAUTO2_REBUILD_SEC`(재계산 주기).
- `RAUTO2_CHAMP_MODE` = recent(최근2주·기본) / regime(현 레짐 과거최고) / maxret. 챔피언 자동선발 = M20 자격풀에서.
- 실거래 OFF(페이퍼) 기본 · Emergency 버튼 · 이메일/텔레그램(rauto_secrets).

## 6. ★주의·교훈 (안 지키면 사고)
- **이름표 = 36mo in-sample 상한**(미시레짐 한계). 실거래 기대는 OOS·held-out 기준으로 (예: COMBO 하락 42.6%는 천장, 최근 OOS는 PF 0.8).
- **AWS winrm/SMB 차단** = 원격 직접 불가. pull 경로만.
- **dashboard 재시작 불요**(파일 서빙). server/rauto_live 변경 시에만 재시작.
- **self.pnl = % 단위**(R_net×exp×100) — trd 확장·복리 계산 시 /100 주의.
- 봇 알파파라미터 추가 시 `_BOTKEYS` 누락 = 봇에 전달 안 됨(조용히 무시되니 주의).
