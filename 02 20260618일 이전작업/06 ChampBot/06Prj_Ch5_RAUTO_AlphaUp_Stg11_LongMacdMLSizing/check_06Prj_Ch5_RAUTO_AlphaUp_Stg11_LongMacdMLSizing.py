# -*- coding: utf-8 -*-
# [파일명] check_06Prj_Ch5_RAUTO_AlphaUp_Stg11_LongMacdMLSizing.py
# 코드길이: 약 140줄 | 내부버전: RAUTO_AlphaUp_06_Ch5_Stg11_LongMacdMLSizing | 전체 출력
# [검사 10항목] 1.필수파일 2.CSV非공백 3.코드해시 4.중복없음 5.미래참조가드+label제외+임계학습기간
#   6.장기MACD장세정확도 7.ML그리드20조합 8.청산/MDD산출 9.세축성적표+엔진해시 10.VERDICT
import os, sys, hashlib, datetime, re, io, tokenize
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); PARENT = os.path.dirname(HERE)
WORKHSTR = os.path.join(PARENT, "00WorkHstr")
VER = "RAUTO_AlphaUp_06_Ch5_Stg11_LongMacdMLSizing"
TESTPY = "test_06Prj_Ch5_RAUTO_AlphaUp_Stg11_LongMacdMLSizing.py"
CHECKPY = "check_06Prj_Ch5_RAUTO_AlphaUp_Stg11_LongMacdMLSizing.py"
TE = os.path.join("bots", "SpTrd_Fib_V1_Champion.py"); SE = os.path.join("bots", "SidewayDCA_Stg7_engine.py")
EXP = {TE: "7f9192e3d50b1afd659a02b9e75764e5438ad57809c93093ab5f1973bb79ca75",
       SE: "dfdfac4394cd780939d4b368d3ccabfbfab8d599ff1236b11f7f0d80f0823086"}
REQ = [TESTPY, CHECKPY, "run.bat", TE, SE, "summary.csv", "long_regime_oos.csv", "sizing_grid.csv",
       "best_by_regime.csv", "best_by_year.csv", "best_by_side.csv", "liquidation_mdd.csv"]


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
    p = os.path.join(HERE, ".stg11_metric"); d = {}
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
    if pr.get("sizing_grid.csv"):
        try:
            dup = int(pd.read_csv(os.path.join(HERE, "sizing_grid.csv")).duplicated().sum())
        except Exception:
            dup = -1
    res.append(("4.중복없음", dup == 0, f"중복{dup}"))
    look = True; memo = "음수shift 미사용 — 장기MACD/임계 과거봉·학습기간만"
    src = open(os.path.join(HERE, TESTPY), encoding="utf-8").read() if pr.get(TESTPY) else ""
    for f in [TESTPY, TE, SE]:
        if pr.get(f) and re.search(r"shift\(\s*-\s*\d", strip_c(open(os.path.join(HERE, f), encoding="utf-8").read())):
            look = False; memo = f"{f}: 음수shift"; break
    if m.get("has_label_in_feats", "False") == "True":
        look = False; memo = "★label 혼입"
    if "np.nanquantile(np.abs(macd3[:cut" in src:
        memo += " | 임계=학습기간만 확인"
    res.append(("5.미래참조가드", look, memo))
    res.append(("6.장기MACD장세정확도", 'long_acc' in m, f"정확도{m.get('long_acc')}%(기준선{m.get('maj')}%)"))
    gok = pr.get("sizing_grid.csv")
    grows = m.get('grid_rows', '0')
    res.append(("7.ML그리드20조합", gok and grows == '20', f"그리드 {grows}행(일치5×불일치4)"))
    res.append(("8.청산/MDD", 'mdd_simple' in m, f"단리MDD{m.get('mdd_simple')}% 최저자본${m.get('mincap')} 청산{m.get('liq_simple')} | 그리드내청산발생:{m.get('any_liq')}"))
    eng = True; em = []
    for f, e in EXP.items():
        if pr.get(f):
            o = sha(os.path.join(HERE, f)) == e; eng = eng and o; em.append(f"{os.path.basename(f)}={'OK' if o else '★불일치'}")
        else:
            eng = False; em.append(f"{os.path.basename(f)}=없음")
    threeok = pr.get("best_by_regime.csv") and pr.get("best_by_year.csv") and pr.get("best_by_side.csv")
    res.append(("9.세축성적표+엔진해시", threeok and eng, "장세/연도/롱숏 산출 | " + " ".join(em)))
    res.append(("10.VERDICT", 'best_agree' in m, f"최적 일치×{m.get('best_agree')}/불일치×{m.get('best_oppo')} 적용PF{m.get('pov_pf')}/{m.get('pov_ret')}%"))
    return all(o for _, o, _ in res), res, hs, m


def analysis(passed, res, hs, m):
    os.makedirs(WORKHSTR, exist_ok=True)
    p = os.path.join(WORKHSTR, datetime.datetime.now().strftime("%Y%m%d_%H%M") + ".txt")
    L = [f"[작업분석] {VER} ({datetime.datetime.now().isoformat(timespec='seconds')})", f"[오염검사] {'PASS' if passed else 'FAIL'}", "-"*60]
    for lb, o, mm in res:
        L.append(f"  {'O' if o else 'X'} {lb}: {mm}")
    L += ["-"*60,
          f"[장기MACD 장세] 정확도 {m.get('long_acc')}%(기준선{m.get('maj')}%)",
          f"[ML최적] 일치×{m.get('best_agree')}/불일치×{m.get('best_oppo')} | 거래{m.get('n_trades')}(일치{m.get('n_agree')}/불일치{m.get('n_oppo')})",
          f"[성과] base PF{m.get('base_pf')}/{m.get('base_ret')}% -> 적용 PF{m.get('pov_pf')}/{m.get('pov_ret')}%/${m.get('pov_profit')}",
          f"[위험] 단리MDD {m.get('mdd_simple')}% 최저자본 ${m.get('mincap')} 청산 {m.get('liq_simple')} | 그리드내청산:{m.get('any_liq')}",
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
    idx_upd(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} | {VER} | {'PASS' if passed else 'FAIL'} | 최적 일치×{m.get('best_agree')}/불일치×{m.get('best_oppo')}")
    print(f"[check] integrity={'PASS' if passed else 'FAIL'}"); print(f"[check] analysis -> {ap}")


if __name__ == "__main__":
    main()
