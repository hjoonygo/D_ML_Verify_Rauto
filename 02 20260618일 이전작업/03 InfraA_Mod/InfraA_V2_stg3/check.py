# -*- coding: utf-8 -*-
# [FILE] check.py  (InfraA_V2_stg3 - contamination 8-check + analysis txt + INDEX)
# CODE LENGTH: approx 195 lines | INTERNAL VER: check_timecut_v1 | full output, no omission
#
# [PURPOSE] test.py 직후. (1)오염검사 8항목 (2)분석txt(시간컷 효과+펀딩비교+판정) (3)INDEX 1줄.
#   출력 -> 상위 D:\ML\verify\00WorkHstr\ . 전량 파일, 복붙요청 없음.
#
# [8 SCENARIOS]
#   1 결과파일존재 : timecut_summary / split / trades ?
#   2 잔존섞임없음 : mtime > .run_start ?
#   3 파일명일치   : timecut_*.csv 허용패턴만?
#   4 데이터정상   : 상위데이터 행수/기간/해시 +36mo경고
#   5 중복없음     : trades (설정,진입시간) 중복 0?
#   6 빔/NaN없음   : summary 거래>0행 누적R NaN 0?
#   7 INDEX이중기록: zip+stamp 중복차단
#   8 출력경로     : ..\00WorkHstr ?
# ==============================================================================

import os, sys, glob, time, hashlib, datetime
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
ZIP_NAME = os.path.basename(HERE)
HSTR = os.path.join(PARENT, "00WorkHstr")
INDEX = os.path.join(HSTR, "00WorkHstr_INDEX.txt")
SUMMARY = "timecut_summary.csv"; SPLIT = "timecut_split.csv"; TRADES = "timecut_trades.csv"
EXPECTED = [SUMMARY, SPLIT, TRADES]
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
    checks.append(("1.결과파일존재", ok1, ", ".join(f"{n.replace('.csv','')}={'O' if os.path.exists(p) else 'X'}" for n, p in paths.items())))

    stale = [n for n, p in paths.items() if os.path.exists(p) and os.path.getmtime(p) < start_ts]
    ok2 = (len(stale) == 0) and ok1
    checks.append(("2.잔존섞임없음", ok2, "stale=" + (",".join(stale) if stale else "없음")))

    found = [os.path.basename(f) for f in glob.glob(os.path.join(HERE, "timecut_*.csv"))]
    bad = [f for f in found if f not in EXPECTED]
    ok3 = (len(bad) == 0) and ok1
    checks.append(("3.파일명일치", ok3, "위반=" + (",".join(bad) if bad else "없음")))

    data = find_parent_data()
    if data:
        try:
            dd = pd.read_csv(data, usecols=['timestamp'])
            span = (pd.to_datetime(dd['timestamp'].iloc[-1]) - pd.to_datetime(dd['timestamp'].iloc[0])).days
            analysis.update(data_rows=len(dd), data_hash=sha8(data), span_days=span, data_path=data)
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
            tt = pd.read_csv(paths[TRADES])
            if set(['설정', '진입시간']).issubset(tt.columns):
                dup = int(tt.duplicated(subset=['설정', '진입시간']).sum())
        except Exception:
            pass
    if os.path.exists(paths[SUMMARY]):
        try:
            s = pd.read_csv(paths[SUMMARY]); nrows = len(s)
            if '누적R_pct' in s.columns and '거래수' in s.columns:
                live = s[pd.to_numeric(s['거래수'], errors='coerce').fillna(0) > 0]
                nan += int(pd.to_numeric(live['누적R_pct'], errors='coerce').isna().sum())
            analysis['summary'] = s.to_dict('records')
        except Exception:
            analysis['summary'] = []
    ok5 = (dup == 0)
    ok6 = (nrows > 0) and (nan == 0) and ok1
    checks.append(("5.중복없음", ok5, f"(설정,진입시간) 중복 {dup}"))
    checks.append(("6.빔/NaN없음", ok6, f"summary {nrows}행, 누적R NaN {nan}"))

    try:
        os.makedirs(HSTR, exist_ok=True)
        w = os.path.join(HSTR, ".w"); open(w, 'w').close(); os.remove(w); ok8 = True
    except Exception:
        ok8 = False
    checks.append(("8.출력경로(..\\00WorkHstr)", ok8, HSTR))
    return checks, analysis


