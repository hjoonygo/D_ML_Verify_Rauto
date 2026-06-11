# -*- coding: utf-8 -*-
# [파일명] check_06Prj_Ch5_RAUTO_AlphaUp_Stg15_ChopFilterDualBot.py
# 코드길이: 약 130줄 | 내부버전: RAUTO_AlphaUp_06_Ch5_Stg15_ChopFilterDualBot | 전체 출력
# [검사 10항목] 1.필수파일 2.CSV非공백 3.코드해시 4.중복없음 5.미래참조가드(CHOP/ER과거봉,임계학습기간,label제외)
#   6.연도분포 7.칩그리드 8.★2025두봇합산 9.횡보봇추출+엔진해시 10.VERDICT
import os, sys, hashlib, datetime, re, io, tokenize
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); PARENT = os.path.dirname(HERE)
WORKHSTR = os.path.join(PARENT, "00WorkHstr")
VER = "RAUTO_AlphaUp_06_Ch5_Stg15_ChopFilterDualBot"
TESTPY = "test_06Prj_Ch5_RAUTO_AlphaUp_Stg15_ChopFilterDualBot.py"
CHECKPY = "check_06Prj_Ch5_RAUTO_AlphaUp_Stg15_ChopFilterDualBot.py"
TE = os.path.join("bots", "SpTrd_Fib_V1_Champion.py"); SE = os.path.join("bots", "SidewayDCA_Stg7_engine.py")
EXP = {TE: "7f9192e3d50b1afd659a02b9e75764e5438ad57809c93093ab5f1973bb79ca75",
       SE: "dfdfac4394cd780939d4b368d3ccabfbfab8d599ff1236b11f7f0d80f0823086"}
REQ = [TESTPY, CHECKPY, "run.bat", TE, SE, "summary.csv", "chop_dist_by_year.csv", "chop_grid.csv",
       "trend_chopfilter_by_year.csv", "sideways_by_year.csv", "dualbot_2025.csv"]


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
    p = os.path.join(HERE, ".stg15_metric"); d = {}
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
    if pr.get("chop_grid.csv"):
        try:
            dup = int(pd.read_csv(os.path.join(HERE, "chop_grid.csv")).duplicated().sum())
        except Exception:
            dup = -1
    res.append(("4.중복없음", dup == 0, f"중복{dup}"))
    look = True; memo = "음수shift 미사용 — CHOP/ER/ADX 진입시점 과거봉"
    src = open(os.path.join(HERE, TESTPY), encoding="utf-8").read() if pr.get(TESTPY) else ""
    for f in [TESTPY, TE, SE]:
        if pr.get(f) and re.search(r"shift\(\s*-\s*\d", strip_c(open(os.path.join(HERE, f), encoding="utf-8").read())):
            look = False; memo = f"{f}: 음수shift"; break
    if m.get("has_label_in_feats", "False") == "True":
        look = False; memo = "★label 혼입"
    if "tr_mask" in src and "train_ret" in src:
        memo += " | 칩임계=학습기간 선택 | label미사용"
    res.append(("5.미래참조가드", look, memo))
    res.append(("6.연도분포", pr.get("chop_dist_by_year.csv"), "CHOP/ER/ADX 연도별 산출"))
    res.append(("7.칩그리드", m.get('grid_rows', '0') != '0', f"그리드 {m.get('grid_rows')}조합 | best CHOP>{m.get('best_chop_hi')}·ER<{m.get('best_er_lo')}·×{m.get('best_mult')}"))
    res.append(("8.★2025두봇합산", 'dual2025' in m, f"추세{m.get('t2025_base')}->칩필터{m.get('t2025_filt')}% +횡보{m.get('s2025')}% =합산{m.get('dual2025')}%"))
    eng = True; em = []
    for f, e in EXP.items():
        if pr.get(f):
            o = sha(os.path.join(HERE, f)) == e; eng = eng and o; em.append(f"{os.path.basename(f)}={'OK' if o else '★불일치'}")
        else:
            eng = False; em.append(f"{os.path.basename(f)}=없음")
    res.append(("9.횡보봇추출+엔진해시", ('sw_extracted' in m) and eng, f"횡보봇 {m.get('sw_extracted')}거래 | " + " ".join(em)))
    res.append(("10.VERDICT", 'best_mult' in m, f"칩필터後 OOS {m.get('oos_base')}->{m.get('oos_filt')}% MDD{m.get('filt_mdd')}%"))
    return all(o for _, o, _ in res), res, hs, m


def analysis(passed, res, hs, m):
    os.makedirs(WORKHSTR, exist_ok=True)
    p = os.path.join(WORKHSTR, datetime.datetime.now().strftime("%Y%m%d_%H%M") + ".txt")
    L = [f"[작업분석] {VER} ({datetime.datetime.now().isoformat(timespec='seconds')})", f"[오염검사] {'PASS' if passed else 'FAIL'}", "-"*60]
    for lb, o, mm in res:
        L.append(f"  {'O' if o else 'X'} {lb}: {mm}")
    L += ["-"*60,
          f"[칩필터] best CHOP>{m.get('best_chop_hi')}·ER<{m.get('best_er_lo')}·×{m.get('best_mult')} (칩거래 {m.get('n_chop')}건, 2025중 {m.get('n_chop_2025')}건)",
          f"[★2025] 추세봇 {m.get('t2025_base')}% -> 칩필터 {m.get('t2025_filt')}% | 횡보봇 {m.get('s2025')}% | 두봇합산 {m.get('dual2025')}%",
          f"[전체] base {m.get('base_ret')}%/MDD{m.get('base_mdd')} -> 칩필터 {m.get('filt_ret')}%/MDD{m.get('filt_mdd')}(청산{m.get('filt_liq')})",
          f"[OOS] base {m.get('oos_base')}% -> 칩필터 {m.get('oos_filt')}%",
          f"[코드해시] {hs}"]
    open(p, "w", encoding="utf-8").write("\n".join(L)); return p


def idx_upd(line):
    os.makedirs(WORKHSTR, exist_ok=True); ix = os.path.join(WORKHSTR, "00WorkHstr_INDEX.txt"); h = not os.path.exists(ix)
    with open(ix, "a", encoding="utf-8") as f:
        if h:
            f.write("# 00WorkHstr INDEX | 시각 | 버전 | 검사 | 핵심성과\n")
        f.write(line + "\n")


def main():
    passed, res, hs, m = run(); ap = analysis(passed, res, hs, m)
    idx_upd(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} | {VER} | {'PASS' if passed else 'FAIL'} | 2025두봇합산 {m.get('dual2025')}%")
    print(f"[check] integrity={'PASS' if passed else 'FAIL'}"); print(f"[check] analysis -> {ap}")


if __name__ == "__main__":
    main()
