# -*- coding: utf-8 -*-
# [FILE] check.py  (InfraA_V2_stg1 - contamination 8-check + analysis txt + INDEX)
# CODE LENGTH: approx 200 lines | INTERNAL VER: check_slpost_v1 | full output, no omission
#
# [PURPOSE] test.py 직후 실행. (1)오염검사 8항목 (2)분석txt(SL설계 비교+판정) (3)INDEX 1줄.
#   모든 출력 -> 상위 D:\ML\verify\00WorkHstr\ . 화면 복붙요청 없음, 전량 파일.
#
# [8 SCENARIOS]
#   1 결과파일존재 : sl_summary / sl_split / sl_trades_best 셋 다?
#   2 잔존섞임없음 : 결과파일 mtime > .run_start(테스트 시작표식)?
#   3 파일명일치   : 폴더의 sl_*.csv 가 허용패턴(딱 3개)뿐?
#   4 데이터정상   : 상위 Merged_Data_with_Regime_Features.csv 행수/기간/해시 + 36mo경고
#   5 중복없음     : sl_trades_best 진입시간 중복 0?
#   6 빔/NaN없음   : summary 행>0 & R/누적R NaN 0?
#   7 INDEX이중기록: zip+stamp 중복기록 차단(PASS만 정식기록)
#   8 출력경로     : ..\00WorkHstr 쓰기 가능?
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
SUMMARY = "sl_summary.csv"; SPLIT = "sl_split.csv"; BEST = "sl_trades_best.csv"
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
    checks.append(("1.결과파일존재", ok1, ", ".join(f"{n.replace('.csv','')}={'O' if os.path.exists(p) else 'X'}" for n, p in paths.items())))

    stale = [n for n, p in paths.items() if os.path.exists(p) and os.path.getmtime(p) < start_ts]
    ok2 = (len(stale) == 0) and ok1
    checks.append(("2.잔존섞임없음", ok2, "stale=" + (",".join(stale) if stale else "없음")))

    found = [os.path.basename(f) for f in glob.glob(os.path.join(HERE, "sl_*.csv"))]
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
    if os.path.exists(paths[BEST]):
        try:
            b = pd.read_csv(paths[BEST])
            if '진입시간' in b.columns:
                dup = int(b.duplicated(subset=['진입시간']).sum())
        except Exception:
            pass
    if os.path.exists(paths[SUMMARY]):
        try:
            s = pd.read_csv(paths[SUMMARY]); nrows = len(s)
            for col in ['누적R_pct', '평균R_pct']:
                if col in s.columns:
                    nan += int(pd.to_numeric(s[col], errors='coerce').isna().sum())
            analysis['summary'] = s.to_dict('records')
        except Exception:
            analysis['summary'] = []
    if os.path.exists(paths[SPLIT]):
        try:
            analysis['split'] = pd.read_csv(paths[SPLIT]).to_dict('records')
        except Exception:
            analysis['split'] = []
    ok5 = (dup == 0)
    ok6 = (nrows > 0) and (nan == 0) and ok1
    checks.append(("5.중복없음", ok5, f"진입시간 중복 {dup}"))
    checks.append(("6.빔/NaN없음", ok6, f"summary {nrows}행, 누적R/평균R NaN {nan}"))

    try:
        os.makedirs(HSTR, exist_ok=True)
        w = os.path.join(HSTR, ".w"); open(w, 'w').close(); os.remove(w); ok8 = True
    except Exception:
        ok8 = False
    checks.append(("8.출력경로(..\\00WorkHstr)", ok8, HSTR))
    return checks, analysis


