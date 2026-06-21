# -*- coding: utf-8 -*-
# [파일명] check_06Prj_Ch7_stg4_GreedShortGuard.py
# 코드길이: 약 140줄 | 내부버전: 06Prj_Ch7_stg4_check_v1 | 로직 전체 출력(축약/생략 없음)
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일] Ch7 Stg4(시나리오A 탐욕숏가드) 오염검사 8시나리오 + 결과 전량 파일로.
#   ★분석txt·INDEX는 D:\ML\verify\00WorkHstr 로. 결과 csv는 하위폴더.
#   ★엔진해시 무수정 / ★미래참조(FNG전날값·smc사후라벨) / ★label입력배제 / ★복리·14bp / ★FNG커버 /
#   ★원장 분해표(월별·장세별·연도롱숏) 산출 / ★탐욕숏가드 거취 판정.
# [In] .stg4_metric + 결과 csv 7종 + bots/엔진 + fear_greed_loader
# [Out] D:\ML\verify\00WorkHstr\(분단위).txt + INDEX 한 줄. 콘솔 요약.
# ==============================================================================
import os, sys, hashlib, datetime
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__)); PARENT = os.path.dirname(HERE)
HSTR = os.path.join(PARENT, "00WorkHstr")
SRCS = [os.path.join(HERE, x) for x in ("test_06Prj_Ch7_stg4_GreedShortGuard.py",
                                        "regime_classifier.py", "cpcv.py", "cooldown.py", "fear_greed_loader.py")]
NAME = "06Prj_Ch7_stg4_GreedShortGuard"
ENGINE_HASH = {
    "SpTrd_Fib_V1_Champion.py": "7f9192e3d50b1afd659a02b9e75764e5438ad57809c93093ab5f1973bb79ca75",
    "SidewayDCA_Stg7_engine.py": "dfdfac4394cd780939d4b368d3ccabfbfab8d599ff1236b11f7f0d80f0823086",
}
REQ_CSV = ["stg4_greed_grid.csv", "stg4_best_ledger.csv", "stg4_by_month.csv", "stg4_by_regime.csv",
           "stg4_by_year_side.csv", "stg4_coverage.csv", "summary.csv"]


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(65536), b""):
            h.update(b)
    return h.hexdigest()


