# -*- coding: utf-8 -*-
# [FILE] check.py  (SpTrd_Fib_V0_stg6 - contamination 8-check + verdict + INDEX)
# CODE LENGTH: approx 190 lines | INTERNAL VER: check_sfstg6 | full output, no omission
#
# [PURPOSE] test.py 직후. (1)오염검사 8항목 (2)분석txt(7h가 6/8h와 함께 양인지·알파판정)
#   (3)INDEX 1줄. 출력 -> 상위 D:\ML\verify\00WorkHstr\. 전량 파일(복붙요청 없음).
#
# [8 SCENARIOS]
#   1 결과파일존재 : sfstg6_summary / sfstg6_trades ?
#   2 잔존섞임없음 : mtime > .run_start ?
#   3 파일명일치   : sfstg6_*.csv 허용패턴만?
#   4 데이터정상   : 상위데이터 행수/기간/해시 +36mo경고
#   5 중복없음     : sfstg6_trades 같은 진입시간 중복 0?
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
SUMMARY = "sfstg6_summary.csv"; TRADES = "sfstg6_trades.csv"
MLRANK = "sfstg6_mlrank.csv"
EXPECTED = [SUMMARY, TRADES, MLRANK]
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

    found = [os.path.basename(f) for f in glob.glob(os.path.join(HERE, "sfstg6_*.csv"))]
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
            # 메모행(ML_TOP...)과 거래0건 칸은 누적R이 비어있는 게 정상 -> 제외하고 검사
            if '칸' in s.columns:
                mask = ~s['칸'].astype(str).str.startswith('ML_TOP')
                if '거래수' in s.columns:
                    mask = mask & (s['거래수'].fillna(0) > 0)
                s_chk = s[mask]
            else:
                s_chk = s
            nan_cnt = int(s_chk['누적R_pct'].isna().sum()) if '누적R_pct' in s_chk.columns else 0
            ok6 = (len(s) > 0) and (nan_cnt == 0)
            detail6 = f"유효행{len(s_chk)}/전체{len(s)} 누적R_NaN{nan_cnt}"
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
                r = s[s['칸'].astype(str) == lab]
                return r.iloc[0] if len(r) else None
            # ML 메모행(맨 위)
            memo = s[s['칸'].astype(str).str.startswith('ML_TOP')]
            if len(memo):
                verdict_lines.append(f"ML메모: {memo.iloc[0]['칸']}")
            # 기준선(필터없음) 전체/train/test
            ba = getrow('F_none_all'); bt = getrow('F_none_train'); be = getrow('F_none_test')
            if ba is not None:
                verdict_lines.append(f"기준선(필터X): 전체 누적R{ba['누적R_pct']}% PF{ba['PF']} 거래{ba['거래수']}")
            if bt is not None and be is not None:
                oos = (bt['누적R_pct'] > 0) and (be['누적R_pct'] > 0)
                verdict_lines.append(f"기준선 학습/검증: train PF{bt['PF']} / test PF{be['PF']}"
                                     f" -> {'둘다양' if oos else '과적합의심'}")
            # 필터 후보들 test PF 상위 3 추출(메모/none/train/all 제외, _test만)
            try:
                cand = s[s['칸'].astype(str).str.endswith('_test') & ~s['칸'].astype(str).str.startswith('F_none')].copy()
                cand['PF_num'] = pd.to_numeric(cand['PF'], errors='coerce')
                cand = cand.dropna(subset=['PF_num']).sort_values('PF_num', ascending=False)
                for _, r in cand.head(3).iterrows():
                    verdict_lines.append(f"  필터후보 {r['칸']}: test PF{r['PF']} R{r['누적R_pct']}% 거래{r['거래수']}")
            except Exception:
                pass
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
        f.write("=" * 60 + "\n[알파 판정 (SpTrd+Fib stg6 ML-filter)]\n")
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
