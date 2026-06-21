# -*- coding: utf-8 -*-
# [파일명] check_06Prj_Ch6_FrameWork_RAUTO_Stg13_TrendStackFinalize.py
# 코드길이: 약 120줄 | 내부버전: 06Prj_Ch6_Stg13_check_v1 | 로직 전체 출력(축약/생략 없음)
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일] Stg13(추세봇 스택 4종 복리+CPCV) 오염검사 8시나리오 + 결과 전량 파일로.
#   ★분석txt·INDEX는 D:\ML\verify\00WorkHstr 로. 결과 csv는 하위폴더.
#   ★엔진해시 무수정 / ★미래참조 가드 / ★label배제 / ★복리기준 / ★칩필터 거취 판정 기록.
# ==============================================================================
import os, sys, hashlib, datetime
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__)); PARENT = os.path.dirname(HERE)
HSTR = os.path.join(PARENT, "00WorkHstr")
SRCS = [os.path.join(HERE, x) for x in ("test_06Prj_Ch6_FrameWork_RAUTO_Stg13_TrendStackFinalize.py",
                                        "regime_classifier.py", "cpcv.py", "cooldown.py")]
NAME = "06Prj_Ch6_Stg13_TrendStackFinalize"
ENGINE_HASH = {
    "SpTrd_Fib_V1_Champion.py": "7f9192e3d50b1afd659a02b9e75764e5438ad57809c93093ab5f1973bb79ca75",
    "SidewayDCA_Stg7_engine.py": "dfdfac4394cd780939d4b368d3ccabfbfab8d599ff1236b11f7f0d80f0823086",
}
REQ_CSV = ["stack4_compare.csv", "stack4_cpcv_paths.csv", "stack4_by_year.csv", "ledger_trades.csv", "summary.csv"]


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(65536), b""):
            h.update(b)
    return h.hexdigest()


def read_metric():
    d = {}; p = os.path.join(HERE, ".stg13_metric")
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

    # S6 4종 잔고 산출
    keys6 = ["1_base_end", "2_chip_end", "3_cool_end", "4_chip_cool_end"]
    ok6 = all(fnum(M.get(k)) is not None for k in keys6)
    res.append(("S6 4종 복리잔고 산출", ok6,
                f"①${M.get('1_base_end','?')} ②${M.get('2_chip_end','?')} ③${M.get('3_cool_end','?')} ④${M.get('4_chip_cool_end','?')}"))

    # S7 칩필터 거취 판정 + degenerate 아님
    e3 = fnum(M.get("3_cool_end")); e4 = fnum(M.get("4_chip_cool_end"))
    deg = any((fnum(M.get(f"{t}_end")) or 0) >= 9e8 for t in ['1_base', '2_chip', '3_cool', '4_chip_cool'])
    if e3 is None or e4 is None:
        ok7 = False; memo7 = "③/④ 미산출"
    else:
        ok7 = (M.get("chip_verdict", "") != "") and (not deg)
        memo7 = f"③쿨만 ${e3:.0f} vs ④칩+쿨 ${e4:.0f} -> {M.get('chip_verdict','?')} (degenerate={deg})"
    res.append(("S7 칩필터 거취 판정(③vs④)", ok7, memo7))

    # S8 CPCV 견고성 산출(4종 다)
    keys8 = ["1_base_cpcv_p25", "3_cool_cpcv_p25", "4_chip_cool_cpcv_p25"]
    ok8 = all(fnum(M.get(k)) is not None for k in keys8)
    res.append(("S8 CPCV 견고성 산출", ok8,
                f"①p25 {M.get('1_base_cpcv_p25','?')} / ③p25 {M.get('3_cool_cpcv_p25','?')} / ④p25 {M.get('4_chip_cool_cpcv_p25','?')}"))

    passed = sum(1 for _, ok, _ in res if ok); verdict = "PASS" if passed == len(res) else "FAIL"
    summary = (f"VERDICT {NAME} | 8시나리오 {passed}/{len(res)} {verdict} | 전부$10k복리 | "
               f"[①base] ${M.get('1_base_end','?')}({M.get('1_base_ret','?')}% MDD{M.get('1_base_mdd','?')} p25{M.get('1_base_cpcv_p25','?')}) | "
               f"[②칩만] ${M.get('2_chip_end','?')}({M.get('2_chip_ret','?')}% p25{M.get('2_chip_cpcv_p25','?')}) | "
               f"[③쿨만] ${M.get('3_cool_end','?')}({M.get('3_cool_ret','?')}% MDD{M.get('3_cool_mdd','?')} p25{M.get('3_cool_cpcv_p25','?')}) | "
               f"[④칩+쿨] ${M.get('4_chip_cool_end','?')}({M.get('4_chip_cool_ret','?')}% MDD{M.get('4_chip_cool_mdd','?')} p25{M.get('4_chip_cool_cpcv_p25','?')}) | "
               f"BEST {M.get('best_variant','?')} -> {M.get('chip_verdict','?')} | check:{verdict}")

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    with open(os.path.join(HSTR, f"{stamp}.txt"), "w", encoding="utf-8") as f:
        f.write(summary + "\n\n[8시나리오 상세]\n")
        for nm2, ok, memo in res:
            f.write(f"  [{'OK' if ok else 'X '}] {nm2} : {memo}\n")
        f.write("\n[엔진 무수정 해시]\n")
        for fn, hsh in ENGINE_HASH.items():
            f.write(f"  {fn} = {hsh[:16]}...\n")
        f.write("\n[메모] 사장님 확정(가): RAUTO 최종 추세봇 스택 확정. Stg12 발견(복리기준 칩필터 단독 손해) 후속.\n"
                "  4종 복리+CPCV: ①base ②칩만 ③쿨만(Stg12에 없던 핵심) ④칩+쿨. ★③vs④로 칩필터 거취 결정.\n"
                "  ③>④면 칩필터 제거(RAUTO엔 쿨다운만), ③<④면 시너지로 유지. 복리잔고+CPCV p25+MDD 종합.\n"
                "  다음: 확정된 추세봇 스택으로 RAUTO 실물제작. 횡보봇 칩필터는 별개(횡보봇엔 유효).\n")

    idx = os.path.join(HSTR, "00WorkHstr_INDEX.txt")
    with open(idx, "a", encoding="utf-8") as f:
        f.write(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} | {NAME} | 분석:{stamp}.txt | {summary}\n")

    print(summary)
    print(f"[check] 분석txt -> {os.path.join(HSTR, stamp+'.txt')}")
    print(f"[check] INDEX 추가 -> {idx}")


if __name__ == "__main__":
    main()
