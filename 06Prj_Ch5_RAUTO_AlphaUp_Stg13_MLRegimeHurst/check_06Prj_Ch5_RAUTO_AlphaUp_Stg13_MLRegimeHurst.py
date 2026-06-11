# -*- coding: utf-8 -*-
# [파일명] check_06Prj_Ch5_RAUTO_AlphaUp_Stg13_MLRegimeHurst.py
# 코드길이: 약 130줄 | 내부버전: RAUTO_AlphaUp_06_Ch5_Stg13_MLRegimeHurst | 전체 출력
# [검사 10항목] 1.필수파일 2.CSV非공백 3.코드해시 4.중복없음 5.미래참조가드+label제외+스케일러학습기간
#   6.ML모델비교 7.특징중요도(Hurst) 8.혼동행렬 9.사이징재검+엔진해시 10.VERDICT
import os, sys, hashlib, datetime, re, io, tokenize
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); PARENT = os.path.dirname(HERE)
WORKHSTR = os.path.join(PARENT, "00WorkHstr")
VER = "RAUTO_AlphaUp_06_Ch5_Stg13_MLRegimeHurst"
TESTPY = "test_06Prj_Ch5_RAUTO_AlphaUp_Stg13_MLRegimeHurst.py"
CHECKPY = "check_06Prj_Ch5_RAUTO_AlphaUp_Stg13_MLRegimeHurst.py"
TE = os.path.join("bots", "SpTrd_Fib_V1_Champion.py"); SE = os.path.join("bots", "SidewayDCA_Stg7_engine.py")
EXP = {TE: "7f9192e3d50b1afd659a02b9e75764e5438ad57809c93093ab5f1973bb79ca75",
       SE: "dfdfac4394cd780939d4b368d3ccabfbfab8d599ff1236b11f7f0d80f0823086"}
REQ = [TESTPY, CHECKPY, "run.bat", TE, SE, "summary.csv", "ml_model_compare.csv", "feature_importance.csv", "confusion_best.csv", "sizing_recheck.csv"]


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
    p = os.path.join(HERE, ".stg13_metric"); d = {}
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
    if pr.get("ml_model_compare.csv"):
        try:
            dup = int(pd.read_csv(os.path.join(HERE, "ml_model_compare.csv")).duplicated().sum())
        except Exception:
            dup = -1
    res.append(("4.중복없음", dup == 0, f"중복{dup}"))
    look = True; memo = "음수shift 미사용 — 특징 과거봉, 스케일러 학습기간 fit"
    src = open(os.path.join(HERE, TESTPY), encoding="utf-8").read() if pr.get(TESTPY) else ""
    for f in [TESTPY, TE, SE]:
        if pr.get(f) and re.search(r"shift\(\s*-\s*\d", strip_c(open(os.path.join(HERE, f), encoding="utf-8").read())):
            look = False; memo = f"{f}: 음수shift"; break
    if m.get("has_label_in_feats", "False") == "True":
        look = False; memo = "★label 혼입(lookahead!)"
    else:
        memo += " | label 제외 확인"
    if "StandardScaler().fit(X[tr])" in src:
        memo += " | 스케일러=학습기간만"
    res.append(("5.미래참조가드", look, memo))
    res.append(("6.ML모델비교", 'model_rows' in m, f"모델 {m.get('model_rows')}개 | best {m.get('best_model')} {m.get('best_acc')}%(기준선{m.get('baseline')}%) 돌파:{m.get('beats_any')}"))
    res.append(("7.특징중요도Hurst", 'top_feat' in m, f"top특징 {m.get('top_feat')} | Hurst순위 {m.get('hurst_rank')}"))
    cok = pr.get("confusion_best.csv") and os.path.getsize(os.path.join(HERE, "confusion_best.csv")) > 20
    res.append(("8.혼동행렬", cok, "산출" if cok else "없음"))
    eng = True; em = []
    for f, e in EXP.items():
        if pr.get(f):
            o = sha(os.path.join(HERE, f)) == e; eng = eng and o; em.append(f"{os.path.basename(f)}={'OK' if o else '★불일치'}")
        else:
            eng = False; em.append(f"{os.path.basename(f)}=없음")
    res.append(("9.사이징재검+엔진해시", ('ml_ret' in m) and eng, f"base{m.get('base_ret')}%/MDD{m.get('base_mdd')}->ML{m.get('ml_ret')}%/MDD{m.get('ml_mdd')}(청산{m.get('ml_liq')}) | " + " ".join(em)))
    res.append(("10.VERDICT", 'best_model' in m, f"best {m.get('best_model')} {m.get('best_acc')}% / OOS base{m.get('oos_base_ret')}->ML{m.get('oos_ml_ret')}%"))
    return all(o for _, o, _ in res), res, hs, m


def analysis(passed, res, hs, m):
    os.makedirs(WORKHSTR, exist_ok=True)
    p = os.path.join(WORKHSTR, datetime.datetime.now().strftime("%Y%m%d_%H%M") + ".txt")
    L = [f"[작업분석] {VER} ({datetime.datetime.now().isoformat(timespec='seconds')})", f"[오염검사] {'PASS' if passed else 'FAIL'}", "-"*60]
    for lb, o, mm in res:
        L.append(f"  {'O' if o else 'X'} {lb}: {mm}")
    L += ["-"*60,
          f"[ML분류] best {m.get('best_model')} acc {m.get('best_acc')}%(기준선{m.get('baseline')}%) 돌파:{m.get('beats_any')} | 특징{m.get('n_feats')}개",
          f"[Hurst] top특징 {m.get('top_feat')} | Hurst중요도순위 {m.get('hurst_rank')}",
          f"[사이징재검] 전체 base{m.get('base_ret')}%/MDD{m.get('base_mdd')} -> ML{m.get('ml_ret')}%/MDD{m.get('ml_mdd')}(청산{m.get('ml_liq')})",
          f"           OOS base{m.get('oos_base_ret')}% -> ML{m.get('oos_ml_ret')}%",
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
    idx_upd(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} | {VER} | {'PASS' if passed else 'FAIL'} | best {m.get('best_model')} {m.get('best_acc')}%")
    print(f"[check] integrity={'PASS' if passed else 'FAIL'}"); print(f"[check] analysis -> {ap}")


if __name__ == "__main__":
    main()
