# -*- coding: utf-8 -*-
# [build_final_package.py] Rauto 프로젝트 최종 일괄 패키지 zip — b25 수정 포함, 5카테고리 전수.
#   ①실매매봇(엔진+러너+컨트롤) ②데이터가공(원천+어댑터) ③모든 테스트 ④검증 데이터가공 ⑤데이터 +문서.
import os, glob, zipfile, shutil
V = r"D:\ML\Verify"
P6 = os.path.join(V, "06Prj_Ch8_Plugin_Stg1_TS_Impatient")
P7 = os.path.join(V, "07 Rauto", "07Prj_Ch4_RunAWS_Stg17_ImpatientFork")
ML = r"D:\ML"
BASE = os.path.join(V, "00WorkHstr", "00Basic_Setup_Package")
OUT = os.path.join(BASE, "Rauto_Project_Final_Package_20260618.zip")

ENGINES = sorted(glob.glob(os.path.join(P6, "rauto3", "bots", "*.py")))
RUNNERS = [os.path.join(P6, "rauto1", "test_Rauto1.py"), os.path.join(P6, "rauto2", "test_Rauto2.py"),
           os.path.join(P6, "rauto3", "test_dual_runner.py")]
CONTROL = sorted(glob.glob(os.path.join(P6, "control_ui", "*")))
DATAPROC = [os.path.join(ML, "compute_oi_derived_features.py"), os.path.join(ML, "merge_monthly_csv_V8X.py"),
            os.path.join(ML, "merge_oi_metrics_36mo.py")] + \
           [os.path.join(P6, "rauto3", "bots", a) for a in
            ("oi_zscore_adapter.py", "atr_ratio_adapter.py", "regime_feature_extractor.py", "dauto_loader.py")]
ALL7 = sorted(glob.glob(os.path.join(P7, "*.py")))
TESTPRE = ("test_", "check_", "diag_", "validate_", "verify_", "graph_")
TESTS = [f for f in ALL7 if os.path.basename(f).startswith(TESTPRE)]
VERIF = [f for f in ALL7 if not os.path.basename(f).startswith(TESTPRE)]
VERIF_ENG = sorted(glob.glob(os.path.join(P7, "bots", "*.py")))
DATA = [os.path.join(P7, x) for x in ("led36_king.csv", "led36_imp_pinned.csv", "comprehensive_4bot.json", "sw_patient.csv")]
DOCS = [os.path.join(V, "CLAUDE.md")] + [os.path.join(BASE, d) for d in (
    "Handover_Rauto_4bot_RealisticBacktest_20260618.docx", "Work_Order_TickSlippage_Precision_20260618.docx",
    "Work_Order_RautoLiveTransition_20260620.docx", "Handover_Rauto_LiveReadiness_20260620.docx")]

