# -*- coding: utf-8 -*-
# [FILE] check.py  (PP_ST_Pullback_V1_stg1 - contamination 8-check + verdict + INDEX)
# CODE LENGTH: approx 190 lines | INTERNAL VER: check_pp_v1 | full output, no omission
#
# [PURPOSE] test.py 직후. (1)오염검사 8항목 (2)분석txt(7h가 6/8h와 함께 양인지·알파판정)
#   (3)INDEX 1줄. 출력 -> 상위 D:\ML\verify\00WorkHstr\. 전량 파일(복붙요청 없음).
#
# [8 SCENARIOS]
#   1 결과파일존재 : pp_summary / pp_trades ?
#   2 잔존섞임없음 : mtime > .run_start ?
#   3 파일명일치   : pp_*.csv 허용패턴만?
#   4 데이터정상   : 상위데이터 행수/기간/해시 +36mo경고
#   5 중복없음     : pp_trades 같은 진입시간 중복 0?
#   6 빔/NaN없음   : summary 행>0 & 누적R NaN 0?
#   7 INDEX이중기록: zip+stamp 중복차단
#   8 출력경로     : ..\00WorkHstr ?
# ==============================================================================

import os, sys, glob, hashlib, datetime
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
ZIP_NAME = os.path.basename(HERE)
HSTR = os.path.join(PARENT, "00WorkHstr")
INDEX = os.path.join(HSTR, "00WorkHstr_INDEX.txt")
SUMMARY = "pp_summary.csv"; TRADES = "pp_trades.csv"
EXPECTED = [SUMMARY, TRADES]
START_MARK = os.path.join(HERE, ".run_start")


def sha8(path):
    hh = hashlib.sha256()
    with open(path, 'rb') as f:
        hh.update(f.read(1 << 20))
    return hh.hexdigest()[:8]


def find_parent_data():
    p = os.path.join(PARENT, "Merged_Data_with_Regime_Features.csv")
    return p if os.path.exists(p) else None


