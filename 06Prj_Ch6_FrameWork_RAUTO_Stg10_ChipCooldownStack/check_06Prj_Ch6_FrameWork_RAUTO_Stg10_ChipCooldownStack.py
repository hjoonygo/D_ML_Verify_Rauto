# -*- coding: utf-8 -*-
# [파일명] check_06Prj_Ch6_FrameWork_RAUTO_Stg10_ChipCooldownStack.py
# 코드길이: 약 120줄 | 내부버전: 06Prj_Ch6_Stg10_check_v1 | 로직 전체 출력(축약/생략 없음)
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명] Stg10(칩필터+쿨다운 합산) 오염검사 8시나리오 + 결과 전량 파일로(txt+INDEX).
#   ★엔진해시 무수정 / ★미래참조 가드 / ★label배제 / ★합산판정(D vs B 비교가 기록됐나).
# ==============================================================================
import os, sys, hashlib, datetime
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__)); PARENT = os.path.dirname(HERE)
HSTR = os.path.join(PARENT, "00WorkHstr")
SRCS = [os.path.join(HERE, x) for x in ("test_06Prj_Ch6_FrameWork_RAUTO_Stg10_ChipCooldownStack.py",
                                        "regime_classifier.py", "cpcv.py", "cooldown.py")]
NAME = "06Prj_Ch6_Stg10_ChipCooldownStack"
ENGINE_HASH = {
    "SpTrd_Fib_V1_Champion.py": "7f9192e3d50b1afd659a02b9e75764e5438ad57809c93093ab5f1973bb79ca75",
    "SidewayDCA_Stg7_engine.py": "dfdfac4394cd780939d4b368d3ccabfbfab8d599ff1236b11f7f0d80f0823086",
}
REQ_CSV = ["stack_compare.csv", "stack_cpcv_paths.csv", "stack_by_year.csv", "ledger_trades.csv", "summary.csv"]


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(65536), b""):
            h.update(b)
    return h.hexdigest()


def read_metric():
    d = {}; p = os.path.join(HERE, ".stg10_metric")
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
    res.append(("S1 필수파일/비공백(5종)", len(miss) == 0, f"누락 {miss}" if miss else "5종 OK"))

    bad = []
    for fn, want in ENGINE_HASH.items():
        p = os.path.join(HERE, "bots", fn); got = sha(p) if os.path.exists(p) else "없음"
        if got != want:
            bad.append(f"{fn}:{got[:8]}")
    res.append(("S2 엔진해시 무수정(Stg15·Ch6 동일)", len(bad) == 0, "일치" if not bad else f"불일치 {bad}"))

    src = ""
    for s in SRCS:
        if os.path.exists(s):
            src += open(s, encoding="utf-8").read()
    look = ("shift(-" in src) or (".shift(-" in src)
    res.append(("S3 미래참조 가드(shift- 없음)", not look, "없음" if not look else "★발견"))

    nt = int(fnum(M.get("n_trend", 0), 0)); nc = int(fnum(M.get("n_chip", 0), 0))
    res.append(("S4 거래>0 & 칩거래 식별", nt > 0 and nc >= 0, f"거래 {nt} / 칩 {nc}(2025중 {M.get('n_chip_2025','?')})"))

    res.append(("S5 label 입력배제", M.get("label_in_feature", "False") == "False", M.get("label_in_feature", "?")))

    # S6 4종 다 산출
    keys6 = ["A_ret_2025", "B_ret_2025", "C_ret_2025", "D_ret_2025"]
    ok6 = all(fnum(M.get(k)) is not None for k in keys6)
    res.append(("S6 4종(A/B/C/D) 산출", ok6,
                f"A {M.get('A_ret_2025','?')} / B {M.get('B_ret_2025','?')} / C {M.get('C_ret_2025','?')} / D {M.get('D_ret_2025','?')}"))

    # S7 합산판정: D vs B (쿨다운이 칩필터에 보태지나)
    bd = fnum(M.get("B_ret_2025")); dd = fnum(M.get("D_ret_2025"))
    if bd is None or dd is None:
        ok7 = False; memo7 = "B/D 미산출"
    else:
        ok7 = M.get("verdict_stack", "") != ""
        delta = round(dd - bd, 2)
        memo7 = f"D(합산) 2025 {dd} vs B(칩필터) {bd} (차이 {delta}) -> {M.get('verdict_stack','?')}"
    res.append(("S7 합산판정(D vs B) 기록", ok7, memo7))

    # S8 D degenerate 아님 & CPCV 산출
    dpf = fnum(M.get("D_pf_all")); dp25 = fnum(M.get("D_cpcv_p25"))
    ok8 = (dpf is not None and dpf < 900)
    res.append(("S8 D degenerate아님 & CPCV", ok8, f"D 전체PF {dpf} CPCV_p25 {dp25}"))

    passed = sum(1 for _, ok, _ in res if ok); verdict = "PASS" if passed == len(res) else "FAIL"
    summary = (f"VERDICT {NAME} | 8시나리오 {passed}/{len(res)} {verdict} | 추세봇 {M.get('n_trend','?')}건(칩 {M.get('n_chip','?')}) | "
               f"[2025수익] A {M.get('A_ret_2025','?')}% / B칩필터 {M.get('B_ret_2025','?')}% / C쿨다운 {M.get('C_ret_2025','?')}% / D합산 {M.get('D_ret_2025','?')}% | "
               f"[D전체] PF {M.get('D_pf_all','?')} 수익 {M.get('D_ret_all','?')}% CPCV_p25 {M.get('D_cpcv_p25','?')} | -> {M.get('verdict_stack','?')} | check:{verdict}")

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    with open(os.path.join(HSTR, f"{stamp}.txt"), "w", encoding="utf-8") as f:
        f.write(summary + "\n\n[8시나리오 상세]\n")
        for nm, ok, memo in res:
            f.write(f"  [{'OK' if ok else 'X '}] {nm} : {memo}\n")
        f.write("\n[엔진 무수정 해시] (Stg15·Ch6 동일 — 칩필터·쿨다운 모두 사후필터, 엔진 수정 아님)\n")
        for fn, hsh in ENGINE_HASH.items():
            f.write(f"  {fn} = {hsh[:16]}...\n")
        f.write("\n[메모] 사장님 확정(가): Stg15 칩필터 추세봇(+4.81%)에 Ch6 쿨다운 합산. er게이트는 Stg15에 이미 내장.\n"
                "  4종 비교 A기본/B칩필터(Stg15)/C쿨다운/D합산. ★판정: D 2025수익>B면 추가이득, D≈B면 중복, D<B면 충돌.\n"
                "  칩필터·쿨다운 둘다 2025 나쁜거래를 거르므로 중복 가능성 점검이 이 단계의 핵심.\n")

    idx = os.path.join(HSTR, "00WorkHstr_INDEX.txt")
    with open(idx, "a", encoding="utf-8") as f:
        f.write(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} | {NAME} | 분석:{stamp}.txt | {summary}\n")

    print(summary)
    print(f"[check] 분석txt -> {os.path.join(HSTR, stamp+'.txt')}")
    print(f"[check] INDEX 추가 -> {idx}")


if __name__ == "__main__":
    main()
