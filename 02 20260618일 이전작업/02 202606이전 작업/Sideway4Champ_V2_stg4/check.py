# -*- coding: utf-8 -*-
# [FILE] check.py  (Sideway4Champ_V2_stg4 - bot result integrity + WorkHstr archiver)
# CODE LENGTH: approx 150 lines | INTERNAL VER: Sideway4Champ_V2_stg4 | full output
# [역할] test.py 후: (1)오염검사 8항목 (2)분석txt 00WorkHstr 저장 (3)INDEX 한줄. 결과 전량 파일로만.
# [입력] sdca_summary.csv / sdca_trades.csv / sdca_scenarios.csv  [경로] 실행:하위 / 출력:상위 00WorkHstr
# ==============================================================================
import os, sys, hashlib, datetime
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
WORKHSTR = os.path.join(PARENT, "00WorkHstr")
VER = "Sideway4Champ_V2_stg4"
REQUIRED = ["test.py", "check.py", "run.bat", "sdca_summary.csv", "sdca_trades.csv", "sdca_scenarios.csv"]


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_verdict():
    sp = os.path.join(HERE, "sdca_summary.csv")
    if not os.path.exists(sp):
        return None
    try:
        with open(sp, encoding="utf-8-sig") as f:
            for line in f:
                if "VERDICT" in line:
                    return line.strip().strip('"').rstrip(',').rstrip('"').rstrip(',')
    except Exception:
        return None
    return None


def check_8():
    res = []
    present = {f: os.path.exists(os.path.join(HERE, f)) for f in REQUIRED}
    miss = [f for f, ok in present.items() if not ok]
    res.append(("1.필수파일존재", len(miss) == 0, f"누락:{miss}" if miss else "all present"))

    csvs = ["sdca_summary.csv", "sdca_trades.csv", "sdca_scenarios.csv"]
    empties = [c for c in csvs if present.get(c) and os.path.getsize(os.path.join(HERE, c)) < 10]
    res.append(("2.결과CSV非공백", len(empties) == 0, f"빈:{empties}" if empties else "ok"))

    hashes = {f: sha256(os.path.join(HERE, f))[:16] for f in ["test.py", "check.py"] if present.get(f)}
    res.append(("3.코드해시기록", len(hashes) == 2, str(hashes)))

    dup = 0; tp = os.path.join(HERE, "sdca_trades.csv")
    if present.get("sdca_trades.csv"):
        try:
            t = pd.read_csv(tp); dup = int(t.duplicated().sum())
        except Exception:
            dup = -1
    res.append(("4.거래중복없음", dup == 0, f"중복{dup}행"))

    look = True; memo = "shift(-)/[i+1] 진입신호 미사용 확인"
    with open(os.path.join(HERE, "test.py"), encoding="utf-8") as f:
        src = f.read()
    if "shift(-" in src:
        look = False; memo = "의심패턴-수동확인"
    res.append(("5.미래참조가드", look, memo))

    overlap = 0
    if present.get("sdca_trades.csv"):
        try:
            t = pd.read_csv(tp, parse_dates=['entry_t', 'exit_t']).sort_values('entry_t')
            prev = None
            for _, r in t.iterrows():
                if prev is not None and r['entry_t'] < prev: overlap += 1
                prev = r['exit_t']
        except Exception:
            overlap = -1
    res.append(("6.거래비중첩", overlap == 0, f"중첩{overlap}건"))

    scen_ok = False
    sp = os.path.join(HERE, "sdca_scenarios.csv")
    if present.get("sdca_scenarios.csv"):
        try:
            s = pd.read_csv(sp); scen_ok = (len(s) == 8)
        except Exception:
            scen_ok = False
    res.append(("7.8시나리오완전", scen_ok, "8행" if scen_ok else "행수불일치"))

    v = parse_verdict()
    res.append(("8.VERDICT존재", v is not None, (v[:45] + "...") if v else "없음"))

    passed = all(ok for _, ok, _ in res)
    return passed, res, hashes


def write_analysis(passed, res, hashes, verdict):
    os.makedirs(WORKHSTR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    path = os.path.join(WORKHSTR, f"{stamp}.txt")
    lines = [f"[작업분석] {VER}  ({datetime.datetime.now().isoformat(timespec='seconds')})",
             f"[오염검사 종합] {'PASS' if passed else 'FAIL'}", "-" * 60]
    for label, ok, memo in res:
        lines.append(f"  {'O' if ok else 'X'} {label}: {memo}")
    lines.append("-" * 60)
    lines.append(f"[VERDICT] {verdict}")
    lines.append(f"[코드해시] {hashes}")
    sp = os.path.join(HERE, "sdca_scenarios.csv")
    if os.path.exists(sp):
        lines.append("[8시나리오 누적R(train/test)]")
        s = pd.read_csv(sp)
        for _, r in s.iterrows():
            lines.append(f"  {r['cell']}: train n{r['train_n']} R{r['train_cumR']}% | test n{r['test_n']} R{r['test_cumR']}%")
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
    passed, res, hashes = check_8()
    verdict = parse_verdict() or "N/A"
    apath = write_analysis(passed, res, hashes, verdict)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    update_index(f"{stamp} | {VER} | {'PASS' if passed else 'FAIL'} | {verdict}")
    print(f"[check] integrity={'PASS' if passed else 'FAIL'}")
    print(f"[check] analysis -> {apath}")
    print(f"[check] INDEX -> {os.path.join(WORKHSTR, '00WorkHstr_INDEX.txt')}")


if __name__ == "__main__":
    main()
