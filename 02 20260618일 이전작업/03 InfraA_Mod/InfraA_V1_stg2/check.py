# -*- coding: utf-8 -*-
# [FILE] check.py  (InfraA_V1_stg2 - contamination 8-check + analysis txt + INDEX)
# CODE LENGTH: approx 210 lines | INTERNAL VER: check_stg2_v1 | full output, no omission
#
# [PURPOSE] test.py 직후 호출. (1)오염검사 8항목 (2)작업분석 txt (3)INDEX 1줄.
#   모든 출력은 하위폴더 아니라 상위 D:\ML\verify\00WorkHstr\ 로. 화면 복붙 요구 없음(전량 파일).
#
# [8 SCENARIOS]
#   1 결과파일존재   : obtest_summary.csv + obtest_yearly.csv + obtest_trades_*.csv(>=1) ?
#   2 잔존섞임없음   : 결과파일 mtime 이 이번 실행시작(.run_start) 이후?
#   3 파일명일치     : obtest_*.csv 가 모두 허용패턴(summary/yearly/trades_*) ?
#   4 데이터정상     : 입력이 상위폴더 파일인지 + 행수/기간/해시 기록
#   5 중복없음       : 각 trades 의 (진입시간,구분,청산시간) 중복 0?
#   6 빔/NaN없음     : summary 행>0 & 순수익 NaN/inf 0 (빈 시나리오=진입0은 정상)
#   7 INDEX이중기록  : 같은 zip명+stamp 이미 있나 확인 후 1줄 추가(PASS만 정식)
#   8 출력경로       : ..\00WorkHstr 쓰기 가능?
#
# [PATH] runs in D:\ML\verify\InfraA_V1_stg2\ ; outputs to ..\00WorkHstr\.
# [FUNCTIONS] sha8 / find_parent_data / run_checks(start_ts) / build_lines / write_outputs
# ==============================================================================

import os, sys, glob, time, hashlib, datetime
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
ZIP_NAME = os.path.basename(HERE)
HSTR = os.path.join(PARENT, "00WorkHstr")
INDEX = os.path.join(HSTR, "00WorkHstr_INDEX.txt")
SUMMARY = "obtest_summary.csv"
YEARLY = "obtest_yearly.csv"
TRADES_GLOB = "obtest_trades_*.csv"
START_MARK = os.path.join(HERE, ".run_start")


def sha8(path):
    hh = hashlib.sha256()
    with open(path, 'rb') as f:
        hh.update(f.read(1 << 20))
    return hh.hexdigest()[:8]


def find_parent_data():
    for n in ["Merged_Data_with_Regime_Features.csv", "Merged_Data.csv"]:
        p = os.path.join(PARENT, n)
        if os.path.exists(p):
            return p
    return None


