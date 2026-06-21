# -*- coding: utf-8 -*-
# [FILE] check.py  (InfraA_V2_stg2 - contamination 8-check + analysis txt + INDEX)
# CODE LENGTH: approx 190 lines | INTERNAL VER: check_sldist_v1 | full output, no omission
#
# [PURPOSE] test.py 직후. (1)오염검사 8항목 (2)분석txt(SL거리/발동 + 자유vs고정 비교 + 판정) (3)INDEX 1줄.
#   출력 -> 상위 D:\ML\verify\00WorkHstr\ . 전량 파일, 복붙요청 없음.
#
# [8 SCENARIOS]
#   1 결과파일존재 : sldist_summary / sldist_trades ?
#   2 잔존섞임없음 : mtime > .run_start ?
#   3 파일명일치   : sldist_*.csv 허용패턴만?
#   4 데이터정상   : 상위데이터 행수/기간/해시 +36mo경고
#   5 중복없음     : trades (설계,진입시간) 중복 0?
#   6 빔/NaN없음   : summary 행>0 & 누적R NaN 0?
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
SUMMARY = "sldist_summary.csv"; TRADES = "sldist_trades.csv"
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
    checks = []; analysis = {'zip': ZIP_NAME, 'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}
    paths = {n: os.path.join(HERE, n) for n in EXPECTED}

    ok1 = all(os.path.exists(p) for p in paths.values())
    checks.append(("1.결과파일존재", ok1, ", ".join(f"{n.replace('.csv','')}={'O' if os.path.exists(p) else 'X'}" for n, p in paths.items())))

    stale = [n for n, p in paths.items() if os.path.exists(p) and os.path.getmtime(p) < start_ts]
    ok2 = (len(stale) == 0) and ok1
    checks.append(("2.잔존섞임없음", ok2, "stale=" + (",".join(stale) if stale else "없음")))

    found = [os.path.basename(f) for f in glob.glob(os.path.join(HERE, "sldist_*.csv"))]
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
            if set(['설계', '진입시간']).issubset(tt.columns):
                dup = int(tt.duplicated(subset=['설계', '진입시간']).sum())
        except Exception:
            pass
    if os.path.exists(paths[SUMMARY]):
        try:
            s = pd.read_csv(paths[SUMMARY]); nrows = len(s)
            if '누적R_pct' in s.columns and '거래수' in s.columns:
                live = s[pd.to_numeric(s['거래수'], errors='coerce').fillna(0) > 0]  # 거래있는 행만
                nan += int(pd.to_numeric(live['누적R_pct'], errors='coerce').isna().sum())
            analysis['summary'] = s.to_dict('records')
        except Exception:
            analysis['summary'] = []
    ok5 = (dup == 0)
    ok6 = (nrows > 0) and (nan == 0) and ok1
    checks.append(("5.중복없음", ok5, f"(설계,진입시간) 중복 {dup}"))
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
    def row(design, mode):
        return next((r for r in summ if r.get('설계') == design and r.get('모드') == mode), None)

    L.append("[Q1 — 1차익절후 잡힌 SL거리(진입가대비%) + 발동 : B고정진입 기준]")
    for d in ['C0_none', 'C1_obtop', 'C2_breakeven', 'C3_fibearly', 'C4_resob']:
        r = row(d, 'B_고정진입')
        if r:
            L.append(f"  [{d:13s}] SL거리 평균 {r.get('SL거리_평균pct')}% (최저 {r.get('SL거리_최저pct')} ~ 최고 {r.get('SL거리_최고pct')}) "
                     f"| SL발동 {r.get('SL발동수')}회 | 강제청산 {r.get('강제청산')} | 피보승자 {r.get('피보승자')}")
    L += ["", "[Q2 — 거래폭증 배제(고정진입 248집합) 시 SL 순효과]"]
    for d in ['C0_none', 'C1_obtop', 'C2_breakeven', 'C3_fibearly', 'C4_resob']:
        a = row(d, 'A_자유진입'); b = row(d, 'B_고정진입')
        if a and b:
            L.append(f"  [{d:13s}] 자유진입: 거래{a.get('거래수')} 누적R{a.get('누적R_pct')}% | "
                     f"고정진입: 거래{b.get('거래수')} 누적R{b.get('누적R_pct')}% PF{b.get('PF')} 파산{b.get('파산')}")
    L += ["", "[B고정진입 학습/검증]"]
    for d in ['C0_none', 'C1_obtop', 'C2_breakeven', 'C3_fibearly', 'C4_resob']:
        tr = row(d, 'B_train'); te = row(d, 'B_test')
        if tr and te:
            L.append(f"  [{d:13s}] 학습 {tr.get('누적R_pct')}% / 검증 {te.get('누적R_pct')}% (PF {te.get('PF')})")

    L += ["", "[★판정]"]
    c0b = row('C0_none', 'B_고정진입')
    cands = []
    for d in ['C1_obtop', 'C2_breakeven', 'C3_fibearly', 'C4_resob']:
        b = row(d, 'B_고정진입'); te = row(d, 'B_test')
        if b and c0b:
            liq_cut = (b.get('강제청산', 9) < c0b.get('강제청산', 9))
            betterR = (b.get('누적R_pct', -999) > c0b.get('누적R_pct', -999))
            te_pos = (te and (te.get('누적R_pct') or -1) > 0)
            ok = liq_cut and betterR and (b.get('파산') == 'NO')
            cands.append((d, b.get('누적R_pct'), ok, te_pos))
            L.append(f"  [{d:13s}] 강제청산 {c0b.get('강제청산')}->{b.get('강제청산')} | "
                     f"고정누적R {c0b.get('누적R_pct')}%->{b.get('누적R_pct')}% | 검증{'양전' if te_pos else '음전'} "
                     f"=> {'★개선' if ok else '개선미흡'}")
    win = [c for c in cands if c[2]]
    if win:
        win.sort(key=lambda x: -(x[1] if x[1] is not None else -1e9))
        L.append(f"  ★권고: {win[0][0]} (고정진입 누적R {win[0][1]}%). "
                 f"거래폭증 없이 강제청산 잡고 R개선{' + 검증양전' if win[0][3] else ''}.")
        L.append("    => 다음: 이 SL을 진입통제(쿨다운/1포지션)와 결합해 자유진입에서도 양전 유지 확인.")
    else:
        L.append("  ★고정진입에서도 C0 대비 개선 설계 없음 => SL거리 자체가 답이 아닐 수 있음. 재토론.")
    L += ["", "  ※ SL거리 +면 진입가 위, -면 아래. B고정=C0가 실제잡은 동일진입에 청산만 설계별(거래폭증 배제).",
          "    실엔진 실시간청산(사후보정 아님). 고정%SL은 stg5 기각으로 제외."]
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
                    f"결과:sldist_summary.csv | 데이터해시:{analysis.get('data_hash','?')} | 메모:SL거리진단+고정진입 | check:PASS\n")
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
