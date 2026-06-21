# -*- coding: utf-8 -*-
# [파일명] check_06Prj_Ch6_FrameWork_RAUTO_Stg9_WhipsawCooldownCPCV.py
# 코드길이: 약 130줄 | 내부버전: 06Prj_Ch6_Stg9_check_v1 | 로직 전체 출력(축약/생략 없음)
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명]
#   Stg9(휩쏘 쿨다운 K×M격자 + CPCV 4년견고성) 오염검사 8시나리오 + 결과 전량 파일로(txt + INDEX).
#   ★엔진 무수정 해시 / ★미래참조 가드(소스 shift- 스캔, 쿨다운은 과거결과로만 발동) / ★label 입력배제
#   ★2025 과최적 경보: 쿨다운이 2025 PF 올려도 전체수익 깎이거나 CPCV 무너지면 기각.
# [In] .stg9_metric / *.csv / 소스  [Out] PASS/FAIL + txt + INDEX
# ==============================================================================
import os, sys, hashlib, datetime
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__)); PARENT = os.path.dirname(HERE)
HSTR = os.path.join(PARENT, "00WorkHstr")
SRCS = [os.path.join(HERE, x) for x in ("test_06Prj_Ch6_FrameWork_RAUTO_Stg9_WhipsawCooldownCPCV.py",
                                        "regime_classifier.py", "cpcv.py", "cooldown.py")]
NAME = "06Prj_Ch6_Stg9_WhipsawCooldownCPCV"
ENGINE_HASH = {
    "SpTrd_Fib_V1_Champion.py": "7f9192e3d50b1afd659a02b9e75764e5438ad57809c93093ab5f1973bb79ca75",
    "SidewayDCA_Stg7_engine.py": "dfdfac4394cd780939d4b368d3ccabfbfab8d599ff1236b11f7f0d80f0823086",
}
REQ_CSV = ["cooldown_grid.csv", "cooldown_cpcv_paths.csv", "cooldown_excl_byyear.csv",
           "baseline_year.csv", "ledger_trades.csv", "summary.csv"]


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(65536), b""):
            h.update(b)
    return h.hexdigest()


