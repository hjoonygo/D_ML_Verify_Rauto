# -*- coding: utf-8 -*-
# [파일명] check.py  (InfraA_V1_stg1 — 오염검사 8항목 + 분석txt + INDEX)
# 코드길이: 약 200줄, 내부버전명: check_obsize_v1, 로직 축약/생략 없이 전체 출력
#
# [목적] test.py 실행 직후 호출. (1)결과물 오염검사 8항목 (2)작업분석 txt 저장
#        (3)INDEX 한 줄 기록. 모든 출력은 하위폴더가 아니라 상위 D:\ML\verify\00WorkHstr\ 로.
#        화면 복붙 요구 없음 — 전부 파일로 남긴다.
#
# [8개 오염 시나리오]
#   1 결과파일존재     : obsize_samples.csv + obsize_summary.csv 존재?
#   2 잔존섞임없음     : 두 CSV의 mtime 이 이번 실행시작(.run_start) 이후?
#   3 파일명일치       : 고정 파일명만 있고 다른 obsize_*.csv(오타/버전) 없음?
#   4 데이터정상(상위) : 입력 데이터가 상위폴더 파일인지 + 행수/기간/해시 기록
#   5 중복없음         : samples 의 (시각,TF) 중복행 0?
#   6 빔/NaN없음       : samples 행수>0 & 'OB있음' 행의 bp 컬럼에 NaN/inf 0?
#   7 INDEX이중기록없음: 같은 zip명+stamp 가 이미 INDEX 에 있나 확인 후 1줄 추가(PASS만 정식)
#   8 출력경로         : 결과 txt/INDEX 가 ..\00WorkHstr\ 로 가는지(쓰기 가능) 검증
#
# [경로규칙] 이 파일은 D:\ML\verify\InfraA_V1_stg1\ 에서 실행. 출력은 ..\00WorkHstr\.
# [함수 In/Out]
#   sha8(path)            -> 파일 앞 1MB 해시 8자리(str)
#   find_parent_data()    -> 상위 데이터 경로(str|None)
#   run_checks(start_ts)  -> (checks:list[(이름,통과,메모)], analysis:dict)
#   build_analysis_lines(analysis, checks) -> list[str]  (형상적 수사 포함 분석본문)
#   write_outputs(checks, analysis) -> (txt_path, all_pass)
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
SAMPLES = "obsize_samples.csv"
SUMMARY = "obsize_summary.csv"
EXPECTED = [SAMPLES, SUMMARY]
START_MARK = os.path.join(HERE, ".run_start")
BP_COLS = ['SLtop_bp', 'SLmean_bp', 'SLbot_bp', '저항두께_bp', 'TPtop_bp', 'TPmean_bp', 'TPbot_bp', '지지두께_bp']


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
    sp = os.path.join(HERE, SAMPLES); up = os.path.join(HERE, SUMMARY)

    # [1] 결과파일 존재
    ok1 = os.path.exists(sp) and os.path.exists(up)
    checks.append(("1.결과파일존재", ok1, f"samples={'O' if os.path.exists(sp) else 'X'}, summary={'O' if os.path.exists(up) else 'X'}"))

    # [2] 잔존섞임 없음(mtime이 실행시작 이후)
    stale = [n for n in EXPECTED if os.path.exists(os.path.join(HERE, n)) and os.path.getmtime(os.path.join(HERE, n)) < start_ts]
    ok2 = (len(stale) == 0) and ok1
    checks.append(("2.잔존섞임없음", ok2, "stale=" + (",".join(stale) if stale else "없음")))

    # [3] 파일명 일치(다른 obsize_*.csv 없음)
    found = [os.path.basename(f) for f in glob.glob(os.path.join(HERE, "obsize_*.csv"))]
    bad = [f for f in found if f not in EXPECTED]
    ok3 = (len(bad) == 0) and ok1
    checks.append(("3.파일명일치", ok3, "위반=" + (",".join(bad) if bad else "없음")))

    # [4] 데이터 정상(상위폴더 + 행수/기간/해시)
    data = find_parent_data()
    if data:
        try:
            dd = pd.read_csv(data, usecols=['timestamp'])
            analysis['data_path'] = data
            analysis['data_rows'] = len(dd)
            analysis['data_span'] = f"{dd['timestamp'].iloc[0]}~{dd['timestamp'].iloc[-1]}"
            analysis['data_hash'] = sha8(data)
            ok4 = (os.path.dirname(data) == PARENT)
            checks.append(("4.데이터정상(상위)", ok4, f"{analysis['data_rows']}행 hash={analysis['data_hash']}"))
        except Exception as e:
            checks.append(("4.데이터정상(상위)", False, f"읽기실패:{e}"))
    else:
        checks.append(("4.데이터정상(상위)", False, "상위폴더 데이터 없음"))

    # [5][6] 중복 + NaN/빔
    dup = nan = 0; nrows = 0
    if os.path.exists(sp):
        try:
            t = pd.read_csv(sp)
            nrows = len(t)
            if all(k in t.columns for k in ['시각', 'TF']):
                dup = int(t.duplicated(subset=['시각', 'TF']).sum())
            # OB '있음' 행만 bp값이 있어야 함. '없음' 행의 공란은 정상(NaN 아님).
            sl_rows = (t['저항_있나'] == '있음') if '저항_있나' in t.columns else pd.Series(False, index=t.index)
            tp_rows = (t['지지_있나'] == '있음') if '지지_있나' in t.columns else pd.Series(False, index=t.index)
            for col in ['SLtop_bp', 'SLmean_bp', 'SLbot_bp', '저항두께_bp']:
                if col in t.columns:
                    nan += int((~np.isfinite(pd.to_numeric(t.loc[sl_rows, col], errors='coerce'))).sum())
            for col in ['TPtop_bp', 'TPmean_bp', 'TPbot_bp', '지지두께_bp']:
                if col in t.columns:
                    nan += int((~np.isfinite(pd.to_numeric(t.loc[tp_rows, col], errors='coerce'))).sum())
            analysis['n_samples'] = nrows
            analysis['ref_price'] = float(pd.to_numeric(t['진입가'], errors='coerce').median()) if '진입가' in t.columns else 0.0
        except Exception as e:
            analysis['samples_err'] = str(e)
    ok5 = (dup == 0)
    ok6 = (nrows > 0) and (nan == 0) and ok1
    checks.append(("5.중복없음", ok5, f"(시각,TF)중복 {dup}"))
    checks.append(("6.빔/NaN없음", ok6, f"행수 {nrows}, NaN(있음행) {nan}"))

    # [8] 출력경로(HSTR 쓰기 가능)
    try:
        os.makedirs(HSTR, exist_ok=True)
        tp = os.path.join(HSTR, ".w"); open(tp, 'w').close(); os.remove(tp)
        ok8 = True
    except Exception:
        ok8 = False
    checks.append(("8.출력경로(..\\00WorkHstr)", ok8, HSTR))
    return checks, analysis


