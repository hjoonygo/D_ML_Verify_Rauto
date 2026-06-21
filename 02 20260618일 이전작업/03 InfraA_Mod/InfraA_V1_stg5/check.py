# -*- coding: utf-8 -*-
# [FILE] check.py  (InfraA_V1_stg5 - contamination 8-check + analysis txt + INDEX)
# CODE LENGTH: approx 210 lines | INTERNAL VER: check_stg5_v1 | full output, no omission
#
# [PURPOSE] test.py 직후. (1)오염검사 8항목 (2)작업분석 txt(12칸·학습검증·과적합판정·권고) (3)INDEX 1줄.
#   출력 -> 상위 D:\ML\verify\00WorkHstr\. 전량 파일, 복붙 요구 없음.
#
# [8 SCENARIOS]
#   1 결과파일존재 : stop_summary/stop_split/stop_trades_best .csv ?
#   2 잔존섞임없음 : mtime > .run_start ?
#   3 파일명일치   : stop_*.csv 허용패턴만?
#   4 데이터정상   : 상위 데이터 행수/기간/해시 +36mo경고
#   5 중복없음     : trades_best (진입시간) 중복 0?
#   6 빔/NaN없음   : summary 12행 & PF/누적R NaN 0?
#   7 INDEX이중기록: zip+stamp 중복 확인 후 1줄(PASS만 정식)
#   8 출력경로     : ..\00WorkHstr 쓰기?
#
# [PATH] D:\ML\verify\InfraA_V1_stg5\ -> ..\00WorkHstr\.
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
SUMMARY = "stop_summary.csv"; SPLIT = "stop_split.csv"; BEST = "stop_trades_best.csv"
EXPECTED = [SUMMARY, SPLIT, BEST]
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

    found = [os.path.basename(f) for f in glob.glob(os.path.join(HERE, "stop_*.csv"))]
    bad = [f for f in found if f not in EXPECTED]
    ok3 = (len(bad) == 0) and ok1
    checks.append(("3.파일명일치", ok3, "위반=" + (",".join(bad) if bad else "없음")))

    data = find_parent_data()
    if data:
        try:
            dd = pd.read_csv(data, usecols=['timestamp'])
            span = (pd.to_datetime(dd['timestamp'].iloc[-1]) - pd.to_datetime(dd['timestamp'].iloc[0])).days
            analysis.update(data_path=data, data_rows=len(dd),
                            data_span=f"{dd['timestamp'].iloc[0]}~{dd['timestamp'].iloc[-1]}",
                            data_hash=sha8(data), span_days=span)
            ok4 = (os.path.dirname(data) == PARENT)
            warn = "" if span >= 900 else f" ★{span}일(36mo미만)"
            checks.append(("4.데이터정상(36mo)", ok4, f"{len(dd)}행 {span}일 hash={analysis['data_hash']}{warn}"))
        except Exception as e:
            checks.append(("4.데이터정상(36mo)", False, f"읽기실패:{e}"))
    else:
        checks.append(("4.데이터정상(36mo)", False, "상위폴더 데이터 없음"))

    dup = 0; nrows = 0; nan = 0
    if os.path.exists(paths[BEST]):
        try:
            t = pd.read_csv(paths[BEST])
            if '진입시간' in t.columns:
                dup = int(t.duplicated(subset=['진입시간']).sum())
        except Exception:
            pass
    if os.path.exists(paths[SUMMARY]):
        try:
            s = pd.read_csv(paths[SUMMARY]); nrows = len(s)
            for col in ['PF', '누적R']:
                if col in s.columns:
                    nan += int(pd.to_numeric(s[col], errors='coerce').isna().sum())
            analysis['summary'] = s.to_dict('records')
        except Exception:
            pass
    ok5 = (dup == 0)
    ok6 = (nrows >= 12) and (nan == 0) and ok1
    checks.append(("5.중복없음", ok5, f"진입시간 중복 {dup}"))
    checks.append(("6.빔/NaN없음", ok6, f"summary {nrows}행(12기대), PF/누적R NaN {nan}"))

    if os.path.exists(paths[SPLIT]):
        try:
            analysis['split'] = pd.read_csv(paths[SPLIT]).to_dict('records')
        except Exception:
            analysis['split'] = []

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
    summ = analysis.get('summary', [])
    L.append("[12칸 성과 — 손절폭 x 모드 (전체 36개월)]")
    for mode in ['A_preTP', 'B_full']:
        label = 'A:익절전까지만(피보보호)' if mode == 'A_preTP' else 'B:전구간(피보까지)'
        L.append(f"  [{label}]")
        for r in summ:
            if str(r.get('모드')) == mode:
                L.append(f"    손절 {r['손절폭pct']}%: 진입 {r['진입']} | PF {r['PF']} | 누적R {r['누적R']}% | "
                         f"사고 {r['사고']}(강제{r['강제청산']}/구멍{r['구멍']}) | 피보승자 {r['피보승자']} | 파산 {r['파산']}")
    L.append("")
    # 학습/검증 과적합 판정
    L.append("[학습(2023~24) vs 검증(2025~26) — 과적합 점검]")
    split = analysis.get('split', [])
    bykey = {}
    for r in split:
        bykey.setdefault((r['모드'], r['손절폭pct']), {})[r['구간']] = r
    robust = []
    for (mode, sp), v in sorted(bykey.items()):
        tr = v.get('학습2023_24', {}); te = v.get('검증2025_26', {})
        trR = tr.get('누적R', 0); teR = te.get('누적R', 0)
        ok = (trR > 0 and teR > 0)
        if ok:
            robust.append((mode, sp, trR, teR))
        L.append(f"  [{mode} {sp}%] 학습 누적R {trR}%(PF{tr.get('PF')}) | 검증 누적R {teR}%(PF{te.get('PF')}) "
                 f"{'★둘다양전(견고)' if ok else ''}")
    L.append("")
    L.append("[★권고]")
    pos = [r for r in summ if r.get('파산') == 'NO' and float(r.get('누적R', -9)) > 0]
    if pos:
        b = max(pos, key=lambda x: float(x['누적R']))
        L.append(f"  전체 최고: {b['모드']} 손절 {b['손절폭pct']}% → 누적R {b['누적R']}%, PF {b['PF']}, 피보승자 {b['피보승자']}, 파산 {b['파산']}")
    if robust:
        rb = max(robust, key=lambda x: min(x[2], x[3]))
        L.append(f"  ★견고 추천(학습·검증 둘다 양전 중 최선): {rb[0]} 손절 {rb[1]}% (학습 {rb[2]}% / 검증 {rb[3]}%)")
        L.append("  = 과적합 아닌 후보. 이 손절폭을 청산엔진에 채택 후보로.")
    else:
        L.append("  ★학습·검증 둘다 양전인 칸 없음 — 손절당김만으론 부족. 진입필터(나무규칙) 병행 필요 신호.")
    L += ["", "  ※ A=익절전만 적용(사고만 차단,피보보호) / B=전구간(피보도 -X%컷). A>B면 '피보 건드리지 마라' 증거.",
          "    합격선 PF>1·파산NO·자본>=50%. 채택 손절폭은 사장님이 표 보고 확정."]
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
    summ = analysis.get('summary', [])
    pos = [r for r in summ if r.get('파산') == 'NO' and float(r.get('누적R', -9)) > 0]
    rectxt = (f"{max(pos,key=lambda x:float(x['누적R']))['모드']}{max(pos,key=lambda x:float(x['누적R']))['손절폭pct']}%(누적R{max(pos,key=lambda x:float(x['누적R']))['누적R']}%)" if pos else "양전칸없음")
    write_header = not os.path.exists(INDEX)
    with open(INDEX, 'a', encoding='utf-8') as f:
        if write_header:
            f.write("# Rauto 작업이력 INDEX | 시각|작업|분석txt|테스트py|결과|데이터해시|권고|check\n")
        if all_pass:
            f.write(f"{analysis['time']} | {ZIP_NAME} | 분석:{os.path.basename(txt_path)} | 테스트:test.py | "
                    f"결과:stop_summary.csv | 데이터해시:{analysis.get('data_hash','?')} | 권고:{rectxt} | check:PASS\n")
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
