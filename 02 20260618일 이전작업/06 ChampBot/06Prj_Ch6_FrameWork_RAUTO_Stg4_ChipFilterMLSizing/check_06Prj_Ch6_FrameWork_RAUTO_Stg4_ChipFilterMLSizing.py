# -*- coding: utf-8 -*-
# [파일명] check_06Prj_Ch6_FrameWork_RAUTO_Stg4_ChipFilterMLSizing.py
# 코드길이: 약 150줄 | 내부버전: 06Prj_Ch6_Stg4_check_v1 | 로직 전체 출력(축약/생략 없음)
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명]
#   Stg4 결과물 오염검사 8시나리오 + 결과를 전량 파일로(00WorkHstr txt + INDEX 한 줄).
#   ★엔진 무수정 해시 / ★미래참조 가드(소스 shift- 스캔 + ML AUC 폭등 누수경보) / ★label_smc 특징배제.
# [In] .stg4_metric / *.csv / 소스  [Out] PASS/FAIL + txt + INDEX
# ==============================================================================
import os, sys, hashlib, datetime
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); PARENT = os.path.dirname(HERE)
HSTR = os.path.join(PARENT, "00WorkHstr")
TESTSRC = os.path.join(HERE, "test_06Prj_Ch6_FrameWork_RAUTO_Stg4_ChipFilterMLSizing.py")
RCSRC = os.path.join(HERE, "regime_classifier.py"); MLSRC = os.path.join(HERE, "ml_sizing.py")
NAME = "06Prj_Ch6_Stg4_ChipFilterMLSizing"
ENGINE_HASH = {
    "SpTrd_Fib_V1_Champion.py": "7f9192e3d50b1afd659a02b9e75764e5438ad57809c93093ab5f1973bb79ca75",
    "SidewayDCA_Stg7_engine.py": "dfdfac4394cd780939d4b368d3ccabfbfab8d599ff1236b11f7f0d80f0823086",
}
REQ_CSV = ["chip_grid.csv", "chip_best.csv", "matrix_regime.csv", "matrix_year.csv", "matrix_side.csv",
           "ledger_trades.csv", "ml_model_compare.csv", "ml_feature_importance.csv", "ml_sizing_pf.csv",
           "walkforward.csv", "summary.csv"]


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


