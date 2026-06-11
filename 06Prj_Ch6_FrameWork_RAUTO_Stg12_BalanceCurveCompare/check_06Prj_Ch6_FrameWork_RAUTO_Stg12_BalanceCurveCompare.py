# -*- coding: utf-8 -*-
# [파일명] check_06Prj_Ch6_FrameWork_RAUTO_Stg12_BalanceCurveCompare.py
# 코드길이: 약 120줄 | 내부버전: 06Prj_Ch6_Stg12_check_v1 | 로직 전체 출력(축약/생략 없음)
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일] Stg12(세 단계 복리 자본곡선 비교) 오염검사 8시나리오 + 결과 전량 파일로.
#   ★분석txt·INDEX는 D:\ML\verify\00WorkHstr 로 출력(지침3-②). 결과 csv는 하위폴더.
#   ★엔진해시 무수정 / ★미래참조 가드 / ★label배제 / ★복리기준 확인 / ★단계 단조성(A->B->C 거래 줄어듦).
# ==============================================================================
import os, sys, hashlib, datetime
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__)); PARENT = os.path.dirname(HERE)
HSTR = os.path.join(PARENT, "00WorkHstr")
SRCS = [os.path.join(HERE, x) for x in ("test_06Prj_Ch6_FrameWork_RAUTO_Stg12_BalanceCurveCompare.py",
                                        "regime_classifier.py", "cooldown.py")]
NAME = "06Prj_Ch6_Stg12_BalanceCurveCompare"
ENGINE_HASH = {
    "SpTrd_Fib_V1_Champion.py": "7f9192e3d50b1afd659a02b9e75764e5438ad57809c93093ab5f1973bb79ca75",
    "SidewayDCA_Stg7_engine.py": "dfdfac4394cd780939d4b368d3ccabfbfab8d599ff1236b11f7f0d80f0823086",
}
REQ_CSV = ["balance_curves.csv", "stage_summary.csv", "by_year_balance.csv", "ledger_trades.csv", "summary.csv"]


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(65536), b""):
            h.update(b)
    return h.hexdigest()


def read_metric():
    d = {}; p = os.path.join(HERE, ".stg12_metric")
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
    res.append(("S2 엔진해시 무수정", len(bad) == 0, "일치" if not bad else f"불일치 {bad}"))

    src = ""
    for s in SRCS:
        if os.path.exists(s):
            src += open(s, encoding="utf-8").read()
    look = ("shift(-" in src) or (".shift(-" in src)
    res.append(("S3 미래참조 가드(shift- 없음)", not look, "없음" if not look else "★발견"))

    res.append(("S4 복리기준 $10,000", fnum(M.get("start")) == 10000.0, f"start={M.get('start','?')}"))

    res.append(("S5 label 입력배제", M.get("label_in_feature", "False") == "False", M.get("label_in_feature", "?")))

    # S6 세 곡선 잔고 산출
    keys6 = ["A_end", "B_end", "C_end", "S_end", "INT_end"]
    ok6 = all(fnum(M.get(k)) is not None for k in keys6)
    res.append(("S6 5곡선 잔고 산출", ok6,
                f"A ${M.get('A_end','?')} / B ${M.get('B_end','?')} / C ${M.get('C_end','?')} / S ${M.get('S_end','?')} / INT ${M.get('INT_end','?')}"))

    # S7 단계 단조성: 칩필터가 거래를 줄이고(A_n>=B_n), 쿨다운이 더 줄임(B_n>=C_n)
    an = fnum(M.get("A_n")); bn = fnum(M.get("B_n")); cn = fnum(M.get("C_n"))
    if None in (an, bn, cn):
        ok7 = False; memo7 = "거래수 미산출"
    else:
        ok7 = (an >= bn >= cn)
        memo7 = f"거래수 A {int(an)} >= B {int(bn)} >= C {int(cn)} (칩·쿨다운이 사후제거 — 단조감소 정상)"
    res.append(("S7 단계 단조성(A>=B>=C 거래수)", ok7, memo7))

    # S8 통합이 두 계좌 합과 일치(INT_end ≈ C_end + S_end, 복리 시간순이라 근사)
    ie = fnum(M.get("INT_end")); ce = fnum(M.get("C_end")); se = fnum(M.get("S_end"))
    if None in (ie, ce, se):
        ok8 = False; memo8 = "잔고 미산출"
    else:
        # 통합은 두 계좌 복리합이므로 C_end + S_end 와 정확히 같아야(독립계좌 가정)
        diff = abs(ie - (ce + se))
        ok8 = diff < max(1.0, 0.001 * ie)
        memo8 = f"INT ${ie:.0f} vs C+S ${(ce+se):.0f} (차이 ${diff:.0f}, 독립계좌라 일치해야)"
    res.append(("S8 통합=C+S 일치(독립계좌)", ok8, memo8))

    passed = sum(1 for _, ok, _ in res if ok); verdict = "PASS" if passed == len(res) else "FAIL"
    summary = (f"VERDICT {NAME} | 8시나리오 {passed}/{len(res)} {verdict} | 전부 $10,000 복리 | "
               f"[A base] ${M.get('A_end','?')}({M.get('A_ret','?')}% MDD{M.get('A_mdd','?')}) | "
               f"[B 칩필터] ${M.get('B_end','?')}({M.get('B_ret','?')}% MDD{M.get('B_mdd','?')}) | "
               f"[C 칩+쿨다운] ${M.get('C_end','?')}({M.get('C_ret','?')}% MDD{M.get('C_mdd','?')}) | "
               f"[횡보봇] ${M.get('S_end','?')}({M.get('S_ret','?')}%) | "
               f"[통합$20k] ${M.get('INT_end','?')}({M.get('INT_ret','?')}% MDD{M.get('INT_mdd','?')}) | check:{verdict}")

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    with open(os.path.join(HSTR, f"{stamp}.txt"), "w", encoding="utf-8") as f:
        f.write(summary + "\n\n[8시나리오 상세]\n")
        for nm2, ok, memo in res:
            f.write(f"  [{'OK' if ok else 'X '}] {nm2} : {memo}\n")
        f.write("\n[엔진 무수정 해시]\n")
        for fn, hsh in ENGINE_HASH.items():
            f.write(f"  {fn} = {hsh[:16]}...\n")
        f.write("\n[메모] 사장님 확정(나, 계좌잔고 복리기준): Ch5 Stg15·Ch6 Stg10·Stg11을 전부 $10,000 복리로 재생성해 단위통일 비교.\n"
                "  A 추세봇base / B +칩필터(Ch5 Stg15) / C +칩+쿨다운(Ch6 Stg10) / S 횡보봇 / INT 통합$20k(Stg11).\n"
                "  ★단순합(이전 177~184%)과 달리 복리 자본곡선이라 실제 계좌 그림. 엔진 1회호출 최적화로 빠름.\n"
                "  ★해석: A->B->C 잔고 증가폭이 각 알파의 복리 기여. INT가 두 봇 합산 실제잔고.\n")

    idx = os.path.join(HSTR, "00WorkHstr_INDEX.txt")
    with open(idx, "a", encoding="utf-8") as f:
        f.write(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} | {NAME} | 분석:{stamp}.txt | {summary}\n")

    print(summary)
    print(f"[check] 분석txt -> {os.path.join(HSTR, stamp+'.txt')}")
    print(f"[check] INDEX 추가 -> {idx}")


if __name__ == "__main__":
    main()
