# -*- coding: utf-8 -*-
# [파일명] check_07Prj_Ch4_RunAWS_Stg8_CausalRecert.py
# §4 check 3역할: ①오염검사(박제 사본 5종 = 원본 해시 일치) ②분석txt ③INDEX 1줄
import os, sys, hashlib, datetime as dt

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
WORKHSTR = r"D:\ML\verify\00WorkHstr"
INDEX = os.path.join(WORKHSTR, "00WorkHstr_INDEX.txt")
STG = "07Prj_Ch4_RunAWS_Stg8_CausalRecert"
ENGINE_SHA = "dfdfac4394cd780939d4b368d3ccabfbfab8d599ff1236b11f7f0d80f0823086"
DEVLEDGER_SHA = "a786876e1b56561707f4cc8dcc11f97c19208ae3f629c8b5e828af060a794b44"
ORIG = {
    os.path.join("bots", "test_07Prj_Ch2_SidewayDCARebuild_Stg1_ExpCutLiqSweep.py"):
        r"D:\ML\verify\07Prj_Ch2_SidewayDCARebuild_Stg1_ExpCutLiqSweep\test_07Prj_Ch2_SidewayDCARebuild_Stg1_ExpCutLiqSweep.py",
    os.path.join("bots", "test_07Prj_Ch4_RunAWS_Stg3_NMultSweep.py"):
        r"D:\ML\verify\07Prj_Ch4_RunAWS_Stg3_NMultSweep\test_07Prj_Ch4_RunAWS_Stg3_NMultSweep.py",
    "07Prj_Ch2_SidewayDCARebuild_Stg1_ExpCutLiqSweep_ledger.csv":
        r"D:\ML\verify\07Prj_Ch2_SidewayDCARebuild_Stg1_ExpCutLiqSweep\07Prj_Ch2_SidewayDCARebuild_Stg1_ExpCutLiqSweep_ledger.csv",
    "bot_sidewaydca_signal.py":
        r"D:\ML\verify\07Prj_Ch4_RunAWS_Stg7_SidewayDCAStream\bot_sidewaydca_signal.py",
}


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for ch in iter(lambda: f.read(65536), b""):
            h.update(ch)
    return h.hexdigest()


def main():
    checks = []
    eng = sha(os.path.join(HERE, "bots", "SidewayDCA_Stg7_engine.py"))
    checks.append(("박제엔진(§8)", eng == ENGINE_SHA, eng[:16]))
    dl = sha(os.path.join(HERE, "bots", "07Prj_Ch2_Stg2_TrendStack_OPVnNSweep_devledger.csv"))
    checks.append(("devledger264(근간)", dl == DEVLEDGER_SHA, dl[:16]))
    for copy_rel, orig in ORIG.items():
        cp = os.path.join(HERE, copy_rel)
        ok = os.path.exists(cp) and os.path.exists(orig) and sha(cp) == sha(orig)
        checks.append((f"사본=원본 {os.path.basename(copy_rel)}", ok, "동일" if ok else "불일치/누락"))
    out_ok = all(os.path.exists(os.path.join(HERE, f)) for f in
                 ["causal_ledger.csv", "recert_summary.csv", "dual_k_sweep.csv", "recert_result.txt"])
    checks.append(("산출4종 존재", out_ok, "OK" if out_ok else "누락(run.bat 미실행?)"))
    tr = os.path.join(HERE, "recert_result.txt")
    t_first = open(tr, "r", encoding="utf-8").read().strip().splitlines()[0] if os.path.exists(tr) else "결과없음"
    checks.append(("재인증 VERDICT", t_first.startswith("VERDICT 5/5"), t_first))

    n_pass = sum(1 for _, ok, _ in checks if ok)
    verdict = f"VERDICT {STG} | 오염검사 {n_pass}/{len(checks)} | {t_first}"
    stamp = dt.datetime.now().strftime("%Y%m%d%H%M")
    body = [verdict] + [f"[{'PASS' if ok else 'FAIL'}] {n} | {note}" for n, ok, note in checks]
    if os.path.exists(tr):
        body += ["", "[전문]", open(tr, "r", encoding="utf-8").read()]
    os.makedirs(WORKHSTR, exist_ok=True)
    with open(os.path.join(WORKHSTR, f"{stamp}.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(body) + "\n")
    with open(INDEX, "a", encoding="utf-8") as f:
        f.write(f"{stamp} | {STG} | 오염검사 {n_pass}/{len(checks)} | {t_first} | 분석:{stamp}.txt\n")
    print(verdict)
    for n, ok, note in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {n} | {note}")


if __name__ == "__main__":
    main()
