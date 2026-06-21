# -*- coding: utf-8 -*-
# [파일명] check_06Prj_Ch5_RAUTO_ConceptRefine_Stg4_StreakML.py
# 코드길이: 약 160줄 | 내부버전: RAUTO_ConceptRefine_06_Ch5_Stg4_StreakML | 로직 전체 출력
# [역할] test 후: 오염검사 10항목 + 분석txt(상위 00WorkHstr) + INDEX 한줄. 결과 전량 파일로만.
# [검사 10항목]
#   1.필수파일 2.CSV非공백 3.코드해시 4.특징행중복없음 5.미래참조가드(shift- 스캔)
#   6.★특징행수=엔진거래수 7.★라벨무결(시작<=출혈) 8.AUC산출(단변량+다변량검증) 9.엔진원본해시 10.VERDICT
# ==============================================================================
import os, sys, hashlib, datetime, re, io, tokenize
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
WORKHSTR = os.path.join(PARENT, "00WorkHstr")
VER = "RAUTO_ConceptRefine_06_Ch5_Stg4_StreakML"
TESTPY = "test_06Prj_Ch5_RAUTO_ConceptRefine_Stg4_StreakML.py"
CHECKPY = "check_06Prj_Ch5_RAUTO_ConceptRefine_Stg4_StreakML.py"
TREND_ENGINE = os.path.join("bots", "SpTrd_Fib_V1_Champion.py")
SDCA_ENGINE = os.path.join("bots", "SidewayDCA_Stg7_engine.py")
EXPECT_HASH = {
    TREND_ENGINE: "7f9192e3d50b1afd659a02b9e75764e5438ad57809c93093ab5f1973bb79ca75",
    SDCA_ENGINE:  "dfdfac4394cd780939d4b368d3ccabfbfab8d599ff1236b11f7f0d80f0823086",
}
REQUIRED = [TESTPY, CHECKPY, "run.bat", TREND_ENGINE, SDCA_ENGINE,
            "streakml_summary.csv", "streakml_univariate.csv", "streakml_features.csv"]


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
    p = os.path.join(HERE, ".streakml_metric"); d = {}
    if os.path.exists(p):
        for ln in open(p, encoding="utf-8"):
            if "=" in ln:
                k, v = ln.strip().split("=", 1); d[k] = v
    return d


def parse_verdict():
    p = os.path.join(HERE, "streakml_summary.csv")
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
    if present.get("streakml_features.csv"):
        try:
            dup = int(pd.read_csv(os.path.join(HERE, "streakml_features.csv")).duplicated().sum())
        except Exception:
            dup = -1
    res.append(("4.특징행중복없음", dup == 0, f"중복{dup}행"))

    look = True; memo = "음수shift 미사용(주석제외, 하네스+엔진) — 특징은 과거봉만"
    for f in [TESTPY, TREND_ENGINE, SDCA_ENGINE]:
        if present.get(f):
            if re.search(r"shift\(\s*-\s*\d", strip_comments(open(os.path.join(HERE, f), encoding="utf-8").read())):
                look = False; memo = f"{f}: 음수shift 발견"; break
    res.append(("5.미래참조가드", look, memo))

    nrows = -1; nt = int(m.get("n_trades", -1) or -1)
    if present.get("streakml_features.csv"):
        try:
            nrows = len(pd.read_csv(os.path.join(HERE, "streakml_features.csv")))
        except Exception:
            nrows = -2
    res.append(("6.특징행수=엔진거래수", nrows == nt and nt > 0, f"특징{nrows} vs 엔진{nt}"))

    nstreak = int(m.get("n_streak", -1) or -1); nstart = int(m.get("n_start", -1) or -1)
    lab_ok = (0 <= nstart <= nstreak) and nstreak >= 0
    res.append(("7.라벨무결(시작<=출혈)", lab_ok, f"출혈{nstreak} 시작{nstart}"))

    auc_ok = False; am = "AUC 없음"
    if present.get("streakml_univariate.csv"):
        try:
            u = pd.read_csv(os.path.join(HERE, "streakml_univariate.csv"))
            has_auc = ('auc' in u.columns and len(u) >= 5)
            has_mv = ('auc_in_te' in m and 'auc_st_te' in m)
            auc_ok = has_auc and has_mv
            am = f"단변량{len(u)}특징, 다변량 in_streak검증AUC={m.get('auc_in_te')}"
        except Exception as e:
            am = f"확인실패:{e}"
    res.append(("8.AUC산출(단·다변량)", auc_ok, am))

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
    L.append(f"[예측가능성] in_streak 검증AUC {m.get('auc_in_te')}(학습{m.get('auc_in_tr')}) / "
             f"streak_start 검증 {m.get('auc_st_te')} -> {m.get('feasible')}")
    L.append(f"[최강특징] {m.get('top_feature')} (AUC {m.get('top_auc')}) | sklearn={m.get('have_sklearn')}")
    up = os.path.join(HERE, "streakml_univariate.csv")
    if os.path.exists(up):
        L.append("[단변량 분리력]")
        for _, r in pd.read_csv(up).iterrows():
            L.append(f"  {r['feature']}: AUC{r['auc']} 효과크기{r['effect_size']} (출혈{r['mean_in']} vs 정상{r['mean_out']})")
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
