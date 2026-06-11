# -*- coding: utf-8 -*-
# [파일명] check_06Prj_Ch5_RAUTO_ConceptRefine_Stg2_GateSplitAudit.py
# 코드길이: 약 175줄 | 내부버전: RAUTO_ConceptRefine_06_Ch5_Stg2_GateSplitAudit | 로직 전체 출력
# [역할] test 후: 오염검사 10항목 + 분석txt(상위 00WorkHstr) + INDEX 한줄. 결과 전량 파일로만.
# [검사 10항목]
#   1.필수파일존재 2.결과CSV非공백 3.코드해시기록 4.분할거래중복없음 5.미래참조가드(shift- 스캔)
#   6.★진입재현일치(repl_ok: 내 게이트판정=엔진 실제진입) 7.★분할평단재현일치(match_rate>=99%)
#   8.게이트감사 연도커버(2023~2026) + 2025월 12행 9.엔진원본일치(해시) 10.VERDICT존재
# [함수 In->Out] sha256 / strip_comments / read_metric / parse_verdict / check_all / write_analysis / update_index / main
# ==============================================================================
import os, sys, hashlib, datetime, re, io, tokenize
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
WORKHSTR = os.path.join(PARENT, "00WorkHstr")
VER = "RAUTO_ConceptRefine_06_Ch5_Stg2_GateSplitAudit"
TESTPY = "test_06Prj_Ch5_RAUTO_ConceptRefine_Stg2_GateSplitAudit.py"
CHECKPY = "check_06Prj_Ch5_RAUTO_ConceptRefine_Stg2_GateSplitAudit.py"
TREND_ENGINE = os.path.join("bots", "SpTrd_Fib_V1_Champion.py")
SDCA_ENGINE = os.path.join("bots", "SidewayDCA_Stg7_engine.py")
EXPECT_HASH = {
    TREND_ENGINE: "7f9192e3d50b1afd659a02b9e75764e5438ad57809c93093ab5f1973bb79ca75",
    SDCA_ENGINE:  "dfdfac4394cd780939d4b368d3ccabfbfab8d599ff1236b11f7f0d80f0823086",
}
REQUIRED = [TESTPY, CHECKPY, "run.bat", TREND_ENGINE, SDCA_ENGINE,
            "audit_summary.csv", "audit_gate_year.csv", "audit_gate_2025m.csv",
            "audit_dec2025.csv", "audit_splitA.csv"]


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
    p = os.path.join(HERE, ".audit_metric"); d = {}
    if os.path.exists(p):
        for ln in open(p, encoding="utf-8"):
            if "=" in ln:
                k, v = ln.strip().split("=", 1); d[k] = v
    return d


def parse_verdict():
    p = os.path.join(HERE, "audit_summary.csv")
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
    if present.get("audit_splitA.csv"):
        try:
            t = pd.read_csv(os.path.join(HERE, "audit_splitA.csv")); dup = int(t.duplicated().sum())
        except Exception:
            dup = -1
    res.append(("4.분할거래중복없음", dup == 0, f"중복{dup}행"))

    look = True; memo = "음수shift 미사용(주석제외, 하네스+엔진)"
    for f in [TESTPY, TREND_ENGINE, SDCA_ENGINE]:
        if present.get(f):
            code = strip_comments(open(os.path.join(HERE, f), encoding="utf-8").read())
            if re.search(r"shift\(\s*-\s*\d", code):
                look = False; memo = f"{f}: 실제 음수shift 발견-수동확인"; break
    res.append(("5.미래참조가드", look, memo))

    repl = (m.get("repl_ok") == "True")
    res.append(("6.진입재현일치(내판정=엔진진입)", repl, f"repl_ok={m.get('repl_ok')}"))

    mr = float(m.get("match_rate", 0) or 0)
    res.append(("7.분할평단재현일치", mr >= 99.0, f"match_rate={mr}%"))

    cover = False; cm = "연도/월 부족"
    if present.get("audit_gate_year.csv"):
        try:
            gy = pd.read_csv(os.path.join(HERE, "audit_gate_year.csv"))
            g25 = pd.read_csv(os.path.join(HERE, "audit_gate_2025m.csv")) if present.get("audit_gate_2025m.csv") else None
            yrs = set(gy['year'].astype(int)) if 'year' in gy.columns else set()
            n25 = len(g25) if g25 is not None else 0
            cover = ({2023, 2024, 2025, 2026} <= yrs) and (n25 == 12)
            cm = f"연도{sorted(yrs)} 2025월수{n25}"
        except Exception as e:
            cm = f"확인실패:{e}"
    res.append(("8.게이트감사 연도/월 커버", cover, cm))

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
    L.append(f"[분할A거품] 엔진 {m.get('cum_eng')}% -> 정직 {m.get('cum_hon')}% = 거품 {m.get('bubble')}%p (당김거래 {m.get('n_bubble')}건)")
    L.append(f"[2025-12] 진입트리거 {m.get('dec2025_trig')}건(숏 {m.get('dec2025_short')}), 무덤차단 {m.get('dec2025_block')}건")
    L.append(f"[지정노출(향후)] 추세E={m.get('trend_E')} 횡보E={m.get('sdca_E')}")
    gp = os.path.join(HERE, "audit_gate_year.csv")
    if os.path.exists(gp):
        L.append("[게이트 감사 연도별]")
        for _, r in pd.read_csv(gp).iterrows():
            L.append(f"  {int(r['year'])}: 롱신호{r['long_sig']} 숏신호{r['short_sig']} 무덤차단{r['blocked']} 진입{r['entered']} 보유중{r['inpos']}")
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
