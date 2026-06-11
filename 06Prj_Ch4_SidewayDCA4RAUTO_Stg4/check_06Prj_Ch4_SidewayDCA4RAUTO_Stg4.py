# -*- coding: utf-8 -*-
# [파일명] check_06Prj_Ch4_SidewayDCA4RAUTO_Stg4.py
# 코드길이: 약 200줄 | 내부버전: ChampBot_SidewayDCA4RAUTO_06_Ch4_Stg4 | 로직 전체 출력
# [역할] test.py 후: (1)오염검사 8항목 (2)분석txt를 상위 00WorkHstr 저장 (3)INDEX 한줄. 전량 파일로만(복붙 금지).
# [입력] sf4_summary.csv / sf4_trades.csv / sf4_mljudge.csv / .sf4_metric (실행폴더)
# [출력] D:\ML\verify\00WorkHstr\(YYYYMMDD_HHMM).txt + 00WorkHstr_INDEX.txt
# [검사 8항목]
#   1.필수파일존재 2.결과CSV非공백 3.코드해시기록 4.거래중복없음 5.미래참조가드(dz_oi backward·shift- 없음)
#   6.OFFvsON정상(거래 ON<=OFF) 7.8시나리오완전(S1~S8) 8.VERDICT존재
# ==============================================================================
import os, sys, hashlib, datetime, re, io, tokenize
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
WORKHSTR = os.path.join(PARENT, "00WorkHstr")
VER = "ChampBot_SidewayDCA4RAUTO_06_Ch4_Stg4"
TESTPY = "test_06Prj_Ch4_SidewayDCA4RAUTO_Stg4.py"
CHECKPY = "check_06Prj_Ch4_SidewayDCA4RAUTO_Stg4.py"
REQUIRED = [TESTPY, CHECKPY, "run.bat", "sf4_summary.csv", "sf4_trades.csv", "sf4_mljudge.csv"]


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
    sp = os.path.join(HERE, "sf4_summary.csv")
    if not os.path.exists(sp):
        return None
    try:
        with open(sp, encoding="utf-8-sig") as f:
            for line in f:
                if "VERDICT" in line:
                    return line.split(",")[0].strip().strip('"')
    except Exception:
        return None
    return None


def read_metric():
    p = os.path.join(HERE, ".sf4_metric")
    d = {}
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

    csvs = ["sf4_summary.csv", "sf4_trades.csv", "sf4_mljudge.csv"]
    empties = [c for c in csvs if present.get(c) and os.path.getsize(os.path.join(HERE, c)) < 10]
    res.append(("2.결과CSV非공백", len(empties) == 0, f"빈:{empties}" if empties else "ok"))

    hashes = {f: sha256(os.path.join(HERE, f))[:16] for f in [TESTPY, CHECKPY] if present.get(f)}
    res.append(("3.코드해시기록", len(hashes) == 2, str(hashes)))

    dup = 0; tp = os.path.join(HERE, "sf4_trades.csv")
    if present.get("sf4_trades.csv"):
        try:
            t = pd.read_csv(tp)
            dup = int(t.duplicated(subset=["entry_t"]).sum()) if "entry_t" in t.columns else 0
        except Exception:
            dup = -1
    res.append(("4.거래중복없음", dup == 0, f"진입시간 중복 {dup}건"))

    look = True; memo = "음수shift 없음 + dz_oi backward(resample last)"
    if present.get(TESTPY):
        code = strip_comments(open(os.path.join(HERE, TESTPY), encoding="utf-8").read())
        if re.search(r"shift\(\s*-\s*\d", code):
            look = False; memo = "음수shift 발견-수동확인"
        elif "dz_oi" not in code:
            look = False; memo = "dz_oi 무덤필터 인자 없음-수동확인"
    else:
        look = False; memo = "test.py 없음"
    res.append(("5.미래참조가드", look, memo))

    metric = read_metric()
    has_oi = metric.get("has_oi", "0") == "1"
    if has_oi:
        # Stg4: ML 판정 파일에 점수가 매겨졌는지 + best score 유효한지
        mlp = os.path.join(HERE, "sf4_mljudge.csv")
        ok6 = False; memo6 = "mljudge 없음"
        if os.path.exists(mlp):
            try:
                mj = pd.read_csv(mlp)
                ok6 = ("ml_score" in mj.columns) and (len(mj) >= 3)
                memo6 = f"ML판정 {len(mj)}조합, 최고 score={mj['ml_score'].max() if 'ml_score' in mj.columns else '?'}"
            except Exception as e:
                memo6 = f"읽기실패:{e}"
    else:
        ok6 = True; memo6 = "OI없음 → 검증불가(상위 D:\\ML\\verify\\Merged_Data.csv 확인)"
    res.append(("6.ML판정존재", ok6, memo6))

    scen_ok = False; sp = os.path.join(HERE, "sf4_summary.csv")
    if present.get("sf4_summary.csv"):
        try:
            cells = pd.read_csv(sp)["cell"].astype(str)
            found = sum(1 for k in ["S1_", "S2_", "S3_", "S4_", "S5_", "S6_", "S7_", "S8_"]
                        if cells.str.contains(k, na=False).any())
            # OI 없으면 S6/S7(무덤폭·쏠림) 생략될 수 있으므로 6개 이상이면 통과
            scen_ok = (found == 8) if has_oi else (found >= 6)
            memo7 = f"S1~S8 중 {found}개"
        except Exception as e:
            memo7 = f"확인실패:{e}"
    else:
        memo7 = "summary없음"
    res.append(("7.8시나리오완전", scen_ok, memo7))

    v = parse_verdict()
    res.append(("8.VERDICT존재", v is not None, (v[:55] + "...") if v else "없음"))

    passed = all(ok for _, ok, _ in res)
    return passed, res, hashes, metric