def build_lines(analysis, checks):
    L = [f"[작업분석] {analysis['zip']}  {analysis['time']}", "=" * 72, "[오염검사 8항목]"]
    for name, ok, memo in checks:
        L.append(f"  {'PASS' if ok else 'FAIL'} | {name} | {memo}")
    all_pass = all(ok for _, ok, _ in checks)
    L.append(f"  => 종합: {'ALL PASS' if all_pass else '★FAIL 있음 — 결과 신뢰 불가'}")
    L += ["", "[입력데이터]", f"  {analysis.get('data_path','?')} | {analysis.get('data_rows','?')}행 "
          f"{analysis.get('span_days','?')}일 hash {analysis.get('data_hash','?')}", ""]

    summ = analysis.get('summary', [])
    def row(lab, mode):
        return next((r for r in summ if r.get('설정') == lab and r.get('모드') == mode), None)

    L.append("[시간제한 × 펀딩 — B_고정진입(거래폭증 배제, 같은 248거래)]")
    for fn in ['fund_old', 'fund_real']:
        L.append(f"  -- 펀딩 {'0.01%/일(구)' if fn=='fund_old' else '0.03%/일(현실)'} --")
        for cut in ['none', '5d', '3d', '2d']:
            r = row(f'cut{cut}_{fn}', 'B_고정')
            if r:
                L.append(f"    [{cut:4s}] 강제청산{r.get('강제청산')} 시간컷{r.get('시간컷')} 피보승자{r.get('피보승자')} "
                         f"| 누적R {r.get('누적R_pct')}% PF {r.get('PF')} 파산{r.get('파산')} 최저자본{r.get('최저자본')}")
    L += ["", "[학습/검증 분리 — 현실펀딩(fund_real) 기준]"]
    for cut in ['none', '5d', '3d', '2d']:
        tr = row(f'cut{cut}_fund_real', 'B_train'); te = row(f'cut{cut}_fund_real', 'B_test')
        if tr and te:
            L.append(f"  [{cut:4s}] 학습 {tr.get('누적R_pct')}% / 검증 {te.get('누적R_pct')}% (검증PF {te.get('PF')})")
    L += ["", "[자유진입 거래폭증 참고(현실펀딩)]"]
    for cut in ['none', '3d']:
        a = row(f'cut{cut}_fund_real', 'A_자유')
        if a:
            L.append(f"  [{cut:4s}] 자유진입 거래수 {a.get('거래수')} 누적R {a.get('누적R_pct')}%")

    L += ["", "[★판정 — 현실펀딩, B고정진입 기준]"]
    c0 = row('cutnone_fund_real', 'B_고정'); c0te = row('cutnone_fund_real', 'B_test')
    win = []
    for cut in ['5d', '3d', '2d']:
        b = row(f'cut{cut}_fund_real', 'B_고정'); te = row(f'cut{cut}_fund_real', 'B_test')
        if b and c0 and c0te:
            liq_cut = (b.get('강제청산', 9) < c0.get('강제청산', 9))
            betterR = (b.get('누적R_pct', -999) > c0.get('누적R_pct', -999))
            te_keep = ((te.get('누적R_pct') or -1) > 0)
            ok = liq_cut and betterR and (b.get('파산') == 'NO')
            L.append(f"  [{cut:4s}] 강제청산 {c0.get('강제청산')}->{b.get('강제청산')} | "
                     f"누적R {c0.get('누적R_pct')}%->{b.get('누적R_pct')}% | "
                     f"검증 {c0te.get('누적R_pct')}%->{te.get('누적R_pct')}%{'(양전유지)' if te_keep else '(음전/죽음)'} "
                     f"=> {'★합격후보' if (ok and te_keep) else ('개선(검증손상)' if ok else '실패')}")
            if ok and te_keep:
                win.append((cut, b.get('누적R_pct')))
    L.append("")
    if win:
        win.sort(key=lambda x: -(x[1] if x[1] is not None else -1e9))
        L.append(f"  ★권고: 시간제한 {win[0][0]} (누적R {win[0][1]}%). 강제청산 감소+R개선+검증양전유지+파산NO.")
        L.append("    => 다음: 이 시간컷을 진입통제와 결합해 자유진입에서도 유지되는지 확인 + 구멍25 별도처리.")
    else:
        L.append("  ★합격 시간컷 없음. 사고는 잡으나 승자절단/검증손상으로 순효과 부족.")
        L.append("    => 시간컷도 한계 확인. 갈래A(레짐 진입필터) 또는 갈래B(전략구조)로 재토론.")
    L += ["", "  ※ 실엔진 실시간 시간청산(사후보정 아님). B고정=C0 248거래 동일진입(거래폭증 배제).",
          "    펀딩 현실화(0.03%/일) 반영. 시간컷=N일째 봉 종가청산."]
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
                    f"결과:timecut_summary.csv | 데이터해시:{analysis.get('data_hash','?')} | 메모:시간제한x펀딩 | check:PASS\n")
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
