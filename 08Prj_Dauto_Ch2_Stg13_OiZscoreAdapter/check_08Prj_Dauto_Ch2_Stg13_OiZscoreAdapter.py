# -*- coding: utf-8 -*-
# [파일명] check_08Prj_Dauto_Ch2_Stg13_OiZscoreAdapter.py — §4 check 3역할
import os, sys, hashlib, datetime as dt

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
WORKHSTR = r"D:\ML\verify\00WorkHstr"
STG = "08Prj_Dauto_Ch2_Stg13_OiZscoreAdapter"
# §8: dauto_collector.py — 어댑터가 소비하는 CSV의 생산자(무수정 확인)
COLLECTOR = r"D:\ML\verify\08Prj_Dauto_Ch1_Collector_Stg1_RestPoller\dauto_collector.py"
COLLECTOR_SHA = "0aa01d98688f66298e4ee3e1b7372df7339a08efde9e7b6be986fab71f5428f4"
MERGED = r"D:\ML\verify\Merged_Data.csv"
MERGED_SIZE = 476327648   # 2026-05-11 사본(=With_OI_Derived_REPAIRED) 크기 대조


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for ch in iter(lambda: f.read(1 << 20), b""):
            h.update(ch)
    return h.hexdigest()


def main():
    checks = []
    got = sha(COLLECTOR)
    checks.append(("dauto_collector.py(§8)", got == COLLECTOR_SHA, got[:16]))
    sz = os.path.getsize(MERGED) if os.path.exists(MERGED) else -1
    checks.append(("Merged_Data.csv 크기대조", sz == MERGED_SIZE, str(sz)))
    for fn in ["oi_zscore_adapter.py", "stg13_grid.csv"]:
        checks.append((f"{fn} 존재", os.path.exists(os.path.join(HERE, fn)), ""))
    tr = os.path.join(HERE, "stg13_result.txt")
    txt = open(tr, "r", encoding="utf-8").read().strip() if os.path.exists(tr) else ""
    vline = next((l for l in txt.splitlines() if l.startswith("VERDICT")), "결과없음")
    checks.append(("결과 존재", vline != "결과없음", vline[:90]))

    n_pass = sum(1 for _, ok, _ in checks if ok)
    stamp = dt.datetime.now().strftime("%Y%m%d%H%M")
    body = [f"VERDICT {STG} | 오염검사 {n_pass}/{len(checks)} | {vline}"] + \
           [f"[{'PASS' if ok else 'FAIL'}] {n} | {note}" for n, ok, note in checks] + ["", "[전문]", txt]
    with open(os.path.join(WORKHSTR, f"{stamp}.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(body) + "\n")
    with open(os.path.join(WORKHSTR, "00WorkHstr_INDEX.txt"), "a", encoding="utf-8") as f:
        f.write(f"{stamp} | {STG} | 오염검사 {n_pass}/{len(checks)} | {vline} | 분석:{stamp}.txt\n")
    print(body[0])
    for n, ok, note in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {n} | {note}")


if __name__ == "__main__":
    main()