def _band(bp):
    """형상적 수사: 거리감(고딩용). 절대값 기준."""
    a = abs(bp)
    if a < 20: return "코앞"
    if a < 50: return "가깝다"
    if a < 100: return "보통"
    return "멀다"


def build_analysis_lines(analysis, checks):
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

    ref = analysis.get('ref_price', 0.0)
    L.append(f"[OB 크기 실측 — 측정 {analysis.get('n_samples','?')}개 시점, BTC≈${ref:,.0f} 기준]")
    sp = os.path.join(HERE, SUMMARY)
    if not os.path.exists(sp):
        L.append("  summary 없음 — 측정 실패."); return L, all_pass
    s = pd.read_csv(sp)

    def med(tf, target):
        r = s[(s['TF'] == tf) & (s['대상'] == target)]
        if len(r) == 0 or pd.isna(pd.to_numeric(r['p50'], errors='coerce').iloc[0]):
            return None
        return float(pd.to_numeric(r['p50'], errors='coerce').iloc[0])

    def dollar(bp):
        return ref * bp / 1e4 if ref else 0.0

    # TF별 핵심 한 줄 (중앙값 기준 + 형상적 수사)
    for tf in [5, 60]:
        L.append(f"  [TF{tf}분 OB]")
        for label, target in [("저항(SL)윗선top", "SL_top"), ("저항(SL)중간mean", "SL_mean"),
                               ("지지(TP)윗선top", "TP_top"), ("지지(TP)중간mean", "TP_mean"),
                               ("저항두께", "저항_두께"), ("지지두께", "지지_두께")]:
            m = med(tf, target)
            none_pct = s[(s['TF'] == tf) & (s['대상'] == target.replace('_mean', '_top').replace('_bottom', '_top'))]
            np_txt = ""
            if target.endswith('_top') or target.endswith('_mean'):
                npc = s[(s['TF'] == tf) & (s['대상'] == target)]['OB없음pct']
                if len(npc): np_txt = f" (OB없음 {float(npc.iloc[0]):.0f}%)"
            if m is None:
                L.append(f"    {label}: 데이터부족")
            else:
                L.append(f"    {label}: 중앙 {m:.1f}bp = 약 ${dollar(m):,.0f} → {_band(m)}{np_txt}")
        L.append("")

    # ★핵심 비교(새 설계 근거)
    L.append("  [★핵심 비교 — 새 설계 판단 근거]")
    sl60_top, sl60_mean = med(60, 'SL_top'), med(60, 'SL_mean')
    tp60_top, tp5_top = med(60, 'TP_top'), med(5, 'TP_top')
    if sl60_top and sl60_mean:
        L.append(f"    SL: 1H top {sl60_top:.0f}bp({_band(sl60_top)}) → 1H mean {sl60_mean:.0f}bp({_band(sl60_mean)})  "
                 f"= {sl60_top - sl60_mean:.0f}bp 가까워짐(${dollar(sl60_top - sl60_mean):,.0f})")
    if tp60_top and tp5_top:
        L.append(f"    TP: 60분 top {tp60_top:.0f}bp({_band(tp60_top)}) → 5분 top {tp5_top:.0f}bp({_band(tp5_top)})  "
                 f"= {tp60_top - tp5_top:.0f}bp 가까워짐(${dollar(tp60_top - tp5_top):,.0f})")
    if sl60_mean and tp5_top:
        rr = tp5_top / sl60_mean if sl60_mean else 0
        L.append(f"    새 설계 추정 RR(=TP5top/SL1Hmean) ≈ {rr:.2f}  → RR≥1.5 게이트 두면 진입 막힘(=RR제거 필요 확인용)")
    L.append("")
    L.append("  ※ 위 수치는 측정값(직접). '새 설계가 흑자'는 미검증(가설). 게이트값은 이 숫자 보고 사장님이 확정.")
    return L, all_pass


