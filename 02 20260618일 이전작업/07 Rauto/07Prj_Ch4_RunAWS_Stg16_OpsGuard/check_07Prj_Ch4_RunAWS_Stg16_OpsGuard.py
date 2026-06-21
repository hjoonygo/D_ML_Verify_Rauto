# -*- coding: utf-8 -*-
# [파일명] check_07Prj_Ch4_RunAWS_Stg16_OpsGuard.py — §4 check 3역할 (Stg14 v4 관례 계승)
# 내부버전: stg16_check_v2 (v1 + ④토큰 평문 grep 자체검사 — 캡틴 보안 보강 2026-06-13)
# [오염검사] ①Stg16 ops 파일 7종 해시상수 ②봇 본체(§8+확정 10종) 무수정 — Stg14 bots 대조
#   ③stg16_result.txt VERDICT 존재 ④토큰 평문 0건(텔레그램 토큰 모양 숫자8~10:영숫자32+ 를
#   산출물·로그 전수 스캔 — 토큰은 OS 환경변수 전용, 어디에도 평문 금지).
#   INDEX 기록은 D:\ 부재 시 aws_workhstr.log 자동 전환.
import os, sys, re, glob, hashlib, datetime as dt

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
STG = "07Prj_Ch4_RunAWS_Stg16_OpsGuard"
WORKHSTR_PC = r"D:\ML\verify\00WorkHstr"

OPS_HASHES = {
    "ops_common.py": "250e9e28a9323d35b0f5cec79cab5eb7b18e8b5b488f2bb59054a6fb61189c43",
    # v2 패치(AWS 발신불능 수습 2026-06-13) — 구해시 c8fce012facdd5ee...(대체됨)
    "alert_telegram.py": "94649cef70658929df43b761230f89d5d60db1b70e76d5d66e63781ab98acfcd",
    "kill_guard.py": "d5ef46d9faf3d559a238f7265162507ec03fd5d264964c3228fdcc042dcb85ee",
    # v2 하트비트(캡틴 승인 2026-06-13) — 구해시 7153989666603c05...(대체됨)
    "alert_check.py": "157e05116c9e8f885e688bcd8bc34067b33db76cb3c3811599f04a76cf751c6b",
    "ops_status.py": "be840c09b8a6db3da5a4031cfd42ef290c5466310fb070a1cf7edd6bb55603a8",
    "telegram_poll.py": "d6eda28d5029908f190dc1d3a40c55cfa0f5f0ff3724569103587034349613db",
    "status_check.bat": "2106b4f57c674db445b575bc2536c824b90bca24b63fddf4075245c71a1197fe",
}
BOT_HASHES = {  # Stg14 check v4와 동일 상수 — 봇 본체 무수정 대조
    "trendstack_signal_engine.py": "c9d784bfd81e8ed4ffccbc07fd3725ee99738c5b42c71102d59ab616a1c8fa2d",
    "bot_trendstack_signal.py": "040da0d277d166cae1456c9c2ea340fd8b8d6c1ae9d079713cef22dc30ffb08a",
    "rauto_paper_engine.py": "f3ff3e652c2d60338ae238807aff322dd5fe632a811348d50607b1e3969c90a3",
    "rauto_contract.py": "40b974ac7859a95fe19b31aa8d7fd503a4dee00726da75c8bd06082b6576791b",
    "SidewayDCA_Stg7_engine.py": "dfdfac4394cd780939d4b368d3ccabfbfab8d599ff1236b11f7f0d80f0823086",
    "bot_sidewaydca_signal.py": "f758ef6d8c2d77b6bea90536c15d6e1fbc2b3c1c452492e9696b4fe58bf7b5e3",
    "oi_zscore_adapter.py": "32b373cfc33817c336c8934075a148b40d7af545635ee67b8e8e1cc1598fd733",
    "atr_ratio_adapter.py": "b2e4a1107707935dc5f05abbc1e6e14cea660395f759a7cc135122640c361811",
    "dauto_loader.py": "97f894f3adaafb7bb927707958d943ed295e4476d81f302a751d51169b41d696",
    "regime_feature_extractor.py": "c3ace85e44cad8b220bc051c231d2544413d1f47e634bbc1370f87210f751a28",
}


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for ch in iter(lambda: f.read(65536), b""):
            h.update(ch)
    return h.hexdigest()


def bots_dir():
    # E/F항 통일: env RAUTO_DIR → C:\run_Rauto → 자기 폴더 → PC Stg14 상대경로
    rd = os.environ.get("RAUTO_DIR", "")
    cands = ([os.path.join(rd, "bots")] if rd else []) + \
        [r"C:\run_Rauto\bots", os.path.join(HERE, "bots"),
         os.path.join(os.path.dirname(HERE), "07Prj_Ch4_RunAWS_Stg14_LivePaperWarmup", "bots")]
    for c in cands:
        if os.path.isdir(c):
            return c
    return None


def main():
    aws_mode = not os.path.isdir(WORKHSTR_PC)
    checks = []
    for fn, want in OPS_HASHES.items():
        p = os.path.join(HERE, fn)
        got = sha(p) if os.path.exists(p) else "(파일없음)"
        checks.append((f"{fn} 해시상수", got == want, got[:16]))
    bd = bots_dir()
    if bd is None:
        checks.append(("bots 폴더 발견", False, "C:\\run_Rauto\\bots·Stg14 모두 부재"))
    else:
        for fn, want in BOT_HASHES.items():
            p = os.path.join(bd, fn)
            got = sha(p) if os.path.exists(p) else "(파일없음)"
            checks.append((f"봇무수정 {fn}", got == want, got[:16]))
    # ④ 토큰 평문 grep 자체검사 — Stg16 전 산출물 + 운영 로그·상태파일
    tok_pat = re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{32,}\b")
    hits = []
    scan = []
    for ext in ("*.py", "*.bat", "*.txt", "*.log", "*.json", "*.csv"):
        scan += glob.glob(os.path.join(HERE, ext))
    for p in scan:
        try:
            body = open(p, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        if tok_pat.search(body):
            hits.append(os.path.basename(p))
    checks.append(("토큰 평문 0건(grep)", not hits,
                   "전수스캔 OK" if not hits else f"발견:{','.join(hits)}"))
    tr = os.path.join(HERE, "stg16_result.txt")
    txt = open(tr, "r", encoding="utf-8").read().strip() if os.path.exists(tr) else ""
    vline = next((l for l in txt.splitlines() if l.startswith("VERDICT")), "결과없음")
    checks.append(("결과 존재", vline != "결과없음", vline[:90]))

    n_pass = sum(1 for _, ok, _ in checks if ok)
    stamp = dt.datetime.now().strftime("%Y%m%d%H%M")
    mode = "AWS모드" if aws_mode else "PC모드"
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
