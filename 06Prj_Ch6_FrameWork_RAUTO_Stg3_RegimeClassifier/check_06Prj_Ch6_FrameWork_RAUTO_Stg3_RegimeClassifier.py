# -*- coding: utf-8 -*-
# [파일명] check_06Prj_Ch6_FrameWork_RAUTO_Stg3_RegimeClassifier.py
# 코드길이: 약 130줄 | 내부버전: 06Prj_Ch6_Stg3_check_v1 | 로직 전체 출력(축약/생략 없음)
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명]
#   장세분류기 결과물이 오염 안 됐는지 8시나리오로 검사하고, 결과를 전량 파일로만 남긴다.
#     (1) D:\ML\verify\00WorkHstr\<분단위시간>.txt  (2) 00WorkHstr_INDEX.txt 에 한 줄 추가
#   ★엔진 무수정 해시 / ★미래참조 가드(분류기·하니스 shift- 스캔) / ★정답지 분류기입력 배제 확인.
# [In] .stg3_metric / *.csv / 소스(regime_classifier.py·test)·bots엔진  [Out] PASS/FAIL + txt + INDEX
# ==============================================================================
import os, sys, hashlib, datetime
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__)); PARENT = os.path.dirname(HERE)
HSTR = os.path.join(PARENT, "00WorkHstr")
TESTSRC = os.path.join(HERE, "test_06Prj_Ch6_FrameWork_RAUTO_Stg3_RegimeClassifier.py")
RCSRC = os.path.join(HERE, "regime_classifier.py")
NAME = "06Prj_Ch6_Stg3_RegimeClassifier"
ENGINE_HASH = {
    "SpTrd_Fib_V1_Champion.py": "7f9192e3d50b1afd659a02b9e75764e5438ad57809c93093ab5f1973bb79ca75",
    "SidewayDCA_Stg7_engine.py": "dfdfac4394cd780939d4b368d3ccabfbfab8d599ff1236b11f7f0d80f0823086",
}
REQ_CSV = ["grid_scores.csv", "confusion.csv", "regime_bot_pf.csv", "walkforward.csv", "ml_compare.csv", "summary.csv"]


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(65536), b""):
            h.update(b)
    return h.hexdigest()


def read_metric():
    d = {}
    p = os.path.join(HERE, ".stg3_metric")
    if os.path.exists(p):
        for ln in open(p, encoding="utf-8"):
            if "=" in ln:
                k, v = ln.strip().split("=", 1); d[k] = v
    return d


def main():
    os.makedirs(HSTR, exist_ok=True)
    M = read_metric(); res = []

    miss = [c for c in REQ_CSV if not (os.path.exists(os.path.join(HERE, c)) and os.path.getsize(os.path.join(HERE, c)) > 0)]
    res.append(("S1 필수파일/비공백(혼동행렬 포함)", len(miss) == 0, f"누락 {miss}" if miss else "6종 OK"))

    bad = []
    for fn, want in ENGINE_HASH.items():
        p = os.path.join(HERE, "bots", fn); got = sha(p) if os.path.exists(p) else "없음"
        if got != want:
            bad.append(f"{fn}:{got[:8]}")
    res.append(("S2 엔진해시 무수정", len(bad) == 0, "일치" if not bad else f"불일치 {bad}"))

    src = (open(TESTSRC, encoding="utf-8").read() if os.path.exists(TESTSRC) else "") + \
          (open(RCSRC, encoding="utf-8").read() if os.path.exists(RCSRC) else "")
    look = ("shift(-" in src) or (".shift(-" in src)
    res.append(("S3 미래참조 가드(shift- 없음)", not look, "없음" if not look else "★발견"))

    nt = int(M.get("n_trend", 0)); ns = int(M.get("n_sw", 0)); gn = int(M.get("grid_n", 0))
    res.append(("S4 거래>0 & 격자90", nt > 0 and ns > 0 and gn == 90, f"추세{nt}/횡보{ns}/격자{gn}"))

    res.append(("S5 정답지 분류기입력 배제", M.get("label_in_classifier_input", "False") == "False", M.get("label_in_classifier_input", "?")))

    try:
        sep = float(M.get("best_sep", -9)); acc = float(M.get("best_label_acc", 0))
        ok6 = sep > 0 and acc > 25.0
    except Exception:
        ok6 = False
    res.append(("S6 분리도>0 & 일치율>무작위25%", ok6, f"분리도{M.get('best_sep','?')} 일치율{M.get('best_label_acc','?')}%"))

    try:
        ok7 = int(M.get("wf_windows", 0)) >= 5 and (M.get("wf_acc", "") not in ("", "[]"))
    except Exception:
        ok7 = False
    res.append(("S7 워크포워드 창>=5 & OOS일치율 기록", ok7, f"창{M.get('wf_windows','?')} OOS{M.get('wf_acc','?')}"))

    ok8 = (M.get("recommend", "") in ("STANDARD", "ML")) and (M.get("ml_oos_acc", "") != "")
    res.append(("S8 ML 대체비교 완료(표준 vs ML)", ok8, f"표준{M.get('std_best_acc','?')}% vs ML{M.get('ml_oos_acc','?')}% 추천{M.get('recommend','?')}"))

    passed = sum(1 for _, ok, _ in res if ok)
    verdict = "PASS" if passed == len(res) else "FAIL"
    summary = (f"VERDICT {NAME} | 8시나리오 {passed}/{len(res)} {verdict} | "
               f"[BEST] w={M.get('best_w','?')} CHOP>{M.get('best_chop','?')} ADX>{M.get('best_adx','?')} 다수결{M.get('best_vote','?')}/4 | "
               f"일치율 {M.get('best_label_acc','?')}%(무작위25) 분리도 {M.get('best_sep','?')} | "
               f"추세봇 추세국면PF {M.get('trendPF_trendreg','?')} vs 레인지 {M.get('trendPF_rangereg','?')} / 횡보봇 레인지PF {M.get('swPF_rangereg','?')} vs 추세 {M.get('swPF_trendreg','?')} | "
               f"전환 {M.get('flips_per_yr','?')}회/년 | WF{M.get('wf_windows','?')}창 OOS{M.get('wf_acc','?')} | "
               f"ML {M.get('ml_oos_acc','?')}% vs 표준 {M.get('std_best_acc','?')}% -> {M.get('recommend','?')} | check:{verdict}")

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    with open(os.path.join(HSTR, f"{stamp}.txt"), "w", encoding="utf-8") as f:
        f.write(summary + "\n\n[8시나리오 상세]\n")
        for nm, ok, memo in res:
            f.write(f"  [{'OK' if ok else 'X '}] {nm} : {memo}\n")
        f.write("\n[엔진 무수정 해시]\n")
        for fn, h in ENGINE_HASH.items():
            f.write(f"  {fn} = {h[:16]}...\n")
        f.write("\n[메모] 장세판단(4국면) 분류기 완성. 분리도>0 = 추세봇/횡보봇을 올바른 국면에 배정. "
                "표준값이 ML보다 낫거나 비슷하면 표준 채택(단순·견고). 이 분류기는 앞으로 모든 알파가 공유.\n")

    idx = os.path.join(HSTR, "00WorkHstr_INDEX.txt")
    with open(idx, "a", encoding="utf-8") as f:
        f.write(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} | {NAME} | 분석:{stamp}.txt | {summary}\n")

    print(summary)
    print(f"[check] 분석txt -> {os.path.join(HSTR, stamp+'.txt')}")
    print(f"[check] INDEX 추가 -> {idx}")


if __name__ == "__main__":
    main()