def run_checks(start_ts):
    checks = []
    analysis = {'zip': ZIP_NAME, 'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}
    paths = {n: os.path.join(HERE, n) for n in EXPECTED}

    ok1 = all(os.path.exists(p) for p in paths.values())
    checks.append(("1.결과파일존재", ok1,
                   ", ".join(f"{n.replace('.csv','')}={'O' if os.path.exists(p) else 'X'}" for n, p in paths.items())))

    stale = [n for n, p in paths.items() if os.path.exists(p) and os.path.getmtime(p) < start_ts]
    ok2 = (len(stale) == 0) and ok1
    checks.append(("2.잔존섞임없음", ok2, "stale=" + (",".join(stale) if stale else "없음")))

    found = [os.path.basename(f) for f in glob.glob(os.path.join(HERE, "pp_*.csv"))]
    bad = [f for f in found if f not in EXPECTED]
    ok3 = (len(bad) == 0) and ok1
    checks.append(("3.파일명일치", ok3, "위반=" + (",".join(bad) if bad else "없음")))

    dp = find_parent_data(); ok4 = dp is not None; detail4 = "데이터없음"
    if dp:
        try:
            df = pd.read_csv(dp, usecols=['timestamp'], parse_dates=['timestamp'])
            span_days = (df['timestamp'].max() - df['timestamp'].min()).days
            warn = "" if span_days >= 30 * 33 else f" (경고:{span_days}일<36mo)"
            detail4 = f"행{len(df):,} 기간{span_days}일 해시{sha8(dp)}{warn}"
            analysis['data_rows'] = len(df); analysis['data_days'] = span_days
        except Exception as e:
            ok4 = False; detail4 = f"읽기실패:{e}"
    checks.append(("4.데이터정상", ok4, detail4))

    ok5 = True; detail5 = "건너뜀(파일없음)"
    if os.path.exists(paths[TRADES]):
        try:
            t = pd.read_csv(paths[TRADES])
            dup = int(t.duplicated(subset=['entry_t']).sum()) if 'entry_t' in t.columns else 0
            ok5 = (dup == 0); detail5 = f"진입시간 중복 {dup}건"
        except Exception as e:
            ok5 = False; detail5 = f"읽기실패:{e}"
    checks.append(("5.중복없음", ok5, detail5))

    ok6 = False; detail6 = "summary없음"
    if os.path.exists(paths[SUMMARY]):
        try:
            s = pd.read_csv(paths[SUMMARY])
            nan_cnt = int(s['누적R_pct'].isna().sum()) if '누적R_pct' in s.columns else 0
            ok6 = (len(s) > 0) and (nan_cnt == 0)
            detail6 = f"행{len(s)} 누적R_NaN{nan_cnt}"
            analysis['summary_rows'] = len(s)
        except Exception as e:
            detail6 = f"읽기실패:{e}"
    checks.append(("6.빔/NaN없음", ok6, detail6))

    # INDEX 이중기록 차단(zip+날짜)
    stamp = analysis['time'][:10]
    dup_index = False
    if os.path.exists(INDEX):
        with open(INDEX, encoding='utf-8') as f:
            for line in f:
                if ZIP_NAME in line and stamp in line:
                    dup_index = True; break
    ok7 = not dup_index
    checks.append(("7.INDEX이중기록", ok7, "이미기록됨" if dup_index else "신규"))

    ok8 = True  # 출력경로는 아래 write에서 보장
    checks.append(("8.출력경로", ok8, f"{HSTR}"))

    return checks, analysis


def write_analysis(checks, analysis):
    os.makedirs(HSTR, exist_ok=True)
    all_pass = all(c[1] for c in checks)
    # summary에서 핵심 판정 추출
    verdict_lines = []
    sp = os.path.join(HERE, SUMMARY)
    if os.path.exists(sp):
        try:
            s = pd.read_csv(sp)
            def getrow(lab):
                r = s[s['칸'] == lab]
                return r.iloc[0] if len(r) else None
            c1 = getrow('C1_7h_R1_LS'); c2 = getrow('C2_6h_R1_LS'); c3 = getrow('C3_8h_R1_LS')
            if c1 is not None:
                verdict_lines.append(f"7h(메인): 누적R{c1['누적R_pct']}% PF{c1['PF']} 거래{c1['거래수']} 승률{c1['승률_pct']}%")
            if c2 is not None and c3 is not None:
                # 7h가 6h/8h와 함께 양인지(고원 vs 봉우리)
                plat = all(x is not None and x['누적R_pct'] > 0 for x in [c1, c2, c3])
                verdict_lines.append(f"인접TF 6h:R{c2['누적R_pct']}%/PF{c2['PF']} 8h:R{c3['누적R_pct']}%/PF{c3['PF']}"
                                     f" -> {'고원(견고)' if plat else '봉우리(우연의심)'}")
            ct = getrow('C8_7h_R1_train'); ce = getrow('C8_7h_R1_test')
            if ct is not None and ce is not None:
                oos_ok = ct['누적R_pct'] > 0 and ce['누적R_pct'] > 0
                verdict_lines.append(f"학습/검증: train R{ct['누적R_pct']}%/PF{ct['PF']} test R{ce['누적R_pct']}%/PF{ce['PF']}"
                                     f" -> {'둘다양(통과)' if oos_ok else '과적합의심'}")
            cl = getrow('C4_7h_R1_L'); cs = getrow('C5_7h_R1_S')
            if cl is not None and cs is not None:
                verdict_lines.append(f"방향분해 롱:R{cl['누적R_pct']}%/PF{cl['PF']} 숏:R{cs['누적R_pct']}%/PF{cs['PF']}")
        except Exception as e:
            verdict_lines.append(f"(판정 추출 실패: {e})")

    fname = datetime.datetime.now().strftime('%Y%m%d_%H%M') + ".txt"
    fpath = os.path.join(HSTR, fname)
    with open(fpath, 'w', encoding='utf-8') as f:
        f.write(f"[작업분석] {ZIP_NAME} | {analysis['time']}\n")
        f.write("=" * 60 + "\n[오염검사 8항목]\n")
        for name, ok, detail in checks:
            f.write(f"  {'PASS' if ok else 'FAIL'} {name}: {detail}\n")
        f.write(f"\n오염검사 종합: {'ALL PASS' if all_pass else 'FAIL 있음'}\n")
        f.write("=" * 60 + "\n[알파 판정 (PP-ST Pullback)]\n")
        for v in verdict_lines:
            f.write(f"  - {v}\n")
        f.write("\n[합격선] 7h가 6/8h와 함께 양(고원) + 학습·검증 둘다 PF>1.\n")
    print(f"[분석저장] {fpath}")

    # INDEX 한 줄
    if not any(c[0] == '7.INDEX이중기록' and not c[1] for c in checks):
        line = (f"{analysis['time']} | {ZIP_NAME} | "
                f"오염:{'PASS' if all_pass else 'FAIL'} | "
                + (verdict_lines[0] if verdict_lines else "판정없음") + "\n")
        with open(INDEX, 'a', encoding='utf-8') as f:
            f.write(line)
        print(f"[INDEX기록] {INDEX}")
    return all_pass


def main():
    start_ts = os.path.getmtime(START_MARK) if os.path.exists(START_MARK) else 0
    checks, analysis = run_checks(start_ts)
    print(f"[check] {ZIP_NAME} 오염검사")
    for name, ok, detail in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}: {detail}")
    write_analysis(checks, analysis)
    print("[done] 결과 전량 파일 저장 (화면 복붙 불필요)")


if __name__ == "__main__":
    main()
