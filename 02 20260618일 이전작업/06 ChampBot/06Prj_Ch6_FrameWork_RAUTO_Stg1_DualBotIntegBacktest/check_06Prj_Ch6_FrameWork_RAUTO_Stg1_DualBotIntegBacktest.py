# -*- coding: utf-8 -*-
# [파일명] check_06Prj_Ch6_FrameWork_RAUTO_Stg1_DualBotIntegBacktest.py
# 코드길이: 약 140줄 | 내부버전: 06Prj_Ch6_Stg1_check_v1 | 로직 전체 출력(축약/생략 없음)
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명]
#   test 코드가 만든 결과물이 '오염'되지 않았는지 8가지 시나리오로 검사하고,
#   결과를 전량 '파일로만' 남긴다(복붙 요청 금지 방침). 두 곳에 기록한다:
#     (1) D:\ML\verify\00WorkHstr\<분단위시간>.txt  ← 이번 작업 분석 결과
#     (2) D:\ML\verify\00WorkHstr\00WorkHstr_INDEX.txt 에 한 줄 추가
#   ★엔진 무수정 증빙: bots/ 두 엔진의 SHA256을 인계서 기준값과 대조한다.
#   ★미래참조 가드: test 소스에 음수 shift(-) 패턴이 있는지 스캔(있으면 경고).
#
# [PATH] test와 같은 폴더에서 실행. 출력은 상위(D:\ML\verify) 아래 00WorkHstr 로.
# [In] test가 남긴 .stg1_metric / *.csv / 본 폴더의 test소스·bots엔진
# [Out] PASS/FAIL 콘솔 + 00WorkHstr\<시간>.txt + INDEX 한 줄
# ==============================================================================
import os, sys, hashlib, datetime
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__)); PARENT = os.path.dirname(HERE)
HSTR = os.path.join(PARENT, "00WorkHstr")
TESTSRC = os.path.join(HERE, "test_06Prj_Ch6_FrameWork_RAUTO_Stg1_DualBotIntegBacktest.py")
NAME = "06Prj_Ch6_Stg1_DualBotIntegBacktest"
# 인계서 확정 무수정 기준해시(전체)
ENGINE_HASH = {
    "SpTrd_Fib_V1_Champion.py": "7f9192e3d50b1afd659a02b9e75764e5438ad57809c93093ab5f1973bb79ca75",
    "SidewayDCA_Stg7_engine.py": "dfdfac4394cd780939d4b368d3ccabfbfab8d599ff1236b11f7f0d80f0823086",
}
REQ_CSV = ["combined_equity.csv", "by_year.csv", "by_regime.csv", "exposure_frontier.csv", "overlap.csv", "summary.csv"]


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(65536), b""):
            h.update(b)
    return h.hexdigest()


def read_metric():
    d = {}
    p = os.path.join(HERE, ".stg1_metric")
    if os.path.exists(p):
        for ln in open(p, encoding="utf-8"):
            if "=" in ln:
                k, v = ln.strip().split("=", 1); d[k] = v
    return d


