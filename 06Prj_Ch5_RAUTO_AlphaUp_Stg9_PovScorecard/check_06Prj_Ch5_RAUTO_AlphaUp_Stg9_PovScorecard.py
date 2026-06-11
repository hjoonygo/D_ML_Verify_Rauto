# -*- coding: utf-8 -*-
# [파일명] check_06Prj_Ch5_RAUTO_AlphaUp_Stg9_PovScorecard.py
# 코드길이: 약 130줄 | 내부버전: RAUTO_AlphaUp_06_Ch5_Stg9_PovScorecard | 전체 출력
# [검사 10항목] 1.필수파일 2.CSV非공백 3.코드해시 4.중복없음 5.미래참조가드+엔진무수정
#   6.거래/POV분포 7.장세별 8.연도별 9.롱숏별+엔진해시 10.VERDICT(base vs POV)
import os, sys, hashlib, datetime, re, io, tokenize
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); PARENT = os.path.dirname(HERE)
WORKHSTR = os.path.join(PARENT, "00WorkHstr")
VER = "RAUTO_AlphaUp_06_Ch5_Stg9_PovScorecard"
TESTPY = "test_06Prj_Ch5_RAUTO_AlphaUp_Stg9_PovScorecard.py"
CHECKPY = "check_06Prj_Ch5_RAUTO_AlphaUp_Stg9_PovScorecard.py"
TE = os.path.join("bots", "SpTrd_Fib_V1_Champion.py"); SE = os.path.join("bots", "SidewayDCA_Stg7_engine.py")
EXP = {TE: "7f9192e3d50b1afd659a02b9e75764e5438ad57809c93093ab5f1973bb79ca75",
       SE: "dfdfac4394cd780939d4b368d3ccabfbfab8d599ff1236b11f7f0d80f0823086"}
REQ = [TESTPY, CHECKPY, "run.bat", TE, SE, "summary.csv", "pov_by_regime.csv", "pov_by_year.csv", "pov_by_side.csv", "pov_all_trades.csv"]


def strip_c(src):
    try:
        ls = src.split("\n")
        for t in tokenize.generate_tokens(io.StringIO(src).readline):
            if t.type == tokenize.COMMENT:
                sr, sc = t.start; _, ec = t.end; ls[sr-1] = ls[sr-1][:sc] + ls[sr-1][ec:]
        return "\n".join(ls)
    except Exception:
        return src


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(8192), b""):
            h.update(c)
    return h.hexdigest()


def metric():
    p = os.path.join(HERE, ".stg9_metric"); d = {}
    if os.path.exists(p):
        for ln in open(p, encoding="utf-8"):
            if "=" in ln:
                k, v = ln.strip().split("=", 1); d[k] = v
    return d


def run():
    res = []; m = metric()
    pr = {f: os.path.exists(os.path.join(HERE, f)) for f in REQ}
    miss = [f for f, o in pr.items() if not o]
    res.append(("1.필수파일", len(miss) == 0, f"누락:{miss}" if miss else "ok"))
    empt = [c for c in REQ if c.endswith(".csv") and pr.get(c) and os.path.getsize(os.path.join(HERE, c)) < 10]
    res.append(("2.CSV非공백", len(empt) == 0, f"빈:{empt}" if empt else "ok"))
    hs = {f: sha(os.path.join(HERE, f))[:16] for f in [TESTPY, CHECKPY] if pr.get(f)}
    res.append(("3.코드해시", len(hs) == 2, str(hs)))
    dup = 0
    if pr.get("pov_all_trades.csv"):
        try:
            dup = int(pd.read_csv(os.path.join(HERE, "pov_all_trades.csv")).duplicated().sum())
        except Exception:
            dup = -1
    res.append(("4.중복없음", dup == 0, f"중복{dup}"))
    look = True; memo = "음수shift 미사용 — 엔진 무수정, dev 진입시점 과거기반"
    for f in [TESTPY, TE, SE]:
        if pr.get(f) and re.search(r"shift\(\s*-\s*\d", strip_c(open(os.path.join(HERE, f), encoding="utf-8").read())):
            look = False; memo = f"{f}: 음수shift"; break
    res.append(("5.미래참조가드", look, memo))
    res.append(("6.거래/POV분포", 'n_all' in m, f"거래{m.get('n_all')}(일치{m.get('n_agree')}/반대{m.get('n_oppo')}/중립{m.get('n_neutral')})"))
    for fn, lab in [("pov_by_regime.csv", "7.장세별"), ("pov_by_year.csv", "8.연도별"), ("pov_by_side.csv", "9.롱숏별")]:
        ok = pr.get(fn) and os.path.getsize(os.path.join(HERE, fn)) > 20
        res.append((lab, ok, "산출" if ok else "없음"))
    eng = True; em = []
    for f, e in EXP.items():
        if pr.get(f):
            o = sha(os.path.join(HERE, f)) == e; eng = eng and o; em.append(f"{os.path.basename(f)}={'OK' if o else '★불일치'}")
        else:
            eng = False; em.append(f"{os.path.basename(f)}=없음")
    res[-1] = (res[-1][0], res[-1][1] and eng, res[-1][2] + " | " + " ".join(em))
    v = (f"base PF{m.get('base_PF')}/승률{m.get('base_win')}%/손익비{m.get('base_payoff')}/수익률{m.get('base_ret')}%/${m.get('base_profit')} "
         f"-> POV PF{m.get('pov_PF')}/승률{m.get('pov_win')}%/손익비{m.get('pov_payoff')}/수익률{m.get('pov_ret')}%/${m.get('pov_profit')}")
    res.append(("10.VERDICT", 'base_PF' in m, v[:60] + "..."))
    return all(o for _, o, _ in res), res, hs, m, v


def analysis(passed, res, hs, m, v):
    os.makedirs(WORKHSTR, exist_ok=True)
    p = os.path.join(WORKHSTR, datetime.datetime.now().strftime("%Y%m%d_%H%M") + ".txt")
    L = [f"[작업분석] {VER} ({datetime.datetime.now().isoformat(timespec='seconds')})", f"[오염검사] {'PASS' if passed else 'FAIL'}", "-"*60]
    for lb, o, mm in res:
        L.append(f"  {'O' if o else 'X'} {lb}: {mm}")
    L += ["-"*60, f"[VERDICT] {v}",
          f"[사이징] 일치×{m.get('m_agree')} 반대×{m.get('m_oppo')} | 거래{m.get('n_all')}(일치{m.get('n_agree')}/반대{m.get('n_oppo')}/중립{m.get('n_neutral')})",
          f"[코드해시] {hs}"]
    open(p, "w", encoding="utf-8").write("\n".join(L)); return p


def idx_upd(line):
    os.makedirs(WORKHSTR, exist_ok=True); ix = os.path.join(WORKHSTR, "00WorkHstr_INDEX.txt"); h = not os.path.exists(ix)
    with open(ix, "a", encoding="utf-8") as f:
        if h:
            f.write("# 00WorkHstr INDEX | 시각 | 버전 | 검사 | 핵심성과\n")
        f.write(line + "\n")


def main():
    passed, res, hs, m, v = run(); ap = analysis(passed, res, hs, m, v)
    idx_upd(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} | {VER} | {'PASS' if passed else 'FAIL'} | {v[:70]}")
    print(f"[check] integrity={'PASS' if passed else 'FAIL'}"); print(f"[check] analysis -> {ap}")


if __name__ == "__main__":
    main()
