# -*- coding: utf-8 -*-
# [FILE] check.py  (InfraA_V3_stg1 - contamination 8-check + realism verdict + INDEX)
# CODE LENGTH: approx 175 lines | INTERNAL VER: check_real8h_v1 | full output, no omission
#
# [PURPOSE] test.py 직후. (1)오염검사 8항목 (2)분석txt(현실화로 성적 어떻게 변했나 판정) (3)INDEX 1줄.
#   출력 -> 상위 D:\ML\verify\00WorkHstr\ . 전량 파일(복붙요청 없음).
#
# [8 SCENARIOS]
#   1 결과파일존재 : real_summary / real_trades ?
#   2 잔존섞임없음 : mtime > .run_start ?
#   3 파일명일치   : real_*.csv 허용패턴만?
#   4 데이터정상   : 상위데이터 행수/기간/해시 +36mo경고
#   5 중복없음     : real_trades 같은설정내 진입시간 중복 0?
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
SUMMARY = "real_summary.csv"; TRADES = "real_trades.csv"
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

    found = [os.path.basename(f) for f in glob.glob(os.path.join(HERE, "real_*.csv"))]
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
            if {'설정', '진입시간'}.issubset(tt.columns):
                dup = int(tt.duplicated(subset=['설정', '진입시간']).sum())
        except Exception:
            pass
    if os.path.exists(paths[SUMMARY]):
        try:
            ss = pd.read_csv(paths[SUMMARY]); nrows = len(ss)
            if '누적R_pct' in ss.columns:
                nan += int(ss['누적R_pct'].isna().sum())
            analysis['summary'] = ss.to_dict('records')
        except Exception:
            analysis['summary'] = []
    ok5 = (dup == 0)
    ok6 = (nrows > 0) and (nan == 0) and ok1
    checks.append(("5.중복없음", ok5, f"설정내 진입시간 중복 {dup}"))
    checks.append(("6.빔/NaN없음", ok6, f"summary {nrows}행, 누적R NaN {nan}"))

    try:
        os.makedirs(HSTR, exist_ok=True)
        w = os.path.join(HSTR, ".w"); open(w, 'w').close(); os.remove(w); ok8 = True
    except Exception:
        ok8 = False
    checks.append(("8.출력경로(..\\00WorkHstr)", ok8, HSTR))
    return checks, analysis


def get_row(summ, setting, mode):
    for r in summ:
        if r.get('설정') == setting and r.get('모드') == mode:
            return r
    return None


def build_lines(analysis, checks):
    L = [f"[작업분석] {analysis['zip']}  {analysis['time']}", "=" * 72, "[오염검사 8항목]"]
    for name, ok, memo in checks:
        L.append(f"  {'PASS' if ok else 'FAIL'} | {name} | {memo}")
    all_pass = all(ok for _, ok, _ in checks)
    L.append(f"  => 종합: {'ALL PASS' if all_pass else '★FAIL 있음 — 결과 신뢰 불가'}")
    L += ["", "[입력데이터]", f"  {analysis.get('data_path','?')} | {analysis.get('data_rows','?')}행 "
          f"{analysis.get('span_days','?')}일 hash {analysis.get('data_hash','?')}", ""]

    summ = analysis.get('summary', [])
    L.append("[현실화 효과 — 같은 C0 진입집합, 펀딩설정만 달리]")
    L.append("  (ALL=전체 / train=23~24 / test=25~26. 누적R%·PF·파산·펀딩총액%)")
    for s in ['R0_old_cont', 'R1_real_cont', 'R2_real_8h']:
        for m in ['ALL', 'train', 'test']:
            r = get_row(summ, s, m)
            if r:
                L.append(f"  [{s:13s}|{m:5s}] 거래{r.get('거래수')} 강제청산{r.get('강제청산')} "
                         f"피보승자{r.get('피보승자')} 누적R{r.get('누적R_pct')}% PF{r.get('PF')} "
                         f"파산{r.get('파산')} 펀딩{r.get('펀딩총액_R_pct')}%")

    L += ["", "[★판정 — 현실화로 본전이 유지되나/적자전환되나]"]
    r0 = get_row(summ, 'R0_old_cont', 'test')
    r1 = get_row(summ, 'R1_real_cont', 'test')
    r2 = get_row(summ, 'R2_real_8h', 'test')
    if r2 is None or r0 is None:
        L.append("  측정불가(요약행 누락). 데이터 확인 필요.")
    else:
        t0 = r0.get('누적R_pct'); t1 = r1.get('누적R_pct') if r1 else None; t2 = r2.get('누적R_pct')
        L.append(f"  검증기 누적R: R0(구펀딩연속) {t0}% -> R1(현실연속) {t1}% -> R2(현실 8h이산) {t2}%")
        if t1 is not None:
            L.append(f"  '연속근사 vs 8h이산' 차이(R2-R1): {round((t2 or 0) - (t1 or 0), 2)}%p")
        L.append(f"  '현실화 총효과'(R2-R0): {round((t2 or 0) - (t0 or 0), 2)}%p")
        if t2 is not None and t2 < 0:
            L.append("  ★검증기 적자전환. 현행 전략은 현실 펀딩에서 음(-). 빈구간보호선(stg2)로 사고감축 필요.")
        elif t2 is not None and t2 < 1.0:
            L.append("  ★검증기 본전 수준(<+1%). 엣지 미약 — stg2 보호선이 사고를 줄여 양전 만드는지가 관건.")
        else:
            L.append("  ★검증기 양(+) 유지. 현실화 후에도 엣지 잔존 — stg2에서 사고감축 시 개선 여지.")
        if r2.get('파산') == 'YES':
            L.append("  ★주의: 파산 발생(자본곡선이 MIN_CAP 도달). 사고감축이 1순위.")
    L += ["", "  ※ 엔진/진입 무수정. 현실화는 펀딩 회계(연속->8h이산)만. ㉠(바닥-5bp)·빈구간보호선은 stg2.",
          "    펀딩 8h이산 = epoch부터 8시간배수(매일 00/08/16 UTC) 통과횟수×8h율. 슬리피지·실펀딩시계열 미사용."]
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
                    f"결과:real_summary.csv | 데이터해시:{analysis.get('data_hash','?')} | 메모:펀딩8h이산 현실화 | check:PASS\n")
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
