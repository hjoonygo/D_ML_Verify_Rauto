# -*- coding: utf-8 -*-
# [파일명] check_05Prj_Ch1_Stg6_SidewayDCA_AlphaUp.py
# 코드길이: 약 165줄 | 내부버전: SidewayDCA_AlphaUp_05_Ch1_Stg6 | 로직 전체 출력
# [역할] test.py 후: (1)오염검사 8항목+9번 (2)분석txt를 상위 00WorkHstr 저장 (3)INDEX 한줄 추가. 결과 전량 파일로만.
# [입력] sdca_summary.csv / sdca_trades.csv / sdca_scenarios.csv / .intrabar_metric (하위 실행폴더)
# [출력] D:\ML\Verify\00WorkHstr\(분단위시각).txt + 00WorkHstr_INDEX.txt
# [검사 8+1항목]
#   1.필수파일존재 2.결과CSV非공백 3.코드해시기록 4.거래중복없음 5.미래참조가드(shift- 스캔)
#   6.거래비중첩 7.8시나리오완전 8.VERDICT존재 | 9.인트라바모호도기록(정직화 측정증빙)
# [함수 In->Out]
#   sha256(p)            파일경로 -> 해시16
#   parse_verdict()      (없음) -> summary의 VERDICT 문자열 or None
#   read_metric()        (없음) -> .intrabar_metric dict or {}
#   check_all()          (없음) -> (passed, 결과리스트, 해시dict, metric)
#   write_analysis(...)  결과 -> 분석txt 경로
#   update_index(line)   한줄 -> INDEX append
#   main()               실행
# ==============================================================================
import os, sys, hashlib, datetime, re, io, tokenize
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import pandas as pd


