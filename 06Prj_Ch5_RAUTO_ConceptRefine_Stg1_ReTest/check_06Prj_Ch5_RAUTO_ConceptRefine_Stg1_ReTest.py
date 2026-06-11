# -*- coding: utf-8 -*-
# [파일명] check_06Prj_Ch5_RAUTO_ConceptRefine_Stg1_ReTest.py
# 코드길이: 약 185줄 | 내부버전: RAUTO_ConceptRefine_06_Ch5_Stg1_ReTest | 로직 전체 출력
# [역할] test.py 후: (1)오염검사 10항목 (2)분석txt를 상위 00WorkHstr 저장 (3)INDEX 한줄 추가. 결과 전량 파일로만.
# [입력] retest_summary/exposure/trend_trades/sdca_trades/scenarios.csv + .retest_metric + bots/엔진2 (하위 실행폴더)
# [출력] D:\ML\Verify\00WorkHstr\(분단위시각).txt + 00WorkHstr_INDEX.txt
# [검사 10항목]
#   1.필수파일존재 2.결과CSV非공백 3.코드해시기록 4.거래중복없음 5.미래참조가드(shift- 스캔)
#   6.거래비중첩 7.노출스윕완전(추세>=8·횡보>=8·시나리오8) 8.VERDICT존재
#   9.★엔진원본일치(bots 2파일 sha256==기대값, 무수정 증빙) 10.노출/청산점검작동(n_liq칼럼+최대안전노출)
# [함수 In->Out] sha256(p)->해시 / strip_comments(src)->주석제거코드 / parse_verdict()->문자열
#                read_metric()->dict / check_all()->(passed,res,hashes,metric) / write_analysis(..)->txt경로
#                update_index(line)->INDEX append / main()->실행
# ==============================================================================
import os, sys, hashlib, datetime, re, io, tokenize
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
WORKHSTR = os.path.join(PARENT, "00WorkHstr")
VER = "RAUTO_ConceptRefine_06_Ch5_Stg1_ReTest"
TESTPY = "test_06Prj_Ch5_RAUTO_ConceptRefine_Stg1_ReTest.py"
CHECKPY = "check_06Prj_Ch5_RAUTO_ConceptRefine_Stg1_ReTest.py"
TREND_ENGINE = os.path.join("bots", "SpTrd_Fib_V1_Champion.py")
SDCA_ENGINE = os.path.join("bots", "SidewayDCA_Stg7_engine.py")

# ★원본 엔진 기대 해시(무수정 증빙). 빌드시 sha256 — 한 글자라도 다르면 9번 FAIL.
EXPECT_HASH = {
    TREND_ENGINE: "7f9192e3d50b1afd659a02b9e75764e5438ad57809c93093ab5f1973bb79ca75",
    SDCA_ENGINE:  "dfdfac4394cd780939d4b368d3ccabfbfab8d599ff1236b11f7f0d80f0823086",
}

REQUIRED = [TESTPY, CHECKPY, "run.bat", TREND_ENGINE, SDCA_ENGINE,
            "retest_summary.csv", "retest_exposure.csv",
            "retest_trend_trades.csv", "retest_sdca_trades.csv", "retest_scenarios.csv"]


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
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_verdict():
    sp = os.path.join(HERE, "retest_summary.csv")
    if not os.path.exists(sp):
        return None
    try:
        with open(sp, encoding="utf-8-sig") as f:
            for line in f:
                if "VERDICT" in line:
                    return line.strip().strip('"').rstrip(',').rstrip('"')
    except Exception:
        return None
    return None


def read_metric():
    p = os.path.join(HERE, ".retest_metric"); d = {}
    if os.path.exists(p):
        for ln in open(p, encoding="utf-8"):
            if "=" in ln:
                k, v = ln.strip().split("=", 1); d[k] = v
    return d