def main():
    os.makedirs(HSTR, exist_ok=True)
    M = read_metric()
    res = []  # (시나리오, 통과여부, 메모)

    # 1) 필수 출력파일 존재 & 비공백
    miss = [c for c in REQ_CSV if not (os.path.exists(os.path.join(HERE, c)) and os.path.getsize(os.path.join(HERE, c)) > 0)]
    res.append(("S1 필수파일/비공백", len(miss) == 0, f"누락/공백 {miss}" if miss else "6종 OK"))

    # 2) 엔진 무수정 해시 대조
    bad = []
    for fn, want in ENGINE_HASH.items():
        p = os.path.join(HERE, "bots", fn)
        got = sha(p) if os.path.exists(p) else "없음"
        if got != want:
            bad.append(f"{fn}:{got[:8]}!={want[:8]}")
    res.append(("S2 엔진해시 무수정", len(bad) == 0, "일치" if not bad else f"불일치 {bad}"))

    # 3) 미래참조 가드 — test소스에 음수 shift 없는지
    src = open(TESTSRC, encoding="utf-8").read() if os.path.exists(TESTSRC) else ""
    look = ("shift(-" in src) or (".shift(-" in src)
    res.append(("S3 미래참조 가드(shift- 없음)", not look, "음수shift 없음" if not look else "★음수shift 발견"))

    # 4) 두 봇 모두 거래 생성
    nt = int(M.get("n_trend", 0)); ns = int(M.get("n_sw", 0))
    res.append(("S4 두 봇 거래>0", nt > 0 and ns > 0, f"추세{nt}/횡보{ns}"))

    # 5) label이 봇 입력에 안 들어감
    res.append(("S5 라벨 봇입력 배제", M.get("has_label_in_bot_input", "False") == "False", M.get("has_label_in_bot_input", "?")))

    # 6) 자본배분 동결값(0.70) 일치
    try:
        ok6 = abs(float(M.get("cap_split_trend", 0)) - 0.70) < 1e-9
    except Exception:
        ok6 = False
    res.append(("S6 자본배분 70/30 동결", ok6, M.get("cap_split_trend", "?")))

    # 7) 기준노출 결과 정합(MDD 수치 존재 & 청산이면 명시)
    try:
        mdd = float(M.get("base_mdd", 1))
        ok7 = (mdd <= 0) and (M.get("base_liq", "") in ("YES", "NO"))
    except Exception:
        ok7 = False
    res.append(("S7 합산결과 정합", ok7, f"MDD {M.get('base_mdd','?')}% 청산 {M.get('base_liq','?')}"))

    # 8) 파라미터 라벨이 '낙관상한치'로 명시 + 펀딩 REAL
    ok8 = ("SNOOPED" in M.get("params", "")) and (M.get("funding_trend", "") == "REAL")
    res.append(("S8 낙관상한치 라벨+펀딩REAL", ok8, f"{M.get('params','?')} | 펀딩 추세{M.get('funding_trend','?')}/횡보{M.get('funding_sw','?')}"))

    passed = sum(1 for _, ok, _ in res if ok)
    verdict = "PASS" if passed == len(res) else "FAIL"
    summary = (f"VERDICT {NAME} | 8시나리오 {passed}/{len(res)} {verdict} | "
               f"기준노출 합산 {M.get('base_ret','?')}%/MDD{M.get('base_mdd','?')}%(청산{M.get('base_liq','?')}) | "
               f"단독 추세 PF{M.get('trend_pf','?')}/{M.get('trend_ret','?')}% 횡보 PF{M.get('sw_pf','?')}/{M.get('sw_ret','?')}% | "
               f"2025 추세{M.get('y2025_trend','?')}%+횡보{M.get('y2025_sw','?')}%={M.get('y2025_sum','?')}% | "
               f"겹침 추세대비{M.get('ov_pct_trend','?')}%/횡보대비{M.get('ov_pct_sw','?')}% | "
               f"권고노출 {M.get('rec_exposure','?')}->{M.get('rec_ret','?')}%/MDD{M.get('rec_mdd','?')}% | "
               f"파라미터={M.get('params','?')} | check:{verdict}")

    # 분석 txt 저장(분단위 시간명)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    txt = os.path.join(HSTR, f"{stamp}.txt")
    with open(txt, "w", encoding="utf-8") as f:
        f.write(summary + "\n\n[8시나리오 상세]\n")
        for nm, ok, memo in res:
            f.write(f"  [{'OK' if ok else 'X '}] {nm} : {memo}\n")
        f.write(f"\n[엔진 무수정 해시 기준]\n")
        for fn, h in ENGINE_HASH.items():
            f.write(f"  {fn} = {h[:16]}...\n")
        f.write(f"\n[메모] 이 수치는 '현재 파라미터=낙관 상한치'다. 월목표 판단용 결정숫자는 Stg2(파라미터 동결+워크포워드) 이후.\n")

    # INDEX 한 줄 추가
    idx = os.path.join(HSTR, "00WorkHstr_INDEX.txt")
    line = f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} | {NAME} | 분석:{stamp}.txt | {summary}\n"
    with open(idx, "a", encoding="utf-8") as f:
        f.write(line)

    print(summary)
    print(f"[check] 분석txt -> {txt}")
    print(f"[check] INDEX 추가 -> {idx}")


if __name__ == "__main__":
    main()