def run_checks(start_ts):
    checks = []
    analysis = {'zip': ZIP_NAME, 'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}
    sp = os.path.join(HERE, SUMMARY); yp = os.path.join(HERE, YEARLY)
    trades = sorted(glob.glob(os.path.join(HERE, TRADES_GLOB)))

    # [1] 결과파일 존재
    ok1 = os.path.exists(sp) and os.path.exists(yp) and len(trades) > 0
    checks.append(("1.결과파일존재", ok1, f"summary={'O' if os.path.exists(sp) else 'X'}, yearly={'O' if os.path.exists(yp) else 'X'}, trades {len(trades)}개"))

    # [2] 잔존섞임 없음
    allf = ([sp, yp] if ok1 else []) + trades
    stale = [os.path.basename(f) for f in allf if os.path.exists(f) and os.path.getmtime(f) < start_ts]
    ok2 = (len(stale) == 0) and ok1
    checks.append(("2.잔존섞임없음", ok2, "stale=" + (",".join(stale) if stale else "없음")))

    # [3] 파일명 일치
    found = [os.path.basename(f) for f in glob.glob(os.path.join(HERE, "obtest_*.csv"))]
    allowed = {SUMMARY, YEARLY}
    bad = [f for f in found if f not in allowed and not f.startswith("obtest_trades_")]
    ok3 = (len(bad) == 0) and ok1
    checks.append(("3.파일명일치", ok3, "위반=" + (",".join(bad) if bad else "없음")))

    # [4] 데이터 정상(상위)
    data = find_parent_data()
    if data:
        try:
            dd = pd.read_csv(data, usecols=['timestamp'])
            analysis['data_path'] = data; analysis['data_rows'] = len(dd)
            analysis['data_span'] = f"{dd['timestamp'].iloc[0]}~{dd['timestamp'].iloc[-1]}"
            analysis['data_hash'] = sha8(data)
            ok4 = (os.path.dirname(data) == PARENT)
            checks.append(("4.데이터정상(상위)", ok4, f"{analysis['data_rows']}행 hash={analysis['data_hash']}"))
        except Exception as e:
            checks.append(("4.데이터정상(상위)", False, f"읽기실패:{e}"))
    else:
        checks.append(("4.데이터정상(상위)", False, "상위폴더 데이터 없음"))

    # [5][6] 중복 + NaN
    dup = nan = 0; nonempty = 0
    for f in trades:
        try:
            t = pd.read_csv(f)
        except Exception:
            continue
        if len(t) == 0:
            continue
        nonempty += 1
        if all(k in t.columns for k in ['진입시간', '구분', '청산시간']):
            dup += int(t.duplicated(subset=['진입시간', '구분', '청산시간']).sum())
        if '순수익' in t.columns:
            v = pd.to_numeric(t['순수익'], errors='coerce')
            nan += int((~np.isfinite(v)).sum())
    ok5 = (dup == 0)
    ok6 = nonempty > 0 and nan == 0 and ok1
    checks.append(("5.중복없음", ok5, f"중복행 {dup}"))
    checks.append(("6.빔/NaN없음", ok6, f"거래있는시나리오 {nonempty}/{len(trades)}, NaN {nan}"))

    # [8] 출력경로
    try:
        os.makedirs(HSTR, exist_ok=True)
        tp = os.path.join(HSTR, ".w"); open(tp, 'w').close(); os.remove(tp)
        ok8 = True
    except Exception:
        ok8 = False
    checks.append(("8.출력경로(..\\00WorkHstr)", ok8, HSTR))

    # 성과 집계(분석본문용)
    if os.path.exists(sp):
        try:
            analysis['summary'] = pd.read_csv(sp).to_dict('records')
        except Exception:
            pass
    return checks, analysis


def build_lines(analysis, checks):
    L = []
    L.append(f"[작업분석] {analysis['zip']}  {analysis['time']}")
    L.append("=" * 64)
    L.append("[오염검사 8항목]")
    for name, ok, memo in checks:
        L.append(f"  {'PASS' if ok else 'FAIL'} | {name} | {memo}")
    all_pass = all(ok for _, ok, _ in checks)
    L.append(f"  => 종합: {'ALL PASS' if all_pass else '★FAIL 있음 — 결과 신뢰 불가'}")
    L.append("")
    L.append("[입력 데이터]")
    L.append(f"  {analysis.get('data_path','?')}")
    L.append(f"  행수 {analysis.get('data_rows','?')} | 기간 {analysis.get('data_span','?')} | 해시 {analysis.get('data_hash','?')}")
    L.append("")
    L.append("[시나리오 성과 — d{3,5,8,10} x ladder{ON,OFF}]")
    recs = analysis.get('summary', [])
    if recs:
        # ladder ON/OFF 그룹으로
        for grp in ['ON', 'OFF']:
            L.append(f"  [ladder {grp}]")
            for r in recs:
                if str(r.get('ladder')) == grp:
                    L.append(f"    {r.get('시나리오')}: 진입 {r.get('진입수')} | PF {r.get('PF')} | 자본 {r.get('수익률')} | 파산 {r.get('파산')}"
                             f"  (SL없음 {r.get('진입실패_SL없음')}, TP없음 {r.get('TP없음')}, SL게이트탈락 {r.get('SL게이트탈락')})")
        # best
        try:
            best = max([r for r in recs if r.get('진입수', 0) > 0], key=lambda x: float(x['PF']))
            L.append("")
            L.append(f"  [최고 PF] {best['시나리오']} → PF {best['PF']}, 자본 {best['수익률']}, 파산 {best['파산']}")
        except ValueError:
            L.append("  [최고 PF] 진입 거래 없음")
    else:
        L.append("  summary 없음")
    L.append("")
    L.append("  ※ PF>1·파산NO·자본>=50% 가 합격선. 측정 아닌 거래시뮬(직접). '흑자전환'은 결과로 판정.")
    return L, all_pass


def write_outputs(checks, analysis):
    os.makedirs(HSTR, exist_ok=True)
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M')
    txt_path = os.path.join(HSTR, f"{stamp}.txt")
    if os.path.exists(txt_path):
        txt_path = os.path.join(HSTR, f"{stamp}{datetime.datetime.now().strftime('%S')}.txt")

    dup_in_index = False
    if os.path.exists(INDEX):
        with open(INDEX, encoding='utf-8') as f:
            if any((ZIP_NAME in line and stamp in line) for line in f):
                dup_in_index = True
    checks.append(("7.INDEX이중기록없음", not dup_in_index, "이미있음" if dup_in_index else "신규"))

    lines, all_pass = build_lines(analysis, checks)
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))

    write_header = not os.path.exists(INDEX)
    with open(INDEX, 'a', encoding='utf-8') as f:
        if write_header:
            f.write("# Rauto 작업이력 INDEX | 시각|작업|분석txt|테스트py|결과|데이터해시|best|check\n")
        if all_pass:
            best = ''
            recs = [r for r in analysis.get('summary', []) if r.get('진입수', 0) > 0]
            if recs:
                b = max(recs, key=lambda x: float(x['PF']))
                best = f"{b['시나리오']}(PF{b['PF']},{b['수익률']})"
            f.write(f"{analysis['time']} | {ZIP_NAME} | 분석:{os.path.basename(txt_path)} | "
                    f"테스트:test.py | 결과:obtest_summary.csv | "
                    f"데이터해시:{analysis.get('data_hash','?')} | best:{best} | check:PASS\n")
        else:
            f.write(f"{analysis['time']} | {ZIP_NAME} | [FAIL — 분석:{os.path.basename(txt_path)} 확인, 정식기록 보류] | check:FAIL\n")
    return txt_path, all_pass


def main():
    start_ts = (os.path.getmtime(START_MARK) if os.path.exists(START_MARK) else time.time() - 3600)
    checks, analysis = run_checks(start_ts)
    txt_path, all_pass = write_outputs(checks, analysis)
    print(f"[check] 분석결과 저장: {txt_path}")
    print(f"[check] INDEX 갱신: {INDEX}")
    print(f"[check] 종합판정: {'ALL PASS' if all_pass else '★FAIL — txt 확인'}")


if __name__ == "__main__":
    main()
