# -*- coding: utf-8 -*-
# [FILE] check.py  (InfraA_V1_stg4 - contamination 8-check + analysis txt + INDEX)
# CODE LENGTH: approx 210 lines | INTERNAL VER: check_stg4_v1 | full output, no omission
#
# [PURPOSE] test.py 직후. (1)오염검사 8항목 (2)작업분석 txt(맞교환·결정나무·권고) (3)INDEX 1줄.
#   출력 -> 상위 D:\ML\verify\00WorkHstr\. 전량 파일, 복붙 요구 없음.
#
# [8 SCENARIOS]
#   1 결과파일존재  : acc_trades_feat/acc_tradeoff/acc_importance/acc_clusters/acc_tree .csv ?
#   2 잔존섞임없음  : mtime > .run_start ?
#   3 파일명일치    : acc_*.csv 허용패턴만?
#   4 데이터정상    : 상위 B데이터 행수/기간/해시 (+A 결합여부는 trades_feat의 oi컬럼 결측률로 메모)
#   5 중복없음      : trades_feat (진입시간) 중복 0?
#   6 빔/NaN없음    : trades_feat 행>0 & R/사고 결측 0? (피처 NaN은 정상=A없거나 워밍업)
#   7 INDEX이중기록 : zip+stamp 중복 확인 후 1줄(PASS만 정식)
#   8 출력경로      : ..\00WorkHstr 쓰기?
#
# [PATH] D:\ML\verify\InfraA_V1_stg4\ -> ..\00WorkHstr\.
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
TRADES = "acc_trades_feat.csv"; TO = "acc_tradeoff.csv"; IMP = "acc_importance.csv"
CL = "acc_clusters.csv"; TREE = "acc_tree.csv"
EXPECTED = [TRADES, TO, IMP, CL, TREE]
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

    found = [os.path.basename(f) for f in glob.glob(os.path.join(HERE, "acc_*.csv"))]
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

    dup = 0; nrows = 0; nan = 0; nacc = 0; flow_pct = None
    tp = paths[TRADES]
    if os.path.exists(tp):
        try:
            t = pd.read_csv(tp); nrows = len(t)
            if '진입시간' in t.columns:
                dup = int(t.duplicated(subset=['진입시간']).sum())
            for col in ['R', '사고']:
                if col in t.columns:
                    nan += int(pd.to_numeric(t[col], errors='coerce').isna().sum())
            if '사고' in t.columns:
                nacc = int(pd.to_numeric(t['사고'], errors='coerce').fillna(0).sum())
            oicols = [c for c in t.columns if c.startswith('oi_') or c.startswith('taker') or c.startswith('top_')]
            if oicols:
                flow_pct = round(t[oicols].notna().any(axis=1).mean() * 100, 1)
            analysis['n_trades'] = nrows; analysis['n_acc'] = nacc; analysis['flow_pct'] = flow_pct
        except Exception:
            pass
    ok5 = (dup == 0)
    ok6 = (nrows > 0) and (nan == 0) and ok1
    checks.append(("5.중복없음", ok5, f"진입시간 중복 {dup}"))
    checks.append(("6.빔/NaN없음", ok6, f"거래 {nrows}건(사고 {nacc}), R/사고 NaN {nan}, A결합 {flow_pct}%"))

    for nm, key in [(TO, 'tradeoff'), (IMP, 'importance'), (TREE, 'tree'), (CL, 'clusters')]:
        if os.path.exists(paths[nm]):
            try:
                analysis[key] = pd.read_csv(paths[nm]).to_dict('records')
            except Exception:
                analysis[key] = []

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
          f"  행수 {analysis.get('data_rows','?')} | {analysis.get('span_days','?')}일 | 해시 {analysis.get('data_hash','?')} | A결합 {analysis.get('flow_pct')}%", ""]
    L.append(f"[거래/사고] 거래 {analysis.get('n_trades','?')} | 사고 {analysis.get('n_acc','?')}건")
    L.append("")
    L.append("[피처 중요도 top8 (지니감소 = 사고 가르는 힘)]")
    for r in (analysis.get('importance', []) or [])[:8]:
        L.append(f"  {r.get('피처')}: {r.get('지니감소')}")
    L.append("")
    L.append("[결정나무 — 사람이 읽는 사고 규칙(깊이3)]")
    for r in (analysis.get('tree', []) or []):
        L.append(f"  {r.get('노드')}  {r.get('규칙')}")
    L.append("")
    L.append("[★맞교환표 — 규칙으로 거를 때 (사고제거 / 승자동반사망 / 제거후평균R)]")
    to = analysis.get('tradeoff', []) or []
    base = next((r for r in to if r.get('규칙') == '[기준]필터없음'), None)
    if base:
        L.append(f"  [기준] 필터없음: 평균R {base.get('제거후평균R_pct')}% (거래 {base.get('제거후거래')})")
    for r in to:
        if r.get('규칙') == '[기준]필터없음':
            continue
        L.append(f"  {r.get('규칙')}: 사고제거 {r.get('제거사고')} / 승자사망 {r.get('동반사망승자')} "
                 f"-> 제거후평균R {r.get('제거후평균R_pct')}% (양전 {r.get('엣지양전')})")
    L.append("")
    pos = [r for r in to if r.get('엣지양전') == 'YES' and r.get('규칙') != '[기준]필터없음']
    L.append("[★권고]")
    if pos:
        pos.sort(key=lambda x: -float(x.get('제거후평균R_pct', -9)))
        b = pos[0]
        L.append(f"  최선 단일규칙: {b['규칙']} → 사고 {b['제거사고']}개 제거, 승자 {b['동반사망승자']}개 희생, 제거후 평균R {b['제거후평균R_pct']}%(양전)")
        L.append("  = 이 조건을 진입게이트에 추가하면 엣지가 음수→양수로 뒤집힐 후보. 다음 단계서 백테스트 재확인.")
    else:
        L.append("  ★단일규칙으로는 엣지 양전 안 됨 — 결정나무 조합(여러 조건 AND) 또는 손절당김 병행 필요.")
        L.append("  나무 상단 분기(위 결정나무)와 군집 프로파일을 조합 규칙 후보로 검토.")
    L += ["", "  ※ ML=numpy 결정나무/지니중요도/KMeans(과적합방지, 외부의존0). 규칙은 '후보'이지 확정 아님.",
          "    채택 전 반드시 다음 사이클서 '그 규칙 넣고 36개월 재백테스트'로 양전 재확인."]
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
    to = analysis.get('tradeoff', []) or []
    pos = [r for r in to if r.get('엣지양전') == 'YES' and r.get('규칙') != '[기준]필터없음']
    rectxt = (max(pos, key=lambda x: float(x['제거후평균R_pct']))['규칙'] if pos else "양전규칙없음")
    write_header = not os.path.exists(INDEX)
    with open(INDEX, 'a', encoding='utf-8') as f:
        if write_header:
            f.write("# Rauto 작업이력 INDEX | 시각|작업|분석txt|테스트py|결과|데이터해시|권고규칙|check\n")
        if all_pass:
            f.write(f"{analysis['time']} | {ZIP_NAME} | 분석:{os.path.basename(txt_path)} | 테스트:test.py | "
                    f"결과:acc_tradeoff.csv | 데이터해시:{analysis.get('data_hash','?')} | 권고:{rectxt} | check:PASS\n")
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
