# -*- coding: utf-8 -*-
# 패키지 매니페스트 + Hstr_Ver_Up zip + 메인 zip 생성.
import os, zipfile, datetime

PKG = r"D:\ML\Verify\06Prj_Ch8_Plugin_Stg1_TS_Impatient"
HS = os.path.join(PKG, "hstr_data_extraction")
VERIFY = r"D:\ML\Verify"
BASIC = r"D:\ML\Verify\00WorkHstr\00Basic_Setup_Package"

# ── 1) 대용량 데이터 매니페스트 ──
manifest = """DATA_MANIFEST — Hstr_Ver_Up_TrendStack 데이터추출 패키지
작성 2026-06-15 · 06Prj_Ch8

[포함된 추출 코드]
 - compute_oi_derived_features.py : OI 파생피처(oi_zscore_24h 등) 생성 원본(v2)
 - oi_zscore_adapter.py           : Stg13 라이브 표준 oi_zscore 어댑터(REPAIRED 계보)
 - atr_ratio_adapter.py           : Stg15 atr_ratio 어댑터(워밍업 N=137 4H봉)
 - regime_feature_extractor.py    : feat_struct/atr_ratio 생성원(SMC 4장세 라벨)
 - dauto_loader.py                : Dauto 1m 스트림 로더
[포함된 소형 데이터]
 - stg6_levsweep_ledger.csv          : TrendStack 확정 거래원장 264건(전략 테스트 기준)
 - Merged_Data_SAMPLE_2000rows.csv   : 통합데이터 구조 샘플(첫 2000행)

[★대용량 데이터 — zip 미포함(용량). 위치·해시로 재현 보장]
 - Merged_Data.csv (약 454MB) @ D:\\ML\\Verify
     sha256 = e397a33201dd2cd7f90f377b83fd82b910fd77cf86ad933a35fcad0647d9f38c
 - Merged_Data_with_Regime_Features.csv (약 665MB) @ D:\\ML\\Verify
     sha256 = 7d8114c53d57154966871da448f86d629e4410197855773bb235a495cf6855b3
 - 원본 보관: G:\\...\\자동매매\\08 BTC거래데이터\\ (BTC by Binance=원본 / 36month BTC Data=통합)
 - 규모: 1,578,240행(1분봉) · 2023-05-01~2026-04-30(36개월) · UTC naive.

[왜 동봉하나] 이 추출코드·데이터는 실 매매봇엔 불필요하지만, 없으면 데이터 보강·수정·재현이 불가.
 라벨/피처 구분: label_smc_*=채점용(실시간 금지) / feat_*=봇입력(실시간 안전, shift 처리).
"""
open(os.path.join(HS, "DATA_MANIFEST.txt"), "w", encoding="utf-8").write(manifest)

# ── 2) 패키지 README ──
readme = """06Prj_Ch8_Plugin_Stg1_TS_Impatient — 인수인계 패키지 (2026-06-15)
================================================================
★ Output of Chat: 성급(Impatient) TS 실행 Plugin (진입 지정가/청산 시장가) — 백테 6관문 통과 후보.

[구성]
 docs/   Handover_06Prj_Ch8_Plugin_stg1.docx  ← 먼저 읽기(인수인계보고서)
         KeyNote_06Prj_Ch8_Plugin_stg1.docx   ← 핵심로직+코드전문
         Guide_AlphaDiscovery_Method_v5.docx  ← v4+TIL 7건
 plugin/ ts_impatient_plugin.py + bots/(§8 무수정 의존)
 research_code/  검증 .py 20종
 results/        ledger/opt/sw csv + 비교 png
 Hstr_Ver_Up_TrendStack_Bot.zip  ← 봇 살아있는 사양서 + 데이터추출코드/데이터

[핵심수치] 실비용~8bp(진입메이커+청산시장가) 3년: 성급TS단독 +1368% / MDD -18.3% / Calmar 75
           CPCV 표준6: p25 +1027% / 최악경로 +830% (전 경로 흑자).
[★알파 저장] 최종 채택 시 G:\\내 드라이브\\00AI개발지식DB\\자산관리\\유동자산\\자동매매\\
             06 ChampBot\\00ALPHA_Confirm_Bot 에 반드시 저장(세션 유실 방지).
[다음 1수] 06-19 라이브 페이퍼 통과 = 최종 채택 게이트.
"""
open(os.path.join(PKG, "README_PACKAGE.txt"), "w", encoding="utf-8").write(readme)


def zipdir(zf, folder, arc_root):
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for fn in files:
            fp = os.path.join(root, fn)
            arc = os.path.join(arc_root, os.path.relpath(fp, folder))
            zf.write(fp, arc)


# ── 3) Hstr_Ver_Up_TrendStack_Bot.zip ──
hstr_zip = os.path.join(PKG, "Hstr_Ver_Up_TrendStack_Bot.zip")
with zipfile.ZipFile(hstr_zip, "w", zipfile.ZIP_DEFLATED) as zf:
    zipdir(zf, HS, "Hstr_Ver_Up_TrendStack_Bot")
print("Hstr zip:", os.path.getsize(hstr_zip), "bytes")
# 사양서 위치(00Basic_Setup_Package)에도 복사
import shutil
shutil.copy(hstr_zip, os.path.join(BASIC, "Hstr_Ver_Up_TrendStack_Bot.zip"))

# ── 4) 메인 zip (hstr_data_extraction 원본폴더는 제외, 대신 위 nested zip 포함) ──
main_zip = os.path.join(VERIFY, "06Prj_Ch8_Plugin_Stg1_TS_Impatient.zip")
with zipfile.ZipFile(main_zip, "w", zipfile.ZIP_DEFLATED) as zf:
    for sub in ["docs", "plugin", "research_code", "results"]:
        zipdir(zf, os.path.join(PKG, sub), "06Prj_Ch8_Plugin_Stg1_TS_Impatient/" + sub)
    for top in ["README_PACKAGE.txt", "Hstr_Ver_Up_TrendStack_Bot.zip",
                "build_docs.js", "build_guide_v5.py", "build_zip.py"]:
        fp = os.path.join(PKG, top)
        if os.path.exists(fp):
            zf.write(fp, "06Prj_Ch8_Plugin_Stg1_TS_Impatient/" + top)
print("MAIN zip:", main_zip, os.path.getsize(main_zip), "bytes")
with zipfile.ZipFile(main_zip) as zf:
    print("entries:", len(zf.namelist()))
"""
"""
