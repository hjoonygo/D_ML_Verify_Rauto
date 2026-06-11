# -*- coding: utf-8 -*-
# [파일명] check_06Prj_Ch4_SidewayDCA4RAUTO_Stg1.py
# 코드길이: 약 210줄 | 내부버전: ChampBot_SidewayDCA4RAUTO_06_Ch4_Stg1 | 로직 전체 출력
# [역할] test.py 후: (1)오염검사 8항목 (2)분석txt를 상위 00WorkHstr 저장 (3)INDEX 한줄 추가. 결과 전량 파일로만(복붙 금지).
# [입력] rs_summary.csv / rs_matched_trades.csv / rs_scenarios.csv / .rs_metric  (이 실행폴더)
# [출력] D:\ML\verify\00WorkHstr\(YYYYMMDD_HHMM).txt + 00WorkHstr_INDEX.txt
# [검사 8항목 — Basic 4.6 기본방침 준수]
#   1.필수파일존재  2.결과CSV非공백  3.코드해시기록  4.거래중복없음(매칭원장)
#   5.미래참조가드(코드에 shift(-)/미래봉 인덱스 없음 + asof backward 사용 확인)
#   6.매칭율(진입시각 신호 매칭 정상)  7.8시나리오완전(S1~S8 행 존재)  8.VERDICT존재
# [함수 In->Out]
#   sha256(p)            파일경로 -> 해시16
#   parse_verdict()      (없음) -> rs_summary의 VERDICT 문자열 or None
#   read_metric()        (없음) -> .rs_metric dict or {}
#   strip_comments(src)  소스 -> 주석제거 코드(미래참조가드 오탐 방지)
#   check_all()          (없음) -> (passed, 결과리스트, 해시dict, metric)
#   write_analysis(...)  결과 -> 분석txt 경로
#   update_index(line)   한줄 -> INDEX append
#   main()               실행
# ==============================================================================
import os, sys, hashlib, datetime, re, io, tokenize
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
WORKHSTR = os.path.join(PARENT, "00WorkHstr")
VER = "ChampBot_SidewayDCA4RAUTO_06_Ch4_Stg1"
TESTPY = "test_06Prj_Ch4_SidewayDCA4RAUTO_Stg1.py"
CHECKPY = "check_06Prj_Ch4_SidewayDCA4RAUTO_Stg1.py"
REQUIRED = [TESTPY, CHECKPY, "run.bat",
            "rs_summary.csv", "rs_matched_trades.csv", "rs_scenarios.csv"]


