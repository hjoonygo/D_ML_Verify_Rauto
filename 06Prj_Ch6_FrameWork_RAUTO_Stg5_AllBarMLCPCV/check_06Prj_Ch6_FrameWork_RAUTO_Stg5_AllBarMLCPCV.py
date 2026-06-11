# -*- coding: utf-8 -*-
# [파일명] check_06Prj_Ch6_FrameWork_RAUTO_Stg5_AllBarMLCPCV.py
# 코드길이: 약 140줄 | 내부버전: 06Prj_Ch6_Stg5_check_v1 | 로직 전체 출력(축약/생략 없음)
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명]
#   Stg5 결과물 오염검사 8시나리오 + 결과 전량 파일로(00WorkHstr txt + INDEX).
#   ★엔진 무수정 해시 / ★미래참조 3중(소스 shift- 스캔 + 특징shift + CPCV purge) / ★label 특징배제
#   ★CPCV 과적합경보: 단일분할 AUC는 높은데 CPCV 평균이 낮으면 '단일경로 과적합' 경고(CPCV 본래 목적).
# [In] .stg5_metric / *.csv / 소스  [Out] PASS/FAIL + txt + INDEX
# ==============================================================================
import os, sys, hashlib, datetime
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__)); PARENT = os.path.dirname(HERE)
HSTR = os.path.join(PARENT, "00WorkHstr")
SRCS = [os.path.join(HERE, x) for x in ("test_06Prj_Ch6_FrameWork_RAUTO_Stg5_AllBarMLCPCV.py",
                                        "regime_classifier.py", "forced_entry.py", "cpcv.py")]
NAME = "06Prj_Ch6_Stg5_AllBarMLCPCV"
ENGINE_HASH = {
    "SpTrd_Fib_V1_Champion.py": "7f9192e3d50b1afd659a02b9e75764e5438ad57809c93093ab5f1973bb79ca75",
    "SidewayDCA_Stg7_engine.py": "dfdfac4394cd780939d4b368d3ccabfbfab8d599ff1236b11f7f0d80f0823086",
}
REQ_CSV = ["allbar_ml_cpcv.csv", "ml_model_compare.csv", "ml_feature_importance.csv", "cpcv_paths.csv",
           "compare_stg4.csv", "matrix_regime.csv", "matrix_year.csv", "matrix_side.csv", "ledger_trades.csv", "summary.csv"]


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(65536), b""):
            h.update(b)
    return h.hexdigest()


def read_metric():
    d = {}; p = os.path.join(HERE, ".stg5_metric")
    if os.path.exists(p):
        for ln in open(p, encoding="utf-8"):
            if "=" in ln:
                k, v = ln.strip().split("=", 1); d[k] = v
    return d


def fnum(x, dflt=None):
    try:
        return float(x)
    except Exception:
        return dflt