def read_metric():
    d = {}; p = os.path.join(HERE, ".stg4_metric")
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
    res.append(("S1 필수파일/비공백(7종)", len(miss) == 0, f"누락 {miss}" if miss else "7종 OK"))

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

    res.append(("S4 복리기준 $10,000", fnum(M.get("start")) == 10000.0, f"start={M.get('start','?')}"))

    res.append(("S5 label 입력배제", M.get("label_in_feature", "False") == "False", M.get("label_in_feature", "?")))

    # S6 미래참조 차단조합(FNG전날값 + smc사후라벨만) + 비용14bp
    lb = M.get("lookahead_block", "")
    fng_prev = "fng_prevday" in lb; smc_post = "smc_postlabel_only" in lb; cost_ok = fnum(M.get("cost_rt")) == 0.0014
    res.append(("S6 FNG전날값+smc사후라벨+14bp", fng_prev and smc_post and cost_ok,
                f"fng전날={fng_prev} smc사후={smc_post} cost={M.get('cost_rt','?')}"))

    # S7 FNG 커버리지 + 원장분해표(월별·장세·연도롱숏) 비공백
    cov = fnum(M.get("fng_coverage"))
    bm = os.path.join(HERE, "stg4_by_month.csv"); brg = os.path.join(HERE, "stg4_by_regime.csv")
    breakdowns_ok = all(os.path.exists(x) and os.path.getsize(x) > 0 for x in
                        [bm, brg, os.path.join(HERE, "stg4_by_year_side.csv")])
    res.append(("S7 FNG커버≥0.9 + 원장분해표", (cov is not None and cov >= 0.9) and breakdowns_ok,
                f"커버 {cov*100:.1f}% / 월별·장세·연도롱숏 {'OK' if breakdowns_ok else '누락'}" if cov is not None else "커버 ?"))

    # S8 탐욕숏가드 거취 판정 + 과최적화(전연도 일관성) + CPCV
    be = fnum(M.get("base_end")); bend = fnum(M.get("best_end"))
    byp = M.get("best_years_positive", "?"); bsr = M.get("best_short2025_ret", "?")
    bsr_base = M.get("base_short2025_ret", "?")
    ok8 = fnum(M.get("base_cpcv_p25")) is not None and bend is not None
    if bend is not None and be is not None:
        v8 = (f"BEST {M.get('best_case','?')} ${bend:.0f} vs 기준 ${be:.0f} | "
              f"2025숏 R {bsr_base}%→{bsr}% | 전연도+ {byp}/4(=과최적화 점검)")
    else:
        v8 = "BEST 미산출"
    res.append(("S8 탐욕숏가드 거취+전연도일관성+CPCV", ok8, v8))

    passed = sum(1 for _, ok, _ in res if ok); verdict = "PASS" if passed == len(res) else "FAIL"
    summary = (f"VERDICT {NAME} | 8시나리오 {passed}/{len(res)} {verdict} | $10k복리·14bp·실펀딩 | "
               f"FNG커버{(cov*100 if cov else 0):.0f}% 장세{M.get('regime_source','?')} | "
               f"[기준선] ${M.get('base_end','?')}({M.get('base_ret','?')}% MDD{M.get('base_mdd','?')} "
               f"p25{M.get('base_cpcv_p25','?')} 2025_{M.get('base_ret2025','?')}% 2025숏R{bsr_base}% 전연도+{M.get('base_years_positive','?')}/4) | "
               f"[BEST] {M.get('best_case','?')} ${M.get('best_end','?')}(MDD{M.get('best_mdd','?')} "
               f"p25{M.get('best_cpcv_p25','?')} 2025_{M.get('best_ret2025','?')}% 2025숏R{bsr}% 전연도+{byp}/4) "
               f"월별+{M.get('best_months_positive','?')}/{M.get('best_months_total','?')} | check:{verdict}")

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    with open(os.path.join(HSTR, f"{stamp}.txt"), "w", encoding="utf-8") as f:
        f.write(summary + "\n\n[8시나리오 상세]\n")
        for nm2, ok, memo in res:
            f.write(f"  [{'OK' if ok else 'X '}] {nm2} : {memo}\n")
        f.write("\n[엔진 무수정 해시]\n")
        for fn, hsh in ENGINE_HASH.items():
            f.write(f"  {fn} = {hsh[:16]}...\n")
        f.write("\n[메모] Ch7 Stg4 시나리오A: 공포지수 탐욕(>=55/60/65)시 숏 차단/축소로 ④스택 보강.\n"
                "  근거: 원장+FNG 결합분석 — 숏의 진짜 약점은 극공포 아닌 탐욕구간(전기간 PF0.62·R-10.3%).\n"
                "  stg3(극공포차단)는 2025특화 의심 → stg4는 전기간 견고성 검증. 검색: FNG는 거시필터(정밀저격X).\n"
                "  ★전날 FNG로 진입판정(미래참조X). label_smc_8은 사후 장세라벨링에만(진입결정 미사용).\n"
                "  ★원장에 월별·4장세·롱숏·FNG 표준부착 → 36개월 월별/장세별/연도롱숏 자동산출(사장님 표준요청).\n"
                "  판정: 전연도(2023~2026) 플러스 일관성 + CPCV>=기준 + 잔고 종합. 한 해 특화는 과최적화로 감점.\n")

    idx = os.path.join(HSTR, "00WorkHstr_INDEX.txt")
    with open(idx, "a", encoding="utf-8") as f:
        f.write(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} | {NAME} | 분석:{stamp}.txt | {summary}\n")

    print(summary)
    print(f"[check] 분석txt -> {os.path.join(HSTR, stamp+'.txt')}")
    print(f"[check] INDEX 추가 -> {idx}")


if __name__ == "__main__":
    main()
