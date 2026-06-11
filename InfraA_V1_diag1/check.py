# -*- coding: utf-8 -*-
# [FILE] check.py  (InfraA_V1_diag1 - contamination 8-check + analysis txt + INDEX)
# CODE LENGTH: approx 190 lines | INTERNAL VER: check_diag1_v1 | full output, no omission
#
# [PURPOSE] test.py 직후. (1)오염검사 8항목 (2)분석txt(가설판정: 사고가 레짐이탈과 관련있나) (3)INDEX 1줄.
#   출력 -> 상위 D:\ML\verify\00WorkHstr\. 전량 파일.
#
# [8 SCENARIOS]
#   1 결과파일존재 : diag_trades / diag_summary ?
#   2 잔존섞임없음 : mtime>.run_start ?
#   3 파일명일치   : diag_*.csv 허용패턴만?
#   4 데이터정상   : 상위데이터 행수/기간/해시 +36mo경고
#   5 중복없음     : diag_trades 진입시간 중복 0?
#   6 빔/NaN없음   : trades 행>0 & R/사고 NaN 0?
#   7 INDEX이중기록: zip+stamp 중복 후 1줄(PASS만 정식)
#   8 출력경로     : ..\00WorkHstr ?
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
TRADES = "diag_trades.csv"; SUMMARY = "diag_summary.csv"
EXPECTED = [TRADES, SUMMARY]
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
    checks = []; analysis = {'zip': ZIP_NAME, 'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}
    paths = {n: os.path.join(HERE, n) for n in EXPECTED}

    ok1 = all(os.path.exists(p) for p in paths.values())
    checks.append(("1.결과파일존재", ok1, ", ".join(f"{n.split('_')[1].split('.')[0]}={'O' if os.path.exists(p) else 'X'}" for n, p in paths.items())))

    stale = [n for n, p in paths.items() if os.path.exists(p) and os.path.getmtime(p) < start_ts]
    ok2 = (len(stale) == 0) and ok1
    checks.append(("2.잔존섞임없음", ok2, "stale=" + (",".join(stale) if stale else "없음")))

    found = [os.path.basename(f) for f in glob.glob(os.path.join(HERE, "diag_*.csv"))]
    bad = [f for f in found if f not in EXPECTED]
    ok3 = (len(bad) == 0) and ok1
    checks.append(("3.파일명일치", ok3, "위반=" + (",".join(bad) if bad else "없음")))

    data = find_parent_data()
    if data:
        try:
            dd = pd.read_csv(data, usecols=['timestamp'])
            span = (pd.to_datetime(dd['timestamp'].iloc[-1]) - pd.to_datetime(dd['timestamp'].iloc[0])).days
            analysis.update(data_rows=len(dd), data_span=f"{dd['timestamp'].iloc[0]}~{dd['timestamp'].iloc[-1]}",
                            data_hash=sha8(data), span_days=span, data_path=data)
            ok4 = (os.path.dirname(data) == PARENT)
            warn = "" if span >= 900 else f" ★{span}일(36mo미만)"
            checks.append(("4.데이터정상(36mo)", ok4, f"{len(dd)}행 {span}일 hash={analysis['data_hash']}{warn}"))
        except Exception as e:
            checks.append(("4.데이터정상(36mo)", False, f"읽기실패:{e}"))
    else:
        checks.append(("4.데이터정상(36mo)", False, "상위폴더 데이터 없음"))

    dup = 0; nrows = 0; nan = 0
    if os.path.exists(paths[TRADES]):
        try:
            t = pd.read_csv(paths[TRADES]); nrows = len(t)
            if '진입시간' in t.columns:
                dup = int(t.duplicated(subset=['진입시간']).sum())
            for col in ['R', '사고']:
                if col in t.columns:
                    nan += int(pd.to_numeric(t[col], errors='coerce').isna().sum())
        except Exception:
            pass
    if os.path.exists(paths[SUMMARY]):
        try:
            analysis['summary'] = pd.read_csv(paths[SUMMARY]).to_dict('records')
        except Exception:
            analysis['summary'] = []
    ok5 = (dup == 0)
    ok6 = (nrows > 0) and (nan == 0) and ok1
    checks.append(("5.중복없음", ok5, f"진입시간 중복 {dup}"))
    checks.append(("6.빔/NaN없음", ok6, f"거래 {nrows}건, R/사고 NaN {nan}"))

    try:
        os.makedirs(HSTR, exist_ok=True)
        w = os.path.join(HSTR, ".w"); open(w, 'w').close(); os.remove(w); ok8 = True
    except Exception:
        ok8 = False
    checks.append(("8.출력경로(..\\00WorkHstr)", ok8, HSTR))
    return checks, analysis


def build_lines(analysis, checks):
    L = [f"[작업분석] {analysis['zip']}  {analysis['time']}", "=" * 64, "[오염검사 8항목]"]
    for name, ok, memo in checks:
        L.append(f"  {'PASS' if ok else 'FAIL'} | {name} | {memo}")
    all_pass = all(ok for _, ok, _ in checks)
    L.append(f"  => 종합: {'ALL PASS' if all_pass else '★FAIL 있음 — 결과 신뢰 불가'}")
    L += ["", "[입력 데이터]", f"  {analysis.get('data_path','?')}",
          f"  행수 {analysis.get('data_rows','?')} | {analysis.get('span_days','?')}일 | 해시 {analysis.get('data_hash','?')}", ""]
    L.append("[진단 — 사고가 '하락장 이탈 후 미청산'과 관련있나]")
    summ = analysis.get('summary', [])
    acc = next((r for r in summ if r.get('구분') == '사고'), None)
    nor = next((r for r in summ if r.get('구분') == '정상'), None)
    cf = next((r for r in summ if str(r.get('구분')).startswith('[반사실]')), None)
    for r in summ:
        L.append(f"  [{r.get('구분')}] 거래 {r.get('거래수')} | 청산시점 하락장이탈 {r.get('청산시점_하락장이탈_비율pct')}% | "
                 f"보유중 이탈경험 {r.get('보유중_하락장이탈_비율pct')}% | 보유중 하락장비율 {r.get('보유중_하락장비율_평균')} | "
                 f"보유봉수중앙 {r.get('보유봉수_중앙')} | 평균R {r.get('평균R_pct')}%")
    L.append("")
    L.append("[★가설 판정]")
    if acc and nor:
        a = acc.get('청산시점_하락장이탈_비율pct') or 0
        nv = nor.get('청산시점_하락장이탈_비율pct') or 0
        if a > nv + 10:
            L.append(f"  ★가설 지지: 사고는 청산시점 하락장이탈 {a}% vs 정상 {nv}% (사고가 {a-nv:.0f}%p 높음)")
            L.append("  = '하락장 끝났는데 숏 유지'가 사고와 관련. 다음단계 '레짐이탈 청산' 유망.")
        elif a < nv - 10:
            L.append(f"  가설 반대: 사고 이탈비율 {a}% < 정상 {nv}%. 사고는 오히려 하락장 한복판에서 남.")
        else:
            L.append(f"  가설 약함: 사고 {a}% vs 정상 {nv}% (차이 작음). 레짐이탈만으론 사고 설명 부족.")
    if cf and acc:
        base = next((r for r in summ if r.get('구분') == '전체'), {})
        L.append(f"  반사실(레짐이탈 즉시청산): 전체 평균R {base.get('평균R_pct')}% -> {cf.get('평균R_pct')}% "
                 f"{'(개선)' if (cf.get('평균R_pct') or -9) > (base.get('평균R_pct') or 0) else '(악화/무변)'}")
        L.append("  => 개선되면 '레짐이탈 청산'을 다음 채팅서 실제 규칙으로 구현 검토. 악화면 기각.")
    L += ["", "  ※ 진단(새 전략 아님). 청산시점 레짐은 그 시각 라벨만 사용(미래참조 아님).",
          "    반사실은 '첫 비하락장 봉 종가청산' 가정의 근사. 실제 구현시 재검증 필요."]
    return L, all_pass


def write_outputs(checks, analysis):
    os.makedirs(HSTR, exist_ok=True)
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M')
    txt_path = os.path.join(HSTR, f"{stamp}.txt")
    if os.path.exists(txt_path):
        txt_path = os.path.join(HSTR, f"{stamp}{datetime.datetime.now().strftime('%S')}.txt")
    dup = False
    if os.path.exists(INDEX):
        with open(INDEX, encoding='utf-8') as f:
            if any((ZIP_NAME in ln and stamp in ln) for ln in f):
                dup = True
    checks.append(("7.INDEX이중기록없음", not dup, "이미있음" if dup else "신규"))
    lines, all_pass = build_lines(analysis, checks)
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))
    write_header = not os.path.exists(INDEX)
    with open(INDEX, 'a', encoding='utf-8') as f:
        if write_header:
            f.write("# Rauto 작업이력 INDEX | 시각|작업|분석txt|테스트py|결과|데이터해시|메모|check\n")
        if all_pass:
            f.write(f"{analysis['time']} | {ZIP_NAME} | 분석:{os.path.basename(txt_path)} | 테스트:test.py | "
                    f"결과:diag_summary.csv | 데이터해시:{analysis.get('data_hash','?')} | 메모:레짐이탈진단 | check:PASS\n")
        else:
            f.write(f"{analysis['time']} | {ZIP_NAME} | [FAIL — 분석:{os.path.basename(txt_path)} 확인] | check:FAIL\n")
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
