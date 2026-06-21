# -*- coding: utf-8 -*-
# [파일명] check_07Prj_Ch4_RunAWS_Stg9_DualKSweepCausal.py
# §4 check 3역할: ①오염검사(근간 사본=원본 해시·causal=§8 해시) ②분석txt ③INDEX 1줄
import os, sys, hashlib, datetime as dt

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
WORKHSTR = r"D:\ML\verify\00WorkHstr"
STG = "07Prj_Ch4_RunAWS_Stg9_DualKSweepCausal"
CAUSAL_SHA = "c4964c5566af96311059172c59ffc17d4f374ebd608f5b30b409b8fbf122b4b9"   # CLAUDE.md §8
S6 = r"D:\ML\verify\07Prj_Ch4_RunAWS_Stg6_DualSynthesis"
ORIG = {
    os.path.join("bots", "test_07Prj_Ch4_RunAWS_Stg6_DualSynthesis.py"): os.path.join(S6, "test_07Prj_Ch4_RunAWS_Stg6_DualSynthesis.py"),
    os.path.join("bots", "07Prj_Ch2_Stg2_TrendStack_OPVnNSweep_devledger.csv"): os.path.join(S6, "07Prj_Ch2_Stg2_TrendStack_OPVnNSweep_devledger.csv"),
    os.path.join("bots", "stg6_levsweep_ledger.csv"): os.path.join(S6, "stg6_levsweep_ledger.csv"),
    os.path.join("bots", "07Prj_Ch2_SidewayDCARebuild_Stg1_ExpCutLiqSweep_ledger.csv"): os.path.join(S6, "07Prj_Ch2_SidewayDCARebuild_Stg1_ExpCutLiqSweep_ledger.csv"),
}


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for ch in iter(lambda: f.read(65536), b""):
            h.update(ch)
    return h.hexdigest()


def main():
    checks = []
    c = sha(os.path.join(HERE, "causal_ledger.csv"))
    checks.append(("causal_ledger=§8해시", c == CAUSAL_SHA, c[:16]))
    for rel, orig in ORIG.items():
        ok = os.path.exists(orig) and sha(os.path.join(HERE, rel)) == sha(orig)
        checks.append((f"사본=원본 {os.path.basename(rel)}", ok, "동일" if ok else "불일치"))
    tr = os.path.join(HERE, "stg9_result.txt")
    txt = open(tr, "r", encoding="utf-8").read().strip() if os.path.exists(tr) else ""
    vline = next((l for l in txt.splitlines() if l.startswith("VERDICT")), "결과없음")
    checks.append(("결과 존재", vline != "결과없음", vline[:80]))

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
