# -*- coding: utf-8 -*-
# [파일명] check_06Prj_Ch5_RAUTO_ConceptRefine_Stg3_Trend1mExit.py
# 코드길이: 약 165줄 | 내부버전: RAUTO_ConceptRefine_06_Ch5_Stg3_Trend1mExit | 로직 전체 출력
# [역할] test 후: 오염검사 10항목 + 분석txt(상위 00WorkHstr) + INDEX 한줄. 결과 전량 파일로만.
# [검사 10항목]
#   1.필수파일존재 2.결과CSV非공백 3.코드해시기록 4.거래중복없음 5.미래참조가드(shift- 스캔)
#   6.★V0복제=엔진일치(repl_ok) 7.★분할1m=7h 동등(no-op 증명) 8.버전3개+연도행 9.엔진원본일치(해시) 10.VERDICT
# ==============================================================================
import os, sys, hashlib, datetime, re, io, tokenize
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
WORKHSTR = os.path.join(PARENT, "00WorkHstr")
VER = "RAUTO_ConceptRefine_06_Ch5_Stg3_Trend1mExit"
TESTPY = "test_06Prj_Ch5_RAUTO_ConceptRefine_Stg3_Trend1mExit.py"
CHECKPY = "check_06Prj_Ch5_RAUTO_ConceptRefine_Stg3_Trend1mExit.py"
TREND_ENGINE = os.path.join("bots", "SpTrd_Fib_V1_Champion.py")
SDCA_ENGINE = os.path.join("bots", "SidewayDCA_Stg7_engine.py")
EXPECT_HASH = {
    TREND_ENGINE: "7f9192e3d50b1afd659a02b9e75764e5438ad57809c93093ab5f1973bb79ca75",
    SDCA_ENGINE:  "dfdfac4394cd780939d4b368d3ccabfbfab8d599ff1236b11f7f0d80f0823086",
}
REQUIRED = [TESTPY, CHECKPY, "run.bat", TREND_ENGINE, SDCA_ENGINE,
            "trend1m_summary.csv", "trend1m_versions.csv", "trend1m_trades_v1.csv", "trend1m_splitchk.csv"]


def strip_comments(src):
    try:
        lines = src.split("\n")
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                sr, sc = tok.start; _, ec = tok.end
                lines[sr - 1] = lines[sr - 1][:sc] + lines[sr - 1][ec:]
        return "\n".join(lines)
    except Exception:
        return src


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(8192), b""):
            h.update(c)
    return h.hexdigest()


def read_metric():
    p = os.path.join(HERE, ".trend1m_metric"); d = {}
    if os.path.exists(p):
        for ln in open(p, encoding="utf-8"):
            if "=" in ln:
                k, v = ln.strip().split("=", 1); d[k] = v
    return d


def parse_verdict():
    p = os.path.join(HERE, "trend1m_summary.csv")
    if not os.path.exists(p):
        return None
    for line in open(p, encoding="utf-8-sig"):
        if "VERDICT" in line:
            return line.strip().strip('"').rstrip(',').rstrip('"')
    return None


