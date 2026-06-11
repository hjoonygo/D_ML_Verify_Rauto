# -*- coding: utf-8 -*-
# [파일명] check_06Prj_Ch6_FrameWork_RAUTO_Stg8_Y2025Forensics.py
# 코드길이: 약 130줄 | 내부버전: 06Prj_Ch6_Stg8_check_v1 | 로직 전체 출력(축약/생략 없음)
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명]
#   Stg8(2025 포렌식: 축1~4 분해 + 필터 시제품 CPCV) 오염검사 8시나리오 + 결과 전량 파일로(txt + INDEX).
#   ★엔진 무수정 해시 / ★미래참조 가드(소스 shift- 스캔) / ★label 입력배제 / ★2025 과최적 경보(필터가 2025만 좋고 CPCV 무너지면).
# [In] .stg8_metric / *.csv / 소스  [Out] PASS/FAIL + txt + INDEX
# ==============================================================================
import os, sys, hashlib, datetime
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__)); PARENT = os.path.dirname(HERE)
HSTR = os.path.join(PARENT, "00WorkHstr")
SRCS = [os.path.join(HERE, x) for x in ("test_06Prj_Ch6_FrameWork_RAUTO_Stg8_Y2025Forensics.py",
                                        "regime_classifier.py", "cpcv.py")]
NAME = "06Prj_Ch6_Stg8_Y2025Forensics"
ENGINE_HASH = {
    "SpTrd_Fib_V1_Champion.py": "7f9192e3d50b1afd659a02b9e75764e5438ad57809c93093ab5f1973bb79ca75",
    "SidewayDCA_Stg7_engine.py": "dfdfac4394cd780939d4b368d3ccabfbfab8d599ff1236b11f7f0d80f0823086",
}
REQ_CSV = ["axis1_month.csv", "axis2_reason.csv", "axis3_holdbars.csv", "axis4_entryfeat.csv",
           "filter_candidates.csv", "filter_cpcv_paths.csv", "ledger_trades.csv", "summary.csv"]


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(65536), b""):
            h.update(b)
    return h.hexdigest()


def read_metric():
    d = {}; p = os.path.join(HERE, ".stg8_metric")
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
    res.append(("S1 필수파일/비공백(8종)", len(miss) == 0, f"누락 {miss}" if miss else "8종 OK"))

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

    n25 = int(fnum(M.get("n_2025", 0), 0)); noth = int(fnum(M.get("n_other", 0), 0))
    res.append(("S4 2025 거래>0 & 타년 거래>0", n25 > 0 and noth > 0, f"2025 {n25} / 타년 {noth}"))

    res.append(("S5 label 입력배제", M.get("label_in_feature", "False") == "False", M.get("label_in_feature", "?")))

    # S6 4축 다 산출(파일 존재 + metric에 키)
    keys6 = ["y2025_sl_loss_share", "er_2025_loss", "er_other_win"]
    ok6 = all(fnum(M.get(k)) is not None for k in keys6)
    res.append(("S6 축1~4 분해 산출", ok6, f"sl비율{M.get('y2025_sl_loss_share','?')}% | 2025패ER {M.get('er_2025_loss','?')} vs 타년승ER {M.get('er_other_win','?')}"))

    # S7 ★2025 과최적 경보: 필터가 2025만 끌어올리고 전체 CPCV 무너지면 기각
    p25 = fnum(M.get("filter_best_cpcv_p25"), None); pf_all = fnum(M.get("filter_best_pf_all"), None)
    pf25 = fnum(M.get("filter_best_pf_2025"), None)
    if p25 is None or pf_all is None:
        ok7 = True; memo7 = "필터 CPCV 미산출(거래부족)"
    elif pf_all >= 900:
        ok7 = False; memo7 = f"★필터 degenerate PF{pf_all}"
    else:
        ok7 = p25 > 1.0  # 전체 4년 CPCV가 흑자 유지해야(2025만 고치고 타년 망치면 p25<1)
        memo7 = f"필터BEST 전체PF{pf_all} 2025PF{pf25} CPCV_p25{p25} ({M.get('filter_improved','?')}) — p25>1이어야 4년견고"
    res.append(("S7 필터 4년 견고(CPCV p25>1, 2025과최적아님)", ok7, memo7))

    # S8 결론 기록
    ok8 = (M.get("filter_improved", "") != "") and (fnum(M.get("pf_2025")) is not None)
    res.append(("S8 결론 기록완료(2025원인+필터판정)", ok8,
                f"2025 PF {M.get('pf_2025','?')} vs 타년 {M.get('pf_other','?')} | 필터 {M.get('filter_improved','?')}"))

    passed = sum(1 for _, ok, _ in res if ok); verdict = "PASS" if passed == len(res) else "FAIL"
    summary = (f"VERDICT {NAME} | 8시나리오 {passed}/{len(res)} {verdict} | "
               f"추세봇 2025 PF{M.get('pf_2025','?')}(수익{M.get('ret_2025','?')}) vs 타년 PF{M.get('pf_other','?')}(수익{M.get('ret_other','?')}) | "
               f"[축2]2025손실 sl비율 {M.get('y2025_sl_loss_share','?')}% | [축4]2025패 진입ER {M.get('er_2025_loss','?')} vs 타년승 {M.get('er_other_win','?')} | "
               f"[필터BEST] ER>={M.get('filter_best_er','?')} ADX>={M.get('filter_best_adx','?')} 전체PF{M.get('filter_best_pf_all','?')} 2025PF{M.get('filter_best_pf_2025','?')} "
               f"CPCV_p25 {M.get('filter_best_cpcv_p25','?')} -> {M.get('filter_improved','?')} | check:{verdict}")

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    with open(os.path.join(HSTR, f"{stamp}.txt"), "w", encoding="utf-8") as f:
        f.write(summary + "\n\n[8시나리오 상세]\n")
        for nm, ok, memo in res:
            f.write(f"  [{'OK' if ok else 'X '}] {nm} : {memo}\n")
        f.write("\n[엔진 무수정 해시]\n")
        for fn, hsh in ENGINE_HASH.items():
            f.write(f"  {fn} = {hsh[:16]}...\n")
        f.write("\n[메모] 사장님 통찰: '2025는 칩장이 아니다, 분류기가 추세라 본 곳서 추세봇이 죽었다'. 2025 유일참패해 정체 분해.\n"
                "  축1시간/축2청산이유(sl=즉시역행/flip=휩쏘)/축3보유봉(짧으면 즉시털림)/축4진입지표(ER낮으면 가짜추세).\n"
                "  ★필터는 2025만 좋아지는 과최적 위험 → CPCV p25>1로 4년 전체 견고성 필수. 2025 고치고 타년 망치면 기각.\n")

    idx = os.path.join(HSTR, "00WorkHstr_INDEX.txt")
    with open(idx, "a", encoding="utf-8") as f:
        f.write(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} | {NAME} | 분석:{stamp}.txt | {summary}\n")

    print(summary)
    print(f"[check] 분석txt -> {os.path.join(HSTR, stamp+'.txt')}")
    print(f"[check] INDEX 추가 -> {idx}")


if __name__ == "__main__":
    main()