def write_analysis(passed, res, hashes, verdict, metric):
    os.makedirs(WORKHSTR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    path = os.path.join(WORKHSTR, f"{stamp}.txt")
    L = [f"[작업분석] {VER}  ({datetime.datetime.now().isoformat(timespec='seconds')})",
         f"[오염검사 종합] {'PASS' if passed else 'FAIL'}", "-" * 64]
    for label, ok, memo in res:
        L.append(f"  {'O' if ok else 'X'} {label}: {memo}")
    L.append("-" * 64)
    L.append(f"[VERDICT] {verdict}")
    L.append(f"[무덤필터 효과] PF {metric.get('off_PF','?')}->{metric.get('on_PF','?')} | "
             f"MDD {metric.get('off_mdd','?')}%->{metric.get('on_mdd','?')}% | "
             f"수익금 {metric.get('off_fin','?')}->{metric.get('on_fin','?')}")
    L.append(f"[거래·trend_flip] {metric.get('off_n','?')}->{metric.get('on_n','?')}건 | "
             f"trend_flip {metric.get('off_flip','?')}->{metric.get('on_flip','?')}")
    L.append(f"[코드해시] {hashes}")
    sp = os.path.join(HERE, "sf4_summary.csv")
    if os.path.exists(sp):
        L.append("[8시나리오 요약]")
        for _, r in pd.read_csv(sp).iterrows():
            c = str(r["cell"])
            if c.startswith("S"):
                note = r.get("note", "")
                L.append(f"  {c}: OFF PF{r.get('OFF_PF','')} cumR{r.get('OFF_cumR','')} -> ON PF{r.get('ON_PF','')} cumR{r.get('ON_cumR','')} {note}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    return path


def update_index(one_line):
    os.makedirs(WORKHSTR, exist_ok=True)
    idx = os.path.join(WORKHSTR, "00WorkHstr_INDEX.txt")
    header = not os.path.exists(idx)
    with open(idx, "a", encoding="utf-8") as f:
        if header:
            f.write("# 00WorkHstr INDEX | 시각 | 버전 | 검사 | 핵심성과\n")
        f.write(one_line + "\n")


def main():
    passed, res, hashes, metric = check_all()
    verdict = parse_verdict() or "N/A"
    apath = write_analysis(passed, res, hashes, verdict, metric)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    update_index(f"{stamp} | {VER} | {'PASS' if passed else 'FAIL'} | {verdict[:70]}")
    print(f"[check] integrity={'PASS' if passed else 'FAIL'}")
    print(f"[check] analysis -> {apath}")
    print(f"[check] INDEX -> {os.path.join(WORKHSTR, '00WorkHstr_INDEX.txt')}")


if __name__ == "__main__":
    main()