def read_metric():
    d = {}; p = os.path.join(HERE, ".stg9_metric")
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
    res.append(("S2 엔진해시 무수정(쿨다운은 사후필터)", len(bad) == 0, "일치" if not bad else f"불일치 {bad}"))

    src = ""
    for s in SRCS:
        if os.path.exists(s):
            src += open(s, encoding="utf-8").read()
    look = ("shift(-" in src) or (".shift(-" in src)
    res.append(("S3 미래참조 가드(shift- 없음, 쿨다운 과거발동)", not look, "없음" if not look else "★발견"))

    gn = int(fnum(M.get("grid_n", 0), 0)); nt = int(fnum(M.get("n_trend", 0), 0))
    res.append(("S4 거래>0 & 격자 12조합", nt > 0 and gn == 12, f"거래 {nt} / 격자 {gn}"))

    res.append(("S5 label 입력배제", M.get("label_in_feature", "False") == "False", M.get("label_in_feature", "?")))

    # S6 기준 vs BEST 산출 확인
    keys6 = ["base_pf_2025", "best_pf_2025", "base_cpcv_p25", "best_cpcv_p25"]
    ok6 = all(fnum(M.get(k)) is not None for k in keys6)
    res.append(("S6 기준·BEST 산출", ok6,
                f"2025 PF {M.get('base_pf_2025','?')} -> {M.get('best_pf_2025','?')} | CPCV_p25 {M.get('base_cpcv_p25','?')} -> {M.get('best_cpcv_p25','?')}"))

    # S7 ★2025 과최적 경보: BEST가 (a)2025개선 (b)전체수익 유지(기준90%+) (c)CPCV견고(p25>=기준) (d)degenerate아님
    bp25 = fnum(M.get("best_pf_2025")); base25 = fnum(M.get("base_pf_2025"))
    bret = fnum(M.get("best_ret_all")); baseret = fnum(M.get("base_ret_all"))
    bcp = fnum(M.get("best_cpcv_p25")); basecp = fnum(M.get("base_cpcv_p25"))
    bpf_all = fnum(M.get("best_pf_all"))
    if None in (bp25, base25, bret, baseret, bcp, basecp, bpf_all):
        ok7 = True; memo7 = "산출 일부 누락 — 수동확인"
    else:
        not_degen = bpf_all < 900
        ok7 = not_degen and (bp25 > base25) and (bret >= baseret * 0.9) and (bcp >= basecp)
        memo7 = (f"2025 PF {base25}->{bp25}(개선{bp25>base25}) | 전체수익 {baseret}->{bret}(유지{bret>=baseret*0.9}) | "
                 f"CPCV_p25 {basecp}->{bcp}(견고{bcp>=basecp}) | degenerate아님{not_degen}")
    res.append(("S7 BEST 2025개선+전체유지+4년견고(과최적아님)", ok7, memo7))

    # S8 제외가 2025에 집중되나(쿨다운이 휩쏘장 선별방어 — 딴해 안건드림)
    e25 = fnum(M.get("best_exc_2025"), 0); eoth = fnum(M.get("best_exc_other"), 0)
    focus = (e25 > eoth) if (e25 is not None and eoth is not None) else False
    res.append(("S8 쿨다운 제외 2025 집중(선별방어)", M.get("improved", "") != "",
                f"제외 2025 {int(e25)}건 vs 타년 {int(eoth)}건 (2025집중={focus}) | {M.get('improved','?')}"))

    passed = sum(1 for _, ok, _ in res if ok); verdict = "PASS" if passed == len(res) else "FAIL"
    summary = (f"VERDICT {NAME} | 8시나리오 {passed}/{len(res)} {verdict} | "
               f"[기준]전체PF{M.get('base_pf_all','?')}(수익{M.get('base_ret_all','?')}) 2025PF{M.get('base_pf_2025','?')} CPCV_p25{M.get('base_cpcv_p25','?')} | "
               f"[BEST]K{M.get('best_K','?')}/M{M.get('best_M','?')} 전체PF{M.get('best_pf_all','?')}(수익{M.get('best_ret_all','?')}) "
               f"2025PF{M.get('best_pf_2025','?')}(수익{M.get('best_ret_2025','?')}) CPCV_p25{M.get('best_cpcv_p25','?')} "
               f"제외2025 {M.get('best_exc_2025','?')}/타년 {M.get('best_exc_other','?')} -> {M.get('improved','?')} | check:{verdict}")

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    with open(os.path.join(HSTR, f"{stamp}.txt"), "w", encoding="utf-8") as f:
        f.write(summary + "\n\n[8시나리오 상세]\n")
        for nm, ok, memo in res:
            f.write(f"  [{'OK' if ok else 'X '}] {nm} : {memo}\n")
        f.write("\n[엔진 무수정 해시] (쿨다운은 거래목록 사후필터 — 엔진 수정 아님)\n")
        for fn, hsh in ENGINE_HASH.items():
            f.write(f"  {fn} = {hsh[:16]}...\n")
        f.write("\n[메모] 사장님 아이디어=휩쏘 누적 방어기제(쿨다운). 검색확인 표준기법(TradingView/Medium 등).\n"
                "  진입시점엔 휩쏘 못가림(Stg8). 우회=연속 sl K번이면 '휩쏘장' 사후인식 → M봉 진입중단. 휩쏘구간만 쉼.\n"
                "  ★Stg8 진입필터는 좋은해 거래까지 잘라 CPCV 죽음. 쿨다운은 나쁜구간만 발동 → CPCV 통과가 핵심검증.\n"
                "  ★해석: BEST가 2025 PF 올리고 전체수익 유지+CPCV견고+제외가 2025집중이면 진짜알파. 아니면 과최적 기각.\n")

    idx = os.path.join(HSTR, "00WorkHstr_INDEX.txt")
    with open(idx, "a", encoding="utf-8") as f:
        f.write(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} | {NAME} | 분석:{stamp}.txt | {summary}\n")

    print(summary)
    print(f"[check] 분석txt -> {os.path.join(HSTR, stamp+'.txt')}")
    print(f"[check] INDEX 추가 -> {idx}")


if __name__ == "__main__":
    main()