def write_outputs(checks, analysis):
    os.makedirs(HSTR, exist_ok=True)
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M')   # 분단위(작업지시)
    txt_path = os.path.join(HSTR, f"{stamp}.txt")
    if os.path.exists(txt_path):                              # 같은 분 충돌시만 초 덧붙임
        txt_path = os.path.join(HSTR, f"{stamp}{datetime.datetime.now().strftime('%S')}.txt")

    # [7] INDEX 이중기록 확인
    dup_in_index = False
    if os.path.exists(INDEX):
        with open(INDEX, encoding='utf-8') as f:
            if any((ZIP_NAME in line and stamp in line) for line in f):
                dup_in_index = True
    checks.append(("7.INDEX이중기록없음", not dup_in_index, "이미있음" if dup_in_index else "신규"))

    lines, all_pass = build_analysis_lines(analysis, checks)
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))

    write_header = not os.path.exists(INDEX)
    with open(INDEX, 'a', encoding='utf-8') as f:
        if write_header:
            f.write("# Rauto 작업이력 INDEX | 시각|작업|분석txt|테스트py|결과|데이터해시|check\n")
        if all_pass:
            f.write(f"{analysis['time']} | {ZIP_NAME} | 분석:{os.path.basename(txt_path)} | "
                    f"테스트:test.py | 결과:obsize_summary.csv | "
                    f"데이터해시:{analysis.get('data_hash','?')} | check:PASS\n")
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