def check_all():
    res = []; m = read_metric()
    present = {f: os.path.exists(os.path.join(HERE, f)) for f in REQUIRED}
    miss = [f for f, ok in present.items() if not ok]
    res.append(("1.필수파일존재", len(miss) == 0, f"누락:{miss}" if miss else "all present"))

    csvs = [f for f in REQUIRED if f.endswith(".csv")]
    empt = [c for c in csvs if present.get(c) and os.path.getsize(os.path.join(HERE, c)) < 10]
    res.append(("2.결과CSV非공백", len(empt) == 0, f"빈:{empt}" if empt else "ok"))

    hashes = {f: sha256(os.path.join(HERE, f))[:16] for f in [TESTPY, CHECKPY] if present.get(f)}
    res.append(("3.코드해시기록", len(hashes) == 2, str(hashes)))

    dup = 0
    if present.get("trend1m_trades_v1.csv"):
        try:
            dup = int(pd.read_csv(os.path.join(HERE, "trend1m_trades_v1.csv")).duplicated().sum())
        except Exception:
            dup = -1
    res.append(("4.거래중복없음", dup == 0, f"중복{dup}행"))

    look = True; memo = "음수shift 미사용(주석제외, 하네스+엔진)"
    for f in [TESTPY, TREND_ENGINE, SDCA_ENGINE]:
        if present.get(f):
            if re.search(r"shift\(\s*-\s*\d", strip_comments(open(os.path.join(HERE, f), encoding="utf-8").read())):
                look = False; memo = f"{f}: 음수shift 발견"; break
    res.append(("5.미래참조가드", look, memo))

    res.append(("6.V0복제=엔진일치", m.get("repl_ok") == "True", f"repl_ok={m.get('repl_ok')}, n엔진{m.get('eng_n')}/V0{m.get('v0_n')}"))
    res.append(("7.분할1m=7h동등(no-op)", m.get("split_noop") == "True", f"최대평단차={m.get('maxdiff')}"))

    ver_ok = False; vm = "버전 부족"
    if present.get("trend1m_versions.csv"):
        try:
            v = pd.read_csv(os.path.join(HERE, "trend1m_versions.csv"))
            ver_ok = (len(v) == 3 and {'cumR_pct', 'MDD_pct', 'PF'} <= set(v.columns))
            vm = f"버전{len(v)}개, 갭(청산{m.get('gap_exit')}/현실{m.get('gap_real')})"
        except Exception as e:
            vm = f"확인실패:{e}"
    res.append(("8.버전3개산출", ver_ok, vm))

    eng_ok = True; em = []
    for f, exp in EXPECT_HASH.items():
        if present.get(f):
            ok = (sha256(os.path.join(HERE, f)) == exp); eng_ok = eng_ok and ok
            em.append(f"{os.path.basename(f)}={'일치' if ok else '★불일치'}")
        else:
            eng_ok = False; em.append(f"{os.path.basename(f)}=없음")
    res.append(("9.엔진원본일치(무수정증빙)", eng_ok, " ".join(em)))

    v = parse_verdict()
    res.append(("10.VERDICT존재", v is not None, (v[:50] + "...") if v else "없음"))

    passed = all(ok for _, ok, _ in res)
    return passed, res, hashes, m, v


def write_analysis(passed, res, hashes, m, v):
    os.makedirs(WORKHSTR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    path = os.path.join(WORKHSTR, f"{stamp}.txt")
    L = [f"[작업분석] {VER}  ({datetime.datetime.now().isoformat(timespec='seconds')})",
         f"[오염검사] {'PASS' if passed else 'FAIL'}", "-" * 60]
    for label, ok, memo in res:
        L.append(f"  {'O' if ok else 'X'} {label}: {memo}")
    L.append("-" * 60)
    L.append(f"[VERDICT] {v}")
    L.append(f"[버전갭] V0 {m.get('v0_cum')}% / VE_1m청산 {m.get('ve_cum')}% / V1_현실 {m.get('v1_cum')}%  "
             f"(청산갭 {m.get('gap_exit')}%p, 현실판갭 {m.get('gap_real')}%p)")
    L.append(f"[분할 no-op] 7h평단=1m평단 최대차 {m.get('maxdiff')} (결정2는 효과없음 확정)")
    vp = os.path.join(HERE, "trend1m_versions.csv")
    if os.path.exists(vp):
        L.append("[버전 상세]")
        for _, r in pd.read_csv(vp).iterrows():
            L.append(f"  {r['version']}: cumR{r['cumR_pct']}% PF{r['PF']} MDD{r['MDD_pct']}% n{r['n']}(sl{r['n_sl']}/flip{r['n_flip']})")
    L.append(f"[코드해시] {hashes}")
    open(path, "w", encoding="utf-8").write("\n".join(L))
    return path


def update_index(line):
    os.makedirs(WORKHSTR, exist_ok=True)
    idx = os.path.join(WORKHSTR, "00WorkHstr_INDEX.txt")
    hdr = not os.path.exists(idx)
    with open(idx, "a", encoding="utf-8") as f:
        if hdr:
            f.write("# 00WorkHstr INDEX | 시각 | 버전 | 검사 | 핵심성과\n")
        f.write(line + "\n")


def main():
    passed, res, hashes, m, v = check_all()
    apath = write_analysis(passed, res, hashes, m, v or "N/A")
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    update_index(f"{stamp} | {VER} | {'PASS' if passed else 'FAIL'} | {v}")
    print(f"[check] integrity={'PASS' if passed else 'FAIL'}")
    print(f"[check] analysis -> {apath}")


if __name__ == "__main__":
    main()
