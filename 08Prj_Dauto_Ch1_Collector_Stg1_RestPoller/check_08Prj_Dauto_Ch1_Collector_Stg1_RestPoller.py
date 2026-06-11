# -*- coding: utf-8 -*-
# [파일명] check_08Prj_Dauto_Ch1_Collector_Stg1_RestPoller.py
# 코드길이: 약 120줄 | §4 check 3역할: ①오염검사 ②분석txt 저장 ③INDEX 1줄 추가
# ─────────────────────────────────────────────────────────────────────────────
# [오염검사 항목 — 고딩 설명]
#   1) 산출 4종 파일 존재 + dauto_collector.py SHA256 기록(이후 Stg 대조 기준)
#   2) read-only 검증: 소스에 주문/키 관련 문자열(/order, apiKey, secret, signature, listenKey)
#      이 없는지 전수 검사 — 있으면 FAIL (캡틴 주의사항)
#   3) CSV 스키마: 최신 일자 파일 헤더 = 확정 13컬럼 정확 일치
#   4) test_result.txt VERDICT 회수
# ==============================================================================
import os, sys, hashlib, datetime as dt

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = r"C:\BinanceData"
WORKHSTR = r"D:\ML\verify\00WorkHstr"
INDEX = os.path.join(WORKHSTR, "00WorkHstr_INDEX.txt")
STG = "08Prj_Dauto_Ch1_Collector_Stg1_RestPoller"
EXPECT_HEADER = ("ts_utc,open,high,low,close,volume,taker_buy_volume,"
                 "open_interest,mark_price,index_price,funding_rate_8h,"
                 "next_funding_time,oi_src")
FORBIDDEN = ["/order", "apikey", "api_key", "secret", "signature", "listenkey"]
FILES = ["dauto_collector.py", f"test_{STG}.py", f"check_{STG}.py",
         "run.bat", "run_collector.bat", "README_AWS.txt"]


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for ch in iter(lambda: f.read(65536), b""):
            h.update(ch)
    return h.hexdigest()


def main():
    checks = []

    # 1) 파일 존재 + 해시
    missing = [f for f in FILES if not os.path.exists(os.path.join(HERE, f))]
    checks.append(("동봉파일6종", not missing, f"누락 {missing}" if missing else "전부 존재"))
    col_hash = sha256(os.path.join(HERE, "dauto_collector.py")) if "dauto_collector.py" not in missing else "없음"

    # 2) read-only 검증(소스 금지문자열)
    bad = []
    for f in FILES:
        if f.startswith("check_"):
            continue   # 검사기 자신은 제외(금지문자열 목록을 들고 있어 자기참조 오탐)
        p = os.path.join(HERE, f)
        if f.endswith((".py", ".bat")) and os.path.exists(p):
            src = open(p, "r", encoding="utf-8", errors="replace").read().lower()
            bad += [f"{f}:{w}" for w in FORBIDDEN if w in src]
    checks.append(("read-only(금지문자열0)", not bad, f"발견 {bad}" if bad else "주문/키 문자열 없음"))

    # 3) CSV 스키마
    hdr_ok, hdr_note = False, "CSV 없음(수집 전이면 test 먼저)"
    if os.path.isdir(ROOT):
        csvs = sorted(f for f in os.listdir(ROOT) if f.startswith("BTCUSDT_1m_") and f.endswith(".csv"))
        if csvs:
            with open(os.path.join(ROOT, csvs[-1]), "r", encoding="utf-8") as fh:
                hdr = fh.readline().strip()
            hdr_ok = (hdr == EXPECT_HEADER)
            hdr_note = f"{csvs[-1]} 헤더 {'일치' if hdr_ok else '불일치: ' + hdr}"
    checks.append(("CSV스키마13컬럼", hdr_ok, hdr_note))

    # 4) test_result 회수
    tr = os.path.join(HERE, "test_result.txt")
    t_verdict = open(tr, "r", encoding="utf-8").read().strip() if os.path.exists(tr) else "test_result.txt 없음(run.bat 미실행)"
    t_ok = t_verdict.startswith("VERDICT 4/4")
    checks.append(("PC실측(=사전실행)", t_ok, t_verdict.splitlines()[0] if t_verdict else ""))

    n_pass = sum(1 for _, ok, _ in checks if ok)
    verdict = (f"VERDICT {STG} | 오염검사 {n_pass}/{len(checks)} | collector_sha256={col_hash[:16]}... "
               f"| 분당 3콜(가중치~4/2400) read-only | 저장루트 {ROOT}")
    body = [verdict] + [f"[{'PASS' if ok else 'FAIL'}] {n} | {note}" for n, ok, note in checks] \
           + ["", "[전문] " + t_verdict, "", f"collector SHA256(전체): {col_hash}"]

    stamp = dt.datetime.now().strftime("%Y%m%d%H%M")
    os.makedirs(WORKHSTR, exist_ok=True)
    rpt = os.path.join(WORKHSTR, f"{stamp}.txt")
    with open(rpt, "w", encoding="utf-8") as f:
        f.write("\n".join(body) + "\n")
    with open(INDEX, "a", encoding="utf-8") as f:
        f.write(f"{stamp} | {STG} | 오염검사 {n_pass}/{len(checks)} | Dauto수집봇v1 REST폴러 "
                f"| collector={col_hash[:8]} | 분석:{stamp}.txt\n")
    print(verdict)
    for n, ok, note in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {n} | {note}")
    print(f"[save] {rpt} + INDEX 1줄")


if __name__ == "__main__":
    main()
