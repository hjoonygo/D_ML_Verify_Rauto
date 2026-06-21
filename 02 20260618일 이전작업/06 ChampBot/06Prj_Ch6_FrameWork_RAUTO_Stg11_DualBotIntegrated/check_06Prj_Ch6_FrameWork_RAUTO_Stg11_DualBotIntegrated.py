# -*- coding: utf-8 -*-
# [파일명] check_06Prj_Ch6_FrameWork_RAUTO_Stg11_DualBotIntegrated.py
# 코드길이: 약 115줄 | 내부버전: 06Prj_Ch6_Stg11_check_v1 | 로직 전체 출력(축약/생략 없음)
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일] Stg11(두 봇 통합 백테스트) 오염검사 8시나리오 + 결과 전량 파일로(txt+INDEX).
#   ★엔진해시 무수정 / ★미래참조 가드 / ★label배제 / ★월목표 갭 기록(RAUTO 제작 우선순위 판단용).
# ==============================================================================
import os, sys, hashlib, datetime
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__)); PARENT = os.path.dirname(HERE)
HSTR = os.path.join(PARENT, "00WorkHstr")
SRCS = [os.path.join(HERE, x) for x in ("test_06Prj_Ch6_FrameWork_RAUTO_Stg11_DualBotIntegrated.py",
                                        "regime_classifier.py", "cooldown.py", "cpcv.py")]
NAME = "06Prj_Ch6_Stg11_DualBotIntegrated"
ENGINE_HASH = {
    "SpTrd_Fib_V1_Champion.py": "7f9192e3d50b1afd659a02b9e75764e5438ad57809c93093ab5f1973bb79ca75",
    "SidewayDCA_Stg7_engine.py": "dfdfac4394cd780939d4b368d3ccabfbfab8d599ff1236b11f7f0d80f0823086",
}
REQ_CSV = ["integrated_by_year.csv", "integrated_by_regime.csv", "equity_curve.csv",
           "monthly_returns.csv", "ledger_trades.csv", "summary.csv"]


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(65536), b""):
            h.update(b)
    return h.hexdigest()


def read_metric():
    d = {}; p = os.path.join(HERE, ".stg11_metric")
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
    res.append(("S2 엔진해시 무수정", len(bad) == 0, "일치" if not bad else f"불일치 {bad}"))

    src = ""
    for s in SRCS:
        if os.path.exists(s):
            src += open(s, encoding="utf-8").read()
    look = ("shift(-" in src) or (".shift(-" in src)
    res.append(("S3 미래참조 가드(shift- 없음)", not look, "없음" if not look else "★발견"))

    nt = int(fnum(M.get("n_trend", 0), 0)); ns = int(fnum(M.get("n_sway", 0), 0))
    res.append(("S4 두 봇 거래>0", nt > 0 and ns > 0, f"추세봇 {nt} / 횡보봇 {ns}"))

    res.append(("S5 label 입력배제", M.get("label_in_feature", "False") == "False", M.get("label_in_feature", "?")))

    # S6 통합 성과 산출
    ct = fnum(M.get("combined_total_pct")); am = fnum(M.get("avg_monthly_pct"))
    ok6 = ct is not None and am is not None
    res.append(("S6 통합 성과 산출", ok6, f"36개월 {ct}% / 월평균 {am}% / MDD {M.get('combined_mdd','?')}"))

    # S7 플러스월 비율(매월 플러스 목표 점검)
    pm = fnum(M.get("pos_months")); nm = fnum(M.get("n_months"))
    if pm is None or nm is None or nm == 0:
        ok7 = False; memo7 = "월 데이터 미산출"
    else:
        ratio = pm / nm * 100
        ok7 = True  # 기록만(목표 달성여부는 사장님 판단)
        memo7 = f"플러스월 {int(pm)}/{int(nm)} ({round(ratio,1)}%) — 목표 '매월플러스'와 비교용"
    res.append(("S7 월별 플러스 비율 기록", ok7, memo7))

    # S8 MDD 기록(파산 위험 점검)
    cm = fnum(M.get("combined_mdd"))
    ok8 = cm is not None and cm > -100
    res.append(("S8 통합 MDD 기록(파산아님)", ok8, f"통합 MDD {cm}% (추세 {M.get('trend_mdd','?')}/횡보 {M.get('sway_mdd','?')})"))

    passed = sum(1 for _, ok, _ in res if ok); verdict = "PASS" if passed == len(res) else "FAIL"
    summary = (f"VERDICT {NAME} | 8시나리오 {passed}/{len(res)} {verdict} | "
               f"추세봇스택 {M.get('n_trend','?')}건 {M.get('trend_total_pct','?')}%(MDD{M.get('trend_mdd','?')}) / "
               f"횡보봇칩 {M.get('n_sway','?')}건 {M.get('sway_total_pct','?')}%(MDD{M.get('sway_mdd','?')}) | "
               f"[통합] 36개월 {M.get('combined_total_pct','?')}% 월평균 {M.get('avg_monthly_pct','?')}% MDD {M.get('combined_mdd','?')}% | "
               f"플러스월 {M.get('pos_months','?')}/{M.get('n_months','?')} | check:{verdict}")

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    with open(os.path.join(HSTR, f"{stamp}.txt"), "w", encoding="utf-8") as f:
        f.write(summary + "\n\n[8시나리오 상세]\n")
        for nm2, ok, memo in res:
            f.write(f"  [{'OK' if ok else 'X '}] {nm2} : {memo}\n")
        f.write("\n[엔진 무수정 해시]\n")
        for fn, hsh in ENGINE_HASH.items():
            f.write(f"  {fn} = {hsh[:16]}...\n")
        f.write("\n[메모] 사장님 확정(가, 독립계좌 합산): Ch6 모든 확정알파 통합. RAUTO 실물제작 전 마지막 종합 백테스트.\n"
                "  추세봇 = er게이트+칩필터(CHOP65/ER0.35)+쿨다운(K4/M8). 횡보봇 = 칩필터 2of3. 각 $10k 독립계좌 합산.\n"
                "  ★이 결과의 '월평균·플러스월·MDD'가 RAUTO 현재 실력 = 월목표와의 갭. 제작 우선순위 판단 근거.\n"
                "  다음: RAUTO 실물 제작(실시간 데이터 수집·주문·리스크관리). 제3 알파(온체인)는 나중.\n")

    idx = os.path.join(HSTR, "00WorkHstr_INDEX.txt")
    with open(idx, "a", encoding="utf-8") as f:
        f.write(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} | {NAME} | 분석:{stamp}.txt | {summary}\n")

    print(summary)
    print(f"[check] 분석txt -> {os.path.join(HSTR, stamp+'.txt')}")
    print(f"[check] INDEX 추가 -> {idx}")


if __name__ == "__main__":
    main()
