# -*- coding: utf-8 -*-
# [파일명] check_06Prj_Ch6_FrameWork_RAUTO_Stg7_TrendGateCPCV.py
# 코드길이: 약 130줄 | 내부버전: 06Prj_Ch6_Stg7_check_v1 | 로직 전체 출력(축약/생략 없음)
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명]
#   Stg7(gate_mode 4종 CPCV + 칩장진입 사후필터) 오염검사 8시나리오 + 결과 전량 파일로(00WorkHstr txt + INDEX).
#   ★엔진 무수정 해시 / ★미래참조 가드(소스 shift- 스캔) / ★label 입력배제 / ★gate 4종 전부 실행됐나.
# [In] .stg7_metric / *.csv / 소스  [Out] PASS/FAIL + txt + INDEX
# ==============================================================================
import os, sys, hashlib, datetime
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__)); PARENT = os.path.dirname(HERE)
HSTR = os.path.join(PARENT, "00WorkHstr")
SRCS = [os.path.join(HERE, x) for x in ("test_06Prj_Ch6_FrameWork_RAUTO_Stg7_TrendGateCPCV.py",
                                        "regime_classifier.py", "cpcv.py")]
NAME = "06Prj_Ch6_Stg7_TrendGateCPCV"
ENGINE_HASH = {
    "SpTrd_Fib_V1_Champion.py": "7f9192e3d50b1afd659a02b9e75764e5438ad57809c93093ab5f1973bb79ca75",
    "SidewayDCA_Stg7_engine.py": "dfdfac4394cd780939d4b368d3ccabfbfab8d599ff1236b11f7f0d80f0823086",
}
REQ_CSV = ["gate_compare.csv", "gate_cpcv_paths.csv", "chipentry_filter.csv",
           "chipentry_cpcv_paths.csv", "ledger_trades.csv", "summary.csv"]


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(65536), b""):
            h.update(b)
    return h.hexdigest()


def read_metric():
    d = {}; p = os.path.join(HERE, ".stg7_metric")
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
    res.append(("S1 필수파일/비공백(6종)", len(miss) == 0, f"누락 {miss}" if miss else "6종 OK"))

    bad = []
    for fn, want in ENGINE_HASH.items():
        p = os.path.join(HERE, "bots", fn); got = sha(p) if os.path.exists(p) else "없음"
        if got != want:
            bad.append(f"{fn}:{got[:8]}")
    res.append(("S2 엔진해시 무수정(gate는 인자, 수정아님)", len(bad) == 0, "일치" if not bad else f"불일치 {bad}"))

    src = ""
    for s in SRCS:
        if os.path.exists(s):
            src += open(s, encoding="utf-8").read()
    look = ("shift(-" in src) or (".shift(-" in src)
    res.append(("S3 미래참조 가드(shift- 없음)", not look, "없음" if not look else "★발견"))

    gn = int(fnum(M.get("gate_n", 0), 0))
    none_n = int(fnum(M.get("gate_none_n", 0), 0))
    res.append(("S4 gate 4종 전부 실행 & 거래>0", gn == 4 and none_n > 0, f"gate종류 {gn} / none거래 {none_n}"))

    res.append(("S5 label 입력배제", M.get("label_in_feature", "False") == "False", M.get("label_in_feature", "?")))

    # S6 gate CPCV 산출 확인(4종 p25 다 있나)
    p25s = [M.get(f"gate_{g}_cpcv_p25") for g in ('none', 'adx', 'er', 'adx_bb')]
    ok6 = all(fnum(x) is not None for x in p25s)
    res.append(("S6 gate 4종 CPCV p25 산출", ok6, f"none/adx/er/adx_bb p25 = {p25s}"))

    # S7 칩장진입 필터 트레이드오프 기록(PF·수익 둘다)
    ca_pf = fnum(M.get("chip_all_pf")); ck_pf = fnum(M.get("chip_keep_pf"))
    ca_ret = fnum(M.get("chip_all_ret")); ck_ret = fnum(M.get("chip_keep_ret"))
    ok7 = all(x is not None for x in (ca_pf, ck_pf, ca_ret, ck_ret))
    res.append(("S7 칩장진입 PF·수익 트레이드오프 기록", ok7,
                f"전체 PF{ca_pf}/수익{ca_ret} -> 칩제외 PF{ck_pf}/수익{ck_ret} | {M.get('chip_tradeoff','?')}"))

    # S8 결론
    ok8 = (M.get("gate_helps", "") != "") and (M.get("chip_tradeoff", "") != "")
    res.append(("S8 결론 기록완료(gate효과+칩장트레이드오프)", ok8,
                f"BEST gate {M.get('best_gate','?')} -> {M.get('gate_helps','?')} / 칩장 {M.get('chip_tradeoff','?')}"))

    passed = sum(1 for _, ok, _ in res if ok); verdict = "PASS" if passed == len(res) else "FAIL"
    summary = (f"VERDICT {NAME} | 8시나리오 {passed}/{len(res)} {verdict} | "
               f"[gate 4종 CPCV p25] none {M.get('gate_none_cpcv_p25','?')} / adx {M.get('gate_adx_cpcv_p25','?')} / "
               f"er {M.get('gate_er_cpcv_p25','?')} / adx_bb {M.get('gate_adx_bb_cpcv_p25','?')} -> BEST {M.get('best_gate','?')} ({M.get('gate_helps','?')}) | "
               f"[칩장진입] 전체 PF{M.get('chip_all_pf','?')}/수익{M.get('chip_all_ret','?')} -> 칩제외 PF{M.get('chip_keep_pf','?')}/수익{M.get('chip_keep_ret','?')} "
               f"(제외 {M.get('chip_excluded_n','?')}건/수익{M.get('chip_excluded_ret','?')}%) -> {M.get('chip_tradeoff','?')} | check:{verdict}")

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    with open(os.path.join(HSTR, f"{stamp}.txt"), "w", encoding="utf-8") as f:
        f.write(summary + "\n\n[8시나리오 상세]\n")
        for nm, ok, memo in res:
            f.write(f"  [{'OK' if ok else 'X '}] {nm} : {memo}\n")
        f.write("\n[엔진 무수정 해시] (gate_mode는 run_strategy 인자 — 엔진 수정 아님)\n")
        for fn, hsh in ENGINE_HASH.items():
            f.write(f"  {fn} = {hsh[:16]}...\n")
        f.write("\n[메모] 추세봇 내장 gate_mode(장세판단 로직)가 칩장 추세봇에 도움되나 검증. 표준값 고정(ER0.40/ADX25).\n"
                "  ★해석: BEST gate의 CPCV p25가 none보다 높으면 게이트 도움. 칩장진입 제외는 PF↑수익↓면 라우팅자살골 재확인.\n"
                "  (A)계열 결과 → 이걸로 (B)엔진수정 필요여부를 사장님과 결정. 엔진수정은 무수정원칙 깨므로 신중.\n")

    idx = os.path.join(HSTR, "00WorkHstr_INDEX.txt")
    with open(idx, "a", encoding="utf-8") as f:
        f.write(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} | {NAME} | 분석:{stamp}.txt | {summary}\n")

    print(summary)
    print(f"[check] 분석txt -> {os.path.join(HSTR, stamp+'.txt')}")
    print(f"[check] INDEX 추가 -> {idx}")


if __name__ == "__main__":
    main()