def strip_comments(src):
    # 주석(문서설명)은 검사대상 아님. 토큰단위로 주석만 공백처리, 코드 인접성 보존.
    try:
        lines = src.split("\n")
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                sr, sc = tok.start; _, ec = tok.end
                lines[sr - 1] = lines[sr - 1][:sc] + lines[sr - 1][ec:]
        return "\n".join(lines)
    except Exception:
        return src  # 토큰화 실패시 원문 그대로(보수적)

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
WORKHSTR = os.path.join(PARENT, "00WorkHstr")
VER = "SidewayDCA_AlphaUp_05_Ch1_Stg6"
TESTPY = "test_05Prj_Ch1_Stg6_SidewayDCA_AlphaUp.py"
CHECKPY = "check_05Prj_Ch1_Stg6_SidewayDCA_AlphaUp.py"
REQUIRED = [TESTPY, CHECKPY, "run.bat",
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


def read_metric():
    p = os.path.join(HERE, ".intrabar_metric")
    d = {}
    if os.path.exists(p):
        try:
            for ln in open(p, encoding="utf-8"):
                if "=" in ln:
                    k, v = ln.strip().split("=", 1); d[k] = v
        except Exception:
            pass
    return d


def check_all():
    res = []
    present = {f: os.path.exists(os.path.join(HERE, f)) for f in REQUIRED}
    miss = [f for f, ok in present.items() if not ok]
    res.append(("1.필수파일존재", len(miss) == 0, f"누락:{miss}" if miss else "all present"))

    csvs = ["sdca_summary.csv", "sdca_trades.csv", "sdca_scenarios.csv"]
    empties = [c for c in csvs if present.get(c) and os.path.getsize(os.path.join(HERE, c)) < 10]
    res.append(("2.결과CSV非공백", len(empties) == 0, f"빈:{empties}" if empties else "ok"))

    hashes = {f: sha256(os.path.join(HERE, f))[:16] for f in [TESTPY, CHECKPY] if present.get(f)}
    res.append(("3.코드해시기록", len(hashes) == 2, str(hashes)))

    dup = 0; tp = os.path.join(HERE, "sdca_trades.csv")
    if present.get("sdca_trades.csv"):
        try:
            t = pd.read_csv(tp); dup = int(t.duplicated().sum())
        except Exception:
            dup = -1
    res.append(("4.거래중복없음", dup == 0, f"중복{dup}행"))

    look = True; memo = "음수shift/미래봉 미사용(주석제외 코드검사)"
    if present.get(TESTPY):
        with open(os.path.join(HERE, TESTPY), encoding="utf-8") as f:
            src = f.read()
        code = strip_comments(src)                       # 문서설명(주석) 제외 후 실제 코드만 검사
        if re.search(r"shift\(\s*-\s*\d", code):          # 진짜 위험: 음수 정수 shift(=미래값 끌어옴)
            look = False; memo = "실제 음수shift 발견-수동확인 필요"
        elif re.search(r"\[\s*i\s*\+\s*[2-9]\d*\s*\]", code):  # 2봉이상 앞선 인덱스 직접참조 의심
            look = False; memo = "미래봉(i+2이상) 직접참조 의심-수동확인"
    else:
        look = False; memo = "test.py 없음"
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

    scen_ok = False; sp = os.path.join(HERE, "sdca_scenarios.csv")
    if present.get("sdca_scenarios.csv"):
        try:
            s = pd.read_csv(sp); scen_ok = (len(s) == 8)
        except Exception:
            scen_ok = False
    res.append(("7.8시나리오완전", scen_ok, "8행" if scen_ok else "행수불일치"))

    v = parse_verdict()
    res.append(("8.VERDICT존재", v is not None, (v[:45] + "...") if v else "없음"))

    # 9. 인트라바 모호도 기록 — 정직화(1분봉 경로 청산)가 실제로 측정됐는지 증빙
    metric = read_metric()
    has_amb = ("ambig_pct" in metric)
    res.append(("9.인트라바모호도기록", has_amb,
                (f"모호봉 {metric.get('ambig_pct')}% (held {metric.get('held_bars')}봉 중 {metric.get('ambig_bars')}봉)")
                if has_amb else "메트릭없음"))

    # 10. stg6 정밀필터 작동 증빙 — summary에 FILTER 행이 있고 차단건수가 기록됐는지
    filt_ok = False; filt_memo = "FILTER 행 없음"
    sp = os.path.join(HERE, "sdca_summary.csv")
    if os.path.exists(sp):
        try:
            s = pd.read_csv(sp)
            frows = s[s['cell'].astype(str).str.contains('FILTER', na=False)]
            if len(frows) > 0:
                # precise 행의 차단건수(sl_cap_hits 칼럼 재활용)
                pre = frows[frows['cell'].astype(str).str.contains('precise', na=False)]
                if len(pre) > 0:
                    blk = pre.iloc[0].get('sl_cap_hits', '?')
                    filt_ok = True; filt_memo = f"FILTER {len(frows)}변형, precise 차단 {blk}건"
                elif frows['cell'].astype(str).str.contains('불가', na=False).any():
                    filt_ok = True; filt_memo = "atr_ratio 없어 필터 비활성(안전장치 작동)"
        except Exception as e:
            filt_memo = f"확인실패:{e}"
    res.append(("10.정밀필터작동", filt_ok, filt_memo + f" | trades={metric.get('trades_label','?')}"))

    # 11. stg6 OI 2차필터 작동 증빙 — summary에 OI_ 행이 있는지(또는 불가 안전장치)
    oi_ok = False; oi_memo = "OI 행 없음"
    if os.path.exists(sp):
        try:
            s = pd.read_csv(sp)
            orows = s[s['cell'].astype(str).str.contains('OI_', na=False)]
            if len(orows) > 0:
                o2 = orows[orows['cell'].astype(str).str.contains(r'1차\+2차', na=False, regex=True)]
                if len(o2) > 0:
                    r0 = o2.iloc[0]
                    oi_ok = True
                    oi_memo = f"OI {len(orows)}변형, 1차+2차 거래{r0.get('full_trades','?')} PF{r0.get('full_PF','?')}"
                elif orows['cell'].astype(str).str.contains('불가', na=False).any():
                    oi_ok = True; oi_memo = "oi_zscore 없어 2차필터 비활성(안전장치 작동)"
        except Exception as e:
            oi_memo = f"확인실패:{e}"
    res.append(("11.OI2차필터작동", oi_ok, oi_memo))

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
    lines.append(f"[인트라바모호도] {metric.get('ambig_pct','N/A')}%  "
                 f"(8h봉 1개만 보던 OLD가 익절/손절 순서를 추측해야 했던 봉 비율)")
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