def check_all():
    res = []
    present = {f: os.path.exists(os.path.join(HERE, f)) for f in REQUIRED}
    miss = [f for f, ok in present.items() if not ok]
    res.append(("1.필수파일존재", len(miss) == 0, f"누락:{miss}" if miss else "all present"))

    csvs = ["retest_summary.csv", "retest_exposure.csv", "retest_trend_trades.csv",
            "retest_sdca_trades.csv", "retest_scenarios.csv"]
    empties = [c for c in csvs if present.get(c) and os.path.getsize(os.path.join(HERE, c)) < 10]
    res.append(("2.결과CSV非공백", len(empties) == 0, f"빈:{empties}" if empties else "ok"))

    hashes = {f: sha256(os.path.join(HERE, f))[:16] for f in [TESTPY, CHECKPY] if present.get(f)}
    res.append(("3.코드해시기록", len(hashes) == 2, str(hashes)))

    dup = 0
    for tf in ["retest_trend_trades.csv", "retest_sdca_trades.csv"]:
        if present.get(tf):
            try:
                t = pd.read_csv(os.path.join(HERE, tf)); dup += int(t.duplicated().sum())
            except Exception:
                dup = -1
    res.append(("4.거래중복없음", dup == 0, f"중복{dup}행"))

    look = True; memo = "음수shift/미래봉 미사용(주석제외, 하네스+엔진2 검사)"
    for f in [TESTPY, TREND_ENGINE, SDCA_ENGINE]:
        if present.get(f):
            code = strip_comments(open(os.path.join(HERE, f), encoding="utf-8").read())
            if re.search(r"shift\(\s*-\s*\d", code):
                look = False; memo = f"{f}: 실제 음수shift 발견-수동확인"
                break
    res.append(("5.미래참조가드", look, memo))

    overlap = 0
    for tf in ["retest_trend_trades.csv", "retest_sdca_trades.csv"]:
        if present.get(tf):
            try:
                t = pd.read_csv(os.path.join(HERE, tf), parse_dates=['entry_t', 'exit_t']).sort_values('entry_t')
                prev = None
                for _, r in t.iterrows():
                    if prev is not None and r['entry_t'] < prev:
                        overlap += 1
                    prev = r['exit_t']
            except Exception:
                overlap = -1
    res.append(("6.거래비중첩(봇별)", overlap == 0, f"중첩{overlap}건"))

    sweep_ok = False; sm = "노출행 부족"
    ep = os.path.join(HERE, "retest_exposure.csv")
    if present.get("retest_exposure.csv"):
        try:
            e = pd.read_csv(ep)
            n_tr = int(e['bot'].astype(str).str.contains('추세').sum())
            n_sd = int(e['bot'].astype(str).str.contains('횡보').sum())
            sc = pd.read_csv(os.path.join(HERE, "retest_scenarios.csv")) if present.get("retest_scenarios.csv") else None
            n_sc = len(sc) if sc is not None else 0
            sweep_ok = (n_tr >= 8 and n_sd >= 8 and n_sc == 8)
            sm = f"추세{n_tr}·횡보{n_sd}·시나리오{n_sc}"
        except Exception as e2:
            sm = f"확인실패:{e2}"
    res.append(("7.노출스윕완전", sweep_ok, sm))

    v = parse_verdict()
    res.append(("8.VERDICT존재", v is not None, (v[:50] + "...") if v else "없음"))

    eng_ok = True; eng_memo = []
    for f, exp in EXPECT_HASH.items():
        if present.get(f):
            got = sha256(os.path.join(HERE, f))
            ok = (got == exp); eng_ok = eng_ok and ok
            eng_memo.append(f"{os.path.basename(f)}={'일치' if ok else '★불일치'}")
        else:
            eng_ok = False; eng_memo.append(f"{os.path.basename(f)}=없음")
    res.append(("9.엔진원본일치(무수정증빙)", eng_ok, " ".join(eng_memo)))

    liq_ok = False; lm = "n_liq칼럼/최대안전노출 없음"
    metric = read_metric()
    if present.get("retest_exposure.csv"):
        try:
            e = pd.read_csv(ep)
            has_nliq = 'n_liq' in e.columns
            has_safe = ('trend_safe_E' in metric and 'sdca_safe_E' in metric)
            liq_ok = has_nliq and has_safe
            lm = f"n_liq칼럼={has_nliq} 추세안전E={metric.get('trend_safe_E')} 횡보안전E={metric.get('sdca_safe_E')}"
        except Exception as e2:
            lm = f"확인실패:{e2}"
    res.append(("10.노출/청산점검작동", liq_ok, lm))

    passed = all(ok for _, ok, _ in res)
    return passed, res, hashes, metric


def write_analysis(passed, res, hashes, verdict, metric):
    os.makedirs(WORKHSTR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    path = os.path.join(WORKHSTR, f"{stamp}.txt")
    lines = [f"[작업분석] {VER}  ({datetime.datetime.now().isoformat(timespec='seconds')})",
             f"[오염검사 종합] {'PASS' if passed else 'FAIL'}", "-" * 60]
    for label, ok, memo in res:
        lines.append(f"  {'O' if ok else 'X'} {label}: {memo}")
    lines.append("-" * 60)
    lines.append(f"[VERDICT] {verdict}")
    lines.append(f"[비용/펀딩] 왕복 {metric.get('cost_rt')} / {metric.get('funding')}")
    lines.append(f"[최대안전노출] 추세 E={metric.get('trend_safe_E')} 횡보 E={metric.get('sdca_safe_E')} (MDD한도 {metric.get('mdd_limit')}%)")
    lines.append(f"[코드해시] {hashes}")
    ep = os.path.join(HERE, "retest_exposure.csv")
    if os.path.exists(ep):
        lines.append("[노출스윕]")
        for _, r in pd.read_csv(ep).iterrows():
            lines.append(f"  {r['bot']} E{r['E_노출']}: PF{r['PF']} cumR{r['cumR_pct']}% MDD{r['MDD_pct']}% 청산{r['n_liq']} -> {r['verdict']}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path


def update_index(one_line):
    os.makedirs(WORKHSTR, exist_ok=True)
    idx = os.path.join(WORKHSTR, "00WorkHstr_INDEX.txt")
    header_needed = not os.path.exists(idx)
    with open(idx, "a", encoding="utf-8") as f:
        if header_needed:
            f.write("# 00WorkHstr INDEX | 시각 | 버전 | 검사 | 핵심성과\n")
        f.write(one_line + "\n")


def main():
    passed, res, hashes, metric = check_all()
    verdict = parse_verdict() or "N/A"
    apath = write_analysis(passed, res, hashes, verdict, metric)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    update_index(f"{stamp} | {VER} | {'PASS' if passed else 'FAIL'} | {verdict}")
    print(f"[check] integrity={'PASS' if passed else 'FAIL'}")
    print(f"[check] analysis -> {apath}")
    print(f"[check] INDEX -> {os.path.join(WORKHSTR, '00WorkHstr_INDEX.txt')}")


if __name__ == "__main__":
    main()
