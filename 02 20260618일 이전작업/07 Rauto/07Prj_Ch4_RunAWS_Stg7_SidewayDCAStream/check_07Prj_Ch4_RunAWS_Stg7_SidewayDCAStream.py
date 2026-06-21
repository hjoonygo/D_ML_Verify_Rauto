# -*- coding: utf-8 -*-
# [파일명] check_07Prj_Ch4_RunAWS_Stg7_SidewayDCAStream.py
# §4 check 3역할: ①오염검사(해시 대조·동봉파일) ②분석txt 저장 ③INDEX 1줄
# 오염검사: 박제엔진=dfdfac43… / rauto_contract=40b974ac… (CLAUDE.md §8) / 원장 사본=원본 동일 해시
import os, sys, hashlib, datetime as dt

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
WORKHSTR = r"D:\ML\verify\00WorkHstr"
INDEX = os.path.join(WORKHSTR, "00WorkHstr_INDEX.txt")
STG = "07Prj_Ch4_RunAWS_Stg7_SidewayDCAStream"
ENGINE_SHA = "dfdfac4394cd780939d4b368d3ccabfbfab8d599ff1236b11f7f0d80f0823086"
CONTRACT_SHA = "40b974ac7859a95fe19b31aa8d7fd503a4dee00726da75c8bd06082b6576791b"
LEDGER_ORIG = r"D:\ML\verify\07Prj_Ch2_SidewayDCARebuild_Stg1_ExpCutLiqSweep\07Prj_Ch2_SidewayDCARebuild_Stg1_ExpCutLiqSweep_ledger.csv"
LEDGER_COPY = os.path.join(HERE, "07Prj_Ch2_SidewayDCARebuild_Stg1_ExpCutLiqSweep_ledger.csv")
FILES = ["bot_sidewaydca_signal.py", f"test_{STG}.py", f"check_{STG}.py", "run.bat",
         "rauto_contract.py", os.path.join("bots", "SidewayDCA_Stg7_engine.py"),
         os.path.basename(LEDGER_COPY)]


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for ch in iter(lambda: f.read(65536), b""):
            h.update(ch)
    return h.hexdigest()


def main():
    checks = []
    missing = [f for f in FILES if not os.path.exists(os.path.join(HERE, f))]
    checks.append(("동봉파일7종", not missing, f"누락 {missing}" if missing else "전부 존재"))
    eng_h = sha256(os.path.join(HERE, "bots", "SidewayDCA_Stg7_engine.py"))
    checks.append(("박제엔진 무수정(§8)", eng_h == ENGINE_SHA, f"{eng_h[:16]}..."))
    con_h = sha256(os.path.join(HERE, "rauto_contract.py"))
    checks.append(("rauto_contract 무수정(§8)", con_h == CONTRACT_SHA, f"{con_h[:16]}..."))
    led_ok = os.path.exists(LEDGER_ORIG) and sha256(LEDGER_ORIG) == sha256(LEDGER_COPY)
    checks.append(("원장 사본=원본 해시", led_ok, "동일" if led_ok else "불일치/원본없음"))
    bot_h = sha256(os.path.join(HERE, "bot_sidewaydca_signal.py"))

    tr = os.path.join(HERE, "stream_match_result.txt")
    t_txt = open(tr, "r", encoding="utf-8").read().strip() if os.path.exists(tr) else "결과 없음(run.bat 미실행)"
    t_first = t_txt.splitlines()[0] if t_txt else ""
    checks.append(("리플레이+mock", t_first.startswith("VERDICT 2/2"), t_first))

    n_pass = sum(1 for _, ok, _ in checks if ok)
    verdict = f"VERDICT {STG} | 오염검사 {n_pass}/{len(checks)} | bot_sha256={bot_h[:16]}... | {t_first}"
    body = [verdict] + [f"[{'PASS' if ok else 'FAIL'}] {n} | {note}" for n, ok, note in checks] \
           + ["", "[전문]", t_txt, "", f"bot SHA256(전체): {bot_h}"]

    stamp = dt.datetime.now().strftime("%Y%m%d%H%M")
    os.makedirs(WORKHSTR, exist_ok=True)
    with open(os.path.join(WORKHSTR, f"{stamp}.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(body) + "\n")
    with open(INDEX, "a", encoding="utf-8") as f:
        f.write(f"{stamp} | {STG} | 오염검사 {n_pass}/{len(checks)} | {t_first} | bot={bot_h[:8]} | 분석:{stamp}.txt\n")
    print(verdict)
    for n, ok, note in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {n} | {note}")
    print(f"[save] {WORKHSTR}\\{stamp}.txt + INDEX 1줄")


if __name__ == "__main__":
    main()