README = """Rauto 자동매매 프로젝트 — 최종 일괄 패키지 (2026-06-18)
================================================================
구성: BTC선물 듀얼봇(TrendStack 추세 + SidewayDCA 횡보), 챔피언 아키텍처.
이 zip = b25 차트수정 포함, 실매매봇·데이터가공·테스트·검증가공·데이터 전수.

[폴더]
01_LiveBots_매매봇/
   engines/   = 검증엔진(무수정 §8): trendstack/sideway 신호엔진·페이퍼엔진·contract 등 15개. 실제 매매 두뇌.
   runners/   = 슬롯 러너(★b25 시각보정 반영): test_Rauto1(R1 성급)·test_Rauto2(R2 성급왕 챔피언)·test_dual_runner(R3/R4 듀얼).
   control/   = 폰 제어앱: control_server(HTTP·git auto-pull)·control_dashboard.html(b25)·sw.js(v25)·manifest·icons.
02_DataProcessing_데이터가공/  = 원천 데이터 가공: OI파생 features·월별 merge·OI지표 merge → Merged_Data.csv 생성. + 라이브 어댑터(oi_z/atr_ratio/regime/dauto).
03_Tests_테스트/   = 테스트·진단·검증·그래프 코드(test_/check_/diag_/validate_/verify_/graph_).
04_Verification_검증가공/  = 백테·검증 데이터가공 코드(bt36_*·comprehensive_4bot·measure_slippage·tick_*·realistic_*·r4_*·worst_trade·liq_precise 등) + engines(실행용).
05_Data_데이터/   = 검증 산출 데이터(led36_king/imp_pinned 원장·comprehensive_4bot.json·sw_patient). + DATA_NOTE(Merged_Data 455MB 위치·생성법).
06_Docs_문서/   = CLAUDE.md(규칙 단일출처·§15 백테5관문)·핸드오버·Work Order.

[★확정 4봇 36개월 현실백테 (검증엔진·핀고정 on_bar·5bp, §15)]
  R1 성급    +5,932% / MDD-20.0% / 승률34 / PF1.72 / 손익비3.38 ($10k)
  R2 성급왕  +11,397% / MDD-17.3% / 승률34 / PF1.90 / 손익비3.69 ($10k, ★챔피언)
  R3 듀얼k1.1 +8,850% / MDD-18.0% / 승률38 / PF1.94 / 손익비3.14 ($20k)
  R4 듀얼k1.4 +30,156% / MDD-23.4% / 승률38 / PF1.94 / 손익비3.14 ($20k, MDD-20% 위반)
  전봇 매년양수·롱숏 양쪽수익. 미반영(다음): 격렬손절 봇계측 틱-실체결(Work Order).

[★b25 차트수정 (이 패키지에 반영)]
  진입십자(open_et)·듀얼 닫힌마커(trd)를 7H봉 라벨 → 실제 체결분(_fillms)으로 보정 → 15m/1H/4H 전부 캔들 정렬.
  듀얼 entry 표시 추가, 15m x축 hh:mm. 검증: 3봇 예외0·진입가가 캔들[저~고] 포함.

[실행 메모]
  · 러너: runners/ + engines/(같은 bots 경로) + C:\\BinanceData 1m. control_server가 git pull로 C:\\Rauto*에 배포.
  · 검증스크립트: 04/ + 04/engines + Merged_Data.csv 필요.
  · 비용 2레이어: 신호엔진 COST=0.0004(거래선정), 실P&L=실행엔진 8bp(메이커진입2+테이커청산4+슬립2)+펀딩. (CLAUDE.md §7)
"""

DATANOTE = """[Merged_Data.csv — 455MB, zip 미포함]
위치: D:\\ML\\Verify\\Merged_Data.csv (1분봉 2023-05-01~2026-04-30, 157.8만행, OHLCV+oi_zscore_24h)
생성: 02_DataProcessing의 merge_monthly_csv_V8X.py(월별 1m병합) + compute_oi_derived_features.py(OI파생) + merge_oi_metrics_36mo.py(OI지표 병합).
주의: oi_zscore_24h는 REPAIRED 계보(z전체shift·mp720·±10클립) — CLAUDE.md §8 LINEAGE_WARNING 참조. 라이브 표준=Stg13 oi_zscore_adapter.
원천 1분봉: Binance Vision(과거 전체) 또는 C:\\BinanceData(라이브 수집, dauto_collector).
"""


def addtree(z, files, arc):
    n = 0
    for f in files:
        if not f or not os.path.exists(f) or os.path.isdir(f):
            continue
        if "__pycache__" in f or f.endswith(".pyc"):
            continue
        z.write(f, arc + "/" + os.path.basename(f)); n += 1
    return n


cnt = {}
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("README_MANIFEST.txt", README)
    cnt["engines"] = addtree(z, ENGINES, "01_LiveBots_매매봇/engines")
    cnt["runners"] = addtree(z, RUNNERS, "01_LiveBots_매매봇/runners")
    cnt["control"] = addtree(z, [c for c in CONTROL if not c.endswith(("state.json",))], "01_LiveBots_매매봇/control")
    cnt["dataproc"] = addtree(z, DATAPROC, "02_DataProcessing_데이터가공")
    cnt["tests"] = addtree(z, TESTS, "03_Tests_테스트")
    cnt["verif"] = addtree(z, VERIF, "04_Verification_검증가공")
    cnt["verif_eng"] = addtree(z, VERIF_ENG, "04_Verification_검증가공/engines")
    cnt["data"] = addtree(z, DATA, "05_Data_데이터")
    z.writestr("05_Data_데이터/DATA_NOTE.txt", DATANOTE)
    cnt["docs"] = addtree(z, DOCS, "06_Docs_문서")

print("ZIP:", OUT)
print("크기:", round(os.path.getsize(OUT) / 1024, 1), "KB")
for k, v in cnt.items():
    print(f"  {k}: {v}")
print("총 파일:", sum(cnt.values()) + 2, "(+README+DATA_NOTE)")