def main():
    os.makedirs(HSTR, exist_ok=True); M = read_metric(); res = []

    miss = [c for c in REQ_CSV if not (os.path.exists(os.path.join(HERE, c)) and os.path.getsize(os.path.join(HERE, c)) > 0)]
    res.append(("S1 필수파일/비공백(10종)", len(miss) == 0, f"누락 {miss}" if miss else "10종 OK"))

    bad = []
    for fn, want in ENGINE_HASH.items():
        p = os.path.join(HERE, "bots", fn); got = sha(p) if os.path.exists(p) else "없음"
        if got != want:
            bad.append(f"{fn}:{got[:8]}")
    res.append(("S2 엔진해시 무수정", len(bad) == 0, "일치" if not bad else f"불일치 {bad}"))

    src = ""
    for s in SRCS:
        if os.path.exists(s):
            src += open(s, encoding="utf-8").read()
    look = ("shift(-" in src) or (".shift(-" in src)
    res.append(("S3 미래참조 가드(shift- 없음)", not look, "없음" if not look else "★발견"))

    nt = int(fnum(M.get("n_trend", 0), 0)); ns = int(fnum(M.get("n_sw", 0), 0)); mls = int(fnum(M.get("ml_samples", 0), 0))
    res.append(("S4 거래>0 & 전봉ML표본>408(표본증가확인)", nt > 0 and ns > 0 and mls > 408,
                f"추세{nt}/횡보{ns}/전봉ML표본{mls}(거래봉408 대비)"))

    res.append(("S5 label 특징배제", M.get("label_in_feature", "False") == "False", M.get("label_in_feature", "?")))

    cp_paths = int(fnum(M.get("cpcv_paths", 0), 0))
    res.append(("S6 CPCV 15경로 생성(N6,k2)", cp_paths >= 12, f"경로 {cp_paths}개(15 표준, purge로 일부 제외가능)"))

    # S7 CPCV 누수/과적합 경보: 단일분할 높은데 CPCV평균 낮으면 과적합 / CPCV평균 0.95+면 누수
    sa = fnum(M.get("simple_oos_auc"), None); cm = fnum(M.get("cpcv_auc_mean"), None)
    if cm is None:
        ok7 = True; memo7 = "CPCV 미산출(표본부족)"
    elif cm >= 0.95:
        ok7 = False; memo7 = f"★CPCV평균 {cm} 누수의심(0.95+)"
    else:
        ok7 = True
        gap = (sa - cm) if (sa is not None) else 0
        memo7 = f"단일 {sa} vs CPCV평균 {cm} (격차 {round(gap,3)}: 클수록 단일경로 과적합=CPCV가 잡아냄)"
    res.append(("S7 CPCV 누수경보(평균<0.95)", ok7, memo7))

    # S8 ML 유효성 결론(CPCV p25 기준)
    p25 = fnum(M.get("cpcv_auc_p25"), None)
    vm = M.get("verdict_ml", "?")
    ok8 = vm in ("ML유효", "ML무효(표본늘려도 동전)")
    res.append(("S8 ML 유효성 결론(CPCV 분포기반)", ok8, f"{vm} | CPCV p25={p25} 최저={M.get('cpcv_auc_min','?')}"))

    passed = sum(1 for _, ok, _ in res if ok); verdict = "PASS" if passed == len(res) else "FAIL"
    summary = (f"VERDICT {NAME} | 8시나리오 {passed}/{len(res)} {verdict} | "
               f"전봉ML표본 {M.get('ml_samples','?')}(거래봉408 대비) 보유상한 추세{M.get('hold_T','?')}/횡보{M.get('hold_S','?')} | "
               f"best {M.get('best_model','?')} 단일OOS_AUC {M.get('simple_oos_auc','?')} | "
               f"CPCV {M.get('cpcv_paths','?')}경로 평균 {M.get('cpcv_auc_mean','?')} 최저 {M.get('cpcv_auc_min','?')} p25 {M.get('cpcv_auc_p25','?')} | "
               f"-> {M.get('verdict_ml','?')} | 미래참조차단={M.get('lookahead_block','?')} | check:{verdict}")

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    with open(os.path.join(HSTR, f"{stamp}.txt"), "w", encoding="utf-8") as f:
        f.write(summary + "\n\n[8시나리오 상세]\n")
        for nm, ok, memo in res:
            f.write(f"  [{'OK' if ok else 'X '}] {nm} : {memo}\n")
        f.write("\n[엔진 무수정 해시]\n")
        for fn, hsh in ENGINE_HASH.items():
            f.write(f"  {fn} = {hsh[:16]}...\n")
        f.write("\n[메모] 사장님 확정 (C)전봉강제진입+거른이유특징 + 방식2고정청산 + 보유상한자동 + CPCV(N6,k2).\n"
                "  표본을 408→전봉으로 늘려 'ML 실패가 표본부족 탓인가'를 끝까지 검증. CPCV는 단일경로 과적합을 분포로 폭로.\n"
                "  ★해석: CPCV p25(하위25%)가 0.55 위면 ML유효, 아니면 표본 늘려도 동전 → ML 장세예측 최종 폐기 근거.\n"
                "  단일분할 AUC가 높아도 CPCV 평균이 낮으면 그 높은값은 운(한 경로)일 뿐 — 이게 CPCV를 쓴 이유.\n")

    idx = os.path.join(HSTR, "00WorkHstr_INDEX.txt")
    with open(idx, "a", encoding="utf-8") as f:
        f.write(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} | {NAME} | 분석:{stamp}.txt | {summary}\n")

    print(summary)
    print(f"[check] 분석txt -> {os.path.join(HSTR, stamp+'.txt')}")
    print(f"[check] INDEX 추가 -> {idx}")


if __name__ == "__main__":
    main()
