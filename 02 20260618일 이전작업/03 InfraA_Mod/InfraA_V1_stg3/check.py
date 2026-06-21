# -*- coding: utf-8 -*-
# [FILE] check.py  (InfraA_V1_stg3 - contamination 8-check + analysis txt + INDEX)
# CODE LENGTH: approx 200 lines | INTERNAL VER: check_stg3_v1 | full output, no omission
#
# [PURPOSE] test.py 직후 호출. (1)오염검사 8항목 (2)작업분석 txt(위험% 권고 포함) (3)INDEX 1줄.
#   모든 출력 -> 상위 D:\ML\verify\00WorkHstr\. 전량 파일, 화면 복붙 요구 없음.
#
# [8 SCENARIOS]
#   1 결과파일존재   : risk_trades_full.csv + risk_grid_summary.csv + risk_montecarlo.csv ?
#   2 잔존섞임없음   : mtime 이 .run_start 이후?
#   3 파일명일치     : risk_*.csv 가 허용패턴(trades_full/grid_summary/montecarlo)만?
#   4 데이터정상     : 상위폴더 데이터 + 행수/기간/해시. ★36개월(>=900일) 경고
#   5 중복없음       : trades_full (진입시간) 중복 0?
#   6 빔/NaN없음     : grid_summary 행>0 & R/파산확률 결측 0?
#   7 INDEX이중기록  : zip명+stamp 중복 확인 후 1줄(PASS만 정식)
#   8 출력경로       : ..\00WorkHstr 쓰기 가능?
#
# [PATH] D:\ML\verify\InfraA_V1_stg3\ 실행 -> ..\00WorkHstr\ 출력.
# [FUNCTIONS] sha8 / find_parent_data / run_checks / recommend(summary,mc) / build_lines / write_outputs
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
TRADES = "risk_trades_full.csv"
GRID = "risk_grid_summary.csv"
MC = "risk_montecarlo.csv"
EXPECTED = [TRADES, GRID, MC]
START_MARK = os.path.join(HERE, ".run_start")
BUST_MAX = 5.0   # 권고: MC파산확률 5% 이하만 후보


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
    checks = []; analysis = {'zip': ZIP_NAME, 'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}
    paths = {n: os.path.join(HERE, n) for n in EXPECTED}

    ok1 = all(os.path.exists(p) for p in paths.values())
    checks.append(("1.결과파일존재", ok1, ", ".join(f"{n}={'O' if os.path.exists(p) else 'X'}" for n, p in paths.items())))

    stale = [n for n, p in paths.items() if os.path.exists(p) and os.path.getmtime(p) < start_ts]
    ok2 = (len(stale) == 0) and ok1
    checks.append(("2.잔존섞임없음", ok2, "stale=" + (",".join(stale) if stale else "없음")))

    found = [os.path.basename(f) for f in glob.glob(os.path.join(HERE, "risk_*.csv"))]
    bad = [f for f in found if f not in EXPECTED]
    ok3 = (len(bad) == 0) and ok1
    checks.append(("3.파일명일치", ok3, "위반=" + (",".join(bad) if bad else "없음")))

    data = find_parent_data()
    if data:
        try:
            dd = pd.read_csv(data, usecols=['timestamp'])
            span_days = (pd.to_datetime(dd['timestamp'].iloc[-1]) - pd.to_datetime(dd['timestamp'].iloc[0])).days
            analysis.update(data_path=data, data_rows=len(dd),
                            data_span=f"{dd['timestamp'].iloc[0]}~{dd['timestamp'].iloc[-1]}",
                            data_hash=sha8(data), span_days=span_days)
            ok4 = (os.path.dirname(data) == PARENT)
            warn = "" if span_days >= 900 else f" ★경고:{span_days}일(36개월 미만)"
            checks.append(("4.데이터정상(36mo)", ok4, f"{len(dd)}행 {span_days}일 hash={analysis['data_hash']}{warn}"))
        except Exception as e:
            checks.append(("4.데이터정상(36mo)", False, f"읽기실패:{e}"))
    else:
        checks.append(("4.데이터정상(36mo)", False, "상위폴더 데이터 없음"))

    # 5,6
    dup = 0; nrows = 0; nan = 0
    tp = paths[TRADES]
    if os.path.exists(tp):
        try:
            t = pd.read_csv(tp); nrows = len(t)
            if '진입시간' in t.columns:
                dup = int(t.duplicated(subset=['진입시간']).sum())
            analysis['n_trades'] = nrows
        except Exception:
            pass
    gp = paths[GRID]
    if os.path.exists(gp):
        try:
            g = pd.read_csv(gp)
            for col in ['위험pct', 'MC파산확률']:
                if col in g.columns:
                    nan += int(g[col].isna().sum())
            analysis['grid'] = g.to_dict('records')
        except Exception:
            pass
    ok5 = (dup == 0)
    ok6 = (nrows > 0) and (nan == 0) and ok1
    checks.append(("5.중복없음", ok5, f"진입시간 중복 {dup}"))
    checks.append(("6.빔/NaN없음", ok6, f"거래 {nrows}건, 그리드NaN {nan}"))

    if os.path.exists(paths[MC]):
        try:
            analysis['mc'] = pd.read_csv(paths[MC]).to_dict('records')[0]
        except Exception:
            pass

    try:
        os.makedirs(HSTR, exist_ok=True)
        w = os.path.join(HSTR, ".w"); open(w, 'w').close(); os.remove(w); ok8 = True
    except Exception:
        ok8 = False
    checks.append(("8.출력경로(..\\00WorkHstr)", ok8, HSTR))
    return checks, analysis


def recommend(grid):
    """MC파산확률<=5% 후보 중 월수익률 최대 = 권고 위험%. (단언 아님, 후보 제시)"""
    cand = []
    for r in grid:
        try:
            pb = float(str(r['MC파산확률']).replace('%', ''))
            mret = float(str(r['월수익률']).replace('%', ''))
            if pb <= BUST_MAX and str(r['실제파산']) == 'NO':
                cand.append((mret, r))
        except Exception:
            continue
    if not cand:
        return None
    cand.sort(key=lambda x: -x[0])
    return cand[0][1]


def build_lines(analysis, checks):
    L = [f"[작업분석] {analysis['zip']}  {analysis['time']}", "=" * 64, "[오염검사 8항목]"]
    for name, ok, memo in checks:
        L.append(f"  {'PASS' if ok else 'FAIL'} | {name} | {memo}")
    all_pass = all(ok for _, ok, _ in checks)
    L.append(f"  => 종합: {'ALL PASS' if all_pass else '★FAIL 있음 — 결과 신뢰 불가'}")
    L += ["", "[입력 데이터]", f"  {analysis.get('data_path','?')}",
          f"  행수 {analysis.get('data_rows','?')} | 기간 {analysis.get('data_span','?')} | {analysis.get('span_days','?')}일 | 해시 {analysis.get('data_hash','?')}", ""]
    mc = analysis.get('mc', {})
    L.append(f"[거래 통계] {mc.get('거래수','?')}건 | {mc.get('연도수','?')}개 연도 | {mc.get('기간개월','?')}개월 | "
             f"평균R {mc.get('평균R_pct','?')}% | 승률 {mc.get('승률_pct','?')}% | 풀켈리 {mc.get('풀켈리','?')} 하프켈리 {mc.get('하프켈리','?')}")
    L.append("")
    L.append("[위험% 그리드 — 사이징 x 위험% (복리, 몬테카를로 2000회)]")
    grid = analysis.get('grid', [])
    for mode in ['fixed', 'sldist']:
        L.append(f"  [{mode}]")
        for r in grid:
            if str(r.get('사이징')) == mode:
                L.append(f"    위험{r['위험pct']}% (켈리x{r.get('켈리배수')}): 수익 {r['실제수익률']} | 월 {r['월수익률']} | "
                         f"최저 {r['최저자본']} | 실제파산 {r['실제파산']} | MC파산 {r['MC파산확률']} | MC중앙 {r['MC중앙자본']}")
    L.append("")
    rec = recommend(grid)
    L.append("[★위험% 권고 — 자본보존 우선]")
    if rec:
        L.append(f"  후보: 사이징 {rec['사이징']} · 위험 {rec['위험pct']}%  → 월 {rec['월수익률']}, MC파산 {rec['MC파산확률']}, 실제파산 {rec['실제파산']}")
        L.append(f"  근거: MC파산확률 {BUST_MAX:.0f}% 이하 & 실제파산 NO 중 월수익률 최대.")
    else:
        L.append(f"  ★후보 없음 — 모든 위험%에서 MC파산>{BUST_MAX:.0f}% 또는 실제파산. = 위험% 문제 아니라 엣지(전략) 문제 신호.")
    L += ["", "  ※ ML=그리드+켈리+몬테카를로(과적합 방지). '박을 위험%'는 이 표 보고 사장님이 확정.",
          "    인수인계 비망록에 '위험%는 수정가능 — 데이터 갱신/엣지 개선 시 재산출' 명시할 것."]
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
    rec = recommend(analysis.get('grid', []))
    write_header = not os.path.exists(INDEX)
    with open(INDEX, 'a', encoding='utf-8') as f:
        if write_header:
            f.write("# Rauto 작업이력 INDEX | 시각|작업|분석txt|테스트py|결과|데이터해시|권고|check\n")
        rectxt = f"{rec['사이징']}{rec['위험pct']}%(월{rec['월수익률']},MC파산{rec['MC파산확률']})" if rec else "후보없음"
        if all_pass:
            f.write(f"{analysis['time']} | {ZIP_NAME} | 분석:{os.path.basename(txt_path)} | 테스트:test.py | "
                    f"결과:risk_grid_summary.csv | 데이터해시:{analysis.get('data_hash','?')} | 권고:{rectxt} | check:PASS\n")
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
