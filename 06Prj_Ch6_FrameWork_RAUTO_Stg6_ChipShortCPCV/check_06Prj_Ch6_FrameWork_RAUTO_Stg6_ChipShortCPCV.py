# -*- coding: utf-8 -*-
# [파일명] check_06Prj_Ch6_FrameWork_RAUTO_Stg6_ChipShortCPCV.py
# 코드길이: 약 135줄 | 내부버전: 06Prj_Ch6_Stg6_check_v1 | 로직 전체 출력(축약/생략 없음)
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명]
#   Stg6(A 칩필터 CPCV + B 숏필터 격자) 오염검사 8시나리오 + 결과 전량 파일로(00WorkHstr txt + INDEX).
#   ★엔진 무수정 해시 / ★미래참조 가드(소스 shift- 스캔) / ★label 입력배제 / ★degenerate(PF999) 캡 확인.
# [In] .stg6_metric / *.csv / 소스  [Out] PASS/FAIL + txt + INDEX
# ==============================================================================
import os, sys, hashlib, datetime
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__)); PARENT = os.path.dirname(HERE)
HSTR = os.path.join(PARENT, "00WorkHstr")
SRCS = [os.path.join(HERE, x) for x in ("test_06Prj_Ch6_FrameWork_RAUTO_Stg6_ChipShortCPCV.py",
                                        "regime_classifier.py", "cpcv.py")]
NAME = "06Prj_Ch6_Stg6_ChipShortCPCV"
ENGINE_HASH = {
    "SpTrd_Fib_V1_Champion.py": "7f9192e3d50b1afd659a02b9e75764e5438ad57809c93093ab5f1973bb79ca75",
    "SidewayDCA_Stg7_engine.py": "dfdfac4394cd780939d4b368d3ccabfbfab8d599ff1236b11f7f0d80f0823086",
}
REQ_CSV = ["chip_cpcv.csv", "chip_cpcv_paths.csv", "short_breakdown.csv", "short_grid.csv",
           "short_cpcv_paths.csv", "ledger_trades.csv", "summary.csv"]


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(65536), b""):
            h.update(b)
    return h.hexdigest()


def read_metric():
    d = {}; p = os.path.join(HERE, ".stg6_metric")
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

    nt = int(fnum(M.get("n_trend", 0), 0)); ns = int(fnum(M.get("n_short", 0), 0)); gn = int(fnum(M.get("short_grid_n", 0), 0))
    res.append(("S4 거래>0 & 숏격자18", nt > 0 and ns > 0 and gn == 18, f"추세{nt}/숏{ns}/격자{gn}"))

    res.append(("S5 label 입력배제", M.get("label_in_feature", "False") == "False", M.get("label_in_feature", "?")))

    # S6 A 칩필터 CPCV: ON p25가 OFF p25보다 높으면 칩필터 효과
    on_p25 = fnum(M.get("chip_on_cpcv_p25"), None); off_p25 = fnum(M.get("chip_off_cpcv_p25"), None)
    if on_p25 is None or off_p25 is None:
        ok6 = False; memo6 = "CPCV 미산출"
    else:
        ok6 = on_p25 >= off_p25
        memo6 = f"ON p25 {on_p25} vs OFF p25 {off_p25} | {M.get('chip_robust','?')} (PF<1경로 {M.get('chip_on_below1','?')}/{M.get('chip_on_paths','?')})"
    res.append(("S6 A 칩필터 CPCV 효과(ON p25>=OFF)", ok6, memo6))

    # S7 B 숏필터: BEST PF가 기존보다 개선 + degenerate(PF999) 아님
    sb = fnum(M.get("short_best_pf"), None); base = fnum(M.get("short_base_pf"), None)
    if sb is None or base is None:
        ok7 = False; memo7 = "숏 미산출"
    else:
        not_degen = sb < 900
        ok7 = (M.get("short_improved", "") == "개선") and not_degen
        memo7 = f"기존 {base} -> BEST {sb} ({M.get('short_improved','?')}) degenerate아님={not_degen} CPCV_p25={M.get('short_best_cpcv_p25','?')}"
    res.append(("S7 B 숏필터 개선 & degenerate아님", ok7, memo7))

    # S8 결론 기록 완료
    ok8 = (M.get("chip_robust", "") in ("견고", "불안정")) and (M.get("short_improved", "") in ("개선", "개선못함"))
    res.append(("S8 A·B 결론 기록완료", ok8, f"칩필터 {M.get('chip_robust','?')} / 숏 {M.get('short_improved','?')}"))

    passed = sum(1 for _, ok, _ in res if ok); verdict = "PASS" if passed == len(res) else "FAIL"
    summary = (f"VERDICT {NAME} | 8시나리오 {passed}/{len(res)} {verdict} | "
               f"추세{M.get('n_trend','?')}(롱{M.get('n_long','?')}/숏{M.get('n_short','?')})/횡보{M.get('n_sw','?')} | "
               f"[A 칩필터2of3] ON CPCV p25 {M.get('chip_on_cpcv_p25','?')} vs OFF {M.get('chip_off_cpcv_p25','?')} -> {M.get('chip_robust','?')} | "
               f"[B 숏] 기존PF {M.get('short_base_pf','?')} -> BEST(하락{M.get('short_best_downonly','?')}/ADX{M.get('short_best_adx','?')}/펀딩{M.get('short_best_fundpos','?')}) "
               f"PF {M.get('short_best_pf','?')}(n{M.get('short_best_n','?')}) -> {M.get('short_improved','?')} | check:{verdict}")

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    with open(os.path.join(HSTR, f"{stamp}.txt"), "w", encoding="utf-8") as f:
        f.write(summary + "\n\n[8시나리오 상세]\n")
        for nm, ok, memo in res:
            f.write(f"  [{'OK' if ok else 'X '}] {nm} : {memo}\n")
        f.write("\n[엔진 무수정 해시]\n")
        for fn, hsh in ENGINE_HASH.items():
            f.write(f"  {fn} = {hsh[:16]}...\n")
        f.write("\n[메모] (라) ML폐기 후 확실수확 굳히기. A=칩필터2of3을 CPCV(PF+거래수)로 과최적검증, "
                "B=숏약점을 장세/년도 분해 후 필터격자(하락장·ADX·OI펀딩)로 개선·CPCV검증.\n"
                "  ★해석: A는 ON p25가 OFF p25보다 높고 PF<1경로 적으면 채택. B는 숏 PF개선+degenerate아님+CPCV견고면 채택.\n"
                "  다음(Stg7)=C 제3 알파(두 봇과 상관낮은 새 수익원, 월목표 갭의 본질).\n")

    idx = os.path.join(HSTR, "00WorkHstr_INDEX.txt")
    with open(idx, "a", encoding="utf-8") as f:
        f.write(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} | {NAME} | 분석:{stamp}.txt | {summary}\n")

    print(summary)
    print(f"[check] 분석txt -> {os.path.join(HSTR, stamp+'.txt')}")
    print(f"[check] INDEX 추가 -> {idx}")


if __name__ == "__main__":
    main()
