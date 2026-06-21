# -*- coding: utf-8 -*-
# [FILE] check.py  (Sideway4Champ_V2_stg3 - regime measurement integrity + WorkHstr archiver)
# CODE LENGTH: approx 130 lines | INTERNAL VER: Sideway4Champ_V2_stg3 | full output
# [역할] measure.py 후 호출: (1)오염검사 8항목 (2)분석txt 00WorkHstr 저장 (3)INDEX 한 줄 추가.
#   결과 전량 파일로만(복붙요청 없음).
# [입력] mrv_regime.csv  [경로] 실행:하위폴더 / 출력:상위 00WorkHstr
# ==============================================================================
import os, sys, hashlib, datetime
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
WORKHSTR = os.path.join(PARENT, "00WorkHstr")
VER = "Sideway4Champ_V2_stg3"
REQUIRED = ["measure.py", "check.py", "run.bat", "mrv_regime.csv"]


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_verdict():
    sp = os.path.join(HERE, "mrv_regime.csv")
    if not os.path.exists(sp):
        return None
    try:
        with open(sp, encoding="utf-8-sig") as f:
            first = f.readline().strip()
        return first if "VERDICT" in first else None
    except Exception:
        return None


def check_8():
    res = []
    present = {f: os.path.exists(os.path.join(HERE, f)) for f in REQUIRED}
    miss = [f for f, ok in present.items() if not ok]
    res.append(("1.필수파일존재", len(miss) == 0, f"누락:{miss}" if miss else "all present"))

    cp = os.path.join(HERE, "mrv_regime.csv")
    res.append(("2.결과CSV非공백", present.get("mrv_regime.csv") and os.path.getsize(cp) > 10, "ok"))

    hashes = {f: sha256(os.path.join(HERE, f))[:16] for f in ["measure.py", "check.py"] if present.get(f)}
    res.append(("3.코드해시기록", len(hashes) == 2, str(hashes)))

    dup = 0
    if present.get("mrv_regime.csv"):
        try:
            t = pd.read_csv(cp, skiprows=1); dup = int(t.duplicated().sum())
        except Exception:
            dup = -1
    res.append(("4.결과중복없음", dup == 0, f"중복{dup}행"))

    note_ok = True; memo = "측정용 미래봉(진입신호 아님) 명시됨"
    with open(os.path.join(HERE, "measure.py"), encoding="utf-8") as f:
        src = f.read()
    if "측정" not in src or "미래봉" not in src:
        note_ok = False; memo = "미래봉 주석 누락-확인"
    res.append(("5.측정성격명시", note_ok, memo))

    reg_ok = False; memo6 = "없음"
    if present.get("mrv_regime.csv"):
        try:
            t = pd.read_csv(cp, skiprows=1)
            regs = set(t['regime'].unique())
            need = {'Q_RANGE', 'L_RANGE', 'W_TREND', 'S_TREND'}
            reg_ok = need.issubset(regs); memo6 = f"장세 {sorted(regs)}"
        except Exception:
            reg_ok = False; memo6 = "파싱실패"
    res.append(("6.4장세완전", reg_ok, memo6))

    col_ok = False; memo7 = "없음"
    if present.get("mrv_regime.csv"):
        try:
            t = pd.read_csv(cp, skiprows=1)
            need = {'TF_h', 'period', 'regime', 'dist_atr_max', 'below_revert_pct', 'above_revert_pct'}
            col_ok = need.issubset(set(t.columns)); memo7 = f"{len(t)}행" if col_ok else "컬럼누락"
        except Exception:
            col_ok = False
    res.append(("7.회귀표완전", col_ok, memo7))

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
    lines.append("[해석] Q_RANGE(조용한횡보) 얕은회귀율이 S_TREND(강추세)보다 높으면 stg8게이트 유효.")
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
    print(f"[check] INDEX updated -> {os.path.join(WORKHSTR, '00WorkHstr_INDEX.txt')}")


if __name__ == "__main__":
    main()