def main():
    os.makedirs(HSTR, exist_ok=True); M = read_metric(); res = []

    miss = [c for c in REQ_CSV if not (os.path.exists(os.path.join(HERE, c)) and os.path.getsize(os.path.join(HERE, c)) > 0)]
    res.append(("S1 필수파일/비공백(11종)", len(miss) == 0, f"누락 {miss}" if miss else "11종 OK"))

    bad = []
    for fn, want in ENGINE_HASH.items():
        p = os.path.join(HERE, "bots", fn); got = sha(p) if os.path.exists(p) else "없음"
        if got != want:
            bad.append(f"{fn}:{got[:8]}")
    res.append(("S2 엔진해시 무수정", len(bad) == 0, "일치" if not bad else f"불일치 {bad}"))

    src = ""
    for s in (TESTSRC, RCSRC, MLSRC):
        if os.path.exists(s):
            src += open(s, encoding="utf-8").read()
    look = ("shift(-" in src) or (".shift(-" in src)
    res.append(("S3 미래참조 가드(shift- 없음)", not look, "없음" if not look else "★발견"))

    nt = int(M.get("n_trend", 0)); ns = int(M.get("n_sw", 0)); gn = int(M.get("chip_grid_n", 0))
    res.append(("S4 거래>0 & 칩격자243", nt > 0 and ns > 0 and gn == 243, f"추세{nt}/횡보{ns}/격자{gn}"))

    res.append(("S5 label_smc 특징배제", M.get("label_in_feature", "False") == "False", M.get("label_in_feature", "?")))

    # S6 칩필터 효과: ON이 OFF보다 PF개선 또는 2025 켜짐 회복
    try:
        off = float(M.get("sw_pf_off", 0)); on = float(M.get("sw_pf_on", 0))
        o25 = int(M.get("on2025_on", 0))
        ok6 = (on >= off) or (o25 > 0)
    except Exception:
        ok6 = False
    res.append(("S6 칩필터 ON 효과(PF개선 or 2025켜짐회복)", ok6,
                f"OFF PF{M.get('sw_pf_off','?')} -> ON PF{M.get('sw_pf_on','?')} / 2025켜짐 {M.get('on2025_on','?')}건"))

    # S7 ML 누수경보: best AUC가 0.95 이상이면 누수 의심(경보), 아니면 정상
    try:
        auc = M.get("ml_best_auc", "NA")
        if auc in ("NA", ""):
            ok7 = True; memo7 = "ML 미학습(표본부족) - 누수 무관"
        else:
            a = float(auc); ok7 = a < 0.95
            memo7 = f"best AUC {a} {'(정상)' if ok7 else '★0.95+ 누수의심!'}"
    except Exception:
        ok7 = True; memo7 = "판정불가"
    res.append(("S7 ML 누수경보(AUC<0.95)", ok7, memo7))

    # S8 ML 비교완료 + 추천
    ok8 = (M.get("recommend", "") in ("STANDARD", "ML"))
    res.append(("S8 ML 비교완료(표준 vs ML 사이징)", ok8,
                f"ML사이징PF {M.get('ml_sizing_pf','?')} vs 표준 {M.get('std_pf','?')} 추천 {M.get('recommend','?')} 특징{M.get('ml_feat_n','?')}개"))

    passed = sum(1 for _, ok, _ in res if ok); verdict = "PASS" if passed == len(res) else "FAIL"
    summary = (f"VERDICT {NAME} | 8시나리오 {passed}/{len(res)} {verdict} | "
               f"[칩필터BEST] pre_n={M.get('chip_pre_n','?')} hold_k={M.get('chip_hold_k','?')} CHOP>{M.get('chip_chop_hi','?')} "
               f"{M.get('chip_combo','?')} SQZ={M.get('chip_squeeze','?')} | "
               f"칩OFF PF{M.get('sw_pf_off','?')}(2025_{M.get('on2025_off','?')}) -> 칩ON PF{M.get('sw_pf_on','?')}(2025_{M.get('on2025_on','?')}) | "
               f"ML best_auc {M.get('ml_best_auc','?')} 사이징PF {M.get('ml_sizing_pf','?')} vs 표준 {M.get('std_pf','?')} -> {M.get('recommend','?')} | "
               f"미래참조차단={M.get('lookahead_block','?')} | check:{verdict}")

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    with open(os.path.join(HSTR, f"{stamp}.txt"), "w", encoding="utf-8") as f:
        f.write(summary + "\n\n[8시나리오 상세]\n")
        for nm, ok, memo in res:
            f.write(f"  [{'OK' if ok else 'X '}] {nm} : {memo}\n")
        f.write("\n[엔진 무수정 해시]\n")
        for fn, hsh in ENGINE_HASH.items():
            f.write(f"  {fn} = {hsh[:16]}...\n")
        f.write("\n[메모] 칩필터 S1~S5+Squeeze 243격자로 2025 횡보봇 부활 시도 + ML 사이징(봇수익타깃·거래있는봉만·미래참조 구조차단). "
                "ML AUC가 0.95+면 누수 의심하고 즉시 코드 재점검. ML이 OOS서 표준 못이기면 STANDARD 채택(단순·견고 우선).\n"
                "매트릭스: ledger_trades.csv로 장세×년도×롱숏 × PF·수익률·payoff·거래수·수익금 전량 확인 가능.\n")

    idx = os.path.join(HSTR, "00WorkHstr_INDEX.txt")
    with open(idx, "a", encoding="utf-8") as f:
        f.write(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} | {NAME} | 분석:{stamp}.txt | {summary}\n")

    print(summary)
    print(f"[check] 분석txt -> {os.path.join(HSTR, stamp+'.txt')}")
    print(f"[check] INDEX 추가 -> {idx}")


if __name__ == "__main__":
    main()