def build_lines(analysis, checks):
    L = [f"[작업분석] {analysis['zip']}  {analysis['time']}", "=" * 70, "[오염검사 8항목]"]
    for name, ok, memo in checks:
        L.append(f"  {'PASS' if ok else 'FAIL'} | {name} | {memo}")
    all_pass = all(ok for _, ok, _ in checks)
    L.append(f"  => 종합: {'ALL PASS' if all_pass else '★FAIL 있음 — 결과 신뢰 불가'}")
    L += ["", "[입력 데이터]",
          f"  {analysis.get('data_path','?')}",
          f"  행수 {analysis.get('data_rows','?')} | {analysis.get('span_days','?')}일 | 해시 {analysis.get('data_hash','?')}", ""]

    L.append("[1차익절후 SL설계 비교 — 전체 36개월]")
    summ = analysis.get('summary', [])
    base = next((r for r in summ if r.get('설계') == 'C0_none'), {})
    for r in summ:
        L.append(f"  [{r.get('설계'):13s}] 거래{r.get('거래수')} 강제청산{r.get('강제청산')} 구멍{r.get('구멍')} "
                 f"피보승자{r.get('피보승자')} | 누적R {r.get('누적R_pct')}% PF {r.get('PF')} "
                 f"파산{r.get('파산')} 최저자본 {r.get('최저자본')}({r.get('자본보존pct')}%)")
    L += ["", "[학습(2023~24)/검증(2025~26) 분리]"]
    for r in analysis.get('split', []):
        L.append(f"  [{r.get('설계'):20s}] 거래{r.get('거래수')} 강제청산{r.get('강제청산')} "
                 f"누적R {r.get('누적R_pct')}% PF {r.get('PF')} 파산{r.get('파산')}")

    L += ["", "[★판정 — 강제청산 줄이면서 승자/검증기간 안죽이는 설계가 있나]"]
    def test_R(design):
        r = next((x for x in analysis.get('split', []) if x.get('설계') == design + '|test'), None)
        return (r.get('누적R_pct') if r else None)
    base_liq = base.get('강제청산'); base_fib = base.get('피보승자'); base_test = test_R('C0_none')
    cand = [r for r in summ if r.get('설계') != 'C0_none']
    winners = []
    for r in cand:
        d = r.get('설계'); liq = r.get('강제청산'); fib = r.get('피보승자')
        tR = test_R(d); cumR = r.get('누적R_pct')
        cond_liq = (base_liq is not None and liq is not None and liq < base_liq)
        cond_fib = (base_fib is not None and fib is not None and fib >= base_fib * 0.9)  # 승자 10%이상 안죽임
        cond_test = (tR is not None and tR > 0)
        cond_bank = (r.get('파산') == 'NO')
        ok = cond_liq and cond_fib and cond_test and cond_bank
        mark = "★합격후보" if ok else "탈락"
        L.append(f"  [{d:13s}] 강제청산 {base_liq}->{liq}{'↓' if cond_liq else ''} | "
                 f"피보승자 {base_fib}->{fib}{'(보존)' if cond_fib else '(학살)'} | "
                 f"검증R {tR}%{'(양전)' if cond_test else '(음전/위험)'} | 파산{r.get('파산')} => {mark}")
        if ok:
            winners.append((d, cumR))
    L.append("")
    if winners:
        winners.sort(key=lambda x: -(x[1] if x[1] is not None else -1e9))
        best = winners[0]
        L.append(f"  ★권고: {best[0]} (누적R {best[1]}%). 강제청산 감소+승자보존+검증양전+파산NO 모두 충족.")
        L.append("    => 다음: 이 설계를 기본 청산엔진에 채택. 남은 손실원(구멍 25건)은 다음 stage 별도 처리.")
    else:
        L.append("  ★합격 설계 없음. 단순 SL설계로는 강제청산을 승자/검증 손상없이 못 잡음.")
        L.append("    => 강제청산 9건의 추가조건(보유봉수/이탈) 결합 필요 or 구멍부터 처리. 재토론.")
    L += ["", "  ※ 실엔진 실시간 청산(사후보정 아님). C0=현행 동일. 고정%SL은 stg5 기각으로 제외(전부 구조형)."]
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
                    f"결과:sl_summary.csv | 데이터해시:{analysis.get('data_hash','?')} | 메모:익절후SL설계비교 | check:PASS\n")
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
