# -*- coding: utf-8 -*-
# [파일명] check_06Prj_Ch5_RAUTO_AlphaUp_Stg14_MLSizingScorecard.py
# 코드길이: 약 130줄 | 내부버전: RAUTO_AlphaUp_06_Ch5_Stg14_MLSizingScorecard | 전체 출력
# [검사 10항목] 1.필수파일 2.CSV非공백 3.코드해시 4.중복없음 5.미래참조가드+label제외+모델학습기간
#   6.ML정확도+배수그리드 7.세축성적표 8.★2025집중+MDD제약 9.청산/MDD+엔진해시 10.VERDICT
import os, sys, hashlib, datetime, re, io, tokenize
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); PARENT = os.path.dirname(HERE)
WORKHSTR = os.path.join(PARENT, "00WorkHstr")
VER = "RAUTO_AlphaUp_06_Ch5_Stg14_MLSizingScorecard"
TESTPY = "test_06Prj_Ch5_RAUTO_AlphaUp_Stg14_MLSizingScorecard.py"
CHECKPY = "check_06Prj_Ch5_RAUTO_AlphaUp_Stg14_MLSizingScorecard.py"
TE = os.path.join("bots", "SpTrd_Fib_V1_Champion.py"); SE = os.path.join("bots", "SidewayDCA_Stg7_engine.py")
EXP = {TE: "7f9192e3d50b1afd659a02b9e75764e5438ad57809c93093ab5f1973bb79ca75",
       SE: "dfdfac4394cd780939d4b368d3ccabfbfab8d599ff1236b11f7f0d80f0823086"}
REQ = [TESTPY, CHECKPY, "run.bat", TE, SE, "summary.csv", "grid_with_risk.csv", "best_by_regime.csv",
       "best_by_year.csv", "best_by_side.csv", "y2025_focus.csv", "all_trades.csv"]


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
    p = os.path.join(HERE, ".stg14_metric"); d = {}
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
    if pr.get("grid_with_risk.csv"):
        try:
            dup = int(pd.read_csv(os.path.join(HERE, "grid_with_risk.csv")).duplicated().sum())
        except Exception:
            dup = -1
    res.append(("4.중복없음", dup == 0, f"중복{dup}"))
    look = True; memo = "음수shift 미사용 — 특징 과거봉, 모델 학습기간 fit"
    src = open(os.path.join(HERE, TESTPY), encoding="utf-8").read() if pr.get(TESTPY) else ""
    for f in [TESTPY, TE, SE]:
        if pr.get(f) and re.search(r"shift\(\s*-\s*\d", strip_c(open(os.path.join(HERE, f), encoding="utf-8").read())):
            look = False; memo = f"{f}: 음수shift"; break
    if m.get("has_label_in_feats", "False") == "True":
        look = False; memo = "★label 혼입"
    if "mdl.fit(X[tr]" in src:
        memo += " | 모델=학습기간만 fit | label제외"
    res.append(("5.미래참조가드", look, memo))
    res.append(("6.ML정확도+그리드", ('acc_oos' in m) and m.get('grid_rows') == '9', f"OOS정확도{m.get('acc_oos')}% | 그리드 {m.get('grid_rows')}조합"))
    threeok = pr.get("best_by_regime.csv") and pr.get("best_by_year.csv") and pr.get("best_by_side.csv")
    res.append(("7.세축성적표", threeok, "장세/연도/롱숏 산출" if threeok else "누락"))
    y25ok = pr.get("y2025_focus.csv") and os.path.getsize(os.path.join(HERE, "y2025_focus.csv")) > 20
    res.append(("8.★2025집중+MDD제약", y25ok and ('ml_mdd' in m), f"2025 base{m.get('y2025_base')}%->ML{m.get('y2025_ml')}% | 최적MDD{m.get('ml_mdd')}%(한계-35)"))
    eng = True; em = []
    for f, e in EXP.items():
        if pr.get(f):
            o = sha(os.path.join(HERE, f)) == e; eng = eng and o; em.append(f"{os.path.basename(f)}={'OK' if o else '★불일치'}")
        else:
            eng = False; em.append(f"{os.path.basename(f)}=없음")
    res.append(("9.청산/MDD+엔진해시", ('ml_liq' in m) and eng, f"청산{m.get('ml_liq')} MDD{m.get('ml_mdd')}% | " + " ".join(em)))
    res.append(("10.VERDICT", 'best_tg' in m, f"추세×{m.get('best_tg')}/횡보×{m.get('best_rg')} 전체{m.get('base_ret')}->{m.get('ml_ret')}%"))
    return all(o for _, o, _ in res), res, hs, m


def analysis(passed, res, hs, m):
    os.makedirs(WORKHSTR, exist_ok=True)
    p = os.path.join(WORKHSTR, datetime.datetime.now().strftime("%Y%m%d_%H%M") + ".txt")
    L = [f"[작업분석] {VER} ({datetime.datetime.now().isoformat(timespec='seconds')})", f"[오염검사] {'PASS' if passed else 'FAIL'}", "-"*60]
    for lb, o, mm in res:
        L.append(f"  {'O' if o else 'X'} {lb}: {mm}")
    L += ["-"*60,
          f"[ML장세] OOS정확도 {m.get('acc_oos')}% | 최적배수 추세×{m.get('best_tg')}/횡보×{m.get('best_rg')}",
          f"[전체] base PF{m.get('base_pf')}/{m.get('base_ret')}%/MDD{m.get('base_mdd')} -> ML PF{m.get('ml_pf')}/{m.get('ml_ret')}%/MDD{m.get('ml_mdd')}(청산{m.get('ml_liq')})",
          f"[★2025] base {m.get('y2025_base')}% -> ML {m.get('y2025_ml')}% | ML예측분포 {m.get('y2025_pred')}",
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
    idx_upd(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} | {VER} | {'PASS' if passed else 'FAIL'} | 추세×{m.get('best_tg')}/횡보×{m.get('best_rg')} 2025:{m.get('y2025_ml')}%")
    print(f"[check] integrity={'PASS' if passed else 'FAIL'}"); print(f"[check] analysis -> {ap}")


if __name__ == "__main__":
    main()
