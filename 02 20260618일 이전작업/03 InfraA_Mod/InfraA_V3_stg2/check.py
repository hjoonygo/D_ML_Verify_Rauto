# -*- coding: utf-8 -*-
# [FILE] check.py  (InfraA_V3_stg2 - contamination 8-check + gap_guard verdict + INDEX)
# CODE LENGTH: approx 180 lines | INTERNAL VER: check_gapguard_v1 | full output, no omission
#
# [PURPOSE] test.py 직후. (1)오염검사 8항목 (2)분석txt(보호선이 liq 잡고 승자 보존하나 판정) (3)INDEX 1줄.
#   출력 -> 상위 D:\ML\verify\00WorkHstr\ . 전량 파일(복붙요청 없음).
#
# [8 SCENARIOS]
#   1 결과파일존재 : guard_summary / guard_trades ?
#   2 잔존섞임없음 : mtime > .run_start ?
#   3 파일명일치   : guard_*.csv 허용패턴만?
#   4 데이터정상   : 상위데이터 행수/기간/해시 +36mo경고
#   5 중복없음     : guard_trades 같은설정내 진입시간 중복 0?
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
SUMMARY = "guard_summary.csv"; TRADES = "guard_trades.csv"
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

    found = [os.path.basename(f) for f in glob.glob(os.path.join(HERE, "guard_*.csv"))]
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
    L.append("[빈구간 보호선 효과 — 같은 C0 진입집합, 펀딩 8h이산 고정]")
    L.append("  (liq=강제청산 hole=구멍 gap=빈구간보호선발동 win=피보승자)")
    for s in ['B0_base', 'B1_tight', 'B2_full', 'B3_loose']:
        for m in ['ALL', 'train', 'test']:
            r = get_row(summ, s, m)
            if r:
                L.append(f"  [{s:8s}|{m:5s}] 거래{r.get('거래수')} liq{r.get('강제청산')} hole{r.get('구멍')} "
                         f"gap{r.get('gap_guard')} win{r.get('피보승자')} OBe{r.get('OB_edge')} "
                         f"누적R{r.get('누적R_pct')}% PF{r.get('PF')} 파산{r.get('파산')} 최저${r.get('최저자본')}")

    L += ["", "[★판정 — 보호선이 liq 잡고 승자 보존하나 / tight vs loose]"]
    b0 = get_row(summ, 'B0_base', 'ALL'); b2 = get_row(summ, 'B2_full', 'ALL'); b3 = get_row(summ, 'B3_loose', 'ALL')
    b0t = get_row(summ, 'B0_base', 'test'); b2t = get_row(summ, 'B2_full', 'test'); b3t = get_row(summ, 'B3_loose', 'test')
    if not (b0 and b2 and b3):
        L.append("  측정불가(요약행 누락).")
    else:
        L.append(f"  liq(강제청산): B0 {b0.get('강제청산')} | B2_tight {b2.get('강제청산')} | B3_loose {b3.get('강제청산')}")
        L.append(f"  피보승자(보존핵심): B0 {b0.get('피보승자')} | B2_tight {b2.get('피보승자')} | B3_loose {b3.get('피보승자')}")
        L.append(f"  전체 누적R%: B0 {b0.get('누적R_pct')} | B2_tight {b2.get('누적R_pct')} | B3_loose {b3.get('누적R_pct')}")
        L.append(f"  파산: B0 {b0.get('파산')} | B2_tight {b2.get('파산')} | B3_loose {b3.get('파산')}")
        if b0t and b2t and b3t:
            L.append(f"  검증기 누적R%: B0 {b0t.get('누적R_pct')} | B2_tight {b2t.get('누적R_pct')} | B3_loose {b3t.get('누적R_pct')}")
        L.append("")
        cands = []
        for nm, b, bt in [('B2_tight', b2, b2t), ('B3_loose', b3, b3t)]:
            win_loss = (b0.get('피보승자', 0) or 0) - (b.get('피보승자', 0) or 0)
            liq_cut = (b0.get('강제청산', 0) or 0) - (b.get('강제청산', 0) or 0)
            dR = round((b.get('누적R_pct', 0) or 0) - (b0.get('누적R_pct', 0) or 0), 2)
            tag = '성공형' if (liq_cut > 0 and win_loss <= 5 and dR > 0 and b.get('파산') == 'NO') else (
                  '승자과다사망' if win_loss > 5 else ('liq미감소' if liq_cut <= 0 else '혼합'))
            L.append(f"  [{nm}] liq {liq_cut}↓ / 승자손실 {win_loss} / 누적R {dR:+}%p / 파산 {b.get('파산')} => {tag}")
            cands.append((nm, tag, dR, b.get('파산')))
        ok_cands = [c for c in cands if c[1] == '성공형']
        if ok_cands:
            best = max(ok_cands, key=lambda c: c[2])
            L.append(f"  => 추천: {best[0]} (성공형 중 누적R 최고). 다음 stg3=hole(엔트리품질).")
        else:
            L.append("  => 둘 다 미흡. 보호선 정의 재검토 또는 hole 우선 검토 필요.")
    L += ["", "  ※ 변경=Phase2 빈구간 보호선 + TP부호. 진입로직·엔진 나머지 무수정. hole은 이번 대상 아님(stg3).",
          "    펀딩 8h이산 고정. 보호선=min(진입가*1.03, 직전OB top), REDUCE후~피보발동전만 작동."]
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
                    f"결과:guard_summary.csv | 데이터해시:{analysis.get('data_hash','?')} | 메모:빈구간보호선+TP-5bp | check:PASS\n")
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
