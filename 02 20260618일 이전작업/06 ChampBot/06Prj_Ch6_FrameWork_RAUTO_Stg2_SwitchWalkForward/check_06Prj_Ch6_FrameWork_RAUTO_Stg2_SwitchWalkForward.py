# -*- coding: utf-8 -*-
# [파일명] check_06Prj_Ch6_FrameWork_RAUTO_Stg2_SwitchWalkForward.py
# 코드길이: 약 130줄 | 내부버전: 06Prj_Ch6_Stg2_check_v1 | 로직 전체 출력(축약/생략 없음)
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명]
#   test 결과물이 오염 안 됐는지 8시나리오로 검사하고, 결과를 전량 파일로만 남긴다.
#     (1) D:\ML\verify\00WorkHstr\<분단위시간>.txt  (2) 00WorkHstr_INDEX.txt 에 한 줄 추가
#   ★엔진 무수정 해시 대조 / ★미래참조 가드(test소스 shift- 스캔) / ★동결규칙 라벨 확인.
# [In] .stg2_metric / *.csv / test소스·bots엔진  [Out] PASS/FAIL + 00WorkHstr\txt + INDEX 한 줄
# ==============================================================================
import os, sys, hashlib, datetime
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__)); PARENT = os.path.dirname(HERE)
HSTR = os.path.join(PARENT, "00WorkHstr")
TESTSRC = os.path.join(HERE, "test_06Prj_Ch6_FrameWork_RAUTO_Stg2_SwitchWalkForward.py")
NAME = "06Prj_Ch6_Stg2_SwitchWalkForward"
ENGINE_HASH = {
    "SpTrd_Fib_V1_Champion.py": "7f9192e3d50b1afd659a02b9e75764e5438ad57809c93093ab5f1973bb79ca75",
    "SidewayDCA_Stg7_engine.py": "dfdfac4394cd780939d4b368d3ccabfbfab8d599ff1236b11f7f0d80f0823086",
}
REQ_CSV = ["all_trades.csv", "mode_compare.csv", "walkforward.csv", "breakdown.csv", "by_year_mode.csv", "summary.csv"]


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(65536), b""):
            h.update(b)
    return h.hexdigest()


def read_metric():
    d = {}
    p = os.path.join(HERE, ".stg2_metric")
    if os.path.exists(p):
        for ln in open(p, encoding="utf-8"):
            if "=" in ln:
                k, v = ln.strip().split("=", 1); d[k] = v
    return d


def main():
    os.makedirs(HSTR, exist_ok=True)
    M = read_metric(); res = []

    miss = [c for c in REQ_CSV if not (os.path.exists(os.path.join(HERE, c)) and os.path.getsize(os.path.join(HERE, c)) > 0)]
    res.append(("S1 필수파일/비공백", len(miss) == 0, f"누락 {miss}" if miss else "6종 OK"))

    bad = []
    for fn, want in ENGINE_HASH.items():
        p = os.path.join(HERE, "bots", fn); got = sha(p) if os.path.exists(p) else "없음"
        if got != want:
            bad.append(f"{fn}:{got[:8]}")
    res.append(("S2 엔진해시 무수정", len(bad) == 0, "일치" if not bad else f"불일치 {bad}"))

    src = open(TESTSRC, encoding="utf-8").read() if os.path.exists(TESTSRC) else ""
    look = ("shift(-" in src) or (".shift(-" in src)
    res.append(("S3 미래참조 가드(shift- 없음)", not look, "없음" if not look else "★발견"))

    nt = int(M.get("n_trend", 0)); ns = int(M.get("n_sw_precise", 0)); nsw = int(M.get("n_switch", 0))
    res.append(("S4 거래>0 & 스위칭거래>0", nt > 0 and ns > 0 and nsw > 0, f"추세{nt}/횡보{ns}/스위칭{nsw}"))

    res.append(("S5 라벨 봇입력 배제", M.get("has_label_in_bot_input", "False") == "False", M.get("has_label_in_bot_input", "?")))

    ok6 = ("FROZEN" in M.get("chip_def", "")) and (M.get("filter_mode", "") == "precise") and (M.get("oi_filter", "") == "False")
    res.append(("S6 칩정의 동결+정밀필터ON+OI꺼짐", ok6, f"{M.get('chip_def','?')} | filter={M.get('filter_mode','?')} | OI={M.get('oi_filter','?')}"))

    try:
        ok7 = int(M.get("wf_windows", 0)) >= 5 and (M.get("wf_oos_pf", "") not in ("", "0", "0.0"))
    except Exception:
        ok7 = False
    res.append(("S7 워크포워드 창>=5 & 통합OOS PF존재", ok7, f"창{M.get('wf_windows','?')} 통합OOS PF{M.get('wf_oos_pf','?')} 안정{M.get('wf_pf_stable','?')}"))

    ok8 = (M.get("funding_trend", "") == "REAL") and (M.get("funding_sw", "") == "REAL")
    res.append(("S8 펀딩 REAL(추세·횡보)", ok8, f"추세{M.get('funding_trend','?')}/횡보{M.get('funding_sw','?')}"))

    passed = sum(1 for _, ok, _ in res if ok)
    verdict = "PASS" if passed == len(res) else "FAIL"
    summary = (f"VERDICT {NAME} | 8시나리오 {passed}/{len(res)} {verdict} | "
               f"[3모드] ①스위칭 PF{M.get('sw_pf','?')}/{M.get('sw_ret','?')}%/MDD{M.get('sw_mdd','?')}(청산{M.get('sw_liq','?')}) "
               f"vs ②병행 PF{M.get('par_pf','?')}/{M.get('par_ret','?')}%/MDD{M.get('par_mdd','?')} "
               f"vs ③단독추세 PF{M.get('soloT_pf','?')}/{M.get('soloT_ret','?')}% / 단독횡보정밀 PF{M.get('soloS_pf','?')}/{M.get('soloS_ret','?')}% | "
               f"[워크포워드] 창{M.get('wf_windows','?')} 통합OOS PF{M.get('wf_oos_pf','?')} 창별{M.get('wf_pf_list','?')} 안정{M.get('wf_pf_stable','?')} | "
               f"★2025 R합: 스위칭{M.get('y2025_switch','?')}% vs 병행{M.get('y2025_parallel','?')}% vs 단독추세{M.get('y2025_soloT','?')}% | "
               f"칩정의 {M.get('chip_def','?')} 정밀필터ON | check:{verdict}")

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    with open(os.path.join(HSTR, f"{stamp}.txt"), "w", encoding="utf-8") as f:
        f.write(summary + "\n\n[8시나리오 상세]\n")
        for nm, ok, memo in res:
            f.write(f"  [{'OK' if ok else 'X '}] {nm} : {memo}\n")
        f.write("\n[엔진 무수정 해시]\n")
        for fn, h in ENGINE_HASH.items():
            f.write(f"  {fn} = {h[:16]}...\n")
        f.write("\n[메모] 결정용 깨끗한 숫자. 워크포워드 OOS PF가 창마다 1 넘고 안정하면 스위칭 알파 인정. 노출은 위험사이징(PF불변).\n")

    idx = os.path.join(HSTR, "00WorkHstr_INDEX.txt")
    with open(idx, "a", encoding="utf-8") as f:
        f.write(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} | {NAME} | 분석:{stamp}.txt | {summary}\n")

    print(summary)
    print(f"[check] 분석txt -> {os.path.join(HSTR, stamp+'.txt')}")
    print(f"[check] INDEX 추가 -> {idx}")


if __name__ == "__main__":
    main()
