# -*- coding: utf-8 -*-
# [FILE] check_05Alpha_UpCh1_stg1.py
# 코드길이: 약 160줄 | 내부버전명: 05Alpha_Up_Ch1_SLfibAB_stg1 | 전체 출력, 축약/생략 없음
# [역할] test.py 실행 후: (1)오염검사 8항목 (2)분석txt를 상위 00WorkHstr에 저장 (3)INDEX 한 줄 추가.
#        결과는 전량 파일로만 남긴다(복붙 요청 없음).
# [입력] sdca_summary.csv / sdca_trades.csv / sdca_scenarios.csv (실행폴더=하위)
# [출력] D:\ML\verify\00WorkHstr\(분단위시간).txt + 00WorkHstr_INDEX.txt
# [경로] 실행: 하위폴더 / 데이터·히스토리: 상위(PARENT)
# [FUNCTIONS]
#   sha256(p)        In: 파일경로            Out: 해시16자       코드 무결성 지문
#   parse_verdict()  In:(없음)               Out: VERDICT 문자열  summary 첫 줄 추출
#   check_8()        In:(없음)               Out: (passed,res,hashes) 8항목 검사
#   write_analysis() In: 검사결과            Out: 분석txt 경로    00WorkHstr에 분석 저장
#   update_index()   In: 한 줄 문자열        Out:(없음)           INDEX에 1줄 append
#   main()           In:(없음)               Out:(없음)           위 3단계 실행
# [변수] REQUIRED(필수파일목록) res(검사결과리스트) hashes(코드해시) passed(종합통과)
# ==============================================================================
import os, sys, hashlib, datetime
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
WORKHSTR = os.path.join(PARENT, "00WorkHstr")
VER = "05Alpha_Up_Ch1_SLfibAB_stg1"
TEST_PY  = "test_05Alpha_UpCh1_stg1.py"
CHECK_PY = "check_05Alpha_UpCh1_stg1.py"
RUN_BAT  = "run.bat"
REQUIRED = [TEST_PY, CHECK_PY, RUN_BAT,
            "sdca_summary.csv", "sdca_trades.csv", "sdca_scenarios.csv"]


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
    # 1.필수파일존재
    present = {f: os.path.exists(os.path.join(HERE, f)) for f in REQUIRED}
    miss = [f for f, ok in present.items() if not ok]
    res.append(("1.필수파일존재", len(miss) == 0, f"누락:{miss}" if miss else "all present"))

    # 2.결과CSV非공백
    csvs = ["sdca_summary.csv", "sdca_trades.csv", "sdca_scenarios.csv"]
    empties = [c for c in csvs if present.get(c) and os.path.getsize(os.path.join(HERE, c)) < 10]
    res.append(("2.결과CSV非공백", len(empties) == 0, f"빈:{empties}" if empties else "ok"))

    # 3.코드해시기록
    hashes = {f: sha256(os.path.join(HERE, f))[:16] for f in [TEST_PY, CHECK_PY] if present.get(f)}
    res.append(("3.코드해시기록", len(hashes) == 2, str(hashes)))

    # 4.거래중복없음
    dup = 0; tp = os.path.join(HERE, "sdca_trades.csv")
    if present.get("sdca_trades.csv"):
        try:
            t = pd.read_csv(tp); dup = int(t.duplicated().sum())
        except Exception:
            dup = -1
    res.append(("4.거래중복없음", dup == 0, f"중복{dup}행"))

    # 5.미래참조가드: 실제 코드 라인만 스캔(주석 # 이후·설명 문자열 제외해 자기참조 오탐 방지)
    look = True; memo = "미래참조 패턴 미사용(체결 open_[i+1] 확인)"
    with open(os.path.join(HERE, TEST_PY), encoding="utf-8") as f:
        lines = f.readlines()
    bad = []
    for ln, raw in enumerate(lines, 1):
        code = raw.split("#", 1)[0]              # 주석 제거
        c = code.replace(" ", "")
        if (".shift(-" in c) or (".iloc[i+1]" in c) or ("[i+1]" in c and "open_" not in c and "<n" not in c):
            bad.append(ln)
    if bad:
        look = False; memo = f"의심 코드라인 {bad} 수동확인"
    res.append(("5.미래참조가드", look, memo))

    # 6.거래비중첩 (동일 sl_mode 안에서 시간 겹침 검사)
    overlap = 0
    if present.get("sdca_trades.csv"):
        try:
            t = pd.read_csv(tp, parse_dates=['entry_t', 'exit_t'])
            if 'sl_mode' in t.columns:
                groups = [g for _, g in t.groupby('sl_mode')]
            else:
                groups = [t]
            for g in groups:
                g = g.sort_values('entry_t'); prev = None
                for _, r in g.iterrows():
                    if prev is not None and r['entry_t'] < prev: overlap += 1
                    prev = r['exit_t']
        except Exception:
            overlap = -1
    res.append(("6.거래비중첩", overlap == 0, f"중첩{overlap}건(모드별)"))

    # 7.8시나리오완전 (A 8행 + B 8행 = 16행, 또는 한쪽표본부족시 8의 배수)
    scen_ok = False; scen_memo = "행수불일치"
    sp = os.path.join(HERE, "sdca_scenarios.csv")
    if present.get("sdca_scenarios.csv"):
        try:
            s = pd.read_csv(sp)
            ln = len(s)
            scen_ok = (ln in (8, 16)) and (ln % 8 == 0)
            scen_memo = f"{ln}행(8x모드수)"
        except Exception:
            scen_ok = False
    res.append(("7.8시나리오완전", scen_ok, scen_memo))

    # 8.VERDICT존재
    v = parse_verdict()
    res.append(("8.VERDICT존재", v is not None, (v[:50] + "...") if v else "없음"))

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
        lines.append("[8시나리오 누적R (sl_mode별 train/test)]")
        s = pd.read_csv(sp)
        for _, r in s.iterrows():
            mode = r['sl_mode'] if 'sl_mode' in s.columns else '-'
            lines.append(f"  [{mode}] {r['cell']}: train n{r['train_n']} R{r['train_cumR']}% | test n{r['test_n']} R{r['test_cumR']}%")
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
