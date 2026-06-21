# -*- coding: utf-8 -*-
# [파일명] check_06Prj_Ch5_RAUTO_ConceptRefine_Stg6_RegimeReferee.py
# 코드길이: 약 150줄 | 내부버전: RAUTO_ConceptRefine_06_Ch5_Stg6_RegimeReferee | 전체 출력
# [검사 10항목] 1.필수파일 2.CSV非공백 3.코드해시 4.중복없음 5.미래참조가드+label제외
#   6.4장세 분류산출 7.추세이분 OOS AUC산출 8.라우팅 잭팟보존산출 9.다중TF산출+엔진해시 10.VERDICT
import os, sys, hashlib, datetime, re, io, tokenize
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); PARENT = os.path.dirname(HERE)
WORKHSTR = os.path.join(PARENT, "00WorkHstr")
VER = "RAUTO_ConceptRefine_06_Ch5_Stg6_RegimeReferee"
TESTPY = "test_06Prj_Ch5_RAUTO_ConceptRefine_Stg6_RegimeReferee.py"
CHECKPY = "check_06Prj_Ch5_RAUTO_ConceptRefine_Stg6_RegimeReferee.py"
TE = os.path.join("bots", "SpTrd_Fib_V1_Champion.py"); SE = os.path.join("bots", "SidewayDCA_Stg7_engine.py")
EXP = {TE: "7f9192e3d50b1afd659a02b9e75764e5438ad57809c93093ab5f1973bb79ca75",
       SE: "dfdfac4394cd780939d4b368d3ccabfbfab8d599ff1236b11f7f0d80f0823086"}
REQ = [TESTPY, CHECKPY, "run.bat", TE, SE, "stg6_summary.csv", "regime_oos.csv", "bot_by_regime.csv", "routing_sim.csv"]


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
    p = os.path.join(HERE, ".stg6_metric"); d = {}
    if os.path.exists(p):
        for ln in open(p, encoding="utf-8"):
            if "=" in ln:
                k, v = ln.strip().split("=", 1); d[k] = v
    return d


def verdict():
    p = os.path.join(HERE, "stg6_summary.csv")
    if not os.path.exists(p):
        return None
    for ln in open(p, encoding="utf-8-sig"):
        if "VERDICT" in ln:
            return ln.strip().strip('"').rstrip(',').rstrip('"')
    return None


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
    if pr.get("regime_oos.csv"):
        try:
            dup = int(pd.read_csv(os.path.join(HERE, "regime_oos.csv")).duplicated().sum())
        except Exception:
            dup = -1
    res.append(("4.중복없음", dup == 0, f"중복{dup}"))
    look = True; memo = "음수shift 미사용 — 특징 과거봉만"
    for f in [TESTPY, TE, SE]:
        if pr.get(f) and re.search(r"shift\(\s*-\s*\d", strip_c(open(os.path.join(HERE, f), encoding="utf-8").read())):
            look = False; memo = f"{f}: 음수shift"; break
    if m.get("has_label_in_feats", "False") == "True":
        look = False; memo = "★label_smc 특징혼입(lookahead!)"
    else:
        memo += " | label_smc 특징제외 확인"
    res.append(("5.미래참조가드+label제외", look, memo))
    res.append(("6.4장세 분류산출", 'acc4' in m, f"정확도{m.get('acc4')}% 기준선{m.get('maj')}%"))
    res.append(("7.추세이분 OOS AUC", 'auc_bin7' in m, f"검증AUC{m.get('auc_bin7')}(RF{m.get('rf_bin7')})"))
    res.append(("8.라우팅 잭팟보존", 'route_jack' in m, f"보존{m.get('route_jack')}% (항상풀{m.get('route_base_mdd')}->라우팅{m.get('route_mdd')})"))
    eng = True; em = []
    for f, e in EXP.items():
        if pr.get(f):
            ok = sha(os.path.join(HERE, f)) == e; eng = eng and ok; em.append(f"{os.path.basename(f)}={'OK' if ok else '★불일치'}")
        else:
            eng = False; em.append(f"{os.path.basename(f)}=없음")
    res.append(("9.다중TF+엔진해시", ('tf_auc' in m) and eng, f"TF={m.get('tf_auc','')[:40]} | " + " ".join(em)))
    v = verdict()
    res.append(("10.VERDICT", v is not None, (v[:50]+"...") if v else "없음"))
    return all(o for _, o, _ in res), res, hs, m, v


def analysis(passed, res, hs, m, v):
    os.makedirs(WORKHSTR, exist_ok=True)
    p = os.path.join(WORKHSTR, datetime.datetime.now().strftime("%Y%m%d_%H%M") + ".txt")
    L = [f"[작업분석] {VER} ({datetime.datetime.now().isoformat(timespec='seconds')})", f"[오염검사] {'PASS' if passed else 'FAIL'}", "-"*60]
    for lb, o, mm in res:
        L.append(f"  {'O' if o else 'X'} {lb}: {mm}")
    L += ["-"*60, f"[VERDICT] {v}",
          f"[4장세] 정확도 {m.get('acc4')}% vs 기준선 {m.get('maj')}% | 장세별AUC {m.get('perclass')}",
          f"[추세이분] 검증AUC {m.get('auc_bin7')} (RF {m.get('rf_bin7')}) | 다중TF {m.get('tf_auc')}",
          f"[변동성] 잭팟 확대국면 비율 {m.get('jack_expand')}%",
          f"[라우팅] 항상풀 {m.get('route_base_cum')}%/MDD{m.get('route_base_mdd')} -> 라우팅 {m.get('route_cum')}%/MDD{m.get('route_mdd')} | 잭팟보존 {m.get('route_jack')}%",
          f"[코드해시] {hs}"]
    open(p, "w", encoding="utf-8").write("\n".join(L)); return p


def idx_upd(line):
    os.makedirs(WORKHSTR, exist_ok=True); ix = os.path.join(WORKHSTR, "00WorkHstr_INDEX.txt")
    h = not os.path.exists(ix)
    with open(ix, "a", encoding="utf-8") as f:
        if h:
            f.write("# 00WorkHstr INDEX | 시각 | 버전 | 검사 | 핵심성과\n")
        f.write(line + "\n")


def main():
    passed, res, hs, m, v = run(); ap = analysis(passed, res, hs, m, v or "N/A")
    idx_upd(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} | {VER} | {'PASS' if passed else 'FAIL'} | {v}")
    print(f"[check] integrity={'PASS' if passed else 'FAIL'}"); print(f"[check] analysis -> {ap}")


if __name__ == "__main__":
    main()
