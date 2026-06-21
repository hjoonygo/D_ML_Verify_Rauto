# -*- coding: utf-8 -*-
# [FILE] check_05Alpha_UpCh1_stg2_Sideway4Champ_Vrfy.py
# 코드길이: 약 175줄 | 내부버전명: 05Alpha_Up_Ch1_S4C_Vrfy_stg2 | 전체 출력, 축약/생략 없음
# [역할] test.py 실행 후: (1)오염검사 8항목 (2)분석txt를 상위 00WorkHstr에 저장 (3)INDEX 1줄 추가.
#        결과는 전량 파일로만(복붙 요청 없음).
# [입력] s4c_summary.csv / s4c_trades.csv / s4c_monthly.csv / s4c_scenarios.csv
# [출력] D:\ML\verify\00WorkHstr\(분단위시간).txt + 00WorkHstr_INDEX.txt
# [경로] 실행: 하위폴더 / 히스토리: 상위 PARENT\00WorkHstr
# [8항목] 1.필수파일 2.CSV非공백 3.코드해시 4.거래중복 5.미래참조가드 6.거래비중첩
#         7.월별-거래합 일치(롱숏 합 = 전체) 8.VERDICT존재
# [FUNCTIONS]
#   sha256(p)/parse_verdict()/check_8()/write_analysis()/update_index()/main()  (stg1 check와 동형)
# ==============================================================================
import os, sys, hashlib, datetime
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
WORKHSTR = os.path.join(PARENT, "00WorkHstr")
VER = "05Alpha_Up_Ch1_S4C_Vrfy_stg2"
TEST_PY  = "test_05Alpha_UpCh1_stg2_Sideway4Champ_Vrfy.py"
CHECK_PY = "check_05Alpha_UpCh1_stg2_Sideway4Champ_Vrfy.py"
REQUIRED = [TEST_PY, CHECK_PY, "run.bat",
            "s4c_summary.csv", "s4c_trades.csv", "s4c_monthly.csv", "s4c_scenarios.csv"]


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_verdict():
    sp = os.path.join(HERE, "s4c_summary.csv")
    if not os.path.exists(sp):
        return None
    with open(sp, encoding="utf-8-sig") as f:
        for line in f:
            if "VERDICT" in line:
                return line.strip().strip('"').rstrip(',')
    return None


def check_8():
    res = []
    present = {f: os.path.exists(os.path.join(HERE, f)) for f in REQUIRED}
    miss = [f for f, ok in present.items() if not ok]
    res.append(("1.필수파일존재", len(miss) == 0, f"누락:{miss}" if miss else "all present"))

    csvs = ["s4c_summary.csv", "s4c_trades.csv", "s4c_monthly.csv", "s4c_scenarios.csv"]
    empties = [c for c in csvs if present.get(c) and os.path.getsize(os.path.join(HERE, c)) < 10]
    res.append(("2.결과CSV非공백", len(empties) == 0, f"빈:{empties}" if empties else "ok"))

    hashes = {f: sha256(os.path.join(HERE, f))[:16] for f in [TEST_PY, CHECK_PY] if present.get(f)}
    res.append(("3.코드해시기록", len(hashes) == 2, str(hashes)))

    tp = os.path.join(HERE, "s4c_trades.csv"); dup = 0
    t = None
    if present.get("s4c_trades.csv"):
        try:
            t = pd.read_csv(tp); dup = int(t.duplicated().sum())
        except Exception:
            dup = -1
    res.append(("4.거래중복없음", dup == 0, f"중복{dup}행"))

    # 5.미래참조: 실제 코드라인만(주석 제외). 진입은 open_[i+1] 체결만 허용
    look = True; memo = "미래참조 패턴 미사용(체결 open_[i+1] 확인)"
    with open(os.path.join(HERE, TEST_PY), encoding="utf-8") as f:
        lines = f.readlines()
    bad = []
    for ln, raw in enumerate(lines, 1):
        c = raw.split("#", 1)[0].replace(" ", "")
        if (".shift(-" in c) or (".iloc[i+1]" in c):
            bad.append(ln)
        if ("[i+1]" in c) and ("open_[i+1]" not in c) and ("i+1<n" not in c):
            bad.append(ln)
    if bad:
        look = False; memo = f"의심 코드라인 {sorted(set(bad))} 수동확인"
    res.append(("5.미래참조가드", look, memo))

    # 6.거래비중첩 (sl_mode+side별 시간 겹침)
    overlap = 0
    if t is not None and len(t) and 'entry_t' in t.columns:
        try:
            tt = t.copy()
            tt['entry_t'] = pd.to_datetime(tt['entry_t']); tt['exit_t'] = pd.to_datetime(tt['exit_t'])
            for _, g in tt.groupby(['sl_mode', 'side']):
                g = g.sort_values('entry_t'); prev = None
                for _, r in g.iterrows():
                    if prev is not None and r['entry_t'] < prev:
                        overlap += 1
                    prev = r['exit_t']
        except Exception:
            overlap = -1
    res.append(("6.거래비중첩", overlap == 0, f"중첩{overlap}건(모드x방향)"))

    # 7.월별-거래합 일치: 월별 trades 합계가 전체 거래수와 일치(모드별)
    ok7 = False; memo7 = "검증불가"
    mp = os.path.join(HERE, "s4c_monthly.csv")
    if t is not None and present.get("s4c_monthly.csv"):
        try:
            m = pd.read_csv(mp)
            if len(m) == 0 and len(t) == 0:
                ok7 = True; memo7 = "양쪽 0건(표본부족)"
            else:
                chk = []
                for sm in t['sl_mode'].unique():
                    tot = len(t[t.sl_mode == sm])
                    msum = int(m[m.sl_mode == sm]['trades'].sum()) if len(m) else 0
                    chk.append(tot == msum)
                ok7 = all(chk) if chk else (len(t) == 0)
                memo7 = f"월별합=거래수 일치:{ok7}"
        except Exception as e:
            memo7 = f"err {e}"
    elif t is not None and len(t) == 0:
        ok7 = True; memo7 = "거래 0건"
    res.append(("7.월별-거래합일치", ok7, memo7))

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
    mp = os.path.join(HERE, "s4c_monthly.csv")
    if os.path.exists(mp):
        try:
            m = pd.read_csv(mp)
            if len(m):
                lines.append("[월별 롱/숏 요약 (앞 24행)]")
                for _, r in m.head(24).iterrows():
                    lines.append(f"  [{r['sl_mode']}] {r['month']} {r['side']}: n{r['trades']} 승{r['win_pct']}% R{r['cumR_pct']}% PF{r['PF']} 손익비{r['payoff']} ${r['pnl_usd']}")
        except Exception:
            pass
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
    update_index(f"{stamp} | {VER} | {'PASS' if passed else 'FAIL'} | {verdict[:120]}")
    print(f"[check] integrity={'PASS' if passed else 'FAIL'}")
    print(f"[check] analysis -> {apath}")
    print(f"[check] INDEX -> {os.path.join(WORKHSTR, '00WorkHstr_INDEX.txt')}")


if __name__ == "__main__":
    main()