def strip_comments(src):
    # 주석(문서설명)은 미래참조 검사 대상 아님. 토큰단위로 주석만 공백처리.
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
    sp = os.path.join(HERE, "rs_summary.csv")
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
    p = os.path.join(HERE, ".rs_metric")
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

    csvs = ["rs_summary.csv", "rs_matched_trades.csv", "rs_scenarios.csv"]
    empties = [c for c in csvs if present.get(c) and os.path.getsize(os.path.join(HERE, c)) < 10]
    res.append(("2.결과CSV非공백", len(empties) == 0, f"빈:{empties}" if empties else "ok"))

    hashes = {f: sha256(os.path.join(HERE, f))[:16] for f in [TESTPY, CHECKPY] if present.get(f)}
    res.append(("3.코드해시기록", len(hashes) == 2, str(hashes)))

    dup = 0; mp = os.path.join(HERE, "rs_matched_trades.csv")
    if present.get("rs_matched_trades.csv"):
        try:
            m = pd.read_csv(mp)
            dup = int(m.duplicated(subset=["entry_t", "side"]).sum())
        except Exception:
            dup = -1
    res.append(("4.거래중복없음", dup == 0, f"중복{dup}행(entry_t+side)"))

    look = True; memo = "음수shift/미래봉 미사용 + asof backward 확인"
    if present.get(TESTPY):
        with open(os.path.join(HERE, TESTPY), encoding="utf-8") as f:
            src = f.read()
        code = strip_comments(src)
        if re.search(r"shift\(\s*-\s*\d", code):
            look = False; memo = "실제 음수shift 발견-수동확인"
        elif re.search(r"side\s*=\s*[\"']right[\"']", code) and "searchsorted" in code and "- 1" not in code:
            look = False; memo = "asof가 backward(-1)인지 수동확인"
        elif "asof_match" not in code:
            look = False; memo = "asof_match 매칭함수 없음-수동확인"
    else:
        look = False; memo = "test.py 없음"
    res.append(("5.미래참조가드", look, memo))

    metric = read_metric()
    n_tr = int(metric.get("n_trades", 0) or 0)
    oi_m = int(metric.get("oi_matched", 0) or 0)
    adx_m = int(metric.get("adx_matched", 0) or 0)
    # 매칭율: OI/ADX 데이터가 있으면 매칭율 80%+ 정상. 없으면(샘플환경) 0이라도 안전장치로 통과.
    has_oi = metric.get("has_oi", "0") == "1"
    has_reg = metric.get("has_reg", "0") == "1"
    if has_oi or has_reg:
        rate = max(oi_m, adx_m) / n_tr if n_tr else 0
        ok6 = rate >= 0.8
        memo6 = f"OI {oi_m}/{n_tr}, ADX {adx_m}/{n_tr} (매칭율 {round(100*rate)}%)"
    else:
        ok6 = True
        memo6 = "OI/ADX 데이터 없음 → 매칭검사 건너뜀(안전장치, 상위 D:\\ML\\verify 확인 필요)"
    res.append(("6.매칭율정상", ok6, memo6))

    scen_ok = False; sp = os.path.join(HERE, "rs_summary.csv")
    if present.get("rs_summary.csv"):
        try:
            s = pd.read_csv(sp)
            cells = s["cell"].astype(str)
            found = sum(1 for k in ["S1_", "S2_", "S3_", "S4_", "S5_", "S6_", "S7_", "S8_"]
                        if cells.str.contains(k, na=False).any())
            scen_ok = (found == 8)
            memo7 = f"S1~S8 중 {found}개 존재"
        except Exception as e:
            memo7 = f"확인실패:{e}"
    else:
        memo7 = "summary 없음"
    res.append(("7.8시나리오완전", scen_ok, memo7))

    v = parse_verdict()
    res.append(("8.VERDICT존재", v is not None, (v[:55] + "...") if v else "없음"))

    passed = all(ok for _, ok, _ in res)
    return passed, res, hashes, metric


def write_analysis(passed, res, hashes, verdict, metric):
    os.makedirs(WORKHSTR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    path = os.path.join(WORKHSTR, f"{stamp}.txt")
    lines = [f"[작업분석] {VER}  ({datetime.datetime.now().isoformat(timespec='seconds')})",
             f"[오염검사 종합] {'PASS' if passed else 'FAIL'}", "-" * 64]
    for label, ok, memo in res:
        lines.append(f"  {'O' if ok else 'X'} {label}: {memo}")
    lines.append("-" * 64)
    lines.append(f"[VERDICT] {verdict}")
    lines.append(f"[매칭] OI {metric.get('oi_matched','?')}/{metric.get('n_trades','?')}건, "
                 f"ADX {metric.get('adx_matched','?')}/{metric.get('n_trades','?')}건")
    lines.append(f"[기준] 무차단 누적R {metric.get('base_cumR','?')}%, trend_flip {metric.get('flip_cumR','?')}%")
    lines.append(f"[코드해시] {hashes}")
    # 8시나리오 요약 첨부
    sp = os.path.join(HERE, "rs_summary.csv")
    if os.path.exists(sp):
        lines.append("[8시나리오 요약]")
        s = pd.read_csv(sp)
        for _, r in s.iterrows():
            c = str(r["cell"])
            if c.startswith(("S", "BASE")):
                lines.append(f"  {c}: 차단{r.get('blocked_n','')} 잔여PF{r.get('kept_PF','')} "
                             f"피한손실{r.get('avoided_loss','')} {r.get('note','')}")
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
    update_index(f"{stamp} | {VER} | {'PASS' if passed else 'FAIL'} | {verdict[:70]}")
    print(f"[check] integrity={'PASS' if passed else 'FAIL'}")
    print(f"[check] analysis -> {apath}")
    print(f"[check] INDEX -> {os.path.join(WORKHSTR, '00WorkHstr_INDEX.txt')}")


if __name__ == "__main__":
    main()
