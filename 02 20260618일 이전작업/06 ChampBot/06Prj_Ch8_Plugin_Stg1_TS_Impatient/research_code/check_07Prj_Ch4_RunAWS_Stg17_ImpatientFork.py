# -*- coding: utf-8 -*-
# [파일명] check_07Prj_Ch4_RunAWS_Stg14_LivePaperWarmup.py — §4 check 3역할
# 내부버전: v4_awsport (캡틴 긴급패치 2026-06-12)
# [v4 변경] 오염검사 = '§8/확정 해시 상수 직접 대조'로 전환(운영지에서 원본 부재여도 무결성
#   검증 가능). PC(원본 경로 존재 시)는 파일 대조 추가 수행(이중 검증). INDEX 기록은 D:\ 부재
#   시 로컬 aws_workhstr.log로 자동 전환(AWS 모드).
import os, sys, hashlib, datetime as dt

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
STG = "07Prj_Ch4_RunAWS_Stg17_ImpatientFork"
WORKHSTR_PC = r"D:\ML\verify\00WorkHstr"

# ── 확정 해시 상수 (§8 + Stg8/13/15 확정판 — 원본 부재 환경에서도 대조 가능) ──
#   ★분기: bot_trendstack_impatient.py(신규 래퍼)만 추가. 나머지 §8 봇은 Stg14와 바이트 동일이어야 PASS
#          (엔진/기존봇 무수정 입증 — 본 check가 매 배치 자동 검증).
HASHES = {
    os.path.join("bots", "bot_trendstack_impatient.py"): "2a3358220fbd43d47c2ac617e7a5347e1fb70f57f67a17fabdaa3a6040d79f5b",
    os.path.join("bots", "trendstack_signal_engine.py"): "c9d784bfd81e8ed4ffccbc07fd3725ee99738c5b42c71102d59ab616a1c8fa2d",
    os.path.join("bots", "bot_trendstack_signal.py"): "040da0d277d166cae1456c9c2ea340fd8b8d6c1ae9d079713cef22dc30ffb08a",
    os.path.join("bots", "rauto_paper_engine.py"): "f3ff3e652c2d60338ae238807aff322dd5fe632a811348d50607b1e3969c90a3",
    os.path.join("bots", "rauto_contract.py"): "40b974ac7859a95fe19b31aa8d7fd503a4dee00726da75c8bd06082b6576791b",
    os.path.join("bots", "SidewayDCA_Stg7_engine.py"): "dfdfac4394cd780939d4b368d3ccabfbfab8d599ff1236b11f7f0d80f0823086",
    os.path.join("bots", "bot_sidewaydca_signal.py"): "f758ef6d8c2d77b6bea90536c15d6e1fbc2b3c1c452492e9696b4fe58bf7b5e3",
    os.path.join("bots", "oi_zscore_adapter.py"): "32b373cfc33817c336c8934075a148b40d7af545635ee67b8e8e1cc1598fd733",
    os.path.join("bots", "atr_ratio_adapter.py"): "b2e4a1107707935dc5f05abbc1e6e14cea660395f759a7cc135122640c361811",
    os.path.join("bots", "dauto_loader.py"): "97f894f3adaafb7bb927707958d943ed295e4476d81f302a751d51169b41d696",
    os.path.join("bots", "regime_feature_extractor.py"): "c3ace85e44cad8b220bc051c231d2544413d1f47e634bbc1370f87210f751a28",
}
# PC 이중검증용 원본 경로(존재할 때만 수행)
PC_ORIGS = {
    os.path.join("bots", "bot_sidewaydca_signal.py"): r"D:\ML\verify\07Prj_Ch4_RunAWS_Stg8_CausalRecert\bot_sidewaydca_signal.py",
    os.path.join("bots", "oi_zscore_adapter.py"): r"D:\ML\verify\08Prj_Dauto_Ch2_Stg13_OiZscoreAdapter\oi_zscore_adapter.py",
    os.path.join("bots", "atr_ratio_adapter.py"): r"D:\ML\verify\08Prj_Dauto_Ch2_Stg15_AtrRatioAdapter\atr_ratio_adapter.py",
    os.path.join("bots", "dauto_loader.py"): r"D:\ML\verify\08Prj_Dauto_Ch2_Stg15_AtrRatioAdapter\dauto_loader.py",
    os.path.join("bots", "regime_feature_extractor.py"): r"D:\ML\verify\08Prj_Dauto_Ch2_Stg15_AtrRatioAdapter\regime_feature_extractor.py",
}


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for ch in iter(lambda: f.read(65536), b""):
            h.update(ch)
    return h.hexdigest()


def main():
    aws_mode = not os.path.isdir(WORKHSTR_PC)
    checks = []
    for rel, want in HASHES.items():
        p = os.path.join(HERE, rel)
        got = sha(p) if os.path.exists(p) else "(파일없음)"
        checks.append((f"{os.path.basename(rel)} 해시상수", got == want, got[:16]))
    if not aws_mode:                                  # PC 이중검증
        for rel, orig in PC_ORIGS.items():
            if os.path.exists(orig):
                okf = sha(os.path.join(HERE, rel)) == sha(orig)
                checks.append((f"{os.path.basename(rel)} 원본파일 대조(PC)", okf, "동일" if okf else "불일치"))
    for fn in ["paper_ledger.csv", "scorecard_daily.csv"]:
        checks.append((f"{fn} 존재", os.path.exists(os.path.join(HERE, fn)), ""))
    tr = os.path.join(HERE, "stg14_result.txt")
    txt = open(tr, "r", encoding="utf-8").read().strip() if os.path.exists(tr) else ""
    vline = next((l for l in txt.splitlines() if l.startswith("VERDICT")), "결과없음")
    checks.append(("결과 존재", vline != "결과없음", vline[:90]))

    n_pass = sum(1 for _, ok, _ in checks if ok)
    stamp = dt.datetime.now().strftime("%Y%m%d%H%M")
    mode = "AWS모드(해시상수만)" if aws_mode else "PC모드(해시상수+원본 이중검증)"
    body = [f"VERDICT {STG} | 오염검사 {n_pass}/{len(checks)} [{mode}] | {vline}"] + \
           [f"[{'PASS' if ok else 'FAIL'}] {n} | {note}" for n, ok, note in checks] + ["", "[전문]", txt]
    if aws_mode:
        with open(os.path.join(HERE, "aws_workhstr.log"), "a", encoding="utf-8") as f:
            f.write(f"\n===== {stamp} =====\n" + "\n".join(body) + "\n")
    else:
        with open(os.path.join(WORKHSTR_PC, f"{stamp}.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(body) + "\n")
        with open(os.path.join(WORKHSTR_PC, "00WorkHstr_INDEX.txt"), "a", encoding="utf-8") as f:
            f.write(f"{stamp} | {STG} | 오염검사 {n_pass}/{len(checks)} [{mode}] | {vline} | 분석:{stamp}.txt\n")
    print(body[0])
    for n, ok, note in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {n} | {note}")


if __name__ == "__main__":
    main()
