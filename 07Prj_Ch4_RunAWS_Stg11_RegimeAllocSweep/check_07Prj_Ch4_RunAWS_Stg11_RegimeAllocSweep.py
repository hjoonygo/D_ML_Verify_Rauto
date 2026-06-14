# -*- coding: utf-8 -*-
# [파일명] check_07Prj_Ch4_RunAWS_Stg11_RegimeAllocSweep.py — §4 check 3역할
import os, sys, hashlib, datetime as dt

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
WORKHSTR = r"D:\ML\verify\00WorkHstr"
STG = "07Prj_Ch4_RunAWS_Stg11_RegimeAllocSweep"
HASHES = {
    "causal_ledger.csv": "c4964c5566af96311059172c59ffc17d4f374ebd608f5b30b409b8fbf122b4b9",
    os.path.join("bots", "trendstack_signal_engine.py"): "c9d784bfd81e8ed4ffccbc07fd3725ee99738c5b42c71102d59ab616a1c8fa2d",
    os.path.join("bots", "07Prj_Ch2_Stg2_TrendStack_OPVnNSweep_devledger.csv"): "a786876e1b56561707f4cc8dcc11f97c19208ae3f629c8b5e828af060a794b44",
}
S6_ORIG = r"D:\ML\verify\07Prj_Ch4_RunAWS_Stg6_DualSynthesis\test_07Prj_Ch4_RunAWS_Stg6_DualSynthesis.py"


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for ch in iter(lambda: f.read(65536), b""):
            h.update(ch)
    return h.hexdigest()


def main():
    checks = []
    for rel, want in HASHES.items():
        got = sha(os.path.join(HERE, rel))
        checks.append((f"{os.path.basename(rel)}(§8/근간)", got == want, got[:16]))
    ok6 = sha(os.path.join(HERE, "bots", "test_07Prj_Ch4_RunAWS_Stg6_DualSynthesis.py")) == sha(S6_ORIG)
    checks.append(("Stg6 합성 사본=원본", ok6, "동일" if ok6 else "불일치"))
    tr = os.path.join(HERE, "stg11_result.txt")
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
